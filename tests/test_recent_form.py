from __future__ import annotations

import pandas as pd

import espn_common as ec
import recent_form as rf

COLS = ["match_id", "date", "comp_code", "squad", "opponent", "home_away", "fotmob_id", "player",
        "minutes", "rating", "goals", "assists"]


def _mr(rows):
    return pd.DataFrame(rows, columns=COLS)


def test_recent_form_splits_from_season_form() -> None:
    """시즌 평균이 좋아도 최근 경기가 처지면 LAST 5 는 낮다 — 사카 노팅엄전(2026-10-19 사용자 지적)."""
    days = ["2026-10-18", "2026-10-13", "2026-10-04", "2026-09-27", "2026-09-20"]
    rows = []
    for i, d in enumerate(days):
        rows.append([f"m{i}", d, "eng.1", "Arsenal", "Opp", "away", "1", "Hot Player", 90, 8.1, 1, 0])
        rows.append([f"m{i}", d, "eng.1", "Arsenal", "Opp", "away", "2", "Cold Player", 90, 6.3 if i < 3 else 7.6, 0, 0])
        rows.append([f"m{i}", d, "eng.1", "Arsenal", "Opp", "away", "3", "Mid Player", 90, 6.9, 0, 0])
    frame = pd.DataFrame([
        {"player": "Hot Player", "squad": "Arsenal", "fm_id": 1, "pos": "FW", "_line": "ATT"},
        {"player": "Cold Player", "squad": "Arsenal", "fm_id": 2, "pos": "FW", "_line": "ATT"},
        {"player": "Mid Player", "squad": "Arsenal", "fm_id": None, "pos": "FW", "_line": "ATT"},   # id 없으면 (팀, 이름)
    ])
    out = rf.add_recent_form(frame, _mr(rows), today="2026-10-19").set_index("player")
    assert out.loc["Hot Player", "_recent"] > out.loc["Mid Player", "_recent"] > out.loc["Cold Player", "_recent"]
    assert out.loc["Cold Player", "_recent_avg3"] == 6.3 and out.loc["Cold Player", "_recent_n"] == 5
    # 60일 지난 경기는 빼고, 평점 없는 경기(짧은 교체)는 세지 않는다
    old = rows + [["x", "2026-07-01", "eng.1", "Arsenal", "Opp", "home", "1", "Hot Player", 90, 3.0, 0, 0],
                  ["y", "2026-10-19", "eng.1", "Arsenal", "Opp", "home", "1", "Hot Player", 5, None, 0, 0]]
    bp = rf.by_player(rf.recent_rows(_mr(old), today="2026-10-19"))
    ms = rf.match_list(rf.lookup(bp, 1, "Arsenal", "Hot Player"))
    assert [m["date"] for m in ms] == days and all(m["rating"] == 8.1 for m in ms)


def test_season_squad_requires_league_team_id(monkeypatch) -> None:
    """이름 키만 보면 안도라 'Inter Club d'Escaldes' 가 인테르로 잡혔다 — 리그 경기에서 본 ESPN 팀 id 일 때만."""
    ec.season_squad_of.cache_clear()
    monkeypatch.setattr(ec, "league_members", lambda lg, y: {"Inter"})
    monkeypatch.setattr(ec, "league_team_ids", lambda lg, y: {"Inter": {"110"}})
    fn = ec.season_squad_of("SerieA", 2026)
    assert fn({"displayName": "Internazionale", "id": "110"}) == "Inter"
    assert fn({"displayName": "Inter Club d'Escaldes", "id": "20391"}) is None
    ec.season_squad_of.cache_clear()
