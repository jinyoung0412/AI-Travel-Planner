import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Flask_server'))


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    import socket
    import httpx
    import requests
    def fail(*args, **kwargs):
        raise AssertionError('External API calls are forbidden in offline tests')
    monkeypatch.setattr(requests.sessions.Session, 'request', fail)
    monkeypatch.setattr(httpx.Client, 'send', fail)
    monkeypatch.setattr(httpx.AsyncClient, 'send', fail)
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket.socket, 'connect_ex', fail)
    import app
    monkeypatch.setattr(app, '_call_claude', fail)


@pytest.fixture
def places():
    import pandas as pd
    return pd.DataFrame([{
        '가게명': f'장소{i}', '주소': f'충남 천안시 테스트로 {i + 1}',
        'latitude': 36.8151 + i * .0001, 'longitude': 127.1139,
        '카테고리': ['한식', '공원', '카페'][i % 3], 'search_category': '관광',
        '방문자수': i, '블로그수': 0, 'blog_tags': '{}', 'Cluster': i % 2,
    } for i in range(60)])
