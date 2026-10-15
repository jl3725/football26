from __future__ import annotations

import pandas as pd

import fetch_match_stats as fms


def test_minute_text_keeps_stoppage_time() -> None:
    assert fms._min_txt("45'+3'") == "45+3"     # 전반 추가시간 — 정수 48 로 바꾸면 후반 48분과 섞인다
    assert fms._min_txt("67'") == "67"
    assert fms._min_txt("") == ""


def test_rows_for_both_sides_and_pass_pct() -> None:
    p = {"state": "post", "score": {"home": 2, "away": 1},
         "goals": [{"minute": "10'", "m": 10, "side": "home"}, {"minute": "45'+2'", "m": 47, "side": "away"},
                   {"minute": "88'", "m": 88, "side": "home"}],
         "cards": [{"side": "away", "color": "red"}],
         "stats": {"possessionPct": {"home": "61.2", "away": "38.8"}, "totalShots": {"home": "15", "away": "6"},
                   "passPct": {"home": "0.9", "away": "0.8"},
                   "accuratePasses": {"home": "450", "away": "240"}, "totalPasses": {"home": "510", "away": "310"}}}
    sched = pd.DataFrame([
        {"event_id": "1", "date": "2026-10-01", "kickoff": "", "comp_code": "eng.1", "squad": "Arsenal", "opponent": "Chelsea", "home_away": "H"},
        {"event_id": "1", "date": "2026-10-01", "kickoff": "", "comp_code": "eng.1", "squad": "Chelsea", "opponent": "Arsenal", "home_away": "A"},
    ])
    rows = {r["squad"]: r for r in fms._rows_for(sched, p)}
    a, c = rows["Arsenal"], rows["Chelsea"]
    assert (a["gf"], a["ga"], a["result"]) == (2, 1, "W") and (c["gf"], c["ga"], c["result"]) == (1, 2, "L")
    assert a["shots"] == 15 and a["opp_shots"] == 6 and c["shots"] == 6
    assert a["pass_pct"] == 88.2 and c["pass_pct"] == 77.4          # 성공/전체로 직접 계산(ESPN 0.9 표시값 아님)
    assert a["goal_min_for"] == "10;88" and a["goal_min_against"] == "45+2"
    assert a["red_against"] == 1 and c["red_for"] == 1


def test_player_events_split_by_side_and_none_marker() -> None:
    import pandas as pd
    import fetch_match_stats as fms
    sched = pd.DataFrame([{"event_id": "1", "date": "2026-09-09", "comp_code": "uefa.champions", "squad": "Arsenal",
                           "home_away": "H", "opponent": "X"}])
    p = {"goals": [{"minute": "23'", "side": "home", "scorer": "Bukayo Saka", "assist": "Declan Rice", "kind": ""},
                   {"minute": "70'", "side": "away", "scorer": "Other", "assist": "", "kind": ""},
                   {"minute": "80'", "side": "home", "scorer": "Kai Havertz", "assist": "", "kind": "pen"}],
         "cards": [{"minute": "50'", "side": "home", "player": "Declan Rice", "color": "yellow"}]}
    ev = fms._events_for(sched, p)
    assert [(e["type"], e["player"]) for e in ev] == [("goal", "Bukayo Saka"), ("assist", "Declan Rice"),
                                                      ("pen", "Kai Havertz"), ("yellow", "Declan Rice")]
    none = fms._events_for(sched, {"goals": [], "cards": []})
    assert none[0]["type"] == "none"                # 기록 없는 경기도 '받았음' 표시
