"""대표팀 경기 평점 — 수집(src/fetch_fotmob_intl.py) · 상대 수준 맞추기·표본(src/allcomp_stats.py nt_*) · OVR 반영.

2026-10-27 사용자: '하베르츠 85·에제 84 정도 — 국대 활약도 넣자'. 유럽·컵처럼 리그 밖 표본으로 OVR 경기력에만 넣는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import allcomp_stats as acs  # noqa: E402
import fetch_fotmob_intl as fi  # noqa: E402
import ratings_v3 as rv3  # noqa: E402


def test_season_edge_puts_summer_tournament_in_finished_season():
    assert fi.season_of("2026-07-18") == "2025_2026"      # 월드컵 3·4위전 — 끝난 시즌
    assert fi.season_of("2026-09-24") == "2026_2027"
    assert fi.season_of("2026-06-06") == "2025_2026"


def test_senior_comp_names():
    assert fi.senior_name("World Cup") and fi.senior_name("UEFA Nations League A") and fi.senior_name("Friendlies")
    for n in ("Women's World Cup", "World Cup Qualification (W) UEFA", "Concacaf W Qualifiers", "EURO U21",
              "World Cup U20", "Summer Olympics", "Friendlies U21"):
        assert not fi.senior_name(n), n
    assert fi._prev_label("2026/2027") == "2025/2026" and fi._prev_label("2026") == "2025"


def test_match_rows_keeps_only_our_players_and_marks_empty_matches():
    match = {"id": 9, "home": {"id": 1, "name": "Germany"}, "away": {"id": 2, "name": "Curacao"},
             "status": {"utcTime": "2026-06-14T19:00:00Z"}}

    def player(pid, team, mins, rating):
        return {"id": pid, "name": f"P{pid}", "teamId": team,
                "stats": [{"stats": {"Minutes played": {"stat": {"value": mins}}, "FotMob rating": {"stat": {"value": rating}},
                                     "Goals": {"stat": {"value": 2}}}}]}
    j = {"content": {"playerStats": {"10": player(10, 1, 90, 8.86), "11": player(11, 1, 0, None), "12": player(12, 2, 90, 6.1)}}}
    idx = {"germany": ("Germany", 1700.0), "curacao": ("Curaçao", 1300.0)}
    rows = fi.match_rows(j, match, 77, "World Cup", {"10": ("EPL", "Arsenal", "Kai Havertz"), "11": ("EPL", "X", "Y")}, idx)
    assert len(rows) == 1                                            # 벤치(0분)·우리 선수 아님은 뺀다
    r = rows[0]
    assert (r["nation"], r["opponent"], r["club"], r["minutes"], r["rating"], r["goals"]) == ("Germany", "Curacao", "Arsenal", 90, 8.86, 2)
    assert r["opp_points"] == 1300.0 and r["nation_points"] == 1700.0 and r["friendly"] == 0
    empty = fi.match_rows(j, match, 114, "Friendlies", {}, idx)
    assert len(empty) == 1 and "fotmob_id" not in empty[0] and empty[0]["friendly"] == 1   # 받았다는 표시만


def test_nt_level_follows_opponent_strength_and_clips():
    cal = (90.0, 0.05)
    assert acs.nt_level(1500, cal) == 90.0
    assert acs.nt_level(1900, cal) > acs.nt_level(1300, cal)
    assert acs.nt_level(9999, cal) == acs.LVL_MAX and acs.nt_level(0, cal) == acs.LVL_MIN
    assert acs.nt_level(None, cal) == acs.nt_level(acs.NT_UNKNOWN_POINTS, cal)    # 랭킹에 없는 나라 = 약체


def test_nt_cal_recovers_slope_from_club_baseline(monkeypatch):
    # 대표팀 평점이 '클럽 평점 + 0.02 × (클럽 리그 수준 − 상대 수준)'으로 나오는 가상 세계 — 상대 수준 = 70 + 0.06 × (점수 − 1500)
    import rating_blend as rb
    rows, base = [], {}
    for i in range(400):
        pts = 1200 + (i % 9) * 90
        true_lvl = 70 + 0.06 * (pts - 1500)
        club_fm = 7.0
        diff_ss = 0.02 * (100 - true_lvl)                             # EPL(100) 선수
        intl_fm = rb.FM_MU + (rb.fm_to_ss(club_fm) + diff_ss - rb.SS_MU) * rb.FM_SD / rb.SS_SD
        rows.append({"fotmob_id": str(1000 + i), "minutes": 90, "rating": intl_fm, "opp_points": pts,
                     "club": "Arsenal", "comp_id": 77, "friendly": 0})
        base[1000 + i] = (club_fm, 2000.0, "EPL")
    t = pd.DataFrame(rows)
    monkeypatch.setattr(rb, "_by_id", lambda read, se: base)
    a, b, n = acs.nt_cal(lambda table, lg, se: t if table == "fotmob_intl_ratings" else None, ["2025_2026"])
    assert n == 400 and abs(b - 0.06) < 0.002 and abs(a - 70) < 0.5


def test_nt_rows_weights_friendlies_half():
    t = pd.DataFrame([{"fotmob_id": "1", "player": "Kai Havertz", "minutes": 90, "rating": 7.5, "opp_points": 1600, "club": "Arsenal", "comp_id": 77, "friendly": 0},
                      {"fotmob_id": "1", "player": "Kai Havertz", "minutes": 60, "rating": 8.0, "opp_points": 1300, "club": "Arsenal", "comp_id": 114, "friendly": 1},
                      {"fotmob_id": None, "player": None, "minutes": None, "rating": None, "opp_points": None, "club": None, "comp_id": 114, "friendly": 1}])
    d = acs.nt_rows(lambda table, lg, se: t, "2025_2026", (90.0, 0.05))
    assert list(d["_w"]) == [acs.W_NT, acs.W_FRIENDLY] and acs.W_FRIENDLY == acs.W_NT / 2
    by_id, _ = acs.rating_table(d)
    assert list(d["comp_code"]) == ["intl.77", "intl.114"]
    assert by_id["1"]["minutes"] == 90 * acs.W_NT + 60 * acs.W_FRIENDLY and by_id["1"]["raw_minutes"] == 150


def test_national_team_sample_moves_ovr():
    # 리그 평점이 낮게 나오는 선수의 대표팀 활약(높은 수준 상대 고평점)이 OVR 경기력에 들어간다
    kw = dict(value=60e6, ss_rating=6.84, minutes=589, age=27, pos_group="ATT", league_level=100,
              prev_minutes=581, prev_ss_rating=6.73)
    base = rv3.absolute_ovr(**kw)
    good = rv3.absolute_ovr(prev_nt_ss_rating=7.45, prev_nt_minutes=416, prev_nt_level=100, **kw)
    poor = rv3.absolute_ovr(prev_nt_ss_rating=6.40, prev_nt_minutes=416, prev_nt_level=100, **kw)
    assert poor <= base <= good and good > poor


def test_short_cameos_count_as_minutes_but_not_rating():
    # 30분 미만 교체 출전 평점은 체계적으로 낮다(클럽 평점보다 −0.45) — 평점에선 빼고, 출전 분·대회 표시는 그대로
    t = pd.DataFrame([{"fotmob_id": "7", "player": "A", "minutes": 90, "rating": 7.4, "_w": 1.0, "_lvl": 100.0,
                       "squad": "X", "comp_code": "uefa.champions", "_fid": "7"},
                      {"fotmob_id": "7", "player": "A", "minutes": 12, "rating": 6.1, "_w": 1.0, "_lvl": 100.0,
                       "squad": "X", "comp_code": "uefa.champions", "_fid": "7"}])
    by_id, _ = acs.rating_table(t)
    assert by_id["7"]["fm_rating"] == 7.4 and by_id["7"]["minutes"] == 90
    assert by_id["7"]["raw_minutes"] == 102 and by_id["7"]["comps"] == {"uefa.champions": 102}
