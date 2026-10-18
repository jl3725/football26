from __future__ import annotations

import pandas as pd

import api.main as M


def _p(name, role, rating, line):
    return {"player": name, "squad": "X", "_mn": 900, "_ss": rating, "_role": role, "_line": line,
            "tm_position": "", "goals": 0, "assists": 0}


def test_team_of_season_picks_formation_for_two_strikers_and_real_fullbacks(monkeypatch) -> None:
    rows = [_p("G", "GK", 7.4, "GK"),
            _p("LB1", "LB", 7.2, "DEF"), _p("RB1", "RB", 7.2, "DEF"),
            _p("CB1", "CB", 7.5, "DEF"), _p("CB2", "CB", 7.45, "DEF"), _p("CB3", "CB", 7.4, "DEF"), _p("CB4", "CB", 7.35, "DEF"),
            _p("DM1", "DM", 7.2, "MID"), _p("CM1", "CM", 7.2, "MID"), _p("CM2", "CM", 7.15, "MID"),
            _p("LW1", "LW", 7.0, "ATT"), _p("RW1", "RW", 7.0, "ATT"),
            _p("ST1", "ST", 7.9, "ATT"), _p("ST2", "ST", 7.8, "ATT")]
    p = pd.DataFrame(rows)
    monkeypatch.setattr(M.ds, "read_table", lambda *a, **k: pd.DataFrame([{"played": 10}]))
    monkeypatch.setattr(M, "_pos_profile", lambda r: {"primary": r["_role"], "secondary": []})
    monkeypatch.setattr(M.rv3, "line_of_row", lambda r: r["_line"])
    for f in ("_player_ovr", "_photo"):
        monkeypatch.setattr(M, f, lambda r: 0)
    monkeypatch.setattr(M.tm, "team_logo", lambda s: "")
    t = M._team_of_season(p, "EPL")
    names = {x["player"] for x in t["xi"]}
    assert {"ST1", "ST2"} <= names                            # 잘하는 스트라이커 둘 다(4-3-3 고정이면 한 명)
    assert t["formation"] in ("4-4-2", "3-5-2")
    slot = {x["slot"]: x["player"] for x in t["xi"]}
    if "LB" in slot:                                           # 백4 면 풀백 자리엔 진짜 풀백
        assert slot["LB"] == "LB1" and slot["RB"] == "RB1"
    assert len(t["xi"]) == 11 and 0 < len(t["subs"]) <= 7
    assert not names & {s["player"] for s in t["subs"]}       # 교체 명단은 XI 밖
