from __future__ import annotations

import pandas as pd

import rating_blend as rb
import ratings_v3 as rv3


def _fm(rows):
    return pd.DataFrame(rows, columns=["fotmob_id", "player", "squad", "rating", "minutes"])


def test_fotmob_scale_and_average() -> None:
    assert abs(rb.fm_to_ss(rb.FM_MU) - rb.SS_MU) < 1e-9                  # 평균은 평균으로
    assert abs(rb.fm_to_ss(rb.FM_MU + rb.FM_SD) - rb.SS_MU - rb.SS_SD) < 1e-9   # 1 표준편차는 1 표준편차로
    tables = {("EPL", "2026_2027"): _fm([[7, "A B", "X", 7.79, 600]]),
              ("EPL", "2025_2026"): _fm([[7, "A B", "Y", 7.2, 1600]]),
              ("LaLiga", "2024_2025"): _fm([[7, "A B", "Z", 6.9, 2000]])}
    frame = pd.DataFrame([{"player": "A B", "squad": "X", "ss_rating": 7.5, "prev_ss_rating": 7.06, "prev_squad": "Y",
                           "prev_minutes": 1636, "prev_league": "EPL"},
                          {"player": "C D", "squad": "X", "ss_rating": 6.9, "prev_ss_rating": None, "prev_squad": None,
                           "prev_minutes": None, "prev_league": None}])
    out = rb.blend(rb.attach(frame, "EPL", None, lambda lg, s: tables.get((lg, s))))
    a, c = out.iloc[0], out.iloc[1]
    assert abs(a["ss_rating"] - (7.5 + rb.fm_to_ss(7.79)) / 2) < 1e-9     # 두 출처 평균
    assert a["ss_rating_sofa"] == 7.5 and a["fm_rating"] == 7.79           # 원래 값은 화면용으로 남김
    assert abs(a["prev_ss_rating"] - (7.06 + rb.fm_to_ss(7.2)) / 2) < 1e-9
    # 2시즌 전은 FotMob id 로 다른 리그(LaLiga)에서도 찾고, 유효 출전은 절반
    assert a["hist_league"] == "LaLiga" and a["hist_minutes"] == 1000
    assert c["ss_rating"] == 6.9 and pd.isna(c["fm_rating"])               # FotMob 에 없으면 Sofascore 그대로


def test_ovr_parts_add_up_to_ovr() -> None:
    rows = [
        {"market_value_eur": 2.5e6, "ss_rating": 7.5, "minutes": 540, "age": 35, "_line": "MID", "prev_ss_rating": 7.07,
         "prev_minutes": 1636, "_league_level": 100},
        {"market_value_eur": 5e7, "prev_market_value_eur": 3e7, "ss_rating": 6.6, "minutes": 10, "age": 16, "_line": "MID",
         "prev_ss_rating": 6.77, "prev_minutes": 157, "_league_level": 100},
        {"market_value_eur": 3e7, "ss_rating": 7.0, "minutes": 540, "age": 31, "_line": "GK", "gk_save_pct": 75,
         "gk_cs_pct": 40, "_league_level": 100},
    ]
    for r in rows:
        p = rv3.ovr_parts_of_row(r)
        assert p["ovr"] == rv3.ovr_of_row(r)
        assert abs(sum(x["value"] for x in p["parts"]) - p["ovr"]) <= 1.0     # 반올림 오차만
        assert p["parts"][0]["key"].startswith("base")
