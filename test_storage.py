"""
test_storage.py — tests for the safe JSON storage helper (storage.py).

Run:  python test_storage.py   (or: pytest test_storage.py)

Covers: round-trip, missing/corrupt → default (no crash), no leftover temp file,
and — the important one — 20 concurrent threads each appending via update_json
all survive (proves the lock prevents lost updates / the F2 race).
"""

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import storage

_results = []
def _check(name, cond):
    _results.append((name, bool(cond)))


def _tmpfile():
    d = Path(tempfile.mkdtemp())
    return d / "data.json"


# 1) round-trip
p = _tmpfile()
storage.write_json(p, {"a": 1, "ב": "שלום"})
_check("round-trip preserves data + unicode", storage.read_json(p) == {"a": 1, "ב": "שלום"})

# 2) missing file → default
_check("missing file returns default", storage.read_json(_tmpfile(), default=[]) == [])

# 3) corrupt file → default (no crash)
p2 = _tmpfile()
p2.write_text("{ this is not valid json", encoding="utf-8")
_check("corrupt file returns default (no raise)", storage.read_json(p2, default={"ok": True}) == {"ok": True})

# 4) empty file → default
p3 = _tmpfile()
p3.write_text("   ", encoding="utf-8")
_check("empty file returns default", storage.read_json(p3, default=[]) == [])

# 5) atomic write leaves no .tmp behind
p4 = _tmpfile()
storage.write_json(p4, [1, 2, 3])
_check("no leftover .tmp file", not p4.with_name(p4.name + ".tmp").exists())

# 6) update_json read-modify-write
p5 = _tmpfile()
storage.write_json(p5, [1])
storage.update_json(p5, lambda cur: (cur or []) + [2], default=[])
_check("update_json appends correctly", storage.read_json(p5) == [1, 2])

# 7) update_json on missing file uses default
p6 = _tmpfile()
storage.update_json(p6, lambda cur: cur + ["x"], default=[])
_check("update_json uses default on missing", storage.read_json(p6) == ["x"])

# 8) THE RACE TEST — 20 threads each append one item; none must be lost
p7 = _tmpfile()
storage.write_json(p7, [])
N = 20
def _worker(i):
    storage.update_json(p7, lambda cur: (cur or []) + [i], default=[])
threads = [threading.Thread(target=_worker, args=(i,)) for i in range(N)]
for t in threads: t.start()
for t in threads: t.join()
final = storage.read_json(p7, default=[])
_check(f"concurrent: all {N} appends survive (no lost updates)",
       sorted(final) == list(range(N)))


def main():
    print("=" * 56)
    print("  storage.py — safe JSON storage tests")
    print("=" * 56)
    passed = sum(1 for _, ok in _results if ok)
    for name, ok in _results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")
    print("-" * 56)
    print(f"  {passed}/{len(_results)} passed")
    if passed != len(_results):
        sys.exit(1)
    print("  All storage tests passed.")


def test_storage_all():   # pytest entry point
    failed = [n for n, ok in _results if not ok]
    assert not failed, f"storage tests failed: {failed}"


if __name__ == "__main__":
    main()
