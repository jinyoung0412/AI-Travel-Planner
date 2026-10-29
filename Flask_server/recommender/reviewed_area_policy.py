"""Reviewed tourism areas for comparing alternative courses, never venue identity.

The official city pages describe Sinjeong Lake's themed parks/gardens as one
lake tourism area. This does not establish that the two catalog entries are the
same venue. Only these reviewed records participate; proximity or a shared word
alone cannot group another attraction, restaurant, cafe, or branch.
"""
import math

from place_identity import normalize, text

POLICY_VERSION = 'reviewed_tourism_areas_20261026_v1'
REVIEWED_AREAS = ({
    'id': 'sinjeong_lake_park_area',
    'label': '신정호 호수 관광 권역',
    'reviewed_on': '2026-10-26',
    'basis': 'same_tourism_area_not_same_venue',
    'sources': (
        'https://asan.go.kr/sinjungho/node/?menu=010200',
        'https://www.asan.go.kr/mayor/news/view.php?a_no=10&cate=news&pds_no=2025042206564332065',
    ),
    'members': (
        {'place_id': 'local:v1:14055d1f43be7c1b7f31671c91cb974aba5d06c566997a6a6d4c666de4783f61',
         'name': '신정호테마공원', 'region': '아산', 'category': '테마공원',
         'latitude': 36.77425907, 'longitude': 126.9720945},
        {'place_id': 'local:v1:1abe0edd9438aa184546eeb647dbcb296e4928707ddc056f753a5d769101173a',
         'name': '아산신정호지방정원', 'region': '아산', 'category': '도시,테마공원',
         'latitude': 36.7694169, 'longitude': 126.9784959},
    ),
},)
# Accommodate normal coordinate serialization rounding (roughly one metre),
# not relocation. Changed catalog coordinates require a new review.
COORDINATE_TOLERANCE_DEGREES = .00001


def reviewed_area(record):
    for area in REVIEWED_AREAS:
        for member in area['members']:
            if (text(record.get('place_id')) != member['place_id'] or
                    normalize(record.get('가게명')) != normalize(member['name']) or
                    text(record.get('지역')) != member['region'] or
                    normalize(record.get('카테고리')) != normalize(member['category'])):
                continue
            try:
                matches = all(not isinstance(record.get(axis), bool) and
                              math.isfinite(float(record[axis])) and
                              abs(float(record[axis]) - member[axis]) <= COORDINATE_TOLERANCE_DEGREES
                              for axis in ('latitude', 'longitude'))
            except (KeyError, TypeError, ValueError, OverflowError):
                matches = False
            if matches:
                return area
    return None


def comparison_key(record, exact_key):
    area = reviewed_area(record)
    return ('reviewed_area', area['id']) if area else ('exact_visit', exact_key)


def applied_areas(courses):
    found = {}
    for course in courses:
        for record in course:
            area = reviewed_area(record)
            if area:
                entry = found.setdefault(area['id'], {'id': area['id'], 'label': area['label'],
                    'basis': area['basis'], 'place_ids': set()})
                entry['place_ids'].add(record['place_id'])
    return [{**entry, 'place_ids': sorted(entry['place_ids'])} for _, entry in sorted(found.items())]
