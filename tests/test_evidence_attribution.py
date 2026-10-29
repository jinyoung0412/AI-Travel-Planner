"""Place-level tag review is separate from a post mentioning a place."""
import json

import pandas as pd
import pytest

from blog_evidence import reviewed_tags_post, tags_from_posts, verify_post
from place_identity import ensure_ids
from Preprocess.RunPreprocess import collect_blog_tags as collector
from Preprocess.RunPreprocess.build_database import merge_verified_tags

PLACES = [
    {'가게명': '가람카페', '주소': '충남 천안시 시험로 12'},
    {'가게명': '나무카페', '주소': '충남 아산시 샘길 34'},
]
POST = {'url': 'https://blog.naver.com/synthetic/123',
        'name_excerpt': '가람카페, 나무카페 방문기',
        'address_excerpt': '충남 천안시 시험로 12\n충남 아산시 샘길 34',
        'tags': ['조용한', '아이와함께']}


def test_two_place_article_mentions_both_but_cannot_share_whole_post_tags():
    for place in PLACES:
        assert verify_post(place, POST)
        assert tags_from_posts(place, [POST]) == ({}, [])
    first = reviewed_tags_post(PLACES[0], POST, ['조용한'])
    second = reviewed_tags_post(PLACES[1], POST, ['아이와함께'])
    assert tags_from_posts(PLACES[0], [first, second])[0] == {'조용한': 1}
    assert tags_from_posts(PLACES[1], [first, second])[0] == {'아이와함께': 1}


@pytest.mark.parametrize('changed', [
    {'tags': ['아이와함께']}, {'url': 'https://blog.naver.com/synthetic/999'},
    {'tag_review': {'scope': 'place_reviewed'}},
])
def test_review_cannot_move_to_different_tags_or_post(changed):
    reviewed = reviewed_tags_post(PLACES[0], POST, ['조용한'])
    assert tags_from_posts(PLACES[0], [{**reviewed, **changed}]) == ({}, [])


@pytest.mark.parametrize('mutation', ['append', 'slice'])
def test_in_place_tag_mutation_cannot_change_recorded_approval(mutation):
    reviewed = reviewed_tags_post(PLACES[0], POST, ['조용한'])
    if mutation == 'append':
        reviewed['tags'].append('힐링')
    else:
        reviewed['tags'][:] = ['아이와함께']
    assert reviewed['tag_review']['approved_tags'] == ['조용한']
    assert tags_from_posts(PLACES[0], [reviewed]) == ({}, [])


def test_raw_collection_preserves_identity_and_tags_in_audit_without_publishing(monkeypatch):
    place = ensure_ids(pd.DataFrame([PLACES[0]])).iloc[0].to_dict()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([POST['url']], 'synthetic'))
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: dict(POST))
    result = collector.collect_with_audit(place, delay=0)
    assert result['record'] == {'blog_tags': '{}', 'verified_posts': '[]', 'blog_tag_status': 'needs_review'}
    assert result['audit']['identity_accepted'] == 1
    assert result['audit']['tag_review_pending'] == 1
    assert result['audit']['posts'][0]['tags'] == POST['tags']
    # Normal resume neither retries already fetched URLs nor loses review data.
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: pytest.fail('unexpected refetch'))
    resumed = collector.collect_with_audit(place, previous=result['audit'], delay=0)
    assert resumed['audit']['posts'] == result['audit']['posts']


def test_legacy_verified_flag_without_place_review_is_quarantined():
    places = ensure_ids(pd.DataFrame(PLACES))
    proof = pd.DataFrame([{'place_id': places.iloc[0]['place_id'], 'blog_tag_status': 'verified',
                          'verified_posts': json.dumps([POST]), 'blog_tags': '{"조용한":99}'}])
    result, quarantine = merge_verified_tags(places, proof)
    assert result['blog_tags'].eq('{}').all()
    assert result['blog_tag_status'].ne('verified').all()
    assert len(quarantine) == 1
    assert json.loads(quarantine.iloc[0]['verified_posts']) == [POST]
