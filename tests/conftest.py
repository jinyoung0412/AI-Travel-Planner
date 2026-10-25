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
