import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Flask_server'))

# Install before importing pytest fixtures or collecting application modules.
from scripts.offline_environment import install
install()

import pytest

pytest_plugins = ['scripts.offline_pytest']


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    # The process-wide transport boundary is installed during collection and
    # remains in place after monkeypatch undoes per-test HTTP/SDK fakes.
    from scripts.offline_environment import forbidden
    import app
    monkeypatch.setattr(app, '_call_claude', forbidden)


@pytest.fixture
def places():
    import pandas as pd
    return pd.DataFrame([{
        '가게명': f'장소{i}', '주소': f'충남 천안시 테스트로 {i + 1}',
        'latitude': 36.8151 + i * .0001, 'longitude': 127.1139,
        '카테고리': ['한식', '공원', '카페'][i % 3], 'search_category': '관광',
        '방문자수': i, '블로그수': 0, 'blog_tags': '{}', 'Cluster': i % 2,
    } for i in range(60)])


# Tests that read the crawled place database (not redistributed; see README
# "데이터 준비") or the frozen pilot manifest derived from it. They skip, rather
# than fail, when those local-only files are absent. Behaviour is unchanged when
# the files are present.
_PLACES_DB = ROOT / 'Flask_server/places.db'
_PILOT_MANIFEST = ROOT / 'Preprocess/pilots/homonym_5.json'
_NEEDS_LOCAL_DATA = {
    'test_spot_diversity.py::test_frozen_db_station_cafe_variety_and_repeatability',
    'test_nearby_location_qa.py::test_nearby_excludes_unsupported_regions_from_frozen_db',
    'test_recommendation_review.py::test_spot_and_course_exclude_flagged_identity_without_renaming',
    'test_recommendation_review.py::test_real_db_holds_only_unresolved_subfacility_and_preserves_parent',
    'test_recommendation_review.py::test_hold_only_candidates_report_a_real_shortage',
    'test_recommendation_review.py::test_hold_is_not_an_address_wide_or_name_wide_block',
    'test_cafe_purpose_boundary.py::test_frozen_db_exact_original_actual_tags_and_manual_cafe_boundary',
    'test_qa_recommendation_quality.py::test_frozen_database_quality_is_readonly_and_qa_park_is_blocked',
    'test_beer_intent.py::test_real_database_beer_recommendation_preserves_db_and_evidence',
    'test_api_boundary.py::test_real_database_read_leaves_bytes_unchanged',
    'test_activity_policy.py::test_real_db_eight_outdoor_shops_are_filtered_without_db_mutation',
}


def pytest_collection_modifyitems(config, items):
    if _PLACES_DB.exists() and _PILOT_MANIFEST.exists():
        return
    skip = pytest.mark.skip(reason='places.db not present; see README 데이터 준비')
    for item in items:
        base = item.nodeid.split('::', 1)
        if len(base) == 2:
            key = Path(base[0]).name + '::' + base[1].split('[')[0]
            if key in _NEEDS_LOCAL_DATA:
                item.add_marker(skip)
