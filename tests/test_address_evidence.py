import json
from pathlib import Path

import pandas as pd
import pytest

from blog_evidence import verify_post
from place_identity import ensure_ids
from Preprocess.RunPreprocess.build_database import merge_verified_tags
from Preprocess.RunPreprocess.collect_blog_tags import collect_place_tags

CASES = json.loads((Path(__file__).parent / 'fixtures/address_cases.json').read_text())
PLACE = {'가게명': '아지트', '주소': '충남 천안시 중앙로 10'}


@pytest.mark.parametrize('case', CASES, ids=[c['label'] for c in CASES])
def test_complete_address_identity(case):
    post = {'url': 'https://blog.naver.com/reviewer/1', 'name_excerpt': '아지트 후기',
            'address_excerpt': case['address'], 'tags': ['wrong-place']}
    assert verify_post(PLACE, post) is case['matches']


@pytest.mark.parametrize('case', CASES, ids=[c['label'] for c in CASES])
def test_mocked_collection_to_database_uses_same_address_rule(case, monkeypatch):
    import Preprocess.RunPreprocess.collect_blog_tags as collector
    place = ensure_ids(pd.DataFrame([PLACE])).iloc[0].to_dict()
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'items': [{'link': 'https://blog.naver.com/reviewer/1'}]}
        text = ('<div class="se-main-container"><p>아지트 후기</p><p>' + case['address'] +
                '</p></div><script>var gsTagName = "source-tag";</script>')
    monkeypatch.setenv('NAVER_API_ID', 'mock')
    monkeypatch.setenv('NAVER_API_SECRET', 'mock')
    monkeypatch.setattr(collector.requests, 'get', lambda *a, **kw: Response())
    result = collect_place_tags(place, delay=0)
    merged, _ = merge_verified_tags(pd.DataFrame([place]), pd.DataFrame([{
        'place_id': place['place_id'], **result}]))
    assert (result['blog_tag_status'] == 'verified') is case['matches']
    assert json.loads(merged.iloc[0]['blog_tags']) == ({'source-tag': 1} if case['matches'] else {})


def test_mixed_post_evidence_keeps_valid_post_and_quarantines_wrong_road():
    place = ensure_ids(pd.DataFrame([PLACE])).iloc[0].to_dict()
    base = {'url': 'https://blog.naver.com/reviewer/1', 'name_excerpt': '아지트 후기',
            'address_excerpt': '천안시 중앙로 10', 'tags': ['right']}
    wrong = {**base, 'url': 'https://blog.naver.com/reviewer/2',
             'address_excerpt': '천안시 서부중앙로 10', 'tags': ['wrong']}
    result, quarantine = merge_verified_tags(pd.DataFrame([place]), pd.DataFrame([{
        'place_id': place['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([base, wrong])}]))
    assert json.loads(result.iloc[0]['verified_posts']) == [base]
    assert json.loads(result.iloc[0]['blog_tags']) == {'right': 1}
    assert len(quarantine) == 1
    assert quarantine.iloc[0]['quarantine_reason'] == 'partially_invalid_post_evidence'
