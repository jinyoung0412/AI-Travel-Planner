"""Bounded immutable catalogue snapshots, never request-specific results."""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock


def database_version(path):
    path = Path(path).resolve()
    def stamp(p):
        try:
            stat = p.stat()
            return stat.st_ino, stat.st_size, stat.st_mtime_ns
        except FileNotFoundError:
            if p == path:
                raise
            return None
    return str(path), stamp(path), stamp(Path(str(path) + '-wal'))


class CatalogueCache:
    def __init__(self, limit=3):
        self.limit = limit
        self.lock = RLock()
        self.entries = OrderedDict()

    def get(self, key, load):
        # One cold load per key, even when several visitors arrive together.
        with self.lock:
            if key not in self.entries:
                value = load()
                self.entries[key] = value
                while len(self.entries) > self.limit:
                    self.entries.popitem(last=False)
            self.entries.move_to_end(key)
            value = self.entries[key]
        # DataFrames and metadata belong to each request. Child policies,
        # radius, preferences, random seeds and courses never enter the cache.
        return deepcopy(value)
