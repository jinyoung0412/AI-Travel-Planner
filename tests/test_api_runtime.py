"""Exercise SDK construction and bounded retry/parse behavior without vendor calls."""
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import httpx
import pytest

import runtime_llm


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setattr(runtime_llm, '_claude', None)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('LLM_TIMEOUT_SECONDS', raising=False)
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('External model HTTP forbidden'))


def response(text='{"tags": ["혼자"]}', stop_reason='end_turn'):
    return SimpleNamespace(content=[SimpleNamespace(type='text', text=text)], stop_reason=stop_reason)


def test_missing_key_never_constructs_sdk(monkeypatch):
    factory = Mock(side_effect=AssertionError('No SDK without key'))
    monkeypatch.setattr(anthropic, 'Anthropic', factory)
    with pytest.raises(RuntimeError):
        runtime_llm.call_claude('system', 'user')
    factory.assert_not_called()


def test_sdk_has_explicit_timeout_and_no_hidden_retries(monkeypatch):
    client = SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=response())))
    factory = Mock(return_value=client)
    monkeypatch.setattr(anthropic, 'Anthropic', factory)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'mock-key')
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', '3')
    assert runtime_llm.call_claude('system', 'user') == {'tags': ['혼자']}
    runtime_llm.call_claude('system2', 'user2')
    factory.assert_called_once()
    options = factory.call_args.kwargs
    assert options['max_retries'] == 0
    assert options['timeout'].read == 3
    assert options['timeout'].connect == 2
    assert client.messages.create.call_args.kwargs['messages'] == [{'role': 'user', 'content': 'user2'}]


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'inf', '11', 'bad'])
def test_invalid_timeout_fails_before_sdk_call(monkeypatch, value):
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError):
        runtime_llm.call_claude('system', 'user')


@pytest.mark.parametrize('text,stop_reason', [('[]', 'end_turn'), ('{bad', 'end_turn'),
    ('{"tags":[]}', 'max_tokens'), ('prose ```json\n{}\n```', 'end_turn')])
def test_invalid_output_or_truncation_is_not_retried(monkeypatch, text, stop_reason):
    create = Mock(return_value=response(text, stop_reason))
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(ValueError):
        runtime_llm.call_claude('s', 'u')
    assert create.call_count == 1


def test_complete_json_code_fence_is_supported(monkeypatch):
    create = Mock(return_value=response('```json\n{"tags": []}\n```'))
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert runtime_llm.call_claude('s', 'u') == {'tags': []}


@pytest.mark.parametrize('status,expected_calls', [(401, 1), (400, 1), (429, 2), (500, 2), (503, 2)])
def test_only_transient_sdk_errors_are_retried_with_a_hard_attempt_cap(monkeypatch, status, expected_calls):
    error = anthropic.APIStatusError('private upstream response', response=httpx.Response(status,
        request=httpx.Request('POST', 'https://mock.invalid')), body=None)
    create = Mock(side_effect=error)
    sleeps = Mock()
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(runtime_llm.time, 'sleep', sleeps)
    with pytest.raises(anthropic.APIStatusError):
        runtime_llm.call_claude('s', 'u', max_retries=100)
    assert create.call_count == expected_calls
    assert sleeps.call_count == expected_calls - 1


def test_timeout_retries_once_then_succeeds(monkeypatch):
    create = Mock(side_effect=[anthropic.APITimeoutError(request=httpx.Request('POST', 'https://mock.invalid')), response()])
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(runtime_llm.time, 'sleep', Mock())
    assert runtime_llm.call_claude('s', 'u') == {'tags': ['혼자']}
    assert create.call_count == 2


@pytest.mark.parametrize('attempts', [0, -1, True, '2'])
def test_invalid_attempt_count_does_not_enter_retry_loop(attempts):
    with pytest.raises(ValueError):
        runtime_llm.call_claude('s', 'u', max_retries=attempts)


@pytest.mark.parametrize('override,expected', [(None, [4, 8, 4]), ('3', [3, 3, 3]), ('10', [10, 10, 10])])
def test_selection_timeout_is_per_request_on_cached_client_and_respects_override(monkeypatch, override, expected):
    create = Mock(return_value=response())
    factory = Mock(return_value=SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(anthropic, 'Anthropic', factory)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'mock-key')
    if override is not None:
        monkeypatch.setenv('LLM_TIMEOUT_SECONDS', override)
    runtime_llm.call_claude('interpret', 'u', max_retries=1)
    runtime_llm.call_claude('select', 'u', max_retries=1, timeout_seconds=8)
    runtime_llm.call_claude('interpret', 'u', max_retries=1)
    factory.assert_called_once()
    assert factory.call_args.kwargs['max_retries'] == 0
    assert [call.kwargs['timeout'].read for call in create.call_args_list] == expected
    assert all(call.kwargs['timeout'].connect == 2 for call in create.call_args_list)


def test_selection_timeout_keeps_ten_second_cap_and_single_attempt(monkeypatch):
    create = Mock(side_effect=anthropic.APITimeoutError(request=httpx.Request('POST', 'https://mock.invalid')))
    monkeypatch.setattr(runtime_llm, '_claude', SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(ValueError):
        runtime_llm.call_claude('s', 'u', max_retries=1, timeout_seconds=11)
    create.assert_not_called()
    with pytest.raises(anthropic.APITimeoutError):
        runtime_llm.call_claude('s', 'u', max_retries=1, timeout_seconds=8)
    assert create.call_count == 1
