"""Test-only process boundary. Production entry points never import this module.

No dotenv file is opened, and no inherited credential values are inspected.
Python children inherit a sitecustomize path so spawn and fresh interpreters
install the same boundary before importing project code.
"""
import atexit
import importlib.abc
import importlib.machinery
import logging
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / 'scripts' / 'offline_bootstrap'
_installed = False
_home = None
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def validated_dart_binary(source):
    """Preserve one explicit executable choice, never arbitrary SDK settings."""
    value = source.get('DART_BIN')
    if not value:
        return ''
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        # Do not echo the inherited value into collection/startup diagnostics.
        raise ValueError('DART_BIN must be an absolute path to an existing executable file')
    return str(path.resolve())


def clean_environment(source, home):
    # Only tool discovery/OS mechanics and a validated Dart executable cross.
    # Application settings, proxy, other SDK, pytest/Python injection do not.
    env = {key: source[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR') if key in source}
    dart = validated_dart_binary(source)
    if dart:
        env['DART_BIN'] = dart
    env.update(HOME=str(home), USERPROFILE=str(home), TMPDIR=str(home),
               LANG='C.UTF-8', PYTHONIOENCODING='utf-8', PYTHONHASHSEED='0',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHON_DOTENV_DISABLED='1',
               NODE_OPTIONS=f'--require="{BOOTSTRAP / "offline_node.cjs"}"',
               PYTHONPATH=os.pathsep.join((str(BOOTSTRAP), str(ROOT), str(ROOT / 'Flask_server'))))
    return env


def forbidden(*args, **kwargs):
    # Never interpolate args, URLs, headers, environment or SDK exceptions.
    raise AssertionError('External API calls are forbidden in offline tests')


def _no_dotenv(*args, **kwargs):
    return False


def _no_dotenv_values(*args, **kwargs):
    return {}


def _no_dotenv_parse(*args, **kwargs):
    return iter(())


def _patch_dotenv(module):
    module.load_dotenv = _no_dotenv
    module.dotenv_values = _no_dotenv_values
    if hasattr(module, 'DotEnv'):
        module.DotEnv.parse = _no_dotenv_parse
        module.DotEnv.dict = _no_dotenv_values
        module.DotEnv.set_as_environment_variables = _no_dotenv


class _DotenvFinder(importlib.abc.MetaPathFinder):
    """Reapply guards when dotenv is reloaded or removed from sys.modules."""
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ('dotenv', 'dotenv.main'):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            original = spec.loader

            class Loader(importlib.abc.Loader):
                def create_module(self, spec):
                    return original.create_module(spec)

                def exec_module(self, module):
                    original.exec_module(module)
                    _patch_dotenv(module)

            spec.loader = Loader()
        return spec


def allow_gateway_loopback():
    """Explicit smoke-script exception: literal loopback TCP only, never DNS."""
    def local(address):
        return isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')

    def connect(sock, address):
        if not local(address):
            forbidden()
        return _connect(sock, address)

    def connect_ex(sock, address):
        if not local(address):
            forbidden()
        return _connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host not in ('127.0.0.1', '::1'):
            forbidden()
        return _getaddrinfo(host, *args, **kwargs)

    def gethostbyaddr(host):
        if host not in ('127.0.0.1', '::1'):
            forbidden()
        # HTTPServer calls getfqdn while binding. Resolve its own literal
        # address locally rather than letting reverse DNS reach a resolver.
        return 'localhost', [], [host]

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    socket.gethostbyaddr = gethostbyaddr


_FIELD = re.compile(
    r'''(?ix)(["']?(?:authorization|proxy-authorization|x-api-key|api[-_]key|'''
    r'''x-naver-client-(?:id|secret)|[a-z0-9_]*(?:api_key|api_secret|api_id|token|password|secret))'''
    r'''["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^,\s}\]\n]+(?:\s+[^,\s}\]\n]+)?)''')


def redact(text):
    """Remove credential fields and currently explicit test credential values."""
    text = str(text)
    for key in os.environ:
        if re.search(r'(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API_ID)', key, re.I):
            value = os.environ[key]
            if value and len(value) >= 4:
                text = text.replace(value, '[REDACTED]')
    return _FIELD.sub(lambda match: match[1] + "'[REDACTED]'", text)


def install():
    global _installed, _home
    if _installed:
        return
    _installed = True
    for path in (ROOT, ROOT / 'Flask_server'):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    _home = tempfile.TemporaryDirectory(prefix='travel-offline-')
    atexit.register(_home.cleanup)
    env = clean_environment(os.environ, _home.name)
    os.environ.clear()
    os.environ.update(env)

    # Disable both public entry points and direct DotEnv parsing, including
    # override=True and reloaded dotenv modules. The documented disable flag
    # is supplemental; older python-dotenv versions need these guards too.
    sys.meta_path.insert(0, _DotenvFinder())
    import dotenv
    import dotenv.main
    _patch_dotenv(dotenv)
    _patch_dotenv(dotenv.main)

    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.socket.sendto = forbidden
    if hasattr(socket.socket, 'sendmsg'):
        socket.socket.sendmsg = forbidden
    socket.getaddrinfo = forbidden
    socket.gethostbyname = forbidden
    socket.gethostbyname_ex = forbidden
    socket.gethostbyaddr = forbidden
    socket.getnameinfo = forbidden
    import requests
    import httpx
    requests.sessions.Session.request = forbidden
    httpx.Client.send = forbidden
    httpx.AsyncClient.send = forbidden

    factory = logging.getLogRecordFactory()

    def safe_record(*args, **kwargs):
        record = factory(*args, **kwargs)
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.msg += '\n' + redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
            record.exc_text = None
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return record

    logging.setLogRecordFactory(safe_record)
