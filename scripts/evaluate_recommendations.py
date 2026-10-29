"""Offline coverage/diversity scorecard, not a real-world preference accuracy claim.

Read the frozen DB once, exercise the public Flask contract across representative
origins and activities, and report shortages as well as successes. No provider
calls, data collection, or operational DB writes are permitted.
"""
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.offline_environment import install
install()
import pandas as pd
import app
from place_identity import quarantine_legacy
from recommender.visits import visit_groups
from recommender.geometry import distances_from


def main():
    source = ROOT / 'Flask_server/places.db'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as conn:
        frame = quarantine_legacy(pd.read_sql('select * from places', conn)).drop_duplicates('place_id')
    app.get_df = lambda region='': (frame[frame['지역'].eq(region)].copy()
        if region and region != '내 주변' else frame.copy())
    groups = visit_groups(frame)
    client = app.app.test_client()
    origins = [('신창역', '아산', 36.76979, 126.95182),
               ('온양온천역', '아산', 36.78055, 127.00316),
               ('천안역', '천안', 36.81028, 127.14684),
               ('두정역', '천안', 36.83365, 127.14894)]
    cases = []
    for name, region, lat, lng in origins:
        for transport in ('대중교통', '차'):
            for activity in ('자연·산책', '문화·역사', '실내 오락', '체험'):
                slots = ['음식', activity, '카페']
                base = dict(region=region, user_lat=lat, user_lng=lng,
                    transport=transport, slot_types=slots, spot_count=3,
                    count=3, user_text='', persona_tags=['친구와', '힐링/여유', '생일'],
                    randomize=True)
                samples = []
                signatures = []
                for seed in (11, 29, 47):
                    started = time.perf_counter()
                    response = client.post('/recommend/course', json={**base, 'seed': seed})
                    body = response.get_json()
                    elapsed = time.perf_counter() - started
                    assert response.status_code in (200, 422), (name, activity, response.status_code)
                    meta = body.get('metadata', {})
                    assert meta.get('constraints_relaxed') == []
                    courses = body.get('courses', [])
                    ids = [tuple(groups[p['place_id']] for p in c) for c in courses]
                    assert len(ids) == len(set(ids))
                    for course, visits in zip(courses, ids):
                        assert len(course) == len(set(visits)) == 3
                        assert all(app.category_matches(p['category'], app.SLOT_CATEGORY_MAP[s])
                            for p, s in zip(course, slots))
                        assert all(float(distances_from((lat, lng), [(p['lat'], p['lng'])])[0])
                            <= app.RADIUS_KM[transport] + 0.001 for p in course)
                        assert all(p['place_id'] in groups for p in course)
                    shared = [len(set(a) & set(b)) for a, b in itertools.combinations(ids, 2)]
                    signatures.append(tuple(ids))
                    samples.append(dict(seed=seed, status=response.status_code,
                        reason=meta.get('reason'), candidates=meta.get('slot_candidate_counts'),
                        returned=len(courses), max_shared_visits=max(shared, default=0),
                        distance_km=[m['estimated_distance_km'] for m in body.get('course_metrics', [])],
                        duration_seconds=round(elapsed, 3),
                        preference_evidence=meta.get('preference_evidence'),
                        names=[[p['name'] for p in course] for course in courses]))
                    if seed == 11:
                        replay = client.post('/recommend/course', json={**base, 'seed': seed}).get_json()
                        assert replay.get('courses', []) == courses
                cases.append(dict(origin=name, region=region, transport=transport,
                    activity=activity, unique_sets=len(set(signatures)), samples=samples))
    negative_cases = []
    constrained = dict(region='아산', user_lat=36.76979, user_lng=126.95182,
        transport='대중교통', spot_count=3, count=3, user_text='', persona_tags=[], seed=11)
    for label, slots, expected in (
        ('없는 쇼핑 후보', ['음식', '쇼핑', '카페'], 'missing_slot_candidates'),
        ('서로 다른 문화 장소 부족', ['문화·역사'] * 3, 'insufficient_distinct_places'),
    ):
        response = client.post('/recommend/course', json={**constrained, 'slot_types': slots})
        body = response.get_json()
        assert response.status_code == 422 and body['metadata']['reason'] == expected
        assert body['courses'] == [] and body['metadata']['constraints_relaxed'] == []
        negative_cases.append(dict(label=label, status=422, reason=expected,
            candidates=body['metadata']['slot_candidate_counts']))
    spot_cases = []
    for name, region, lat, lng in origins:
        for transport in ('대중교통', '차'):
            for tag in ('카페 투어', '자연/산책'):
                samples, signatures = [], []
                for seed in (11, 29, 47):
                    payload = dict(region=region, user_lat=lat, user_lng=lng,
                        transport=transport, count=5, user_text='',
                        persona_tags=['친구와', tag], randomize=True, seed=seed)
                    response = client.post('/recommend/spot', json=payload)
                    body = response.get_json()
                    assert response.status_code == 200
                    places = body['places']
                    ids = tuple(sorted(groups[p['place_id']] for p in places))
                    assert 0 < len(ids) <= 5 and len(ids) == len(set(ids))
                    assert all(app.category_matches(p['category'], app.derive_category_from_tags([tag]))
                               for p in places)
                    assert all(float(distances_from((lat,lng), [(p['lat'],p['lng'])])[0])
                               <= app.RADIUS_KM[transport] + .001 for p in places)
                    if seed == 11:
                        assert client.post('/recommend/spot', json=payload).get_json()['places'] == places
                    signatures.append(ids)
                    samples.append(dict(seed=seed, returned=len(places),
                        display_order=body.get('metadata', {}).get('display_order'),
                        names=[p['name'] for p in places]))
                spot_cases.append(dict(origin=name, transport=transport, activity=tag,
                    unique_sets=len(set(signatures)), samples=samples))
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == after
    report = dict(scope='Offline category, radius, identity, seed replay and diversity checks; '
        'not measured satisfaction, live model accuracy, travel time or opening hours.',
        source_sha256=before, db_preserved=True, places=len(frame),
        verified_places=int(frame['blog_tag_status'].eq('verified').sum()),
        scenarios=len(cases), unique_requests=len(cases)*3, replay_requests=len(cases),
        complete_scenarios=sum(all(s['returned']==3 for s in c['samples']) for c in cases),
        shortage_scenarios=sum(any(s['status']==422 for s in c['samples']) for c in cases),
        varied_scenarios=sum(c['unique_sets']>1 for c in cases),
        negative_controls=negative_cases, cases=cases,
        spot_scenarios=len(spot_cases), spot_requests=len(spot_cases)*4,
        varied_spot_scenarios=sum(c['unique_sets']>1 for c in spot_cases), spot_cases=spot_cases)
    output=ROOT/'local_artifacts/recommendation_scorecard.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases', 'spot_cases')}, ensure_ascii=False, indent=2))
    print('output:', output)


if __name__ == '__main__':
    main()
