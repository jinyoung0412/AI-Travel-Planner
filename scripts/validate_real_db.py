"""Read-only real-DB audit. All Claude/network calls are blocked explicitly."""
import argparse
import ast
import json
import hashlib
import sqlite3
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Flask_server'))
sys.path.insert(0, str(ROOT))
import app
from recommendation_ai import route_metrics
from place_identity import quarantine_legacy


def forbidden(*args, **kwargs):
    raise AssertionError('This validation is offline: external calls forbidden')


def validate_output_path(output, protected):
    """Reject symlink and hardlink aliases of audited source databases."""
    output = Path(output)
    for source in map(Path, protected):
        if output.resolve() == source.resolve() or (
            output.exists() and source.exists() and output.samefile(source)
        ):
            raise ValueError('Report output must not replace an audited source database')


def baseline(backup):
    rec = types.ModuleType('baseline_recommendation')
    cluster = types.ModuleType('baseline_cluster')
    source = lambda path: subprocess.check_output(['git', 'show', f'0d7b21f:{path}'], cwd=ROOT, text=True)
    exec(source('Flask_server/recommendation_ai.py'), rec.__dict__)
    exec(source('Flask_server/clustering_ai.py'), cluster.__dict__)
    # Evaluate only original pure filters, not Flask/Anthropic initialization.
    tree = ast.parse(source('Flask_server/app.py'))
    from geopy.distance import geodesic
    scope = {'pd': pd, 'json': json, 'geodesic': geodesic, 'RADIUS_KM': app.RADIUS_KM}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ('filter_radius', '_tag_has_any', 'filter_keywords'):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline_filters>', 'exec'), scope)
    with sqlite3.connect(Path(backup).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        old = pd.read_sql('select * from places where 지역 = \'천안\'', conn)
    radius = scope['filter_radius'](old, 36.8151, 127.1139, '대중교통')
    np.random.seed(42)
    clustered = cluster.perform_clustering(radius, '대중교통')
    np.random.seed(42)
    courses = rec.generate_from_slots(clustered, ['음식', '자연·산책', '카페'], [], scope['filter_keywords'], n=5)
    return {'returned_count': len(courses), 'cluster_count': int(clustered['Cluster'].nunique()),
            'estimated_distances_km': [route_metrics(c, (36.8151, 127.1139))['estimated_distance_km'] for c in courses]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-db', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'local_artifacts/real_db_validation.json')
    args = parser.parse_args()
    app._call_claude = forbidden
    import requests
    requests.sessions.Session.request = forbidden
    source = Path(app.DB_PATH).resolve()
    try:
        validate_output_path(args.output, [source, *([args.baseline_db] if args.baseline_db else [])])
    except ValueError as error:
        parser.error(str(error))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as conn:
        df = quarantine_legacy(pd.read_sql('select * from places', conn)).drop_duplicates('place_id')
        quarantined = conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0]
        integrity = conn.execute('pragma integrity_check').fetchone()[0]
    # Exercise the HTTP contract against the audited snapshot without opening a
    # writable operational connection inside the application.
    def audited_frame(region=''):
        if region and region != '내 주변':
            return df[df['지역'].eq(region)].copy()
        return df.copy()
    app.get_df = audited_frame
    payload = {'user_lat': 36.8151, 'user_lng': 127.1139, 'transport': '대중교통', 'region': '천안',
               'slot_types': ['음식', '자연·산책', '카페'], 'spot_count': 3, 'count': 5,
               'persona_tags': [], 'seed': 42}
    start = time.perf_counter()
    client = app.app.test_client()
    response = client.post('/recommend/course', json=payload)
    result = response.get_json()
    elapsed = time.perf_counter() - start
    repeated = client.post('/recommend/course', json=payload).get_json()
    assert response.status_code == 200 and len(result['courses']) == 5
    assert result['courses'] == repeated['courses']
    assert result['metadata']['constraints_relaxed'] == []
    for c in result['courses']:
        assert len({p['place_id'] for p in c}) == 3
        assert all(app.category_matches(p['category'], app.SLOT_CATEGORY_MAP[s]) for p, s in zip(c, payload['slot_types']))
    spot = client.post('/recommend/spot', json={**payload, 'user_text': '닭갈비', 'persona_tags': ['맛집 탐방']})
    spot_result = spot.get_json()
    assert spot.status_code == 200
    assert all(app.category_matches(p['category'], ['닭갈비']) for p in spot_result['places'])
    samples = df[df['가게명'].isin(['아지트', '일미식당'])]
    assert len(samples) == 12 and samples['place_id'].nunique() == 12
    assert samples['blog_tags'].eq('{}').all()
    assert integrity == 'ok'
    source_hash_after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_hash_after == source_hash, 'Operational DB changed during audit'
    report = {'offline': True, 'source_sha256_before': source_hash,
              'source_sha256_after': source_hash_after,
              'verified_places': int(df['blog_tag_status'].eq('verified').sum()),
              'origin': payload, 'db_integrity': integrity,
              'place_count': len(df), 'unique_ids': df['place_id'].nunique(),
              'quarantine_rows': quarantined, 'contamination_samples': samples[
                  ['place_id', '가게명', '주소', 'blog_tag_status', 'blog_tags']].to_dict('records'),
              'course_http_status': response.status_code, 'elapsed_seconds': round(elapsed, 3),
              'repeatable': True, 'course_response': result,
              'explicit_spot_response': spot_result}
    if args.baseline_db:
        report['original_baseline'] = baseline(args.baseline_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('course_response', 'contamination_samples', 'explicit_spot_response')}, ensure_ascii=False, indent=2))
    print('course_distances_km:', [m['estimated_distance_km'] for m in result['course_metrics']])
    print('slot_candidates:', result['metadata']['slot_candidate_counts'])
    print('output:', args.output)


if __name__ == '__main__':
    main()
