"""Literal context grounding must retain exclusions and calendar boundaries."""
import pytest

from category_policy import directly_excluded
from intent_context import (TAG_SIGNALS, context_only, grounded_tags,
                            positive_context_matches, source_preferences)


def tags(text, proposed=('기념일', '생일')):
    return grounded_tags(proposed, text, directly_excluded)


@pytest.mark.parametrize('text', [
    '기념일 아니고 평소 밥집', '기념일 말고 저렴하고 빠른 식사',
    '기념일이 아니라 평소 식사', '기념일은 제외하고 식사',
    '기념일 분위기 말고 편한 식사', '기념일인 곳 말고',
    '여자친구랑 기념관', '전쟁기념관을 방문', '기념품 구경',
    '기념사진 찍기', '5일 동안 여행', '15일 여행', '10월 28일 식사',
    '100일 동안 여행', '100일간 여행', '100일 여행 일정',
])
def test_nonoccasion_or_excluded_occasion_does_not_ground_tag(text):
    assert tags(text) == []


@pytest.mark.parametrize('text', [
    '여자친구랑 100일기념 식당', '여친이랑 100일 데이트',
    '200일', '1000일', '1100일', '1주년', '10주년', '백일', '천일',
    '기념일 식사', '결혼 기념으로 식당',
])
def test_explicit_anniversary_labels_remain_supported(text):
    assert tags(text) == ['기념일']


@pytest.mark.parametrize('text,expected', [
    ('기념일 아니고 생일 식사', ['생일']),
    ('생일 말고 기념일 식사', ['기념일']),
    ('기념일 말고 생일, 다음에는 기념일 식사', ['기념일', '생일']),
    ('100일은 아니고 200일 기념', ['기념일']),
    ('생일도 기념일도 아니고 평소 식사', []),
])
def test_each_explicit_positive_mention_keeps_its_own_scope(text, expected):
    assert tags(text) == expected


@pytest.mark.parametrize('text,expected', [
    ('여자친구랑 데이트', ['연인과']),
    ('여자   친구와 친구들이 함께', ['친구와', '연인과']),
    ('여자친구 말고 친구와 식사', ['친구와']),
    ('친구 말고 남친이랑 식사', ['연인과']),
])
def test_friend_signal_inside_couple_label_is_not_independent(text, expected):
    assert tags(text, ('친구와', '연인과')) == expected


@pytest.mark.parametrize('text,expected', [
    ('조용한 곳 말고 활기찬 데이트', ['lively']),
    ('조용한 카페는 싫고 활기찬 곳', ['lively']),
    ('안 조용한 곳을 원해', []),
    ('조용하지 않은 곳', []),
    ('로맨틱한 분위기 말고 여유로운 데이트', ['relaxed']),
    ('여유 말고 활기찬 곳, 다음에는 조용한 카페', ['quiet', 'lively']),
    ('조용한 카페와 로맨틱한 식사', ['quiet', 'romantic']),
])
def test_source_preferences_use_only_positive_literal_evidence(text, expected):
    preferences = source_preferences(text)
    assert [p['field'] for p in preferences] == expected
    assert [p['id'] for p in preferences] == [f's1.p{i + 1}' for i in range(len(preferences))]
    assert all(p['quote'] in text for p in preferences)


def test_reusable_helper_returns_original_spans_and_skips_excluded_occurrence():
    text = '기념일 말고 생일, 다음 기념일은 함께'
    matches = positive_context_matches(text, TAG_SIGNALS['기념일'])
    assert [m.group() for m in matches] == ['기념일']
    assert matches[0].start() == text.rfind('기념일')


@pytest.mark.parametrize('text', [
    '기념일 아니고', '조용한 곳 말고', '5일 동안 여행', '100일간 여행',
])
def test_grounding_does_not_expand_context_only_model_bypass(text):
    assert not context_only(text)
