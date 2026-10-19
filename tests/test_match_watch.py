"""경기 종료 감시 판단 — 끝난 경기 GRACE 대기, 물결 중엔 MIN_GAP 묶기, 마지막 물결은 바로, 남은 경기 판단."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parent.parent / "scripts"), str(Path(__file__).resolve().parent.parent / "src")]

import match_watch as mw  # noqa: E402

T0 = dt.datetime(2026, 10, 24, 14, 0, tzinfo=dt.timezone.utc)   # 토요일 14:00Z


def fx(rows: list[tuple[str, str, bool]]) -> pd.DataFrame:
    return pd.DataFrame([{"event_id": i, "comp_code": "eng.1", "kickoff": pd.Timestamp(k), "done": done}
                         for i, k, done in rows])


def test_waits_grace_then_refreshes_when_wave_over() -> None:
    w = mw.Watch(T0)
    f = fx([("a", "2026-10-24T11:30Z", False)])
    # 13:25 종료 예상 경기가 14:00 에 처음 'post' — 킥오프+1:55+20분(13:45) 지났으니 바로
    d = w.decide(f, {"a": "post"}, T0)
    assert d["refresh"] == ["a"]
    # 방금 끝난 경기(킥오프 12:30, 종료 예상 14:25)는 처음 본 뒤 20분 기다림
    w2 = mw.Watch(T0)
    f2 = fx([("b", "2026-10-24T12:30Z", False)])
    assert w2.decide(f2, {"b": "post"}, T0)["refresh"] == []
    assert w2.decide(f2, {"b": "post"}, T0 + dt.timedelta(minutes=20))["refresh"] == ["b"]


def test_batches_during_wave_with_min_gap() -> None:
    w = mw.Watch(T0)
    f = fx([("a", "2026-10-24T11:30Z", False), ("b", "2026-10-24T11:45Z", False),
            ("c", "2026-10-24T14:00Z", False), ("d", "2026-10-24T16:30Z", False)])
    d = w.decide(f, {"a": "post", "c": "in"}, T0)
    assert d["refresh"] == ["a"] and d["live"] == ["c"]
    w.handled.update(d["refresh"])
    w.last_refresh = T0
    # 30분 뒤 b 도 끝났지만 c 진행 중 + 지난 갱신 90분 안 → 묶어서 나중에
    t1 = T0 + dt.timedelta(minutes=30)
    d = w.decide(f, {"a": "post", "b": "post", "c": "in"}, t1)
    assert d["refresh"] == [] and d["held"] == ["b"] and w.busy(d)
    # c 까지 끝나고 d 는 3시간 밖 → 물결 끝, 90분 안이어도 바로
    t2 = T0 + dt.timedelta(hours=2, minutes=20)
    d = w.decide(f, {"a": "post", "b": "post", "c": "post", "d": "pre"}, t2)
    assert sorted(d["refresh"]) == ["b", "c"] and d["soon"] == ["d"] and d["next_kick"] == pd.Timestamp("2026-10-24T16:30Z")


def test_already_done_in_data_and_postponed_ignored() -> None:
    w = mw.Watch(T0)
    f = fx([("a", "2026-10-24T10:00Z", True), ("p", "2026-10-24T10:00Z", False)])
    d = w.decide(f, {"a": "post", "p": "postponed"}, T0)
    assert d["refresh"] == [] and not w.busy(d) and d["next_kick"] is None
