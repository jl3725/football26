"""MLS(2026-11-09) — 달력 연도 시즌 토큰·FotMob/TM 시즌 이름·컨퍼런스 순위표·플레이오프 분리·Elo 승격팀 판별."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import leagues as L  # noqa: E402


def test_calendar_season_window_and_names() -> None:
    assert L.season_window("MLS", 2025) == ("2025-01-01", "2025-12-31")
    assert L.season_window("MLS", 2026) == ("2026-01-01", "2027-06-30")       # 마지막 달력 시즌 — 2027 단축 시즌까지
    assert L.season_window("MLS", 2027) == ("2027-07-01", "2028-06-30")       # 2027-28 부터 7~6월
    assert L.season_window("EPL", 2026) == ("2026-07-01", "2027-06-30")
    assert (L.fm_season("MLS", 2025), L.fm_season("EPL", 2025)) == ("2025", "2025/2026")
    assert (L.tm_season("MLS", 2026), L.tm_season("EPL", 2026)) == (2025, 2026)
    assert [L.token_of_fm_season("MLS", x) for x in ("2025", "2026", "2027", "2027/2028")] == \
        ["2025_2026", "2026_2027", "2026_2027", "2027_2028"]
    assert L.token_of_fm_season("EPL", "2026") is None


def _row(i, name, played, pts):
    return {"id": i, "idx": 0, "name": name, "played": played, "wins": 0, "draws": 0, "losses": 0,
            "scoresStr": "0-0", "goalConDiff": 0, "pts": pts}


def test_conference_standings_rank_by_overall_table() -> None:
    import lite_league as ll
    east = [_row(1, "Nashville SC", 34, 77), _row(3, "Inter Miami CF", 34, 60)]
    west = [_row(2, "Vancouver Whitecaps", 34, 64), _row(4, "LA Galaxy", 34, 40)]
    overall = [dict(r, idx=i + 1) for i, r in enumerate(sorted(east + west, key=lambda r: -r["pts"]))]
    d = {"table": [{"data": {"tables": [{"leagueName": "Eastern", "table": {"all": east}},
                                         {"leagueName": "Western", "table": {"all": west}},
                                         {"leagueName": "Supporters Shield", "table": {"all": overall}}]}}]}
    rows = ll.standings_rows(d)
    assert [(r["rank"], r["squad"], r["group"]) for r in rows] == [
        (1, "Nashville SC", "Eastern"), (2, "Vancouver Whitecaps", "Western"), (3, "Inter Miami CF", "Eastern"), (4, "LA Galaxy", "Western")]
    # 스플릿(그룹 표가 더 치름) — 컨퍼런스로 보지 않는다
    split = {"table": [{"data": {"tables": [{"leagueName": "Championship", "table": {"all": [_row(1, "A", 27, 30)]}},
                                            {"leagueName": "Relegation", "table": {"all": [_row(2, "B", 27, 10)]}},
                                            {"leagueName": "Regular", "table": {"all": [_row(1, "A", 22, 40), _row(2, "B", 22, 12)]}}]}}]}
    assert ll._conferences(split) is None


def test_playoffs_are_not_league_matches() -> None:
    import lite_league as ll
    from fetch_fotmob_matches import playoff_code
    assert ll._code("MLS", {"leagueId": 130, "name": "Major League Soccer Playoff"}, {}) == ("usa.1.playoffs", "플레이오프")
    assert ll._code("MLS", {"leagueId": 130, "name": "Major League Soccer"}, {}) == ("usa.1", "리그")
    assert playoff_code("usa.1", {"round": "1/8", "roundName": "Round of 16"}) == "usa.1.playoffs"
    assert playoff_code("aut.1", {"round": "25", "roundName": "25"}) == "aut.1"


def test_elo_promoted_cutoff_is_per_league() -> None:
    import team_elo as te
    ms = pd.DataFrame([
        {"event_id": "1", "date": "2025-02-22", "comp_code": "usa.1", "home": "LAFC", "away": "Seattle", "hg": 1, "ag": 0, "lg_h": "MLS", "lg_a": "MLS"},
        {"event_id": "2", "date": "2025-08-16", "comp_code": "eng.1", "home": "Arsenal", "away": "Leeds", "hg": 1, "ag": 0, "lg_h": "EPL", "lg_a": "EPL"},
    ])
    elo, _ = te.run(ms, {"MLS": 1450.0, "EPL": 1700.0})
    # 예전엔 첫 경기(MLS 2월)로 '첫 시즌 끝'을 2025-07-01 로 잡아 8월 첫 EPL 팀이 전부 승격팀(−80)이 됐다
    assert elo["Arsenal"] + elo["Leeds"] == 2 * 1700.0
