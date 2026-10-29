"""Purpose must survive candidate caps, AI ordering and rule fallbacks."""
import copy
import json

import pandas as pd
import pytest

import app
import travel_intent as intent
import selection_wire
from recommendation_context import apply_context, build_context, context_cost, resolve_generic_meal_ambiguities
from recommender import spot_quality
from recommender.constants import FOOD_CATS
from recommendation_ai import add_scores
from test_travel_intent import BASE, frame, plan, stage, choice


def meals():
    result = frame(('분식', '햄버거', '한식', '일식당', '양식', '카페', '공원'))
    result['방문자수'] = [100000, 90000, 100, 300, 500, 2000, 500]
    result['origin_distance_km'] = .3
    return result


def test_celebration_meal_beats_popular_fast_food_without_claiming_ambience():
    data = dict(BASE, user_text='여자친구랑 100일기념 식당')
    annotated, metadata = apply_context(meals(), build_context(data))
    scored = add_scores(annotated, [])
    ranked = spot_quality.rank(scored[scored['카테고리'].ne('카페') & scored['카테고리'].ne('공원')], '대중교통')
    assert ranked.iloc[0]['카테고리'] not in ('분식', '햄버거')
    assert metadata['purposes'] == ['기념일']
    assert metadata['venue_ambience_verified'] is False
    assert metadata['deprioritized_candidate_count'] == 2
    assert len(annotated) == len(meals())  # Lower priority, not a hidden exclusion.


@pytest.mark.parametrize('text', ['친구랑 밥 먹을 식당', '혼자 식당', '기념일 아니고 평소 식당', '기념관 보고 식당', '5일 동안 여행하며 식당'])
def test_ordinary_negative_and_landmark_contexts_do_not_trigger_celebration(text):
    result, metadata = apply_context(meals(), build_context(dict(BASE, user_text=text)))
    assert not metadata['celebration_dining']
    assert result['_request_context_cost'].sum() == 0


def test_explicit_casual_food_and_manual_occasion_are_preserved():
    data = dict(BASE, user_text='생일에 분식 식당', persona_tags=[])
    result, _ = apply_context(meals(), build_context(data, explicit_categories=['분식']))
    assert context_cost(result.iloc[0]) == 0
    manual = build_context(dict(BASE, user_text='', persona_tags=['연인과', '기념일']))
    assert manual['celebration_dining'] and manual['companion'] == '연인과'
    assert build_context(dict(BASE, user_text='여자친구랑 식당'))['celebration_dining'] is False


def test_manual_companion_and_mood_override_do_not_resurrect_sentence_context():
    context = build_context(dict(BASE, user_text='여자친구랑 로맨틱한 식당',
        persona_tags=['혼자', '활동적인']), dict(companion=dict(value='혼자', source='manual')))
    assert context['companion'] == '혼자'
    assert '연인과' not in context['tags'] and '로맨틱한' not in context['tags']
    assert not context['celebration_dining']


@pytest.mark.parametrize('text', ['100일 기념 저렴하고 빠른 식당', '생일에 간단하게 먹을 식당', '기념일 가성비 식당'])
def test_casual_meal_request_overrides_default_celebration_preference(text):
    result, context = apply_context(meals(), build_context(dict(BASE, user_text=text)))
    assert context['casual_meal_requested'] and result['_request_context_cost'].sum() == 0


def test_explicit_food_is_scoped_to_its_stage_instead_of_every_meal():
    p = plan([stage('분식', ['분식']), stage('식당', FOOD_CATS)])
    context = build_context(dict(BASE, user_text='100일 기념 분식 먹고 식당'), p, ['분식', '식당'])
    annotated, _ = apply_context(meals(), context)
    casual = annotated.iloc[0].to_dict()
    assert context_cost(casual, 's1') == 0
    assert context_cost(casual, 's2') == 1
    assert intent.candidate_record(casual, p['stages'][0], intent.DATA_VERSION)['context_category_cost'] == 0
    assert intent.candidate_record(casual, p['stages'][1], intent.DATA_VERSION)['context_category_cost'] == 1


def test_explicit_menu_alternative_is_not_demoted_by_default_occasion():
    p = plan([stage('떡볶이나 파스타 식당', ['분식', '파스타'])])
    context = build_context(dict(BASE, user_text='생일에 떡볶이나 파스타 식당'), p, ['파스타', '식당'])
    row = dict(카테고리='분식,떡볶이')
    annotated, _ = apply_context(pd.DataFrame([row]), context)
    assert context_cost(annotated.iloc[0], 's1') == 0


@pytest.mark.parametrize('quote,reason,resolved', [
    ('식당', '구체적인 음식 종류가 명시되지 않았습니다.', True),
    ('평소에 먹을 식당', '음식 종류를 지정하지 않아 구체 범위 확인 필요', True),
    ('식당', '음식 종류와 예산 확인 필요', False),
    ('식당', '음식 종류와 채식 여부 확인 필요', False),
    ('식당', '음식 종류와 반려견 동반 여부 확인 필요', False),
    ('식당', '음식 종류와 포장 가능 여부 확인 필요', False),
    ('식당', '구체적인 음식 종류가 명시되지 않았습니다. 한식, 고기, 양식 등 선택이 필요합니다.', True),
    ('평소에 먹을 식당', '음식 종류(한식, 양식, 중식 등)를 지정하지 않아 구체 범위 확인 필요', True),
    ('예약 가능한 식당', '음식 종류와 예약 확인 필요', False),
    ('알레르기 없는 식당', '알레르기 확인 필요', False),
])
def test_only_redundant_cuisine_question_is_removed(quote, reason, resolved):
    p = plan([stage('식당', FOOD_CATS)])
    p['ambiguities'] = [dict(quote=quote, reason=reason)]
    assert bool(resolve_generic_meal_ambiguities(p)['ambiguities']) is not resolved


