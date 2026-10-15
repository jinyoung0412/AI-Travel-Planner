"""Regression coverage for safe stage dispatch and offline audit entry points."""
import sys

import pytest

import run_data_prep
from scripts import check_offline


@pytest.mark.parametrize('args', [[], ['--check']])
def test_stage_check_never_dispatches(monkeypatch, args):
    monkeypatch.setattr(sys, 'argv', ['run_data_prep.py', *args])
    monkeypatch.setattr(run_data_prep.subprocess, 'run', lambda *a, **k: pytest.fail('dispatched'))
    run_data_prep.main()


@pytest.mark.parametrize('args', [['--stgae', 'crawl'], ['--check', '--stage', 'crawl']])
def test_invalid_stage_options_are_errors(monkeypatch, args):
    monkeypatch.setattr(sys, 'argv', ['run_data_prep.py', *args])
    with pytest.raises(SystemExit) as error:
        run_data_prep.main()
    assert error.value.code == 2


def test_stage_arguments_and_root_are_preserved(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['run_data_prep.py', '--stage', 'build', '--db', 'copy.db'])
    calls = []
    monkeypatch.setattr(run_data_prep.subprocess, 'run', lambda *a, **k: calls.append((a, k)))
    run_data_prep.main()
    assert calls == [(([sys.executable, str(run_data_prep.STAGES['build']), '--db', 'copy.db'],),
                      {'cwd': run_data_prep.ROOT, 'check': True})]


def test_python_checks_do_not_dispatch_collection_or_mutation():
    commands = list(check_offline.commands('python', 'flutter'))
    assert commands
    assert not any('--apply' in command or '--stage' in command for command, _ in commands)
    assert all(cwd == check_offline.ROOT for _, cwd in commands)


def test_offline_http_clients_are_blocked():
    import httpx
    import requests
    for request in (lambda: httpx.get('https://example.com'), lambda: requests.get('https://example.com')):
        with pytest.raises(AssertionError, match='forbidden'):
            request()


@pytest.mark.parametrize('alias', ['direct', 'symlink', 'hardlink'])
def test_audit_output_cannot_overwrite_source_database(tmp_path, alias):
    from scripts.validate_real_db import validate_output_path
    source = tmp_path / 'places.db'
    source.write_bytes(b'preserved database')
    output = tmp_path / 'report.json'
    if alias == 'direct':
        output = source
    elif alias == 'symlink':
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    with pytest.raises(ValueError, match='source database'):
        validate_output_path(output, [source])
    assert source.read_bytes() == b'preserved database'
