"""
선택 인프라(Neo4j·Qdrant) 차단기(circuit breaker).

클러스터가 꺼져 있으면 연결 시도마다 DNS 실패·타임아웃으로 수 초가 걸리고, 단일 워커(Render 무료)에서는
그동안 다른 요청까지 멈춘다 — 2026-10 운영에서 케미스트리·추천이 죽은 상태로 Overview 전체를 10초 넘게
붙잡았다. 한 번 실패하면 일정 시간 동안은 시도하지 않고 즉시 '미가동'을 돌려준다.

사용:
    from infra_health import guard
    with guard("neo4j") as ok:
        if not ok: return {...unavailable...}
        ...연결·조회... (예외가 나면 자동으로 차단 시작)
"""
from __future__ import annotations

import contextlib
import time

_DOWN_UNTIL: dict[str, float] = {}
_LAST_REASON: dict[str, str] = {}
COOLDOWN = 10 * 60   # 초 — 실패 후 재시도까지


def is_down(name: str) -> bool:
    return _DOWN_UNTIL.get(name, 0.0) > time.monotonic()


def reason(name: str) -> str:
    return _LAST_REASON.get(name, "")


def mark_down(name: str, why: str = "") -> None:
    _DOWN_UNTIL[name] = time.monotonic() + COOLDOWN
    _LAST_REASON[name] = (why or "")[:120]


def mark_up(name: str) -> None:
    _DOWN_UNTIL.pop(name, None)
    _LAST_REASON.pop(name, None)


class _Probe:
    """`with guard(name) as ok:` — ok 가 False 면 차단 중. 블록 안 예외는 차단으로 기록하고 다시 던진다."""

    def __init__(self, name: str):
        self.name = name
        self.ok = not is_down(name)

    def __bool__(self) -> bool:
        return self.ok


@contextlib.contextmanager
def guard(name: str):
    probe = _Probe(name)
    try:
        yield probe
    except Exception as e:  # noqa: BLE001
        if probe.ok:
            mark_down(name, f"{type(e).__name__}: {e}")
        raise
    else:
        if probe.ok:
            mark_up(name)


def status() -> dict:
    """/api/health 용 — 어떤 선택 인프라가 차단 중인지."""
    now = time.monotonic()
    return {n: {"down": until > now, "retry_in_s": max(0, int(until - now)), "reason": _LAST_REASON.get(n, "")}
            for n, until in _DOWN_UNTIL.items()}
