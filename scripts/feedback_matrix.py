"""Offline feedback matrix with explicit denominators; never an all-app QA claim.

python scripts/feedback_matrix.py --phase baseline --recommendation-limit 48
python scripts/feedback_matrix.py --phase final --recommendation-limit 0

Only this process's Flask test client is used. The existing offline boundary
blocks dotenv and all external traffic before application code is imported.
A zero limit executes the complete *pairwise array*, not the Cartesian space.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import closing
import copy
import hashlib
import itertools
import json
import logging
import math
from pathlib import Path
import random
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'local_artifacts/feedback_overhaul/2026-10-28'
DB = ROOT / 'Flask_server/places.db'
PILOT = ROOT / 'Preprocess/pilots/homonym_5.json'
FROZEN = {
    'Flask_server/places.db': '6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be',
    'Preprocess/pilots/homonym_5.json': '3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest(root=ROOT):
    paths = [*root.glob('Flask_server/**/*.py'), *root.glob('android_app/lib/*.dart'),
             *root.glob('NodeJs_server/*.js'), root/'place_identity.py', root/'place_quality.py',
             root/'category_policy.py', root/'scripts/feedback_matrix.py',
             root/'tests/test_feedback_matrix.py',
             root/'android_app/test/feedback_matrix_request_test.dart']
    files = {str(p.relative_to(root)): digest(p) for p in sorted(paths) if p.is_file()}
    return {'files': files, 'sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def _strings(text):
    return re.findall(r"'([^']*)'", text)


def _block(text, name):
    found = re.search(r'\b' + re.escape(name) + r'\s*=\s*\{(.*?)\n\};', text, re.S)
    if not found:
        raise ValueError(f'UI extraction failed: {name}; update harness, do not assume old choices')
    return found[1]


def extract_ui_options(root=ROOT):
    """Extract wire values from actual Dart controls, fail closed on new syntax."""
    screen = (root/'android_app/lib/input_screen.dart').read_text()
    options = (root/'android_app/lib/input_options.dart').read_text()
    hubs = (root/'android_app/lib/transit_hubs.dart').read_text()
    choices = re.findall(r"options:\s*const\s*\[([^]]+)\]", screen)
    regions = next((_strings(c) for c in choices if "'내 주변'" in c), None)
    transports = next((_strings(c) for c in choices if "'대중교통'" in c), None)
    counts = re.search(r'_countOptions\s*=>\s*_isSpot\s*\?\s*\[([^]]+)\]\s*:\s*\[([^]]+)\]', screen)
    visits = re.search(r'children:\s*\[([\d,\s]+)\]\.map\(\(n\)', screen)
    if not (regions and transports and counts and visits):
        raise ValueError('UI count/region/transport extraction failed; harness needs an explicit update')
    groups = {k: _strings(v) for k,v in re.findall(r"'([^']+)':\s*\[(.*?)\]", _block(options, '_kTagGroups'), re.S)}
    slots = re.findall(r"'([^']+)':\s*_SlotStyle", _block(options, '_kSlotStyles'))
    centers = [(r, float(a), float(b)) for r,a,b in re.findall(
        r"'([^']+)':\s*LocationFix\(([\d.]+),\s*([\d.]+)\)", _block(options, '_kRegionCenters'))]
    origins = []
    for region, block in re.findall(r"'([^']+)':\s*\[(.*?)\n\s*\],", _block(hubs, 'transitHubs'), re.S):
        for name,lat,lng in re.findall(r"TransitHub\(\s*'([^']+)',\s*([\d.]+),\s*([\d.]+),", block):
            origins.append(dict(id=f'{region}/{name}/대중교통', region=region, name=name,
                                transport='대중교통', lat=float(lat), lng=float(lng), kind='hub'))
    for region,lat,lng in centers:
        origins.append(dict(id=f'{region}/중심/차', region=region, name=region+' 중심',
                            transport='차', lat=lat, lng=lng, kind='region_center'))
    # Infinite GPS coordinates are not enumerable. These are fixed representatives.
    for transport in transports:
        origins.append(dict(id=f'내 주변/천안중심/{transport}', region='내 주변', name='대표 GPS 천안 중심',
                            transport=transport, lat=centers[0][1], lng=centers[0][2], kind='representative_gps'))
    if len(groups) != 5 or not slots or len(origins) < 4:
        raise ValueError('UI extraction incomplete')
    excluded = re.search(r'get\s+_visibleTagGroups(.*?)Future<void>', screen, re.S)
    hidden = re.findall(r"e\.key\s*!=\s*'([^']+)'", excluded[1]) if excluded else []
    return dict(regions=regions, transports=transports, origins=origins, tag_groups=groups,
                course_hidden_tag_groups=hidden, activities=slots,
                spot_counts=[int(n) for n in counts[1].split(',')],
                course_counts=[int(n) for n in counts[2].split(',')],
                course_visit_counts=[int(n) for n in visits[1].split(',')])


def finite_space(options):
    """Unique direct-picker states only; arbitrary text/GPS explicitly excluded."""
    groups = options['tag_groups']
    def count_tags(hidden=()):
        return math.prod(2**len(tags) if name == '어떤 분위기' else len(tags)+1
                         for name,tags in groups.items() if name not in hidden)
    spatial = len(options['origins'])
    spot_tags, course_tags = count_tags(), count_tags(options['course_hidden_tag_groups'])
    sequences = sum(len(options['activities'])**n for n in options['course_visit_counts'])
    return dict(spatial_representatives=spatial,
        spot_tag_states=spot_tags, course_tag_states=course_tags,
        direct_course_activity_sequences=sequences,
        spot_direct_picker_states=spatial*len(options['spot_counts'])*spot_tags,
        course_direct_picker_states=spatial*len(options['course_counts'])*sequences*course_tags,
        interpretation='Finite direct-picker state count with one representative GPS point. '
                       'Optional tags include none; mood includes every subset. Course hidden tag groups are excluded. '
                       'Equivalent natural-language states, arbitrary coordinates, text, history and seeds are not counted.',
        non_enumerated_axes=['all GPS coordinates', 'all <=1000-character text', 'all seed/history values',
                             'all natural-language intent states'])


def extract_api_count_limits(root=ROOT):
    """Read numeric public count bounds from the actual schema AST."""
    tree=ast.parse((root/'Flask_server/api_request.py').read_text())
    call=next(node for node in ast.walk(tree) if isinstance(node,ast.Call)
              and isinstance(node.func,ast.Name) and node.func.id=='integer'
              and node.args and isinstance(node.args[0],ast.Constant) and node.args[0].value=='count')
    low=ast.literal_eval(call.args[2])
    high=call.args[3]
    if not isinstance(high,ast.IfExp) or not isinstance(high.test,ast.Name) or high.test.id!='course':
        raise ValueError('API count schema changed; update matrix extraction')
    return {'spot':{'min':low,'max':ast.literal_eval(high.orelse)},
            'course':{'min':low,'max':ast.literal_eval(high.body)}}


def required_pairs(levels):
    return {(i,a,j,b) for i in range(len(levels)) for j in range(i+1,len(levels))
            for a in range(levels[i]) for b in range(levels[j])}


def row_pairs(row):
    return {(i,row[i],j,row[j]) for i in range(len(row)) for j in range(i+1,len(row))}


def covering_array(levels, seed=2810):
    """Greedy deterministic pairwise cover, independently measurable afterwards."""
    rng = random.Random(seed)
    missing = required_pairs(levels)
    rows = []
    while missing:
        pair = min(missing)
        best, score = None, -1
        for _ in range(64):
            row = [rng.randrange(n) for n in levels]
            row[pair[0]], row[pair[2]] = pair[1], pair[3]
            covered = len(row_pairs(row) & missing)
            if covered > score:
                best, score = row, covered
        rows.append(best)
        missing.difference_update(row_pairs(best))
    # Keep a small baseline useful: cover every individual value first, while
    # preserving the exact same full pairwise row set and denominator.
    remaining=rows[:]
    prioritized=[]
    values={(i,value) for i,n in enumerate(levels) for value in range(n)}
    while values:
        index=max(range(len(remaining)),key=lambda j:sum((i,v) in values for i,v in enumerate(remaining[j])))
        row=remaining.pop(index)
        prioritized.append(row)
        values.difference_update(enumerate(row))
    return prioritized+remaining


def pairwise_plan(options, mode):
    g = options['tag_groups']
    factors = dict(origin=[o['id'] for o in options['origins']],
        result_count=options[f'{mode}_counts'], companion=['', *g['누구와']],
        mood=['', *g['어떤 분위기']], occasion=['', *g['특별한 날']])
    if mode == 'spot':
        factors.update(environment=['', *g['실내 · 야외']], activity=['', *g['어떤 활동']])
    else:
        factors.update(visit_count=options['course_visit_counts'], activity=options['activities'])
        if '실내 · 야외' not in options['course_hidden_tag_groups']:
            factors['environment'] = ['', *g['실내 · 야외']]
    rows = covering_array([len(v) for v in factors.values()])
    total = required_pairs([len(v) for v in factors.values()])
    achieved = set().union(*(row_pairs(row) for row in rows))
    assert achieved == total
    return dict(factors=factors, rows=rows, required_pairs=len(total), covered_pairs=len(achieved),
                method='Deterministic greedy strength-2 covering array. A mood value is one mood or none; '
                       'multi-mood subsets are a separate exhaustive schema check. Origin is a valid composite '
                       'region/transport/coordinate, avoiding impossible region/hub combinations. '
                       'Course activity rotates the other slots so every slot position sees every activity; '
                       'the array does not cover every possible 3-5 activity sequence.')


class Findings:
    def __init__(self):
        self.checks = Counter()
        self.failures = []

    def check(self, condition, label, details=None):
        self.checks[label] += 1
        if not condition:
            self.failures.append(dict(check=label, details=details))


def offline_runtime():
    sys.path.insert(0, str(ROOT))
    from scripts.offline_environment import install
    install()
    import app
    import pandas as pd
    logging.getLogger().setLevel(logging.CRITICAL)
    app._call_claude = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('matrix forced provider unavailable'))
    # Production get_df is executed before memoization, preserving any service-area
    # fix in that function rather than reconstructing its old behavior in the test.
    lookup = {region: app.get_df(region) for region in ('', '내 주변', '천안', '아산')}
    app.get_df = lambda region='': lookup[region].copy(deep=True)
    return app, pd


def source_city(record):
    """Independent source-address jurisdiction; DB region labels may be unknown."""
    address=str(record.get('주소','')).strip()
    words=address.split()
    while words and words[0] in ('대한민국','한국','충남','충청남도'):
        words.pop(0)
    return {'천안시':'천안','아산시':'아산'}.get(words[0]) if words else None


def candidate_pool(app,region):
    frame=app.get_df(region)
    if hasattr(app,'filter_service_candidates'):
        frame,_=app.filter_service_candidates(frame,region)
    frame,_=app.filter_reviewed_candidates(frame)
    frame,_=app.filter_coordinate_candidates(frame)
    return frame


def frozen_audit(app, pd, options, findings):
    from place_identity import quarantine_legacy
    from recommender.visits import visit_groups
    with closing(sqlite3.connect(DB.as_uri()+'?mode=ro', uri=True)) as conn:
        raw = pd.read_sql('SELECT * FROM places', conn)
    frame = quarantine_legacy(raw).drop_duplicates('place_id')
    groups = visit_groups(frame)
    kinds = Counter(frame['카테고리'].fillna(''))
    regions = Counter(frame['지역'].fillna(''))
    audit = dict(raw_rows=len(raw), eligible_identity_rows=len(frame),
        regions=dict(regions), category_kinds=dict(sorted(kinds.items())),
        duplicate_ids=int(raw['place_id'].duplicated().sum()),
        exact_visit_alias_extra_rows=len(frame)-len(set(groups.values())),
        source_child_venues=int(frame.apply(app.child_venue, axis=1).sum()),
        verified_tag_rows=int(frame.get('blog_tag_status', pd.Series(dtype=str)).eq('verified').sum()))
    audit['source_address_service_cities']=dict(Counter(source_city(row) or 'outside_or_unrecognized'
        for row in frame.to_dict('records')))
    result = []
    radius_evaluated_rows=0
    for origin in options['origins']:
        local = candidate_pool(app,origin['region'])
        radius_evaluated_rows += len(local)
        radius = app.RADIUS_KM[origin['transport']]
        actual = app.filter_radius(local, origin['lat'], origin['lng'], origin['transport'])
        # Independent haversine implementation, applied to every available row.
        def distance(row):
            a,b = math.radians(origin['lat']), math.radians(float(row['latitude']))
            dlat = b-a
            dlon = math.radians(float(row['longitude'])-origin['lng'])
            q = math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
            return 6371*2*math.asin(min(1,math.sqrt(q)))
        expected = {r['place_id'] for r in local.to_dict('records') if distance(r) <= radius+1e-7}
        findings.check(set(actual.place_id) == expected, 'exhaustive_radius_membership', origin['id'])
        actual_cities=[source_city(r) for r in actual.to_dict('records')]
        findings.check(set(actual_cities) <= {'천안','아산'}, 'candidate_service_region',
                       dict(origin=origin['id'], unsupported_source_cities=dict(Counter(c for c in actual_cities if c not in ('천안','아산')))))
        if origin['region'] != '내 주변':
            findings.check(set(actual_cities) <= {origin['region']}, 'candidate_selected_region', origin['id'])
        activities = {'기본 활동': app.ACTIVITY_CATS, **app.ACTIVITY_TAG_CATEGORIES}
        for child in (False, True):
            tags = ['아이와 함께'] if child else ['부모님 모시고']
            allowed, meta = app.filter_child_candidates(actual, dict(persona_tags=tags, user_text=''))
            findings.check(meta['child_venues_allowed'] is child, 'family_gate_companion', origin['id'])
            if not child:
                findings.check(not any(app.child_venue(r) for r in allowed.to_dict('records')),
                               'family_gate_excludes_children', origin['id'])
            records=allowed.to_dict('records')
            for activity,cats in activities.items():
                chosen = app.filter_keywords(allowed, cats, [])
                expected_ids=set()
                for record in records:
                    category=str(record.get('카테고리','') or '').strip()
                    effective=category or str(record.get('search_category','') or '')
                    if record.get('category_source')=='search_fallback':
                        effective=''
                    if app.category_matches(effective,cats,record['가게명']):
                        expected_ids.add(record['place_id'])
                findings.check(set(chosen.place_id)==expected_ids, 'exhaustive_activity_filter',
                               dict(origin=origin['id'], activity=activity, child=child))
                result.append(dict(origin=origin['id'], child_allowed=child, activity=activity,
                                   candidates=len(chosen), distinct_visits=len(set(groups[p] for p in chosen.place_id))))
    audit['candidate_cells'] = result
    audit['filter_universe'] = dict(valid_spatial_origins=len(options['origins']),
        raw_spatial_input_rows=sum(len(app.get_df(o['region'])) for o in options['origins']),
        radius_row_evaluations=radius_evaluated_rows,
        activity_family_cells=len(result),
        note='Every row per spatial origin, every public/legacy activity per two child-gate states. '
             'This is factorized filter coverage, not all preference/cartesian request combinations.')
    return frame,groups,audit


def exhaustive_schema(app, options, findings):
    from api_request import parse_recommendation
    from runtime_llm import PERSONA_TAGS
    from recommender.constants import CORE_ACTIVITY_LABELS, CORE_ACTIVITY_TAG_SLOTS
    ui_tags = {t for tags in options['tag_groups'].values() for t in tags}
    findings.check(ui_tags == set(PERSONA_TAGS), 'ui_api_tag_inventory', dict(
        ui_only=sorted(ui_tags-set(PERSONA_TAGS)), api_only=sorted(set(PERSONA_TAGS)-ui_tags)))
    findings.check(set(options['transports']) == set(app.RADIUS_KM), 'ui_api_transport_inventory')
    findings.check(set(options['activities']) == set(CORE_ACTIVITY_LABELS), 'ui_api_activity_inventory')
    findings.check(set(options['tag_groups']['어떤 활동']) == set(CORE_ACTIVITY_TAG_SLOTS), 'ui_api_activity_tag_inventory')
    base = dict(user_lat=36.8151, user_lng=127.1139, region='천안', transport='대중교통')
    api_limits=extract_api_count_limits()
    for mode,bounds in api_limits.items():
        for count in range(bounds['min'],bounds['max']+1):
            findings.check(parse_recommendation({**base,'count':count},course=mode=='course')['count']==count,
                           'exhaustive_api_count_schema',dict(mode=mode,count=count))
    # Every mood subset is validated independently. Interactions of the other tag
    # groups are sampled by pairwise routes, not falsely called exhaustive.
    moods = options['tag_groups']['어떤 분위기']
    for mask in range(2**len(moods)):
        selected = [t for i,t in enumerate(moods) if mask & (1<<i)]
        data = parse_recommendation({**base,'persona_tags':selected})
        findings.check(data['persona_tags'] == selected, 'exhaustive_mood_subset_schema')
    for tag in ui_tags:
        findings.check(parse_recommendation({**base,'persona_tags':[tag]})['persona_tags'] == [tag], 'exhaustive_single_tag_schema', tag)
    for mode in ('spot','course'):
        for length in range(101):
            history=[f'matrix:{i}' for i in range(length)]
            parsed=parse_recommendation({**base,'recent_place_ids':history},course=mode=='course')
            findings.check(parsed.get('recent_place_ids')==history,'exhaustive_history_length_schema',dict(mode=mode,length=length))
    for o in options['origins']:
        for mode in ('spot','course'):
            for count in options[f'{mode}_counts']:
                for visits in options['course_visit_counts'] if mode == 'course' else (None,):
                    payload = dict(base, region=o['region'], transport=o['transport'], user_lat=o['lat'],user_lng=o['lng'],count=count)
                    if mode == 'course':
                        payload.update(spot_count=visits,slot_types=[options['activities'][0]]*visits)
                    findings.check(parse_recommendation(payload,course=mode=='course')['count'] == count,
                                   'exhaustive_origin_count_schema')
    for length in options['course_visit_counts']:
        for slots in itertools.product(options['activities'], repeat=length):
            data = parse_recommendation({**base,'spot_count':length,'slot_types':list(slots)},course=True)
            findings.check(data['slot_types'] == list(slots), 'exhaustive_course_sequence_schema')
    return dict(api_count_limits=api_limits,mood_subsets=2**len(moods), single_tags=len(ui_tags),
                all_course_sequences=sum(len(options['activities'])**n for n in options['course_visit_counts']),
                note='Schema acceptance and order preservation only; these are not 9288 recommendation executions.')


def payload_for(options, plan, row, mode, seed=11):
    values = {k:vals[index] for (k,vals),index in zip(plan['factors'].items(),row)}
    origin = next(o for o in options['origins'] if o['id'] == values['origin'])
    tags = [values[k] for k in ('companion','mood','occasion') if values[k]]
    if mode == 'spot':
        tags += [values[k] for k in ('environment','activity') if values[k]]
    elif values.get('environment'):
        tags.append(values['environment'])
    body = dict(user_lat=origin['lat'], user_lng=origin['lng'], region=origin['region'],
        transport=origin['transport'], count=values['result_count'], persona_tags=tags,
        user_text='', seed=seed, randomize=True)
    if mode == 'course':
        activities = options['activities']
        start = activities.index(values['activity'])
        slots = [activities[(start+i)%len(activities)] for i in range(values['visit_count'])]
        body.update(spot_count=values['visit_count'], slot_types=slots)
    return values,body


def response_checks(app, findings, mode, payload, response, groups, frame, label):
    body = response.get_json() or {}
    findings.check(response.status_code in (200,422), 'recommendation_contract_status', dict(case=label,status=response.status_code,reason=body.get('reason')))
    courses = [body.get('places',[])] if mode == 'spot' else body.get('courses',[])
    meta = body.get('metadata',{})
    findings.check(meta.get('constraints_relaxed') == [], 'recommendation_constraints_preserved', label)
    known = frame.set_index('place_id', drop=False)
    signatures = []
    distances = []
    for course in courses:
        ids = [p['place_id'] for p in course]
        findings.check(all(pid in groups for pid in ids), 'recommendation_known_ids', label)
        visits = [groups.get(pid,pid) for pid in ids]
        findings.check(len(visits) == len(set(visits)), 'recommendation_distinct_visits', label)
        if mode == 'course':
            findings.check(len(course) == payload['spot_count'], 'recommendation_course_length', label)
        else:
            findings.check(len(course) <= payload['count'], 'recommendation_spot_count', label)
        signatures.append(tuple(visits))
        for i,p in enumerate(course):
            original = known.loc[p['place_id']]
            actual_city=source_city(original)
            findings.check(actual_city in ('천안','아산'), 'recommendation_service_region', dict(case=label,place_id=p['place_id'],db_region=original['지역'],source_city=actual_city))
            if payload['region'] != '내 주변':
                findings.check(actual_city == payload['region'], 'recommendation_selected_region', label)
            d = float(app.distances_from((payload['user_lat'],payload['user_lng']),[[p['lat'],p['lng']]])[0])
            distances.append(d)
            findings.check(d <= app.RADIUS_KM[payload['transport']]+1e-7, 'recommendation_radius', label)
            if mode == 'course':
                cats = app.SLOT_CATEGORY_MAP[payload['slot_types'][i]]
            else:
                cats = meta.get('category_filters')
                if cats is None:
                    stages=meta.get('travel_request',{}).get('stages',[])
                    cats=stages[0]['category_filters'] if stages else []
            findings.check(app.category_matches(p['category'],cats,p['source_name']), 'recommendation_activity', label)
            if not app.children_allowed(payload):
                findings.check(not app.child_venue(original), 'recommendation_family_gate', dict(case=label,name=p['name']))
    findings.check(len(signatures) == len(set(signatures)), 'recommendation_distinct_courses', label)
    findings.check(len(courses) <= payload['count'] if mode == 'course' else True,'recommendation_course_count',label)
    nonempty = any(courses)
    findings.check((response.status_code == 200) == nonempty, 'empty_response_status_separation', label)
    if payload.get('recent_place_ids') and nonempty:
        recent={groups.get(pid,pid) for pid in payload['recent_place_ids']}
        selected={pid for ids in signatures for pid in ids}
        variation=meta.get('recommendation_variation') or {}
        findings.check(variation.get('repeated_count')==len(recent & selected)
                       and variation.get('new_count')==len(selected-recent),
                       'history_overlap_metadata_matches_actual_visits',label)
    return dict(status=response.status_code, reason=body.get('reason') or meta.get('reason'),
        returned=len(courses) if mode == 'course' else len(courses[0]),
        ids=signatures, place_ids=[[p['place_id'] for p in c] for c in courses],
        candidates=meta.get('slot_candidate_counts') or meta.get('candidate_counts'),
        max_distance_km=max(distances,default=None), family_policy=meta.get('family_policy'),
        recommendation_variation=meta.get('recommendation_variation'),
        names=[[p['name'] for p in course] for course in courses])


def recommendations(app, options, plans, findings, groups, frame, limit):
    results = []
    client = app.app.test_client()
    for mode,plan in plans.items():
        rows = plan['rows'][:limit] if limit else plan['rows']
        for index,row in enumerate(rows):
            values,payload = payload_for(options,plan,row,mode)
            start = time.perf_counter()
            response = client.post('/recommend/'+mode,json=payload)
            result = response_checks(app,findings,mode,payload,response,groups,frame,f'{mode}-{index}')
            results.append(dict(id=f'{mode}-{index}',mode=mode,values=values,request=payload,
                                seconds=round(time.perf_counter()-start,4),**result))
        covered = set().union(*(row_pairs(row) for row in rows))
        plan['executed_rows'] = len(rows)
        plan['executed_pairs'] = len(covered)
        plan['required_single_values'] = sum(len(v) for v in plan['factors'].values())
        plan['executed_single_values'] = len({(i,value) for row in rows for i,value in enumerate(row)})
        plan['remaining_rows'] = len(plan['rows'])-len(rows)
    return results


def reruns(app,options,findings,groups,frame):
    """S6 fixed case plus every valid origin/transport representative."""
    client = app.app.test_client()
    results=[]
    for origin in options['origins']:
        # All origins and all activities appear; the user case is exact in a separate row.
        tags=['친구와','활동적인','실내 위주']
        payload=dict(user_lat=origin['lat'],user_lng=origin['lng'],region=origin['region'],
                     transport=origin['transport'],count=10,persona_tags=tags,user_text='',randomize=True)
        samples=[]
        for seed in (11,29,47):
            body={**payload,'seed':seed}
            r=client.post('/recommend/spot',json=body)
            samples.append(response_checks(app,findings,'spot',body,r,groups,frame,f'rerun/{origin["id"]}/{seed}'))
        history_samples=[]
        previous=[pid for ids in samples[0]['place_ids'] for pid in ids]
        # Only last displayed IDs cross this contract; history is never a hard exclusion.
        for seed in (29,47):
            body={**payload,'seed':seed,'recent_place_ids':previous}
            r=client.post('/recommend/spot',json=body)
            sample=response_checks(app,findings,'spot',body,r,groups,frame,f'history-rerun/{origin["id"]}/{seed}')
            history_samples.append(sample)
            previous=[pid for ids in sample['place_ids'] for pid in ids]
        replay=client.post('/recommend/spot',json={**payload,'seed':11}).get_json()
        findings.check(tuple(groups[p['place_id']] for p in replay.get('places',[])) == tuple(samples[0]['ids'][0]),
                       'rerun_seed_replay',origin['id'])
        signatures=[tuple(sorted(s['ids'][0])) for s in samples]
        overlap=[len(set(a)&set(b)) for a,b in itertools.combinations(signatures,2)]
        pool=candidate_pool(app,origin['region'])
        pool,_=app.filter_child_candidates(pool,payload)
        pool=app.filter_radius(pool,origin['lat'],origin['lng'],origin['transport'])
        pool=app.filter_keywords(pool,app.ACTIVITY_CATS,[])
        candidates=len(set(groups[pid] for pid in pool.place_id))
        results.append(dict(origin=origin['id'],samples=samples,history_samples=history_samples,
                            unique_compositions=len(set(signatures)),
                            eligible_distinct_candidates=candidates,
                            repeated_despite_more_than_requested=candidates>payload['count'] and len(set(signatures))<len(samples),
                            max_shared_places=max(overlap,default=0),
                            interpretation='Observed compositions across three seeds; no forced variation assertion when candidates are scarce.'))
    return results


def boundaries(app, findings):
    client=app.app.test_client()
    base=dict(user_lat=36.8151,user_lng=127.1139,region='천안',transport='대중교통',count=3,persona_tags=[])
    results=[]
    invalid=[('bool latitude',{'user_lat':True}),('NaN latitude',{'user_lat':'NaN'}),
        ('infinite longitude',{'user_lng':'Infinity'}),('missing latitude',{'user_lat':None}),
        ('latitude range',{'user_lat':91}),('longitude range',{'user_lng':-181}),
        ('unknown region',{'region':'안성'}),('unknown transport',{'transport':'도보'}),
        ('bool count',{'count':True}),('zero count',{'count':0}),('too many count',{'count':21}),
        ('bad tags',{'persona_tags':['']}),('text overflow',{'user_text':'가'*1001})]
    invalid += [('history overflow',{'recent_place_ids':['x']*101}),
                ('empty history id',{'recent_place_ids':['']}),
                ('long history id',{'recent_place_ids':['x'*201]}),
                ('history not array',{'recent_place_ids':'x'}),
                ('history non-string',{'recent_place_ids':[True]})]
    for mode in ('spot','course'):
        modebase={**base,**(dict(spot_count=3,slot_types=['음식','자연·산책','카페']) if mode=='course' else {})}
        for label,patch in invalid:
            r=client.post('/recommend/'+mode,json={**modebase,**patch})
            findings.check(r.status_code==400 and r.json.get('reason')=='invalid_request','invalid_boundary',dict(mode=mode,label=label,status=r.status_code))
            results.append(dict(mode=mode,label=label,status=r.status_code,reason=r.json.get('reason')))
        for label,patch in [('south',{'user_lat':36.549999}),('north',{'user_lat':37.050001}),
                            ('west',{'user_lng':126.799999}),('east',{'user_lng':127.350001})]:
            r=client.post('/recommend/'+mode,json={**modebase,**patch})
            findings.check(r.status_code==422 and r.json.get('reason')=='outside_service_area','service_area_boundary',dict(mode=mode,label=label,status=r.status_code))
            results.append(dict(mode=mode,label=label,status=r.status_code,reason=r.json.get('reason')))
    # Empty candidate and interpretation outage have different machine reasons.
    original_get_df=app.get_df
    empty=app.get_df('천안').iloc[:0].copy()
    app.get_df=lambda region='': empty.copy()
    try:
        r=client.post('/recommend/spot',json={**base,'count':3})
    finally:
        app.get_df=original_get_df
    findings.check(r.status_code==422 and r.json.get('metadata',{}).get('reason')=='insufficient_candidates',
                   'empty_candidate_reason',dict(status=r.status_code,body=r.json))
    results.append(dict(label='explicit empty purpose',status=r.status_code,reason=r.json.get('reason') or r.json.get('metadata',{}).get('reason')))
    r=client.post('/recommend/spot',json={**base,'user_text':'여자친구랑 100일기념 데이트'})
    findings.check(r.status_code==503 and r.json.get('reason')=='category_unavailable','provider_failure_separate_from_empty',r.status_code)
    results.append(dict(label='forced interpretation outage',status=r.status_code,reason=r.json.get('reason')))
    return results


def family_boundaries(app,options,findings):
    """Q1 expected product boundary includes specifically child-purpose museums."""
    records=[('키즈카페','키즈카페',True),('일반 카페','카페',False),
             ('어린이박물관','박물관',True),('어린이체험관','박물관,체험관',True),
             ('일반 역사박물관','박물관',False),('유관순열사기념관','기념관',False),
             ('키즈카페 부설점','카페',True),('실내놀이터','실내놀이터',True)]
    results=[]
    for companion in ['',*options['tag_groups']['누구와']]:
        data=dict(persona_tags=[companion] if companion else [],user_text='')
        allowed=companion in ('아이와 함께','유아/영아 동반')
        findings.check(app.children_allowed(data)==allowed,'exhaustive_companion_child_scope',companion)
        for name,category,child in records:
            row={'가게명':name,'카테고리':category}
            actual=app.child_venue(row)
            findings.check(actual==child,'child_venue_purpose_boundary',dict(companion=companion,name=name,
                category=category,expected_child_purpose=child,actual_child_purpose=actual))
            results.append(dict(companion=companion,name=name,category=category,expected_child_purpose=child,
                                actual_child_purpose=actual,child_allowed=allowed))
    return dict(cases=results,denominator=len(results),
                note='Child-purpose museum boundary is an expected product criterion from Q1; '
                     'it does not classify every museum as a child venue.')


def korean_contract_cases(app,options,findings,groups,frame):
    """Handwritten Korean interpretation fixtures; zero claims of LLM accuracy."""
    import travel_intent as ti
    client=app.app.test_client()
    results=[]
    original_model=app._call_claude
    def plan(stages=(),companion=None,exclusions=(),ambiguities=()):
        return dict(schema_version=1,companion=companion,stages=[dict(id=f's{i+1}',activity=q,
            quote=q,category_filters=cats,conditions=conditions,preferences=[]) for i,(q,cats,conditions) in enumerate(stages)],
            exclusions=list(exclusions),ambiguities=list(ambiguities),unsupported=[],requested_visit_count=None)
    date='여자친구랑 100일기념 데이트'
    fixture=plan(companion={'value':'연인과','quote':'여자친구랑'},
                 ambiguities=[{'quote':'데이트','reason':'방문 활동을 선택해주세요.'}])
    calls=[]
    def model(system,message,**kwargs):
        if system==ti.SELECTION_SYSTEM:
            raise RuntimeError('matrix exercises guarded offline selection fallback')
        calls.append(json.loads(message))
        return copy.deepcopy(fixture)
    app._call_claude=model
    base=dict(user_lat=36.8013,user_lng=127.13587,region='천안',transport='대중교통',
              count=3,persona_tags=['연인과','로맨틱한','기념일'],intent_version=1,
              user_text=date,plan_mode='natural',seed=11,randomize=True)
    try:
        first=client.post('/travel/interpret',json={**base,'mode':'spot'})
        findings.check(first.status_code==200 and first.json.get('clarification_required') is True
                       and first.json.get('clarification',{}).get('token'),
                       'korean_context_activity_prompt',dict(status=first.status_code,reason=first.json.get('reason')))
        token=first.json.get('clarification',{}).get('token')
        for activity in options['activities']:
            payload={**base,'mode':'spot','activity_choice':activity,'clarification_token':token}
            preview=client.post('/travel/interpret',json=payload)
            findings.check(preview.status_code==200 and preview.json.get('intent_token'),
                           'korean_context_all_activity_choices',dict(activity=activity,status=preview.status_code,reason=preview.json.get('reason')))
            actual=None
            if preview.json.get('intent_token'):
                body={**payload,'intent_token':preview.json['intent_token']}
                response=client.post('/recommend/spot',json=body)
                actual=response_checks(app,findings,'spot',body,response,groups,frame,'korean-date/'+activity)
                findings.check(response.status_code in (200,422) and response.json.get('reason')!='intent_unavailable',
                               'korean_activity_shortage_not_parse_failure',activity)
            results.append(dict(label='100일 기념 '+activity,preview_status=preview.status_code,
                preview_reason=preview.json.get('reason'),recommendation=actual))
        # A manual course must preserve the already selected order, without a second activity question.
        payload={**base,'mode':'course','plan_mode':'manual','spot_count':3,'slot_types':['음식','자연·산책','카페']}
        preview=client.post('/travel/interpret',json=payload)
        findings.check(preview.status_code==200 and preview.json.get('intent_token'),
                       'korean_manual_course_no_requestion',dict(status=preview.status_code,reason=preview.json.get('reason')))
        actual=None
        if preview.json.get('intent_token'):
            body={**payload,'intent_token':preview.json['intent_token']}
            response=client.post('/recommend/course',json=body)
            actual=response_checks(app,findings,'course',body,response,groups,frame,'korean-manual-date')
        results.append(dict(label='100일 식사→산책→카페',preview_status=preview.status_code,recommendation=actual))

        recipes=[
            ('부모님과 전시를 보고 싶어요','부모님 모시고','부모님과','전시',['전시'],[],[]),
            ('친구와 실내 볼링을 하고 싶어요','친구와','친구와','볼링',['볼링'],
             [dict(field='indoor',quote='실내',required=True,value=True)],[]),
            ('카페 말고 공원을 걷고 싶어요',None,None,'공원',['공원'],[],
             [dict(category_filters=['카페'],quote='카페 말고')]),
            ('카페 말고는 가지 않을래요',None,None,'카페',['카페'],[],[]),
            ('혼자 맥주 박물관에 가고 싶어요','혼자','혼자','박물관',['박물관'],[],[]),
            ('아이와 함께 키즈카페에 가고 싶어요','아이와 함께','아이와 함께','키즈카페',['키즈카페'],[],[]),
        ]
        for text,who,quote,activity,cats,conditions,exclusions in recipes:
            fixture=plan([(activity,cats,conditions)],{'value':who,'quote':quote} if who else None,exclusions)
            payload={**base,'user_text':text,'persona_tags':[],'mode':'spot'}
            preview=client.post('/travel/interpret',json=payload)
            findings.check(preview.status_code==200 and preview.json.get('intent_token'),
                           'korean_fixture_preview',dict(text=text,status=preview.status_code,reason=preview.json.get('reason')))
            actual=None
            if preview.json.get('intent_token'):
                body={**payload,'intent_token':preview.json['intent_token']}
                response=client.post('/recommend/spot',json=body)
                if conditions:
                    findings.check(response.status_code==422 and response.json.get('reason') in ('unverified_conditions','missing_slot_candidates'),
                                   'mandatory_condition_preserved',dict(text=text,status=response.status_code,reason=response.json.get('reason')))
                    actual=dict(status=response.status_code,reason=response.json.get('reason'))
                else:
                    actual=response_checks(app,findings,'spot',body,response,groups,frame,'korean-fixture/'+text)
            results.append(dict(label=text,preview_status=preview.status_code,preview_reason=preview.json.get('reason'),recommendation=actual))
    finally:
        app._call_claude=original_model
    return dict(cases=results,interpretation_stub_calls=len(calls),live_provider_calls=0,
                note='Handwritten structured fixtures test Korean control/quote/negation/required-condition contracts. '
                     'They do not measure real model language understanding or satisfaction.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['baseline','final'],default='baseline')
    parser.add_argument('--recommendation-limit',type=int)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if args.recommendation_limit is None:
        args.recommendation_limit=0 if args.phase=='final' else 48
    if args.recommendation_limit<0:
        parser.error('limit must be >=0')
    if args.phase=='final' and args.recommendation_limit:
        parser.error('final phase requires complete pairwise execution: use --recommendation-limit 0')
    output=args.output or ARTIFACTS/f'matrix-{args.phase}.json'
    started=time.perf_counter()
    before=source_manifest()
    hashes={name:digest(ROOT/name) for name in FROZEN}
    if hashes != FROZEN or json.loads(PILOT.read_text()).get('collection_authorized_now') is not False:
        raise RuntimeError('Frozen data precondition failed')
    options=extract_ui_options()
    space=finite_space(options)
    plans={mode:pairwise_plan(options,mode) for mode in ('spot','course')}
    app,pd=offline_runtime()
    findings=Findings()
    schema=exhaustive_schema(app,options,findings)
    print('matrix: schema complete',flush=True)
    frame,groups,audit=frozen_audit(app,pd,options,findings)
    print('matrix: frozen filter audit complete',flush=True)
    requests=recommendations(app,options,plans,findings,groups,frame,args.recommendation_limit)
    print('matrix: recommendation sample complete',flush=True)
    variations=reruns(app,options,findings,groups,frame)
    controls=boundaries(app,findings)
    family=family_boundaries(app,options,findings)
    korean=korean_contract_cases(app,options,findings,groups,frame)
    after=source_manifest()
    frozen_after={name:digest(ROOT/name) for name in FROZEN}
    findings.check(hashes==frozen_after,'frozen_data_preserved')
    drift=[p for p,h in before['files'].items() if after['files'].get(p)!=h]
    drift += [p for p in after['files'] if p not in before['files']]
    if args.phase=='final':
        findings.check(not drift,'final_source_stable',drift)
    request_counts=dict(pairwise_recommendations=len(requests),
        rerun_recommendations=sum(len(v['samples'])+len(v.get('history_samples',[]))+1 for v in variations),
        boundary_requests=len(controls),
        korean_fixture_requests=1+len(korean['cases'])+sum(c.get('recommendation') is not None for c in korean['cases']))
    report=dict(phase=args.phase,status='FINDINGS' if findings.failures else 'PASS_WITH_SCOPE_LIMITS',
        method='Offline Flask test client; external transport and dotenv blocked. '
               'Schema/filter factor exhaustions plus pairwise and representatives; no Cartesian end-to-end completion claim.',
        options=options,finite_space=space,schema=schema,plans=plans,
        source_before=before,source_after=after,source_drift=drift,stable_source=not drift,
        frozen_before=hashes,frozen_after=frozen_after,db_preserved=hashes==frozen_after,
        frozen_audit=audit,requests=requests,reruns=variations,boundaries=controls,
        family_boundaries=family,korean_contract_cases=korean,
        http_request_counts={**request_counts,'total':sum(request_counts.values())},
        check_counts=dict(findings.checks),check_total=sum(findings.checks.values()),failures=findings.failures,
        seconds=round(time.perf_counter()-started,2),
        unexecuted=['Cartesian end-to-end recommendation space','all arbitrary GPS/text/history values',
                    'live provider Korean language accuracy','real device keyboard/GPS/accessibility',
                    'live photo identity/availability','operational Node gateway (root integration scope)'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps(dict(output=str(output),status=report['status'],checks=report['check_total'],
        failures=len(findings.failures),source_drift=drift,db_preserved=report['db_preserved'],
        pairwise={m:{k:p[k] for k in ('required_pairs','executed_pairs','executed_rows','remaining_rows')} for m,p in plans.items()},
        seconds=report['seconds']),ensure_ascii=False,indent=2))
    return 1 if findings.failures else 0


if __name__=='__main__':
    raise SystemExit(main())
