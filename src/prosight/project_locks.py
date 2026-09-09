"""Per-project synchronization for local file and ingestion operations."""
from threading import Lock, RLock
from weakref import WeakKeyDictionary

_guard = Lock()
_locks = WeakKeyDictionary()

def project_lock(repository, code):
    with _guard:
        return _locks.setdefault(repository, {}).setdefault(code, RLock())
