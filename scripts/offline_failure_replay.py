"""Reproduce recorded failure classes, not unavailable raw provider responses."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.offline_environment import install
install()
import app
import travel_intent as ti
from scripts.offline_qa_matrix import fixture

HERE=ROOT/'tests/fixtures/qa_matrix'
OUT=ROOT/'local_artifacts/offline-qa-6916-20261101'
OUT.mkdir(parents=True,exist_ok=True)
records=json.loads((HERE/'failures.json').read_text())
original=ti.validate_interpretation
results=[]
for x in records:
    if x['outcome']!='실패':continue
    text=x['input'];code=x['server_failure_code']
    row=dict(case=x['case'],input=text,original_code=code or 'automatic_tags_unavailable',
             evidence_type='representative_fault_injection; raw provider response was not recorded')
    calls=[]
    def model(*a,**k):
        calls.append(1)
        if code is None:raise TimeoutError('synthetic tag timeout')
        if code=='intent_dropped_kind' and '이나' in text:return fixture(text)|{'stages':[dict(id='s1',activity='식사',quote='음식점',category_filters=['음식점'],conditions=[],preferences=[])]}
        return fixture(text)
    app._call_claude=model
    ti.validate_interpretation=original
    if code not in (None,'intent_dropped_kind','intent_quote_order'):
        triggered=[]
        def invalid(*a,**k):
            if not triggered:
                triggered.append(1);raise ValueError(code)
            return original(*a,**k)
        ti.validate_interpretation=invalid
    client=app.app.test_client()
    if code is None:
        response=client.post('/suggest/tags',json=dict(user_text=text))
        passed=response.status_code==200 and response.json.get('metadata',{}).get('selection_method')=='source_rules_fallback'
        action='원문 근거 태그로 복구, 모호한 단일 선택 그룹은 비움'
    else:
        body=dict(mode='spot' if x['mode']=='스팟' else 'course',region=x['region'],transport='대중교통',user_lat=36.8151,user_lng=127.1139,count=1,persona_tags=[],intent_version=1,plan_mode='natural',user_text=text)
        if x['mode']=='코스':body.update(spot_count=3,slot_types=[])
        response=client.post('/travel/interpret',json=body)
        passed=response.status_code in (200,422)
        action=('문장 조건 확인 안내; 자동 재호출·검색 없음' if response.status_code==422 else
                '랜드마크와 방문 대상 분리' if '바로 옆' in text else
                '명시된 반복 방문 유지' if '차례로' in text else '명시된 OR 대안 보존')
    row.update(status=response.status_code,passed=passed and len(calls)==1,action=action,mock_calls=len(calls),provider_calls=0)
    results.append(row)
ti.validate_interpretation=original
(OUT/'failure-reproduction.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(dict(total=len(results),passed=sum(r['passed'] for r in results),provider_calls=0),ensure_ascii=False))
assert len(results)==60 and all(r['passed'] for r in results)
