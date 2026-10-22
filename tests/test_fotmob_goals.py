"""FotMob 슈팅맵 골 상황 — 득점한 우리 팀 기준, 자책골은 상대 득점, 골 없는 우리 팀은 none 한 줄."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch_fotmob_matches as fm  # noqa: E402

MATCH = {"id": 99, "home": {"id": 1, "name": "Bayern München"}, "away": {"id": 2, "name": "1. FC Köln"},
         "status": {"utcTime": "2026-10-18T13:30:00Z"}}
SIDES = {"1": ("Bundesliga", "Bayern Munich"), "2": ("Bundesliga", "Köln")}


def _j(shots):
    return {"content": {"shotmap": {"shots": shots}}}


def test_goal_rows_situations_and_own_goal() -> None:
    shots = [{"eventType": "Goal", "teamId": 1, "playerName": "Harry Kane", "min": 12, "situation": "Penalty", "isOwnGoal": False, "expectedGoals": 0.79},
             {"eventType": "Goal", "teamId": 1, "playerName": "Michael Olise", "min": 40, "situation": "FromCorner", "isOwnGoal": False},
             {"eventType": "Goal", "teamId": 2, "playerName": "Some Defender", "min": 70, "situation": "RegularPlay", "isOwnGoal": True},
             {"eventType": "Miss", "teamId": 2, "playerName": "X", "min": 80, "situation": "RegularPlay"}]
    rows = fm.goal_rows(_j(shots), MATCH, "ger.1", SIDES)
    by = [(r["squad"], r["situation"], r["own_goal"]) for r in rows]
    assert ("Bayern Munich", "Penalty", 0) in by and ("Bayern Munich", "FromCorner", 0) in by
    assert ("Bayern Munich", "OwnGoal", 1) in by                      # 쾰른 수비수 자책골 = 바이에른 득점
    assert ("Köln", "none", 0) in by and len(rows) == 4               # 쾰른은 골 없음 → 받았다는 표시
    assert all(r["date"] == "2026-10-18" and r["comp_code"] == "ger.1" for r in rows)


def test_goal_rows_no_shotmap_leaves_for_retry() -> None:
    assert fm.goal_rows({"content": {}}, MATCH, "ger.1", SIDES) == []
    only_ours = fm.goal_rows(_j([{"eventType": "Goal", "teamId": 1, "situation": "RegularPlay"}]), MATCH, "ger.dfb_pokal",
                             {"1": ("Bundesliga", "Bayern Munich")})
    assert [r["squad"] for r in only_ours] == ["Bayern Munich"]       # 우리 리그 밖 상대는 행 없음
