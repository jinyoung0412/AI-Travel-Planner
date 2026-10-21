"""Use fake sentinels only; never inspect the user's dotenv or credentials."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.offline_environment import ROOT, clean_environment, redact

SENTINEL = 'offline-fake-credential-79241'


def run_probe(code, tmp_path, *, bootstrap=True, pytest_args=None):
    env = clean_environment(os.environ, tmp_path)
    if not bootstrap:
        # Prove ordinary pytest/conftest startup independently of sitecustomize.
        env.pop('PYTHONPATH')
        env.pop('PYTHON_DOTENV_DISABLED')
    env.update({key: SENTINEL for key in (
        'ANTHROPIC_API_KEY', 'KAKAO_API_KEY', 'NAVER_API_ID', 'NAVER_API_SECRET',
        'UNRELATED_PRIVATE_SETTING', 'HTTP_PROXY', 'PLACES_DB_PATH',
        'ANTHROPIC_MODEL', 'LLM_TIMEOUT_SECONDS', 'TRAVEL_DATA_DIR')})
    path = tmp_path / 'probe.py'
    path.write_text(code)
    if pytest_args is None:
        command = [sys.executable, str(path)]
    else:
        command = [sys.executable, '-m', 'pytest', '-c', str(ROOT / 'pytest.ini'),
                   '-p', 'scripts.offline_pytest', *pytest_args, str(path)]
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=60)


def test_environment_is_an_allowlist_not_a_known_key_denylist(tmp_path):
    env = clean_environment({'PATH': '/usr/bin', 'NEW_PROVIDER_CREDENTIAL': SENTINEL,
                             'PYTEST_ADDOPTS': '--showlocals', 'PYTHONSTARTUP': SENTINEL,
                             'NODE_OPTIONS': SENTINEL, 'HOME': SENTINEL}, tmp_path)
    assert SENTINEL not in json.dumps(env)
    assert env['HOME'] == str(tmp_path)
    assert env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'


@pytest.mark.parametrize('reload_module', [False, True])
def test_dotenv_never_opens_a_file_or_overwrites_explicit_fakes(tmp_path, monkeypatch, reload_module):
    import dotenv
    import dotenv.main
    if reload_module:
        importlib.reload(dotenv.main)
        importlib.reload(dotenv)
    path = tmp_path / '.env'
    path.write_text('NAVER_API_SECRET=' + SENTINEL + '\nOTHER_SECRET=' + SENTINEL)
    before = path.read_bytes()
    monkeypatch.setenv('NAVER_API_SECRET', 'explicit-fake')
    monkeypatch.delenv('OTHER_SECRET', raising=False)
    import builtins
    original = builtins.open

    def no_open(file, *args, **kwargs):
        if str(file) == str(path):
            pytest.fail('dotenv tried to read the sentinel file')
        return original(file, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, 'open', no_open)
        guard.setenv('PYTHON_DOTENV_DISABLED', '0')
        assert dotenv.load_dotenv(path, override=True) is False
        assert dotenv.main.load_dotenv(path, override=True) is False
        assert dotenv.dotenv_values(path) == {}
        assert dotenv.main.DotEnv(path).dict() == {}
        assert list(dotenv.main.DotEnv(path).parse()) == []
    assert os.environ['NAVER_API_SECRET'] == 'explicit-fake'
    assert 'OTHER_SECRET' not in os.environ
    assert path.read_bytes() == before


@pytest.mark.parametrize('bootstrap', [False, True])
def test_collection_is_clean_before_importing_app(tmp_path, bootstrap):
    result = run_probe('''
import os
assert 'UNRELATED_PRIVATE_SETTING' not in os.environ
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'HTTP_PROXY' not in os.environ
import app, runtime_llm
assert app.DB_PATH.endswith('Flask_server/places.db')
assert runtime_llm.MODEL == 'claude-haiku-4-5-20251001'
def test_collected(): pass
''', tmp_path, bootstrap=bootstrap, pytest_args=['-q'])
    assert result.returncode == 0, result.stdout + result.stderr


def test_subprocess_and_spawn_install_boundary_before_target_imports(tmp_path):
    result = run_probe('''
import os, multiprocessing, socket
import dotenv
assert 'UNRELATED_PRIVATE_SETTING' not in os.environ
assert dotenv.load_dotenv('/does-not-exist', override=True) is False
def probe():
    assert 'NAVER_API_SECRET' not in os.environ
    try: socket.create_connection(('203.0.113.1', 443))
    except AssertionError: pass
    else: raise AssertionError('transport was not blocked')
if __name__ == '__main__':
    probe()
    child = multiprocessing.get_context('spawn').Process(target=probe)
    child.start()
    child.join(15)
    if child.is_alive():
        child.terminate()
        child.join(5)
        raise AssertionError('spawn hung')
    assert child.exitcode == 0
''', tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_explicit_fake_key_and_sdk_remain_usable(monkeypatch):
    from types import SimpleNamespace
    import anthropic
    import runtime_llm
    monkeypatch.setenv('ANTHROPIC_API_KEY', SENTINEL)
    monkeypatch.setattr(runtime_llm, '_claude', None)
    seen = []

    def factory(**kwargs):
        seen.append(kwargs['api_key'])
        return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw:
            SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(text='{}', type='text')])))

    monkeypatch.setattr(anthropic, 'Anthropic', factory)
    assert runtime_llm.call_claude('fake system', 'fake user') == {}
    assert seen == [SENTINEL]


def test_normal_python_dotenv_loading_is_unchanged(tmp_path):
    path = tmp_path / '.env'
    path.write_text('OFFLINE_FAKE_RUNTIME=' + SENTINEL)
    env = {'PATH': os.defpath, 'HOME': str(tmp_path)}
    result = subprocess.run([sys.executable, '-c',
        "import dotenv, os, sys; assert dotenv.load_dotenv(sys.argv[1]); "
        "assert os.environ['OFFLINE_FAKE_RUNTIME'] == sys.argv[2]", str(path), SENTINEL],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, 'Normal runtime dotenv behavior changed'


@pytest.mark.parametrize('transport', ['requests', 'httpx', 'async_httpx', 'socket', 'udp'])
def test_unmocked_transports_stay_blocked_with_fake_keys(transport, monkeypatch):
    import asyncio
    import socket
    import requests
    import httpx
    monkeypatch.setenv('ANTHROPIC_API_KEY', SENTINEL)
    headers = {'Authorization': 'Bearer ' + SENTINEL}
    with pytest.raises(AssertionError, match='forbidden'):
        if transport == 'requests':
            requests.get('https://example.invalid', headers=headers)
        elif transport == 'httpx':
            httpx.get('https://example.invalid', headers=headers)
        elif transport == 'async_httpx':
            async def request():
                async with httpx.AsyncClient() as client:
                    await client.get('https://example.invalid', headers=headers)
            asyncio.run(request())
        else:
            with socket.socket(type=socket.SOCK_DGRAM if transport == 'udp' else socket.SOCK_STREAM) as sock:
                if transport == 'udp':
                    sock.sendto(b'fake', ('203.0.113.1', 443))
                else:
                    sock.connect(('203.0.113.1', 443))


@pytest.mark.parametrize('method,args', [
    ('getaddrinfo', ('example.invalid', 443)), ('gethostbyname', ('example.invalid',)),
    ('gethostbyname_ex', ('example.invalid',)), ('gethostbyaddr', ('203.0.113.1',)),
    ('getnameinfo', (('203.0.113.1', 443), 0)),
])
def test_dns_cannot_bypass_transport_boundary(method, args):
    import socket
    with pytest.raises(AssertionError, match='forbidden'):
        getattr(socket, method)(*args)


def test_gateway_reverse_lookup_is_local_and_external_lookup_stays_blocked(monkeypatch):
    import socket
    from scripts.offline_environment import allow_gateway_loopback
    # Keep this script-only exception scoped to the probe.
    for target, name in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                         (socket, 'getaddrinfo'), (socket, 'gethostbyaddr')):
        monkeypatch.setattr(target, name, getattr(target, name))
    allow_gateway_loopback()
    assert socket.getfqdn('127.0.0.1') == 'localhost'
    with pytest.raises(AssertionError, match='forbidden'):
        socket.gethostbyaddr('203.0.113.1')
    with pytest.raises(AssertionError, match='forbidden'):
        socket.getaddrinfo('example.invalid', 443)


def test_failed_pytest_reports_redact_headers_logs_and_environment(tmp_path):
    # The inner test deliberately fails; inspect captured output without ever
    # forwarding it to the tool/user, even if this regression itself fails.
    result = run_probe('''
import logging, os
def test_failure():
    secret = 'offline-' + 'fake-credential-79241'
    os.environ['NAVER_API_SECRET'] = secret
    logging.warning('Authorization: Bearer %s', secret)
    print({'X-Naver-Client-Id': secret, 'X-Naver-Client-Secret': secret})
    raise RuntimeError(dict(os.environ))
''', tmp_path, pytest_args=['-q', '--showlocals', '--junitxml=' + str(tmp_path / 'result.xml')])
    outputs = result.stdout + result.stderr + (tmp_path / 'result.xml').read_text()
    assert result.returncode == 1
    assert SENTINEL not in outputs, 'Fake credential leaked in captured pytest output'
    assert '[REDACTED]' in outputs


def test_contextual_redaction_does_not_need_environment_values():
    text = repr({'Authorization': 'Bearer ' + SENTINEL, 'X-Naver-Client-Id': SENTINEL,
                 'X-Naver-Client-Secret': SENTINEL, 'ANTHROPIC_API_KEY': SENTINEL})
    assert SENTINEL not in redact(text)


@pytest.mark.parametrize('phase', ['collection', 'setup', 'teardown'])
def test_failure_phase_outputs_are_redacted(tmp_path, phase):
    common = '''
import os, pytest, logging
os.environ['NAVER_API_SECRET'] = 'offline-' + 'fake-credential-79241'
def fail():
    try:
        raise RuntimeError({'Authorization': 'Bearer ' + os.environ['NAVER_API_SECRET']})
    except RuntimeError:
        logging.exception('fake request failure')
        raise
'''
    code = common + {
        'collection': 'fail()\n',
        'setup': '@pytest.fixture(autouse=True)\ndef boundary(): fail()\ndef test_probe(): pass\n',
        'teardown': '@pytest.fixture(autouse=True)\ndef boundary():\n    yield\n    fail()\ndef test_probe(): pass\n',
    }[phase]
    result = run_probe(code, tmp_path, pytest_args=['-q', '--log-cli-level=WARNING',
        '--junitxml=' + str(tmp_path / 'result.xml')])
    outputs = result.stdout + result.stderr + (tmp_path / 'result.xml').read_text()
    assert result.returncode in (1, 2)
    assert SENTINEL not in outputs, 'Fake credential leaked from failure phase'
    assert '[REDACTED]' in outputs


def test_node_boundary_blocks_dotenv_and_external_transport(tmp_path):
    import shutil
    if not shutil.which('node'):
        pytest.skip('Node is not installed')
    env = clean_environment(os.environ, tmp_path)
    source = '''
const assert = require('node:assert/strict');
assert.deepEqual(require('dotenv').config({path: process.argv[1]}), {parsed:{}});
assert.throws(() => require('node:net').connect(443, '203.0.113.1'), /forbidden/);
assert.throws(() => require('node:dns').lookup('example.invalid', () => {}), /forbidden/);
'''
    dotenv = tmp_path / '.env'
    dotenv.write_text('NAVER_API_SECRET=' + SENTINEL)
    result = subprocess.run(['node', '-e', source, str(dotenv)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, 'Node offline boundary probe failed'