def test_context_cost_survives_course_rescoring_and_matches_quality_validator():
    annotated, _ = apply_context(meals(), build_context(dict(BASE, user_text='100일 기념 식당')))
    scored = add_scores(annotated, [])
    p = plan([stage('식당', FOOD_CATS), stage('카페', ['카페']), stage('공원', ['공원'])])
    rows = scored.to_dict('records')
    pools = [[dict(row=row, public=intent.candidate_record(row, s, intent.DATA_VERSION))
              for row in rows if app.category_matches(row['카테고리'], s['category_filters'])] for s in p['stages']]
    start = (BASE['user_lat'], BASE['user_lng'])
    selected, metadata = intent.course_rule_selection(pools, p, 1, start, '대중교통')
    costs = intent.selection_costs(selected, pools, start, '대중교통')
    assert selected[0][0]['place_id'] not in set(scored.iloc[:2]['place_id'])
    assert costs[0] <= metadata['quality_limit'] + 1e-9
    # Explicit selection of the penalized venue must have a worse real cost,
    # even though it has many more reviews and the engine recalculates scores.
    casual = copy.deepcopy(selected)
    casual[0][0] = choice(pools[0][0]['public'], 's1')
    assert intent.selection_costs(casual, pools, start, '대중교통')[0] > costs[0]


def test_same_place_can_have_different_context_cost_in_two_meal_stages():
    p = plan([stage('분식', ['분식']), stage('식당', FOOD_CATS), stage('카페', ['카페'])])
    context = build_context(dict(BASE, user_text='100일 기념 분식 먹고 식당 다음 카페'), p, ['분식', '식당', '카페'])
    annotated, _ = apply_context(meals(), context)
    scored = add_scores(annotated, [])
    rows = scored.to_dict('records')
    pools = [[dict(row=row, public=intent.candidate_record(row, s, intent.DATA_VERSION))
              for row in rows if app.category_matches(row['카테고리'], s['category_filters'])] for s in p['stages']]
    start = (BASE['user_lat'], BASE['user_lng'])
    selected, metadata = intent.course_rule_selection(pools, p, 1, start, '대중교통')
    by_id = scored.set_index('place_id')['카테고리'].to_dict()
    assert by_id[selected[0][0]['place_id']] == '분식'
    assert by_id[selected[0][1]['place_id']] not in ('분식', '햄버거')
    assert intent.selection_costs(selected, pools, start, '대중교통')[0] <= metadata['quality_limit'] + 1e-9


@pytest.mark.parametrize('fail_model', [False, True])
def test_request_context_reaches_model_and_first_spot_survives_reverse_ai_or_timeout(monkeypatch, fail_model):
    monkeypatch.setattr(app, 'get_df', lambda _: meals())
    payloads = []
    raw = plan([stage('식당', FOOD_CATS)], companion=dict(value='연인과', quote='여자친구'))
    def model(system, message, **kwargs):
        payload = json.loads(message)
        if system != intent.SELECTION_SYSTEM:
            return copy.deepcopy(raw)
        payloads.append(payload)
        if fail_model:
            raise TimeoutError()
        # A hostile rank order still cannot promote downranked casual kinds.
        return selection_wire.expand({'order': list(reversed(range(payload['expected_count'])))}, payload)
    monkeypatch.setattr(app, '_call_claude', model)
    data = dict(BASE, user_text='여자친구랑 100일기념 식당', count=5, randomize=True, seed=17)
    response = app.app.test_client().post('/recommend/spot', json=data)
    assert response.status_code == 200, response.json
    body = response.json
    assert len(body['places']) == 5
    assert body['places'][0]['category'] not in ('분식', '햄버거')
    assert body['places'][-1]['category'] in ('분식', '햄버거')
    assert payloads[0]['request_context']['purposes'] == ['기념일']
    assert payloads[0]['request_context']['companion'] == '연인과'
    compact = json.loads(selection_wire.prepare(payloads[0])[1])
    assert compact['request_context']['purposes'] == ['기념일']
    assert 'user_lat' not in compact and 'source_text' not in compact
    assert all(not p['travel_explanation']['satisfied_conditions'] or
               p['travel_explanation']['satisfied_conditions'] == ['장소 종류'] for p in body['places'])
    assert body['metadata']['selection_method'] == ('rules_fallback' if fail_model else 'ai_candidates')


def test_manual_tags_use_same_context_policy_and_spots_are_ranked_not_tsp(monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: meals())
    data = dict(BASE, user_text='', persona_tags=['기념일', '맛집 탐방'], count=5, randomize=False)
    data.pop('intent_version')
    response = app.app.test_client().post('/recommend/spot', json=data)
    assert response.status_code == 200, response.json
    assert response.json['places'][0]['category'] not in ('분식', '햄버거')
    assert response.json['metadata']['display_order'] == 'rule_quality_order'
