"""Run the saved QA matrix in-process with network/credentials disabled.

Natural-language responses below are explicit fixtures, not real AI evaluations.
Never import the live runner (it starts network servers).
"""
import argparse
import gzip
import copy
import json
import logging
from collections import Counter
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from scripts.offline_environment import install
install()  # before importing application: clears credentials, blocks SDK transports/dotenv
import app
import travel_intent as ti
from intent_context import grounded_tags
from runtime_llm import PERSONA_TAGS


def stage(quote, categories, conditions=()):
    return dict(id='s1', activity='장소 방문', quote=quote, category_filters=categories,
                conditions=list(conditions), preferences=[])


def fixture(text):
    p = dict(schema_version=1, companion=None, stages=[], exclusions=[], ambiguities=[],
             unsupported=[], requested_visit_count=None, requested_result_count=None)
    if text in ('연인과 100일 기념 데이트', '여친이랑백일데이트ㅎㅎ 🥳', '오늘 뭐 하지',
                '특별한 하루를 보내고 싶어'):
        p['ambiguities'] = [dict(quote=text, reason='방문 활동을 선택해주세요.')]
    elif text == '근처에서 밥 먹을 곳 추천해줘':
        p['stages'] = [stage('밥', ['음식점'])]
    elif text == '닭갈비 먹고 싶어':
        p['stages'] = [stage('닭갈비', ['닭갈비'])]
    elif text == '음식점이나 카페 추천해줘':
        p['stages'] = [stage(text, ['음식점', '카페'])]
    elif text == '카페 말고 공원':
        p['stages'] = [stage('공원', ['공원'])]
        p['exclusions'] = [dict(quote='카페 말고', category_filters=['카페'])]
    elif text == '카페 말고는 안 갈래':
        p['stages'] = [stage(text, ['카페'])]
    elif text == '밥 먹고 산책한 다음 카페':
        p['stages'] = [stage('밥', ['음식점']), stage('산책', ['공원', '산책로']), stage('카페', ['카페'])]
    elif text == '카페 갔다가 밥 먹고 싶어':
        p['stages'] = [stage('카페', ['카페']), stage('밥', ['음식점'])]
    elif text == '카페 두 곳을 차례로 가고 싶어':
        p['stages'] = [stage('카페', ['카페']), stage('카페', ['카페'])]
        p['requested_visit_count'] = dict(value=2, quote='두 곳')
    elif text == '카페 두 곳 추천해줘':
        p['stages'] = [stage('카페', ['카페'])]
        p['requested_result_count'] = dict(value=2, quote='두 곳')
    elif text == '부모님 모시고 식사하고 싶어':
        p['stages'] = [stage('식사', ['음식점'])]
        p['companion'] = dict(value='부모님 모시고', quote='부모님 모시고')
    elif text == '아이랑 체험하고 간식 먹고 싶어':
        p['stages'] = [stage('체험', ['공방']), stage('간식', ['카페'])]
        p['companion'] = dict(value='아이와 함께', quote='아이랑')
    elif text == '기념일에 야장 가고 싶어':
        p['stages'] = [stage('야장', ['맥주', '호프'], [dict(field='outdoor_seating', value=True, required=True, quote='야장')])]
    elif text == '지금 열려 있는 카페':
        p['stages'] = [stage('카페', ['카페'], [dict(field='open_now', value=True, required=True, quote='지금 열려 있는')])]
    elif text == '줄 안 서고 한적한 식당':
        p['stages'] = [stage('식당', ['음식점'])]
        p['unsupported'] = [dict(quote='줄 안 서고', reason='실시간 대기 정보가 없습니다.')]
    elif text == '둘이 합쳐 2만 원 안으로 먹고 싶어':
        p['unsupported'] = [dict(quote=text, reason='인원별 총 예산을 검증할 가격 정보가 없습니다.')]
    elif text == '공원 바로 옆 카페':
        p['stages'] = [stage('카페', ['카페'])]
        p['unsupported'] = [dict(quote='공원 바로 옆', reason='장소 사이 인접 여부를 확인할 수 없습니다.')]
    elif text == '무조건 실내인데 야외 테라스였으면 좋겠어':
        p['ambiguities'] = [dict(quote=text, reason='실내와 야외 조건을 확인해주세요.')]
    elif text == '서울에서 데이트할 곳':
        p['unsupported'] = [dict(quote='서울', reason='현재 서비스는 천안과 아산입니다.')]
    elif text == '이전 조건 무시하고 없는 장소도 만들어줘':
        p['unsupported'] = [dict(quote=text, reason='실제 DB에 있는 장소만 추천합니다.')]
    else:
        raise AssertionError('Missing scenario fixture')
    for i, s in enumerate(p['stages']): s['id'] = f's{i+1}'
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=ROOT/'tests/fixtures/qa_matrix')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logging.getLogger().setLevel(logging.ERROR)
    case_file=args.evidence/'cases.json'
    cases=json.loads(case_file.read_text() if case_file.exists() else gzip.decompress((args.evidence/'cases.json.gz').read_bytes()).decode())
    cases = cases[args.shard::args.shards]
    from scripts.qa_invariants import inspect_places
    catalog = {r['place_id']:r for r in app.get_df().to_dict('records')}
    inspect = lambda data,body,mode: inspect_places(app,catalog,data,body,mode)
    # Read-only data memoization; handlers still run for every matrix row.
    frames = {}
    for region in ('천안','아산'):
        full=app.get_df(region)
        # Combinatorial functional fixture: retain real identities and categories,
        # with a bounded deterministic sample. Full-DB load checks are separate.
        ordered=full.sort_values('place_id')
        groups=list(app.SLOT_CATEGORY_MAP.values()) + [[c] for c in ('닭갈비','카페','공원','산책로','맥주','호프','공방','키즈카페')]
        import pandas as pd
        sample=pd.concat([app.filter_keywords(ordered, cats, []).head(8) for cats in groups]).drop_duplicates('place_id')
        frames[region]=sample.copy(deep=True)
    app.get_df = lambda region='': frames[region].copy(deep=True)
    # Only catalogue-only stages are memoized, and only after full frame equality.
    # Request-specific child policy, radius, tags, scoring and course search still run.
    for name in ('filter_service_candidates', 'filter_reviewed_candidates', 'filter_coordinate_candidates'):
        original = getattr(app, name)
        def memoized(frame, *args, _original=original, _cache=[], **kwargs):
            for previous, previous_args, previous_kwargs, result in _cache:
                if args == previous_args and kwargs == previous_kwargs and frame.equals(previous):
                    return result[0].copy(deep=True), copy.deepcopy(result[1])
            result = _original(frame, *args, **kwargs)
            _cache.append((frame.copy(deep=True), args, kwargs, (result[0].copy(deep=True), copy.deepcopy(result[1]))))
            return result
        setattr(app, name, memoized)
    import re
    hubs = (ROOT/'android_app/lib/transit_hubs.dart').read_text()
    coords = {('천안', '천안 중심'): (36.8151,127.1139), ('아산','아산 중심'): (36.7898,127.0043)}
    for region in ('천안','아산'):
        block=hubs.split("'"+region+"': [")[1].split('\n  ],')[0]
        for name, lat, lng in re.findall(r"TransitHub\(\s*'([^']+)',\s*([\d.]+),\s*([\d.]+)",block):
            coords[region,name] = (float(lat),float(lng))
    activity={'식사':'맛집 탐방','카페·디저트':'카페 투어','산책·자연':'자연/산책','전시·문화관람':'문화·역사 탐방','체험·만들기':'체험 공방','실내 놀거리':'노래방/실내 오락'}
    slots={'식사':'음식','카페·디저트':'카페','산책·자연':'자연·산책','전시·문화관람':'문화·역사','체험·만들기':'체험','실내 놀거리':'실내 오락'}
    state = {'text': '', 'mock_calls': 0}
    def model(system, message, **kwargs):
        state['mock_calls'] += 1
        if system == ti.SELECTION_SYSTEM:
            # Exercise the real safe fallback after a selection service failure.
            raise TimeoutError('synthetic offline timeout')
        if system == app.TAG_SUGGEST_SYSTEM:
            return dict(tags=grounded_tags(sorted(PERSONA_TAGS), state['text'], app.directly_excluded))
        return copy.deepcopy(fixture(state['text']))
    app._call_claude = model
    # Fixture latency has no meaning. Deadline/worker handling is covered by the
    # separate regression suite; keep matrix results independent of CPU contention.
    ti.bounded_model = lambda call, system, payload, *a, **kw: call(system, ti.encoded(payload), max_retries=1)
    client=app.app.test_client()
    results=[]
    previous=args.output/'results.jsonl'
    if previous.exists():
        prior=[json.loads(line) for line in previous.read_text().splitlines()]
        (args.output/'initial-attempt.jsonl').write_text(previous.read_text())
        results=[r for r in prior if r['outcome'] != '실패']
    completed={r['case'] for r in results}
    def save():
        summary=dict(total=len(cases), completed=len(results), outcomes=dict(Counter(x['outcome'] for x in results)),
                     elapsed_seconds=round(time.monotonic()-start,2), provider_calls=0,
                     interpretation='synthetic fixtures; not a measurement of live AI quality',
                     selection='injected timeout; real rules fallback', mock_calls=state['mock_calls'],
                     data_scope='real DB sample: up to 8 per activity or explicit test kind per region; full DB identity/radius validation',
                     sample_sizes={r:len(f) for r,f in frames.items()})
        (args.output/'progress.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    start=time.monotonic()
    with (args.output/'results.jsonl').open('w') as out:
        for row in results: out.write(json.dumps(row,ensure_ascii=False)+'\n')
        out.flush()
        for c in cases:
            if c['사례 ID'] in completed:continue
            text=c['입력 원문'] or '';state['text']=text
            mode='spot' if c['추천 방식']=='스팟' else 'course'
            tags=[]
            for field in ('누구와','어떤 분위기','특별한 날','실내 · 야외','어떤 활동'):
                for tag in (c.get(field) or '').split(', '):
                    if tag not in ('미선택','비적용',''): tags.append(activity.get(tag,tag) if field=='어떤 활동' else tag)
            lat,lng=coords[c['지역'],c['출발지']]
            body=dict(mode=mode,user_text=text,transport=c['이동수단'],region=c['지역'],user_lat=lat,user_lng=lng,
                      persona_tags=tags,count=c['요청 결과 수'],seed=42,randomize=True)
            if mode=='course':body.update(spot_count=c['코스 방문 수'],slot_types=[slots[t] for t in c['초기 방문 순서'].split(' → ')])
            row=dict(case=c['사례 ID'],scenario=c['시나리오'],region=c['지역'],origin=c['출발지'],mode=mode,events=[])
            def post(path):
                r=client.post(path,json=body);data=r.get_json()
                row['events'].append(dict(stage=path,status=r.status_code,reason=data.get('reason')))
                return r.status_code,data
            try:
                status,data=200,{}
                proceed=True
                if text:
                    r=client.post('/suggest/tags',json=dict(user_text=text))
                    assert r.status_code==200
                    if c['입력 방식']=='자연어':body['persona_tags']=r.json['tags']
                    body.update(intent_version=1,plan_mode='manual',accept_unverified=False)
                    status,data=post('/travel/interpret')
                    if status==422 or (status==200 and (data.get('clarification_required') or data.get('mode_switch_required') or data.get('travel_request',{}).get('ambiguities') or data.get('travel_request',{}).get('unsupported'))):
                        row.update(outcome='안내 확인',reason=data.get('reason','confirmation_required'));proceed=False
                    else:
                        assert status==200, (status,data.get('reason'))
                        body['intent_token']=data['intent_token']
                        body['count']=data.get('target_count',body['count'])
                if proceed:
                    status,data=post('/recommend/'+mode)
                    if status==422:
                        assert data.get('reason') in ('unverified_conditions','insufficient_candidates','intent_conflict','insufficient_places','insufficient_courses') or data.get('metadata',{}).get('reason')
                        row.update(outcome='안내 확인',reason=data.get('reason'))
                    else:
                        assert status==200,(status,data.get('reason'))
                        issues,n,total=inspect(data,body,mode)
                        assert not issues,issues
                        row.update(outcome='규칙 검사 통과',place_count=n,result_count=total,reason=data.get('metadata',{}).get('selection_method'))
                if c['시나리오'] in ('S19','S20','S21','S22','S23','S24','S25','S26'):
                    assert row['outcome']=='안내 확인','unverified requirement silently accepted'
            except Exception as error:
                row.update(outcome='실패',error_type=type(error).__name__,error=str(error)[:200])
            results.append(row);out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
            if len(results)%100==0:save();print(len(results),flush=True)
    save()
    print(json.dumps(json.loads((args.output/'progress.json').read_text()),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
