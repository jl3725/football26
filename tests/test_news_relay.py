"""뉴스 이어 달리기 — 마지막 수집 110분 넘고 도는 것 없을 때만 실행, 자기 이어 달리기는 다른 것이 없을 때만(2026-11-12)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT)]

import news_relay as nr  # noqa: E402

NOW = dt.datetime(2026, 11, 12, 6, 0, tzinfo=dt.timezone.utc)


def _r(i, status, mins_ago):
    return {"id": i, "status": status, "created_at": (NOW - dt.timedelta(minutes=mins_ago)).isoformat().replace("+00:00", "Z")}


def test_news_due_rules() -> None:
    assert nr.news_due([_r(1, "completed", 130)], NOW)[0] is True
    assert nr.news_due([_r(1, "completed", 60)], NOW)[0] is False           # 2시간 안 — 번역 한도 생각해 더 자주 안 함
    assert nr.news_due([_r(2, "in_progress", 5), _r(1, "completed", 300)], NOW)[0] is False
    assert nr.news_due([_r(2, "queued", 1)], NOW)[0] is False
    assert nr.news_due([], NOW)[0] is True


def test_relay_self_only_when_no_other_active() -> None:
    assert nr.other_relay_active([_r(10, "in_progress", 300)], "10") is False      # 지금 이 실행
    assert nr.other_relay_active([_r(11, "queued", 1), _r(10, "in_progress", 300)], "10") is True


def test_tick_dispatches_when_due() -> None:
    sent = []
    assert nr.tick(False, NOW, get_runs=lambda wf: [_r(1, "completed", 200)], do=lambda wf, dry: sent.append(wf) or True)
    assert sent == ["daily_news.yml"]
    assert not nr.tick(False, NOW, get_runs=lambda wf: [_r(1, "completed", 30)], do=lambda wf, dry: sent.append(wf) or True)
    assert sent == ["daily_news.yml"]
