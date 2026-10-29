"""Tourism-area overlap is soft course variety, not a place-identity merge."""
import copy

import pandas as pd
import pytest

import app
import travel_intent as ti
from recommendation_ai import search_courses
from Flask_server.recommender import course_variety as cv
from Flask_server.recommender import reviewed_area_policy as ap
from Flask_server.recommender.visits import visit_key, visit_groups


def parks():
    addresses = ['충남 아산시 점양동 산5', '충남 아산시 방축동 526-7']
    return [dict(place_id=m['place_id'], 가게명=m['name'], 지역=m['region'], 카테고리=m['category'],
                 주소=address, latitude=m['latitude'], longitude=m['longitude'], 방문자수=100, 블로그수=0)
            for m, address in zip(ap.REVIEWED_AREAS[0]['members'], addresses)]


def test_reviewed_members_share_area_but_keep_distinct_visit_identities():
    a, b = parks()
    assert ap.reviewed_area(a)['id'] == ap.reviewed_area(b)['id']
    assert visit_key(a) != visit_key(b)
    groups = visit_groups(pd.DataFrame([a,b]))
    assert groups[a['place_id']] != groups[b['place_id']]


@pytest.mark.parametrize('change', [
    {'place_id':'unreviewed-id'}, {'가게명':'신정호테마공원 카페'}, {'지역':'천안'},
    {'카테고리':'카페'}, {'latitude':36.775}, {'longitude':126.98},
    {'latitude':None}, {'latitude':float('nan')}, {'latitude':True},
])
def test_identity_name_region_purpose_and_coordinate_guards_fail_closed(change):
    row = {**parks()[0], **change}
    assert ap.reviewed_area(row) is None


def test_coordinate_serialization_rounding_is_not_relocation():
    row = parks()[0]
    row.update(latitude=round(row['latitude'],6),longitude=round(row['longitude'],6))
    assert ap.reviewed_area(row) is not None


def options():
    a,b=parks()
    other=[dict(place_id=pid,가게명=pid,주소='충남 아산시 테스트로 '+str(i+1),지역='아산',
                카테고리='한식' if pid.startswith('food') else '카페',latitude=36.77,longitude=126.98)
           for i,pid in enumerate(['food0','food1','cafe0','cafe1'])]
    rows=[a,b,*other]; byid={r['place_id']:r for r in rows}
    choices=[(.10,('food0',a['place_id'],'cafe0')),
             (.11,('food0',b['place_id'],'cafe1')),
             (.13,('food1',b['place_id'],'cafe1'))]
    complete={ids:(cost,[byid[pid] for pid in ids]) for cost,ids in choices}
    return complete, visit_groups(pd.DataFrame(rows))


def test_selection_does_not_count_neighbouring_park_label_as_an_extra_changed_visit():
    complete, groups=options()
    before=copy.deepcopy(complete)
    selected=cv.select(complete,2,0,groups)
    assert [c[0]['place_id'] for c in selected] == ['food0','food1']
    assert complete==before
    metadata=cv.course_summary(selected,groups)
    assert metadata['comparison_basis']=='reviewed_tourism_areas_and_exact_visits'
    assert metadata['max_shared_visits']==1
    assert metadata['similar_pair_count']==0
    assert metadata['reviewed_area_groups'][0]['place_ids']==sorted(p['place_id'] for p in parks())


def test_unavoidable_area_overlap_is_disclosed_even_when_place_ids_differ():
    complete,groups=options()
    constrained=dict(list(complete.items())[:2])
    selected=cv.select(constrained,2,0,groups)
    metadata=cv.course_summary(selected,groups)
    assert len(selected)==2
    assert metadata['exact_max_shared_visits']==1
    assert metadata['exact_similar_pair_count']==0
    assert metadata['max_shared_visits']==2
    assert metadata['similar_pair_count']==1


def test_same_course_may_visit_two_distinct_places_in_one_area():
    rows=pd.DataFrame(parks())
    courses, metadata=search_courses(rows,[['공원'],['공원']],[],app.filter_keywords,
                                   n=1,start=(36.76979,126.95182))
    assert len(courses)==1
    assert {p['place_id'] for p in courses[0]}==set(rows.place_id)
    assert metadata['slot_candidate_counts']==[2,2]
    assert metadata['constraints_relaxed']==[]


def test_intent_and_rules_share_the_area_comparison_definition():
    complete,groups=options()
    paths=[v[1] for v in list(complete.values())[:2]]
    pools=[]
    for i in range(3):
        byid={p[i]['place_id']:p[i] for p in paths}
        pools.append([{'row':r,'public':{'place_id':pid}} for pid,r in byid.items()])
    choices=[[{'place_id':r['place_id']} for r in path] for path in paths]
    intent=ti.selection_diversity(choices,pools)
    rule=cv.course_summary(paths,groups)
    assert intent==rule
