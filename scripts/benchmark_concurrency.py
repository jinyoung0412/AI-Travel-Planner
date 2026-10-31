"""Offline full-DB single and four-client benchmark; provider requests are blocked."""
import sys,time,json,cProfile,pstats,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.offline_environment import install
install()
import app
import travel_intent as ti
app._call_claude=lambda *a,**kw: (_ for _ in ()).throw(TimeoutError('offline selection'))
text='연인과 100일 기념 데이트'
# Context-only fixed interpretation, real DB/ranking/course engine.
raw=dict(schema_version=1,companion=dict(value='연인과',quote='연인과'),stages=[],exclusions=[],ambiguities=[dict(quote=text,reason='방문 활동 선택')],unsupported=[],requested_visit_count=None)
original=app._call_claude
app._call_claude=lambda system,*a,**kw:raw if system!=ti.SELECTION_SYSTEM else original(system,*a,**kw)
body=dict(mode='course',user_text=text,region='천안',transport='대중교통',user_lat=36.8100,user_lng=127.1463,count=1,spot_count=3,slot_types=['음식','자연·산책','카페'],persona_tags=['연인과','기념일'],seed=42,randomize=True,intent_version=1,plan_mode='manual',accept_unverified=False)
def run(i):
 b=dict(body,seed=42+i);client=app.app.test_client();r=client.post('/travel/interpret',json=b)
 assert r.status_code==200,r.json
 b['intent_token']=r.json['intent_token'];start=time.monotonic();r=client.post('/recommend/course',json=b)
 return dict(status=r.status_code,seconds=round(time.monotonic()-start,3),reason=r.json.get('reason'),error=r.json.get('error'),courses=len(r.json.get('courses',[])))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--profile',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'local_artifacts/concurrency-benchmark');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 results={}
 if args.profile:
  prof=cProfile.Profile();prof.enable();results['single']=[run(0)];prof.disable()
  with (args.output/(args.label+'-profile.txt')).open('w') as out:pstats.Stats(prof,stream=out).sort_stats('cumulative').print_stats(45)
 else:results['single']=[run(0)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results['four_simultaneous']=list(pool.map(run,range(4)))
 (args.output/(args.label+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))
