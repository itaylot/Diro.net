"""
storage.py — safe JSON persistence: atomic writes + cross-process locking.

WHY THIS EXISTS
  Multiple *separate processes* (dashboard, apartment_agent, facebook_agent) and
  threads (scan_now, /api/ingest) read-modify-write the same JSON files. Two
  problems:
    1. `Path.write_text` is NOT atomic — a reader can catch a half-written file
       → JSONDecodeError → crash / 500.
    2. There is no lock — two writers that both read→mutate→write clobber each
       other (last-writer-wins → lost listings).

HOW IT FIXES THEM
  • Atomic writes: serialize to `<file>.tmp` then `os.replace()` (atomic on both
    Windows and POSIX). A reader therefore always sees a *whole* file.
  • Cross-process locking: a per-file lock (via `filelock`) serializes the
    read-modify-write so concurrent updaters can't lose each other's changes.

API
  read_json(path, default=None)            -> data        (never raises)
  write_json(path, data)                                  (atomic, locked)
  update_json(path, mutate, default=None)  -> new_data    (locked read-modify-write)

  `mutate(current)` receives the current value (or `default`) and returns the
  new value to persist.

Reads are intentionally lock-free: because every write is atomic, a reader can
only ever observe the old or the new complete file, never a partial one. The
lock matters only for the read-modify-write critical section in `update_json`.
"""

import json
import os
from pathlib import Path

from filelock import FileLock

_LOCK_TIMEOUT = 15  # seconds to wait for the lock before giving up


def _lock_for(path: Path) -> FileLock:
    return FileLock(str(path) + ".lock", timeout=_LOCK_TIMEOUT)


def _safe_load(p: Path, default):
    """Read + parse a JSON file, returning `default` on missing/empty/corrupt."""
    try:
        if not p.exists():
            return default
        txt = p.read_text(encoding="utf-8")
        return json.loads(txt) if txt.strip() else default
    except Exception:
        return default


def _atomic_write(p: Path, data) -> None:
    """Write JSON to a temp file in the same dir, then atomically replace."""
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)  # atomic on Windows + POSIX


def read_json(path, default=None):
    """Safe read — never raises; missing/corrupt → `default`."""
    return _safe_load(Path(path), default)


def write_json(path, data) -> None:
    """Atomic, locked write (overwrites the whole file)."""
    p = Path(path)
    with _lock_for(p):
        _atomic_write(p, data)


def update_json(path, mutate, default=None):
    """
    Locked read-modify-write. Holds the file lock across read → mutate → write,
    so concurrent updaters serialize instead of clobbering each other.
    Returns the new value.
    """
    p = Path(path)
    with _lock_for(p):
        current = _safe_load(p, default)
        new = mutate(current)
        _atomic_write(p, new)
        return new
