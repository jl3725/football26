"""원천이 막혔을 때 대체 원천이 있으면 DATA STATUS 는 '대체 원천'(fallback) — 2026-11-05 사용자 '원천 중단 살릴 방법'."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import agent_registry as reg  # noqa: E402
import ops_status as os_  # noqa: E402

NOW = dt.datetime(2026, 11, 5, 3, 0, tzinfo=dt.timezone.utc)


def _entries():
    return [{"t": "2026-11-01T03:00:00+00:00", "runner": "match_refresh", "step": "understat_live", "league": None, "ok": True, "code": 0},
            {"t": "2026-11-05T02:00:00+00:00", "runner": "match_refresh", "step": "understat_live", "league": None, "ok": False, "code": 75}]


def test_source_down_with_fallback_is_fallback_state() -> None:
    f = reg.Feed("understat", "xG", ("understat_live",), ("match_refresh",), "매일", 36, fallback="FotMob xG")
    s = os_.feed_status(f, _entries(), NOW)
    assert s["state"] == "fallback" and s["fallback"] == "FotMob xG" and s["down"] == ["understat_live"]
    g = reg.Feed("understat", "xG", ("understat_live",), ("match_refresh",), "매일", 36)
    assert os_.feed_status(g, _entries(), NOW)["state"] == "down"
    assert os_.RANK["fallback"] < os_.RANK["down"] < os_.RANK["warn"]


def test_registry_marks_understat_fallback() -> None:
    feeds = {f.key: f for a in reg.AGENTS for f in a.feeds}
    assert "FotMob" in feeds["understat"].fallback and feeds["units"].fallback
