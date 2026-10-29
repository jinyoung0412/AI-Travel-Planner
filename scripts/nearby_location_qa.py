"""Independent QA: real ephemeral Node→Flask HTTP, frozen read-only DB, no providers.
Run after nearby_location_qa_test.dart with NEARBY_QA_EXPORT=true.
"""
import hashlib
import json
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.offline_environment import install, allow_gateway_loopback
install()
allow_gateway_loopback()
import app
from flask import request
from werkzeug.serving import make_server

OUT = ROOT / 'local_artifacts/nearby_qa/2026-10-27'
DB = ROOT / 'Flask_server/places.db'
PILOT = ROOT / 'Preprocess/pilots/homonym_5.json'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    frozen = {str(p.relative_to(ROOT)): digest(p) for p in (DB, PILOT)}
    assert frozen['Flask_server/places.db'] == '6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be'
    assert frozen['Preprocess/pilots/homonym_5.json'] == '3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa'
    assert json.loads(PILOT.read_text())['collection_authorized_now'] is False
    def forbidden(*args, **kwargs):
        raise AssertionError('외부 모델 호출 금지')
    app._call_claude = forbidden
    seen = []
    @app.app.before_request
    def capture():
        seen.append({'path': request.path, 'body': request.get_json(silent=True)})
    server = make_server('127.0.0.1', 0, app.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    gateway = None
    cases = []
    try:
        # offline_environment's Node preload blocks dotenv and all non-loopback TCP.
        source = '''
const {createApp}=require('./NodeJs_server/server');
const {createRequire}=require('node:module');
const axios=createRequire(require('node:path').resolve('NodeJs_server/server.js'))('axios');
const base=process.argv[1];
const httpClient={post(url,...args){
  if(!url.startsWith(base+'/'))throw Error('외부 호출 금지');
  return axios.post(url,...args);
},get(){throw Error('외부 호출 금지');}};
const server=createApp({httpClient,env:{FLASK_BASE_URL:base,KAKAO_API_KEY:''}})
.listen(0,'127.0.0.1',()=>console.log(JSON.stringify({port:server.address().port})));
'''
        gateway = subprocess.Popen(['node', '-e', source, f'http://127.0.0.1:{server.server_port}'],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as sel:
            sel.register(gateway.stdout, selectors.EVENT_READ)
            assert sel.select(15), '독립 게이트웨이 기동 실패'
            port = json.loads(gateway.stdout.readline())['port']
        opener = build_opener(ProxyHandler({}))
        def post(mode, body):
            path = f'/recommend/{mode}'
            req = Request(f'http://127.0.0.1:{port}{path}',
                data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type':'application/json'})
            try:
                response = opener.open(req, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                status, envelope = response.status, json.load(response)
            assert seen[-1] == {'path':path, 'body':body}, 'Flask 실제 수신 본문 불일치'
            return status, envelope.get('data', envelope.get('error', envelope))
        with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as conn:
            regions = dict(conn.execute('SELECT 지역,COUNT(*) FROM places GROUP BY 지역').fetchall())
            lookup = {r[0]: r[1:] for r in conn.execute('SELECT place_id,지역,latitude,longitude FROM places')}
        ui = json.loads((OUT/'ui_cases.json').read_text())
        unique = {}
        for case in ui:
            if 'body' not in case: continue
            b = case['body']
            # One representative per real origin/mode/transport, deterministic seed.
            b = {**b, 'seed': 42}
            key = (case['mode'], b['user_lat'], b['user_lng'], b['region'], b['transport'])
            unique.setdefault(key, {**case, 'body':b})
        for case in unique.values():
            mode,b = case['mode'],case['body']
            status,data = post(mode,b)
            assert status in (200,422)
            assert data.get('reason') != 'outside_service_area'
            places = data.get('places',[]) if mode=='spot' else [p for c in data.get('courses',[]) for p in c]
            radius = app.RADIUS_KM[b['transport']]
            distances=[]
            unsupported=[]
            for p in places:
                actual_region,lat,lng=lookup[p['place_id']]
                if actual_region not in ('천안','아산'):
                    unsupported.append({**p,'db_region':actual_region})
                assert p['lat']==lat and p['lng']==lng
                distance=float(app.distances_from((b['user_lat'],b['user_lng']),[[lat,lng]])[0])
                assert distance<=radius+1e-8
                distances.append(distance)
            cases.append({'id':case['id'],'mode':mode,'kind':'real_gateway_frozen_db',
                'expected':'Flask 수신 좌표/지역/교통 일치; 유효 범위 및 거리 필터',
                'status':'KNOWN_DEFECT' if unsupported else 'PASS','unsupported_region_places':unsupported,
                'http_status':status,'request':b,'flask_received':seen[-1],
                'returned_places':len(places),'place_ids':[p['place_id'] for p in places],
                'max_origin_distance_km':max(distances,default=None),'radius_km':radius,
                'response_metadata':data.get('metadata',{})})
        for mode in ('spot','course'):
            base={'user_lat':36.8151,'user_lng':127.1139,'region':'내 주변','transport':'대중교통',
                'persona_tags':['친구와'],'count':3,'seed':42}
            if mode=='course': base.update(spot_count=3,slot_types=['음식','자연·산책','카페'])
            for name,patch,expected,reason in [
                ('남 외부',{'user_lat':36.549999},422,'outside_service_area'),
                ('북 외부',{'user_lat':37.050001},422,'outside_service_area'),
                ('서 외부',{'user_lng':126.799999},422,'outside_service_area'),
                ('동 외부',{'user_lng':127.350001},422,'outside_service_area'),
                ('서울 외부',{'user_lat':37.5},422,'outside_service_area'),
                ('위도 누락',{'user_lat':None},400,'invalid_request'),
                ('위도 NaN 문자열',{'user_lat':'NaN'},400,'invalid_request'),
                ('경도 무한 문자열',{'user_lng':'Infinity'},400,'invalid_request'),
                ('위도 범위',{'user_lat':91},400,'invalid_request'),
                ('경도 범위',{'user_lng':-181},400,'invalid_request'),
                ('bool 좌표',{'user_lat':True},400,'invalid_request'),
                ('지원하지 않는 지역',{'region':'공주'},400,'invalid_request'),
                ('지원하지 않는 이동수단',{'transport':'도보'},400,'invalid_request'),
            ]:
                body={**base,**patch}; status,data=post(mode,body)
                assert status==expected and data['reason']==reason,(name,status,data)
                cases.append({'id':f'{mode}-{name}','kind':'real_gateway_validation','status':'PASS',
                    'expected':{'http_status':expected,'reason':reason},
                    'actual':{'http_status':status,'reason':data['reason']},'flask_received':seen[-1]})
            for region in ('천안','아산'):
                b={**base,'region':region,'transport':'차','user_lat':36.8151 if region=='천안' else 36.7898,
                    'user_lng':127.1139 if region=='천안' else 127.0043}
                status,data=post(mode,b); assert status==200
                places=data.get('places',[]) if mode=='spot' else [p for c in data['courses'] for p in c]
                assert all(lookup[p['place_id']][0]==region for p in places)
                cases.append({'id':f'{mode}-manual-{region}','kind':'real_gateway_region_filter',
                    'status':'PASS','http_status':status,'request':b,'returned_places':len(places)})
        result={'method':'isolated real HTTP Node→Flask, providers blocked, frozen DB read only',
            'ports':{'node':port,'flask':server.server_port},'cases':cases,'db_regions':regions,
            'flask_received_count':len(seen),'hashes_before':frozen}
    finally:
        if gateway:
            gateway.terminate(); gateway.communicate(timeout=10)
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        after={str(p.relative_to(ROOT)):digest(p) for p in (DB,PILOT)}
        assert frozen==after,'원본 데이터 해시 변경'
    result['hashes_after']=after
    (OUT/'http_cases.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'executed':len(cases),'passed':sum(c['status']=='PASS' for c in cases),
        'known_defect_cases':sum(c['status']=='KNOWN_DEFECT' for c in cases),'real_http_flask_received':len(seen),'data_preserved':True},ensure_ascii=False))
if __name__=='__main__': main()
