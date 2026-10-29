"""A companion/mood-only request must use public activity purposes."""
import pandas as pd
import app
from place_identity import ensure_ids


def test_no_category_does_not_recommend_lodging_or_retail(monkeypatch):
    rows=ensure_ids(pd.DataFrame([dict(가게명=f'장소{i}',주소=f'충남 천안시 시험로 {i+1}',
        지역='천안',카테고리=kind,latitude=36.8151,longitude=127.1139,
        방문자수=count,블로그수=0,blog_tags='{}') for i,(kind,count) in enumerate([
            ('호텔',1000000),('모텔',900000),('펜션',800000),('소품샵',700000),
            ('카페',600000),('공원',10),('박물관',9),('볼링장',8),('공방',7)])]))
    monkeypatch.setattr(app,'get_df',lambda _:rows)
    r=app.app.test_client().post('/recommend/spot',json=dict(user_lat=36.8151,
        user_lng=127.1139,region='천안',transport='대중교통',count=10,
        persona_tags=['연인과','로맨틱한']))
    assert r.status_code==200,r.json
    assert {p['category'] for p in r.json['places']}=={'공원','박물관','볼링장','공방'}
    assert r.json['metadata']['constraints_relaxed']==[]
    assert r.json['metadata']['preference_evidence']=='unavailable'
