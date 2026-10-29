"""Exercise the actual provider boundary, not only the app's model stub."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import runtime_llm
import selection_wire as wire
import travel_intent as intent
from test_travel_intent import frame, plan, stage


def fixture(stages=1, count=10):
    p = plan([stage('카페', ['카페']) for _ in range(stages)])
    rows = frame(('카페',) * 30).to_dict('records')
    pools = []
    for i, s in enumerate(p['stages']):
        candidates = []
        for row in rows[i * (30 // stages):(i + 1) * (30 // stages)]:
            row['origin_distance_km'] = .5
            public = intent.candidate_record(row, s, intent.DATA_VERSION)
            public['unverified_condition_ids'] = [s['id'] + ':p1']
            candidates.append(dict(row=row, public=public))
        pools.append(candidates)
    references = [[n % len(pool) for pool in pools] for n in range(count)]
    payload = dict(mode='spot' if stages == 1 else 'course', count=count,
                   expected_count=count, selection_seed=1,
                   stages=[dict(id=s['id'], category_filters=s['category_filters'], preferences=['quiet'])
                           for s in p['stages']],
                   candidates=[[r['public'] for r in pool] for pool in pools],
                   reference_indices=references)
    return payload, pools, p


def test_compact_provider_roundtrip_preserves_exact_evidence_and_unknown_conditions(monkeypatch):
    payload, pools, p = fixture()
    original = copy.deepcopy(payload)
    response = SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(
        type='text', text=json.dumps({'order': list(range(payload['expected_count']))}))])
    create = Mock(return_value=response)
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.delenv('LLM_TIMEOUT_SECONDS', raising=False)
    result = runtime_llm.call_claude(intent.SELECTION_SYSTEM, intent.encoded(payload),
                                   max_tokens=512, max_retries=1, timeout_seconds=8,
                                   compact_selection=True)
    assert intent.validate_selection(result, pools, p, 10, 'spot', expected=10) == result['courses']
    assert payload == original
    options = create.call_args.kwargs
    message = options['messages'][0]['content']
    assert options['max_tokens'] == 512 and options['timeout'].read == 8
    assert 'local:v1:' not in message and 'evidence_refs' not in message
    assert len(message.encode()) < len(intent.encoded(payload).encode()) / 2
    assert len(json.dumps({'order': list(range(payload['expected_count']))})) < len(intent.encoded(result)) / 10
    assert result['courses'][0][0]['unverified_condition_ids'] == ['s1:p1']
    assert result['courses'][0][0]['satisfied_condition_ids'] == []
    result['courses'][0][0]['unverified_condition_ids'].clear()
    assert payload == original


@pytest.mark.parametrize('index', [-1, 30, True, False, 1.0, '0', None, {}, []])
def test_foreign_or_malformed_candidate_reference_is_rejected(index):
    payload, _, _ = fixture(count=1)
    with pytest.raises(ValueError, match='selection_identity'):
        wire.expand({'order': [index]}, payload)


@pytest.mark.parametrize('result', [{}, {'order': [], 'claims': []}, {'order': []},
                                   {'order': [[0]]}, {'order': 0}])
def test_invalid_shape_or_count_is_rejected(result):
    payload, _, _ = fixture(count=1)
    with pytest.raises(ValueError):
        wire.expand(result, payload)


def test_duplicate_choices_still_fail_existing_validator():
    payload, pools, p = fixture(count=2)
    with pytest.raises(ValueError, match='selection_identity'):
        wire.expand({'order': [0, 0]}, payload)


def test_stage_local_indices_restore_only_that_stages_candidate():
    payload, pools, p = fixture(stages=3, count=3)
    result = wire.expand({'order': [2, 0, 1]}, payload)
    intent.validate_selection(result, pools, p, 3, 'course', expected=3)
    assert result['courses'][0][1]['place_id'] == pools[1][2]['public']['place_id']
    compact = json.loads(wire.prepare(payload)[1])
    assert len({r['place'] for item in compact['recommendations'] for r in item['visits']}) == 9
    assert [item['index'] for item in compact['recommendations']] == [0, 1, 2]


def test_shared_identity_across_stages_keeps_same_local_place_key():
    payload, _, _ = fixture(stages=3, count=1)
    payload['candidates'][1][0] = copy.deepcopy(payload['candidates'][0][0])
    compact = json.loads(wire.prepare(payload)[1])
    assert compact['recommendations'][0]['visits'][0]['place'] == compact['recommendations'][0]['visits'][1]['place']


def test_worst_size_output_is_small_and_full_contract_stays_bounded():
    payload, _, _ = fixture(stages=5, count=10)
    result = {'order': list(range(payload['expected_count']))}
    assert len(intent.encoded(payload).encode()) < 36000
    assert len(intent.encoded(wire.expand(result, payload)).encode()) < 24000
    assert len(json.dumps(result)) < 512


def test_model_cannot_replace_validated_route_or_claim_new_evidence():
    payload, _, _ = fixture(stages=3, count=1)
    for extra in [{'courses': [[0, 1, 2]]}, {'evidence_refs': ['invented']},
                  {'satisfied_condition_ids': ['quiet']}]:
        with pytest.raises(ValueError, match='intent_schema'):
            wire.expand({'order': [0], **extra}, payload)
