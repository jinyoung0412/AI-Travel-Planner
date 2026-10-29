"""Five-place collection preparation and manual review; never writes a DB.

Preparation performs no network calls. Collection requires a separately enabled
manifest. Raw extraction remains in the local audit; exported evidence contains
only human-approved taste tags from human-confirmed identities.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blog_evidence import verify_post
from Preprocess.RunPreprocess.build_database import read_database
from Preprocess.RunPreprocess.collect_blog_tags import collect_with_audit, CollectionInterrupted, canonical_blog_url
from Preprocess.RunPreprocess.collection_state import has_retryable_failures, archive_file, audit_matches_place
from Preprocess.crawler.storage import atomic_output, exclusive_output

MANIFEST = ROOT / 'Preprocess/pilots/homonym_5.json'
OUTPUT = ROOT / 'local_artifacts/homonym_5'
DB = ROOT / 'Flask_server/places.db'
IDENTITY_FIELDS = ('place_id', 'identity_key', '가게명', '주소', 'latitude', 'longitude')
GENERIC = {'후기', '일상', '충남', '충청남도', '천안', '아산', '내돈내산'}
ENGAGEMENT = ('서이추', '서로이웃', '이웃추가', '블챌', '블로그챌린지', '체험단', '협찬', '행사', '이벤트', '공지', '기자단', '원고료', '광고')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    with atomic_output(path) as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def checked_targets(manifest_path, db):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    targets = manifest['targets']
    if (len(targets) != 5 or len({p['place_id'] for p in targets}) != 5 or
            manifest['max_places'] != 5 or manifest['max_unique_posts_per_place'] != 30):
        raise ValueError('고정된 5개 ID / 장소당 최대 30개 글이 필요합니다.')
    if digest(db) != manifest['baseline_db_sha256']:
        raise ValueError('DB가 고정 표본 기준에서 변경됐습니다. 수집 전 표본을 다시 검토하세요.')
    places = read_database(db)
    if places['place_id'].duplicated().any() or len(places) != manifest['baseline_place_count']:
        raise ValueError('장소 수 또는 ID 무결성이 기준과 다릅니다.')
    by_id = places.set_index('place_id', drop=False)
    for target in targets:
        if target['place_id'] not in by_id.index or any(
                by_id.loc[target['place_id'], k] != target[k] for k in IDENTITY_FIELDS):
            raise ValueError(f"고정 표본 신원 불일치: {target['place_id']}")
    with sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        quarantine = conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0]
    if quarantine != manifest['baseline_quarantine_count']:
        raise ValueError('기존 격리 기록 수가 기준과 다릅니다.')
    return manifest, targets


def prepare(manifest_path=MANIFEST, db=DB, output=OUTPUT):
    manifest, targets = checked_targets(manifest_path, db)
    output = Path(output)
    if (output / 'collection.json').exists() or any(output.glob('collection-*.json')):
        raise ValueError('기존 수집 기록이 있습니다. 미실행 보고서로 덮어쓸 수 없습니다.')
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(targets).to_csv(output / 'targets.csv', index=False, encoding='utf-8-sig')
    report = {'pilot_id': manifest['pilot_id'], 'state': 'not_attempted_user_deferred',
              'target_count': len(targets), 'max_unique_posts_per_place': 30,
              'api_requests': 0, 'identity_precision': None, 'precision_denominator': 0,
              'actual_taste_restoration': False, 'keyword_rank_comparison': 'not_run_no_collected_evidence',
              'credentials_present': {key: bool(os.getenv(key)) for key in ('NAVER_API_ID', 'NAVER_API_SECRET')},
              'source_sha256': digest(db), 'source_places': manifest['baseline_place_count'],
              'source_quarantine': manifest['baseline_quarantine_count'], 'db_applied': False}
    save_json(output / 'preparation.json', report)
    if not (output / 'review.json').exists():
        save_json(output / 'review.json', {'pilot_id': manifest['pilot_id'], 'entries': []})
    return report


def _post_revision(post):
    # Only reviewable content matters: request times and transport traces do not
    # invalidate an unchanged human decision.
    fields = ('url', 'outcome', 'name_excerpt', 'address_excerpt', 'provider_url',
              'tags', 'tag_parser', 'error_type', 'http_status')
    payload = {key: post[key] for key in fields if key in post}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _sync_review(entries, runs):
    known = {(entry['place_id'], entry['url']): entry for entry in entries}
    for run in runs:
        for post in run['audit']['posts']:
            key = (run['place_id'], post['url'])
            revision = _post_revision(post)
            entry = known.get(key)
            if entry is None:
                entry = {'place_id': run['place_id'], 'url': post['url'],
                         'identity_match': None, 'approved_taste_tags': [], 'notes': ''}
                entries.append(entry)
                known[key] = entry
            elif ((entry.get('post_revision') is not None and entry['post_revision'] != revision) or
                  (entry.get('automatic_outcome') is not None and entry['automatic_outcome'] != post['outcome'])):
                history = entry.setdefault('history', [])
                history.append({**copy.deepcopy({key: value for key, value in entry.items() if key != 'history'}),
                                'superseded_at': datetime.now(timezone.utc).isoformat()})
                entry.update(identity_match=None, approved_taste_tags=[], notes='')
            entry.update(automatic_outcome=post['outcome'], post_revision=revision)


def _load_runs(output, manifest, targets, *, require_consistent=False):
    """Read checkpoints without publishing or changing any manual decisions.

    Resume restores journals saved before a failed summary publication. Export
    must instead refuse stale/missing summaries so new evidence gets reviewed.
    Summary-only legacy records remain readable when no journal supersedes them.
    """
    summary_path = output / 'collection.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        if not isinstance(summary, dict) or summary.get('pilot_id') != manifest['pilot_id']:
            raise ValueError('기존 수집의 pilot_id가 다릅니다.')
        runs = summary.get('runs')
        if not isinstance(runs, list):
            raise ValueError('기존 수집 요약 형식이 다릅니다.')
    elif require_consistent:
        raise ValueError('수집 요약이 없습니다. collect --resume으로 복구 후 다시 검토하세요.')
    else:
        runs = []

    def validate(run, index):
        if (index >= len(targets) or not isinstance(run, dict) or
                run.get('place_id') != targets[index]['place_id'] or
                not isinstance(run.get('audit'), dict) or
                not isinstance(run['audit'].get('posts'), list)):
            raise ValueError('기존 수집 순서 또는 고정 ID 불일치')
        audit = run['audit']
        if (('place_id' in audit and audit['place_id'] != run['place_id']) or
                ('place_identity' in audit and not audit_matches_place(audit, targets[index]))):
            raise ValueError('기존 수집의 고정 표본 신원이 다릅니다.')

    for index, run in enumerate(runs):
        validate(run, index)
    latest = dict(enumerate(runs))
    for checkpoint in sorted(output.glob('collection-*.json')):
        if '.history-' in checkpoint.name:
            continue
        match = re.fullmatch(r'collection-([1-9][0-9]*)\.json', checkpoint.name)
        if match is None:
            raise ValueError('고정 표본 밖의 수집 체크포인트입니다.')
        index = int(match[1]) - 1
        run = json.loads(checkpoint.read_text(encoding='utf-8'))
        validate(run, index)
        if require_consistent and (index >= len(runs) or run != runs[index]):
            raise ValueError('최신 수집 저널과 요약이 다릅니다. collect --resume으로 복구 후 다시 검토하세요.')
        latest[index] = run
    if sorted(latest) != list(range(len(latest))):
        raise ValueError('고정 표본 수집 체크포인트 순서가 누락됐습니다.')
    return [latest[index] for index in range(len(latest))]


def collect(manifest_path=MANIFEST, db=DB, output=OUTPUT, resume=False):
    manifest, targets = checked_targets(manifest_path, db)
    if manifest.get('collection_authorized_now') is not True:
        raise ValueError('이번 실행은 수집 준비만 허용됐습니다. 실제 수집은 비활성 상태입니다.')
    load_dotenv(ROOT / '.env')
    if not all(os.getenv(k) for k in ('NAVER_API_ID', 'NAVER_API_SECRET')):
        raise ValueError('NAVER_API_ID / NAVER_API_SECRET 누락: 외부 요청 0회.')
    output = Path(output)
    with exclusive_output(output / '.pilot'):
        return _collect(manifest, targets, output, resume)


def _collect(manifest, targets, output, resume):
    existing = (output / 'collection.json').exists() or any(output.glob('collection-*.json'))
    if existing and not resume:
        raise ValueError('기존 수집 기록이 있습니다. 재개는 --resume으로 명시하세요.')
    output.mkdir(parents=True, exist_ok=True)
    review_path = output / 'review.json'
    review = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {
        'pilot_id': manifest['pilot_id'], 'entries': []}
    if review.get('pilot_id') != manifest['pilot_id']:
        raise ValueError('기존 검토의 pilot_id가 다릅니다.')
    if review['entries'] and not resume:
        raise ValueError('기존 수동 검토를 덮어쓸 수 없습니다.')
    runs = _load_runs(output, manifest, targets) if existing else []
    entries = review['entries']

    def checkpoint():
        save_json(output / 'collection.json', {'pilot_id': manifest['pilot_id'], 'runs': runs,
                  'retryable_targets': [run['place_id'] for run in runs if has_retryable_failures(run['audit'])],
                  'remaining_targets': [place['place_id'] for i, place in enumerate(targets)
                                        if i >= len(runs) or runs[i]['audit'].get('status') == 'interrupted' ]})
        _sync_review(entries, runs)
        save_json(review_path, {**review, 'entries': entries})

    checkpoint()
    for index, place in enumerate(targets):
        previous = runs[index]['audit'] if index < len(runs) else None
        if previous is not None and previous.get('status') != 'interrupted' and not has_retryable_failures(previous):
            continue
        prior_path = output / f'collection-{index + 1}.json'
        if prior_path.exists():
            archive_file(prior_path)
        # Old exports no longer describe the current pending review. Preserve
        # them as history before changing any evidence, including on interrupt.
        for filename in ('reviewed_tags.csv', 'review_metrics.json'):
            export_path = output / filename
            if export_path.exists():
                archive_file(export_path)
                export_path.unlink()
        interrupted = None
        try:
            result = collect_with_audit(place, max_posts=30, previous=previous,
                                        **({'retry_failed': True} if resume else {}))
        except CollectionInterrupted as exc:
            result, interrupted = exc.result, exc
        run = {'place_id': place['place_id'], **result}
        if index < len(runs):
            runs[index] = run
        else:
            runs.append(run)
        save_json(output / f'collection-{index + 1}.json', run)
        checkpoint()
        if interrupted is not None:
            raise interrupted
        if run['audit'].get('search_error', {}).get('http_status') in (401, 403):
            break
    return {'collected_places': len(runs), 'api_requests': sum(
        len(run['audit']['request_trace']) for run in runs), 'db_applied': False}


def is_taste_tag(tag, place):
    cleaned = re.sub(r'[\s#]+', '', tag).casefold()
    regions = set(GENERIC)
    for token in str(place.get('주소', '')).split():
        if token.endswith(('시', '군', '구', '읍', '면', '동')):
            regions.update((token, token[:-1]))
    return bool(cleaned and cleaned not in regions and not cleaned.startswith(ENGAGEMENT))


def export_reviewed(manifest_path=MANIFEST, db=DB, output=OUTPUT):
    """Export curated evidence only. Applying it remains a separate DB operation."""
    manifest, targets = checked_targets(manifest_path, db)
    output = Path(output)
    with exclusive_output(output / '.pilot'):
        return _export_reviewed(manifest, targets, output)


def _export_reviewed(manifest, targets, output):
    target_map = {p['place_id']: p for p in targets}
    runs = _load_runs(output, manifest, targets, require_consistent=True)
    review = json.loads((output / 'review.json').read_text(encoding='utf-8'))
    if review['pilot_id'] != manifest['pilot_id']:
        raise ValueError('검토 대상 파일의 pilot_id가 다릅니다.')
    reviews = {}
    for entry in review['entries']:
        key = (entry['place_id'], entry['url'])
        if key in reviews:
            raise ValueError('중복 수동 검토 항목입니다.')
        reviews[key] = entry
    rows, denominator, confirmed, potential_misses = [], 0, 0, 0
    seen = set()
    for run in runs:
        pid = run['place_id']
        if pid not in target_map or pid in seen:
            raise ValueError('고정 표본 밖의 ID 또는 중복 수집입니다.')
        seen.add(pid)
        kept, urls = [], set()
        for post in run['audit']['posts']:
            canonical = canonical_blog_url(post['url'])
            if not canonical or canonical in urls or len(urls) >= 30:
                raise ValueError('수집 글 URL 중복 또는 최대 개수 초과입니다.')
            urls.add(canonical)
            entry = reviews.get((pid, post['url']))
            if entry is not None and (
                (entry.get('post_revision') is not None and entry['post_revision'] != _post_revision(post)) or
                (entry.get('automatic_outcome') is not None and entry['automatic_outcome'] != post['outcome'])
            ):
                raise ValueError('최신 글 근거와 수동 검토가 다릅니다. 재개 후 다시 검토하세요.')
            if post['outcome'] != 'identity_accepted':
                potential_misses += bool(post['outcome'] == 'identity_rejected' and
                                         entry and entry.get('identity_match') is True)
                continue
            if entry is None or type(entry.get('identity_match')) is not bool:
                raise ValueError('자동 허용 글 전체에 대한 수동 신원 판정이 필요합니다.')
            denominator += 1
            if not entry['identity_match']:
                continue
            if not verify_post(target_map[pid], post):
                raise ValueError('허용 글의 신원 근거가 현재 규칙에 맞지 않습니다.')
            approved = entry.get('approved_taste_tags')
            if (not isinstance(approved, list) or any(not isinstance(t, str) or
                    t not in post.get('tags', []) or not is_taste_tag(t, target_map[pid]) for t in approved)):
                raise ValueError('취향 태그는 추출된 태그의 부분집합이어야 하며 지역·교류·행사 태그는 제외합니다.')
            confirmed += 1
            if approved:
                from blog_evidence import reviewed_tags_post
                kept.append(reviewed_tags_post(target_map[pid], post, approved))
        if kept:
            rows.append({'place_id': pid, 'blog_tag_status': 'verified',
                         'verified_posts': json.dumps(kept, ensure_ascii=False)})
    collected_keys = {(run['place_id'], post['url']) for run in runs for post in run['audit']['posts']}
    if set(reviews) - collected_keys:
        raise ValueError('수집 기록 밖의 수동 검토 항목입니다.')
    with atomic_output(output / 'reviewed_tags.csv', encoding='utf-8-sig') as stream:
        pd.DataFrame(rows, columns=['place_id', 'blog_tag_status', 'verified_posts']).to_csv(stream, index=False)
    metrics = {'identity_precision': confirmed / denominator if denominator else None,
               'precision_denominator': denominator, 'identity_confirmed': confirmed,
               'places_with_reviewed_taste': len(rows), 'potential_false_negatives': potential_misses,
               'collected_places': len(seen), 'target_count': 5, 'db_applied': False,
               'http_attempts': sum(len(run['audit'].get('request_trace', [])) for run in runs),
               'latest_fetch_failures': sum(post['outcome'] == 'fetch_error'
                   for run in runs for post in run['audit']['posts'])}
    save_json(output / 'review_metrics.json', metrics)
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'collect', 'export-reviewed'], nargs='?', default='prepare')
    parser.add_argument('--resume', action='store_true', help='기존 감사·검토를 보존하며 미완료 및 일시적 실패 URL을 재개·재시도')
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--db', type=Path, default=DB)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    args = parser.parse_args()
    action = {'prepare': prepare, 'collect': collect, 'export-reviewed': export_reviewed}[args.action]
    kwargs = {'resume': args.resume} if args.action == 'collect' else {}
    print(json.dumps(action(args.manifest, args.db, args.output_dir, **kwargs), ensure_ascii=False, indent=2))
