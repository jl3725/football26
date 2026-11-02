"""
운영 서버 메모리 돌려주기(리눅스 glibc) — 쓰고 놓은 메모리를 운영체제에 실제로 돌려준다.

2026-11-03: 메모리를 쓰는 캐시를 110MB 줄였는데(로컬 Windows 418 → 308MB) 운영(Render, 512MB) 데우기 직후는 437MB 그대로였다.
리눅스 glibc 는 데우기처럼 잠깐 크게 썼다 놓은 메모리를 프로세스에 쥐고 있고(힙 조각·스레드마다 따로 잡는 영역), pandas 의 큰
배열은 한 번 놓으면 다음부터 힙에서 받아 더 쌓인다. 그래서
  · setup(): 시작 때 스레드별 영역 수를 2개로(M_ARENA_MAX), 큰 배열은 늘 따로 받아 놓을 때 바로 돌려주게(M_MMAP_THRESHOLD 고정)
  · trim(): malloc_trim(0) — 미리 데우기가 끝났을 때와 live_sync 주기(10분)마다. 돌려준 양은 /api/health proc 에
리눅스가 아니면(로컬 Windows·mac) 아무것도 안 한다.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import datetime as dt
import os
import sys

M_MMAP_THRESHOLD, M_ARENA_MAX = -3, -8
MMAP_THRESHOLD = 128 * 1024
ARENA_MAX = 2
STATE: dict = {"trim_at": "", "trim_freed_mb": None, "trims": 0}
_LIBC: list = []


def _libc():
    if _LIBC:
        return _LIBC[0]
    lib = None
    if sys.platform.startswith("linux"):
        try:
            lib = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
            lib.malloc_trim  # noqa: B018 — glibc 가 아니면(musl) 없음
        except (OSError, AttributeError):
            lib = None
    _LIBC.append(lib)
    return lib


def rss_mb() -> float | None:
    """지금 프로세스 메모리(RSS, MB) — 리눅스(/proc)만."""
    try:
        with open("/proc/self/statm", encoding="ascii") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 2**20, 1)
    except (OSError, ValueError, AttributeError, IndexError):
        return None


def setup() -> bool:
    lib = _libc()
    if lib is None:
        return False
    try:
        lib.mallopt(M_ARENA_MAX, ARENA_MAX)
        lib.mallopt(M_MMAP_THRESHOLD, MMAP_THRESHOLD)
        return True
    except (AttributeError, OSError):
        return False


def trim() -> float | None:
    """쓰고 놓은 메모리를 돌려준다 — 줄어든 MB(리눅스 아니면 None)."""
    lib = _libc()
    if lib is None:
        return None
    before = rss_mb()
    try:
        lib.malloc_trim(0)
    except (AttributeError, OSError):
        return None
    after = rss_mb()
    freed = round(before - after, 1) if before is not None and after is not None else None
    STATE.update(trim_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), trim_freed_mb=freed,
                 trims=STATE["trims"] + 1)
    return freed
