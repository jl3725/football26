"""평점 세 원천 평균(Sofascore·FotMob·365Scores) — 2026-11-05 사용자 '원천 3곳 평균이면 신빙성이 오르지 않나'."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import fetch_365_ratings as f365  # noqa: E402
import rating_blend as rb  # noqa: E402


def _game():
    def member(mid, rank, mins):
        return {"id": mid, "status": 1, "ranking": rank, "stats": [{"type": 30, "name": "Minutes", "value": f"{mins}'"}]}
    return {"id": 99, "startTime": "2026-10-24T14:00:00Z",
            "members": [{"id": 1, "athleteId": 11, "name": "Bukayo Saka"}, {"id": 2, "athleteId": 22, "name": "Declan Rice"},
                        {"id": 3, "athleteId": 33, "name": "Bench Guy"}, {"id": 4, "athleteId": 44, "name": "Jordan Pickford"}],
            "homeCompetitor": {"name": "Arsenal", "lineups": {"members": [member(1, 7.4, 90), member(2, 7.1, 85), member(3, -1, 4)]}},
            "awayCompetitor": {"name": "Everton", "lineups": {"members": [member(4, 6.2, 90)]}}}


def test_match_rows_parse_ratings_minutes_and_skip_unrated() -> None:
    rows = f365.match_rows(_game(), ["Arsenal", "Everton"], "EPL")
    got = {r["player"]: (r["squad"], r["minutes"], r["rating"], r["opponent"]) for r in rows}
    assert got == {"Bukayo Saka": ("Arsenal", 90, 7.4, "Everton"), "Declan Rice": ("Arsenal", 85, 7.1, "Everton"),
                   "Jordan Pickford": ("Everton", 90, 6.2, "Arsenal")}                 # 평점 없는(−1) 교체는 뺀다


def test_season_table_minutes_weighted() -> None:
    mr = pd.DataFrame([{"match_id": "1", "date": "2026-10-01", "squad": "Arsenal", "opponent": "x", "home_away": "home",
                        "athlete_id": "11", "player": "Bukayo Saka", "minutes": 90, "rating": 8.0},
                       {"match_id": "2", "date": "2026-10-08", "squad": "Arsenal", "opponent": "y", "home_away": "away",
                        "athlete_id": "11", "player": "Bukayo Saka", "minutes": 30, "rating": 6.0}])
    st = f365.season_table(mr)
    r = st.iloc[0]
    assert r["apps"] == 2 and r["minutes"] == 120 and abs(r["rating"] - 7.5) < 1e-9      # (8×90 + 6×30) / 120


def test_blend_averages_three_sources_with_coverage() -> None:
    f = pd.DataFrame([{"squad": "A", "player": "P", "pos": "MF", "ss_rating": 7.0, "ss_minutes": 900,
                       "fm_rating": rb.FM_MU, "fm_minutes": 900, "s365_rating": 7.0, "s365_minutes": 900}])
    out = rb.blend(f)
    # 365 척도는 표본이 모자라 기본값으로 바뀐다 — 셋 다 같은 출전이면 1/3 씩
    s365 = rb.S365_REF_MU + (7.0 - rb.S365_MU) * rb.S365_REF_SD / rb.S365_SD
    want = (7.0 + rb.SS_MU + s365) / 3
    assert abs(float(out["ss_rating"].iloc[0]) - want) < 1e-6
    assert abs(float(out["ss_share_365"].iloc[0]) - 1 / 3) < 1e-6
    # 365 가 반만 반영했으면 몫도 줄어든다
    out2 = rb.blend(f.assign(s365_minutes=450))
    assert float(out2["ss_share_365"].iloc[0]) < 1 / 3


def test_blend_lite_does_not_double_count_fotmob() -> None:
    fm = 7.2
    f = pd.DataFrame([{"squad": "A", "player": "P", "pos": "MF", "ss_rating": float(rb.fm_to_ss(fm)), "ss_minutes": 900,
                       "fm_rating": fm, "fm_minutes": 900, "s365_rating": None, "s365_minutes": None}])
    out = rb.blend(f, lite=True)
    assert abs(float(out["ss_rating"].iloc[0]) - float(rb.fm_to_ss(fm))) < 1e-9     # FotMob 하나뿐 — 두 번 세지 않음
