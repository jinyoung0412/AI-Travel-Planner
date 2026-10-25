"""Compatibility API for offline recommendation scoring and ordered-slot search.

Implementation lives in recommender/{scoring,geometry,search}. Existing Flask,
validation-script and standalone imports keep their names and call signatures.
"""
import sys
from pathlib import Path

# Direct execution of Flask_server/app.py needs the shared root identity module.
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from Flask_server.recommender.constants import (FOOD_CATS, CAFE_CATS, ACTIVITY_CATS,
                                               SLOT_CATEGORY_MAP, RADIUS_KM)
from Flask_server.recommender.scoring import add_scores
from Flask_server.recommender.geometry import distances_from, route_metrics, greedy_tsp
from Flask_server.recommender.search import search_courses


def generate_from_slots(df, slot_types, blog_tag_keywords, filter_fn, n=3,
                        start=None, transport='대중교통', seed=0):
    categories = [SLOT_CATEGORY_MAP.get(slot, []) for slot in slot_types]
    return search_courses(df, categories, blog_tag_keywords, filter_fn, n, start, transport, seed)[0]


def fixed_categories(spots):
    if spots not in (3, 4, 5):
        raise ValueError('spot_count는 3~5이어야 합니다.')
    return [FOOD_CATS, ACTIVITY_CATS, CAFE_CATS, ACTIVITY_CATS, FOOD_CATS][:spots]


def generate_fixed_courses(df, blog_tag_keywords, filter_fn, n=3, spots=5,
                           start=None, transport='대중교통', seed=0):
    return search_courses(df, fixed_categories(spots), blog_tag_keywords, filter_fn,
                          n, start, transport, seed)[0]


def find_best_for_plan(df, stops, filter_fn, start=None):
    tags = list(dict.fromkeys(t for stop in stops for t in stop.get('blog_tag_keywords', [])))
    courses, _ = search_courses(df, [s['category_filters'] for s in stops], tags, filter_fn, 1, start)
    return courses[0] if courses else []


def select_courses(clustered, stops, filter_fn, top_n=3, start=None):
    tags = list(dict.fromkeys(t for s in stops for t in s.get('blog_tag_keywords', [])))
    courses, _ = search_courses(clustered, [s['category_filters'] for s in stops], tags,
                               filter_fn, top_n, start)
    return [{'course': c, 'total_score': sum(p['score'] for p in c)} for c in courses]
