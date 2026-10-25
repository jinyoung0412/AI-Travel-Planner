"""Fake-only regressions for INT-01/02/03; no vendor, DNS or SDK calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.offline_environment import ROOT, clean_environment


def node(source, temporary, *, esm=False, offline=True):
    if not shutil.which('node'):
        pytest.skip('Node executable is required')
    env = clean_environment(os.environ, temporary)
    if not offline:
        env.pop('NODE_OPTIONS')
    result = subprocess.run(['node', *(['--input-type=module'] if esm else []), '-e', source],
                            cwd=temporary, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, 'Fake-only Node boundary regression failed: ' + result.stderr
    return result.stdout


@pytest.mark.parametrize('entry', ['bare', 'resolved', 'config', 'subpath'])
@pytest.mark.parametrize('esm', [False, True])
def test_dotenv_is_replaced_before_module_evaluation(tmp_path, entry, esm):
    package = tmp_path / 'node_modules/dotenv'
    (package / 'lib').mkdir(parents=True)
    (package / 'package.json').write_text(json.dumps({'name': 'dotenv', 'main': 'lib/main.js',
        'exports': {'.': './lib/main.js', './config': './config.js', './lib/main.js': './lib/main.js'}}))
    # Any evaluation, including ESM loading a CJS package, is already a failure.
    for path in (package / 'lib/main.js', package / 'config.js'):
        path.write_text("throw new Error('dotenv implementation was evaluated');")
    fake = tmp_path / 'fake.env'
    fake.write_text('INT_FAKE_VALUE=fake-only-value\n')
    target = {'bare': 'dotenv', 'resolved': (package / 'lib/main.js').as_uri() if esm
              else str(package / 'lib/main.js'), 'config': 'dotenv/config',
              'subpath': 'dotenv/lib/main.js'}[entry]
    cjs_target = f'require.resolve({json.dumps(target)})' if entry == 'resolved' else json.dumps(target)
    imported = (f"import dotenv, {{config, parse}} from {json.dumps(target)};"
                if esm else f"const dotenv = require({cjs_target}); const {{config, parse}} = dotenv;")
    source = imported + f'''
const assert = {"(await import('node:assert/strict')).default" if esm else "require('node:assert/strict')"};
assert.deepEqual(config({{path: {json.dumps(str(fake))}}}), {{parsed: {{}}}});
assert.deepEqual(parse('INT_FAKE_VALUE=fake-only-value'), {{}});
assert.equal(process.env.INT_FAKE_VALUE, undefined);
console.log('dotenv guarded before evaluation');
'''
    assert 'dotenv guarded before evaluation' in node(source, tmp_path, esm=esm)
    assert fake.read_text() == 'INT_FAKE_VALUE=fake-only-value\n'


def test_esm_dynamic_file_url_query_is_guarded(tmp_path):
    package = tmp_path / 'node_modules/dotenv/lib'
    package.mkdir(parents=True)
    module = package / 'main.js'
    module.write_text("throw new Error('dotenv implementation was evaluated');")
    source = f'''(async () => {{
const {{default: dotenv}} = await import({json.dumps(module.as_uri() + '?probe=1#fragment')});
require('node:assert/strict').deepEqual(dotenv.config(), {{parsed: {{}}}});
console.log('dynamic import guarded');
}})().catch(() => {{process.exitCode = 1;}});'''
    assert 'dynamic import guarded' in node(source, tmp_path)


def test_normal_node_process_keeps_dotenv_behavior(tmp_path):
    fake = tmp_path / 'fake.env'
    fake.write_text('INT_FAKE_VALUE=fake-only-value\n')
    source = f'''
const {{createRequire}} = require('node:module');
const load = createRequire({json.dumps(str(ROOT / 'NodeJs_server/server.js'))});
load('dotenv').config({{path: {json.dumps(str(fake))}, quiet:true}});
require('node:assert/strict').equal(process.env.INT_FAKE_VALUE, 'fake-only-value');
console.log('normal dotenv retained');
'''
    assert 'normal dotenv retained' in node(source, tmp_path, offline=False)


@pytest.mark.parametrize('esm', [False, True])
def test_installed_dotenv_realpath_alias_is_guarded(tmp_path, esm):
    alias = tmp_path / 'aliased-module.js'
    alias.symlink_to(ROOT / 'NodeJs_server/node_modules/dotenv/lib/main.js')
    fake = tmp_path / 'fake.env'
    fake.write_text('INT_FAKE_VALUE=fake-only-value\n')
    imported = (f"import dotenv from {json.dumps(alias.as_uri())};" if esm else
                f"const dotenv = require({json.dumps(str(alias))});")
    source = imported + f'''
const assert = {"(await import('node:assert/strict')).default" if esm else "require('node:assert/strict')"};
assert.deepEqual(dotenv.config({{path: {json.dumps(str(fake))}, quiet:true}}), {{parsed:{{}}}});
assert.equal(process.env.INT_FAKE_VALUE, undefined);
console.log('installed alias guarded');
'''
    assert 'installed alias guarded' in node(source, tmp_path, esm=esm)


def test_default_and_custom_callback_promise_dns_never_reach_native_queries(tmp_path):
    source = r'''
const assert = require('node:assert/strict');
const dns = require('node:dns');
const promises = require('node:dns/promises');
// Replace ALL native channel query methods before invoking any DNS API.
// No c-ares query function may run, even if a regression removes the guards.
const proto = process.binding('cares_wrap').ChannelWrap.prototype;
let dispatches = 0;
for (const key of Object.getOwnPropertyNames(proto)) {
  if (/^query|^getHostByAddr$/.test(key)) proto[key] = () => {dispatches++; return 0;};
}
assert.ok(Object.getOwnPropertyNames(proto).includes('queryA'));
let checked = 0;
for (const [label, api] of [ ['default callback', dns], ['custom callback', new dns.Resolver()],
    ['default promise', promises], ['custom promise', new promises.Resolver()] ]) {
  const names = new Set([...Object.keys(api), ...Object.getOwnPropertyNames(Object.getPrototypeOf(api))]);
  for (const name of names) {
    if ((/^resolve/.test(name) || name === 'reverse') && typeof api[name] === 'function') {
      const args = name === 'resolve' ? ['offline-probe.invalid', 'A'] :
        [name === 'reverse' ? '203.0.113.1' : 'offline-probe.invalid'];
      if (label.includes('callback')) args.push(() => {});
      assert.throws(() => api[name](...args), /forbidden/, label + ':' + name);
      checked++;
    }
  }
}
// getnameinfo is separate from c-ares queries. Establish the shared guard
// identity before calling it, so a missing guard cannot invoke native DNS.
for (const api of [dns, promises]) {
  assert.equal(api.lookupService, api.resolve4);
  assert.throws(() => api.lookupService('203.0.113.1', 443, () => {}), /forbidden/);
}
assert.equal(dispatches, 0);
assert.ok(checked >= 40);
require('node:fs').writeSync(1, JSON.stringify({checked, native_dispatches:dispatches}));
'''
    result = json.loads(node(source, tmp_path))
    assert result['native_dispatches'] == 0


def test_esm_dns_named_exports_and_literal_loopback_lookup(tmp_path):
    source = r'''
import assert from 'node:assert/strict';
import {lookup, resolve4, Resolver} from 'node:dns';
import {lookup as promiseLookup, resolve4 as promiseResolve4} from 'node:dns/promises';
const proto = process.binding('cares_wrap').ChannelWrap.prototype;
let queries = 0;
for (const key of Object.getOwnPropertyNames(proto)) {
  if (/^query|^getHostByAddr$/.test(key)) proto[key] = () => {queries++; return 0;};
}
assert.throws(() => resolve4('offline-probe.invalid', () => {}), /forbidden/);
assert.throws(() => new Resolver().resolve4('offline-probe.invalid', () => {}), /forbidden/);
assert.throws(() => promiseResolve4('offline-probe.invalid'), /forbidden/);
assert.throws(() => promiseLookup('203.0.113.1'), /forbidden/);
const result = await new Promise((resolve, reject) => lookup('127.0.0.1', (error, address) =>
  error ? reject(error) : resolve(address)));
assert.equal(result, '127.0.0.1');
assert.equal((await promiseLookup('::1')).address, '::1');
assert.equal(queries, 0);
console.log('ESM exports and literal lookup retained');
'''
    assert 'literal lookup retained' in node(source, tmp_path, esm=True)


def test_changing_default_dns_servers_does_not_remove_query_guards(tmp_path):
    source = r'''
const assert = require('node:assert/strict');
const dns = require('node:dns');
const promises = require('node:dns/promises');
const proto = process.binding('cares_wrap').ChannelWrap.prototype;
let queries = 0;
for (const key of Object.getOwnPropertyNames(proto)) {
  if (/^query|^getHostByAddr$/.test(key)) proto[key] = () => {queries++; return 0;};
}
dns.setServers(['127.0.0.1']);
promises.setServers(['127.0.0.1']);
assert.throws(() => dns.resolve4('offline-probe.invalid', () => {}), /forbidden/);
assert.throws(() => promises.resolve4('offline-probe.invalid'), /forbidden/);
assert.equal(queries, 0);
console.log('resolver reset remains guarded');
'''
    assert 'reset remains guarded' in node(source, tmp_path)


def executable(tmp_path):
    path = tmp_path / 'fake dart executable'
    path.write_text('#!/bin/sh\nprintf "fake-dart-selected"\n')
    path.chmod(0o700)
    return path


def test_only_validated_dart_override_crosses_allowlist(tmp_path):
    path = executable(tmp_path)
    env = clean_environment({'DART_BIN': str(path), 'UNKNOWN_SECRET': 'fake-secret',
                             'FLUTTER_ROOT': 'fake-sdk-injection'}, tmp_path)
    assert env.get('DART_BIN') == str(path.resolve())
    assert 'UNKNOWN_SECRET' not in env and 'FLUTTER_ROOT' not in env


@pytest.mark.parametrize('kind', ['relative', 'missing', 'directory', 'not_executable'])
def test_invalid_explicit_dart_override_fails_without_exposing_path(tmp_path, kind):
    candidate = {'relative': Path('fake-secret-location'), 'missing': tmp_path / 'fake-secret-location',
                 'directory': tmp_path, 'not_executable': tmp_path / 'nonexecuting'}[kind]
    if kind == 'not_executable':
        candidate.write_text('fake-only data')
        candidate.chmod(0o600)
    with pytest.raises(ValueError, match='DART_BIN') as error:
        clean_environment({'DART_BIN': str(candidate)}, tmp_path)
    assert str(candidate) not in str(error.value)


@pytest.mark.parametrize('bootstrap', [False, True])
def test_dart_override_survives_bootstrap_and_stale_package_config(tmp_path, bootstrap):
    path = executable(tmp_path)
    env = clean_environment({**os.environ, 'DART_BIN': str(path)}, tmp_path)
    source = '''
import json, os, pathlib, runpy, subprocess, sys
assert os.environ.get('DART_BIN') == sys.argv[1]
suite = runpy.run_path('tests/test_api_dart.py')
assert suite['DART'] == sys.argv[1]
has_packages = suite['PACKAGES'].exists()
config = pathlib.Path(sys.argv[1]).parent / 'stale-packages.json'
config.write_text(json.dumps({'packages':[{'name':'flutter', 'rootUri':'file:///missing-sdk/packages/flutter'}]}))
scope = suite['dart_sdk'].__globals__
scope['PACKAGES'] = config
scope['shutil'].which = lambda name: None
assert suite['dart_sdk']() == sys.argv[1]
assert subprocess.check_output([suite['DART']], text=True) == 'fake-dart-selected'
for mark in suite['test_dart_client_http_contract'].pytestmark:
    if mark.name == 'skipif': assert mark.args == (not has_packages,)
child = subprocess.run([sys.executable, '-B', '-c', 'import os,sys; assert os.environ.get("DART_BIN")==sys.argv[1]', sys.argv[1]])
assert child.returncode == 0
print('explicit Dart selection and child boundary retained')
'''
    command = [sys.executable, '-B', '-c', source, str(path)]
    if not bootstrap:
        env.pop('PYTHONPATH')
        env.pop('PYTHON_DOTENV_DISABLED')
        probe = tmp_path / 'probe.py'
        # Ordinary pytest must install the same root conftest boundary.
        probe.write_text('import sys\nsys.argv = [sys.argv[0], ' + repr(str(path)) + ']\n' +
                         source + '\ndef test_collected(): pass\n')
        command = [sys.executable, '-B', '-m', 'pytest', '-q', '-s', '-p', 'no:cacheprovider', str(probe)]
    result = subprocess.run(command, cwd=ROOT,
                            env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, 'Fake-only Dart configuration regression failed: ' + result.stderr
    assert 'child boundary retained' in result.stdout
