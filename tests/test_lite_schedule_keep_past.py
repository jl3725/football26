"""라이트 리그 일정 — FotMob 팀 응답 창에서 밀려난 끝난 경기를 지난 파일에서 이어받는다(2026-11-22 MLS 2~8월 경기 빠짐)."""
from __future__ import annotations

import pandas as pd

import lite_league as ll


def _row(squad, eid, date, status="completed", code="usa.1"):
    return {"squad": squad, "comp": "리그", "comp_code": code, "date": date, "kickoff": f"{date}T00:00Z", "home_away": "H",
            "opponent": "X", "gf": 1 if status == "completed" else None, "ga": 0 if status == "completed" else None,
            "score": "1-0" if status == "completed" else "", "result": "W" if status == "completed" else "",
            "status": status, "event_id": str(eid), "opponent_logo": ""}


def test_keeps_completed_rows_that_fell_out_of_window() -> None:
    old = pd.DataFrame([_row("Columbus Crew", 1, "2026-03-01"), _row("Columbus Crew", 2, "2026-09-01")])
    new = pd.DataFrame([_row("Columbus Crew", 2, "2026-09-01"), _row("Columbus Crew", 3, "2027-03-01", "scheduled")])
    out = ll.keep_past(new, old, "MLS")
    assert sorted(out["event_id"]) == ["1", "2", "3"]


def test_does_not_revive_rows_inside_new_window_or_outside_season() -> None:
    old = pd.DataFrame([_row("Columbus Crew", 9, "2026-10-01"),            # 새 응답 기간 안 — 원천이 뺀 경기는 살리지 않음
                        _row("Columbus Crew", 8, "2025-05-01"),            # 지난 시즌(창 밖)
                        _row("Columbus Crew", 7, "2026-04-01", "scheduled"),  # 끝나지 않은 경기
                        _row("Gone FC", 6, "2026-04-01")])                 # 이번 응답에 없는 팀
    new = pd.DataFrame([_row("Columbus Crew", 2, "2026-09-01")])
    out = ll.keep_past(new, old, "MLS")
    assert list(out["event_id"]) == ["2"]


def test_no_old_file_returns_new() -> None:
    new = pd.DataFrame([_row("Columbus Crew", 2, "2026-09-01")])
    assert ll.keep_past(new, None, "MLS") is new
