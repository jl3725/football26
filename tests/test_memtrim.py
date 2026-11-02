"""메모리 돌려주기(src/memtrim.py) — 리눅스 glibc 가 아니면 아무것도 안 한다(로컬 Windows·mac 에서 깨지지 않게)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import memtrim  # noqa: E402


def test_noop_without_glibc(monkeypatch):
    monkeypatch.setattr(memtrim, "_LIBC", [None])
    assert memtrim.setup() is False and memtrim.trim() is None


def test_trim_records_freed(monkeypatch):
    class Lib:
        def malloc_trim(self, n):
            return 1
    seq = iter([400.0, 310.0])
    monkeypatch.setattr(memtrim, "_LIBC", [Lib()])
    monkeypatch.setattr(memtrim, "rss_mb", lambda: next(seq))
    monkeypatch.setitem(memtrim.STATE, "trims", 0)
    assert memtrim.trim() == 90.0 and memtrim.STATE["trim_freed_mb"] == 90.0 and memtrim.STATE["trims"] == 1
