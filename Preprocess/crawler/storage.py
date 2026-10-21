"""Atomic local checkpoints: an interrupt must leave the previous file readable."""
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


class OutputInUseError(RuntimeError):
    """Another writer owns this output; retry explicitly after it finishes."""


@contextmanager
def exclusive_output(path):
    """Nonblocking process-wide ownership, released even if a worker crashes.

    Keep the sidecar inode after unlocking: unlinking it could let another
    process lock a different inode while a previous owner still holds the old one.
    Atomic replacement protects readers; this lock protects read/modify/write.
    """
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError:
            raise OutputInUseError('출력을 다른 작업이 사용 중입니다. 종료 후 다시 실행하세요.') from None
        try:
            yield
        finally:
            release()


@contextmanager
def atomic_output(path, *, encoding='utf-8'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', encoding=encoding, newline='',
                                dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
