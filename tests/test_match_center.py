from __future__ import annotations

import datetime as dt

import pandas as pd

import match_center as mc


def _rows(rows):
    cols = ["squad", "comp", "comp_code", "date", "kickoff", "home_away", "opponent", "status", "event_id", "result"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def test_matches_dedupe_kst_and_canonical_names() -> None:
    epl = _rows([
        ("Manchester City", "챔피언스리그", "uefa.champions", "2026-10-14", "2026-10-14T19:00Z", "H", "Paris Saint-Germain", "scheduled", "1", ""),
        ("Arsenal", "리그", "eng.1", "2026-10-18", "2026-10-18T15:30Z", "A", "Nottingham Forest", "scheduled", "2", ""),
        ("Nottingham Forest", "리그", "eng.1", "2026-10-18", "2026-10-18T15:30Z", "H", "Arsenal", "scheduled", "2", ""),
    ])
    l1 = _rows([("PSG", "챔피언스리그", "uefa.champions", "2026-10-14", "2026-10-14T19:00Z", "A", "Manchester City", "scheduled", "1", "")])
    ms = mc.matches_from({"EPL": epl, "Ligue1": l1}, dt.date(2026, 10, 14), 7)
    assert len(ms) == 2                                   # 같은 경기(양 팀 행·두 리그 파일)는 한 번만
    ucl = ms[0]
    assert ucl["kst"] == "10/15(목) 04:00" and ucl["d_day"] == 1   # UTC 19:00 → 한국 다음날 04:00
    assert ucl["away"] == {"team": "PSG", "league": "Ligue1"}       # ESPN 이름 대신 우리 표기·리그


def test_big_score_rules() -> None:
    top = mc.big_score({"comp_code": "eng.1", "home": {"league": "EPL", "rank": 1, "ovr": 90},
                        "away": {"league": "EPL", "rank": 2, "ovr": 89}})
    low = mc.big_score({"comp_code": "eng.1", "home": {"league": "EPL", "rank": 15, "ovr": 80},
                        "away": {"league": "EPL", "rank": 2, "ovr": 89}})
    cup = mc.big_score({"comp_code": "eng.league_cup", "home": {"league": "EPL", "rank": 15, "ovr": 79},
                        "away": {"league": None, "rank": None, "ovr": None}})
    assert "1위 경쟁" in top[1] and "강팀 대결" in top[1] and top[0] > 50
    assert low[1] == [] and low[0] < 30 and cup[0] < 0
