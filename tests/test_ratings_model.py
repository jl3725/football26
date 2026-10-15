from __future__ import annotations

import pandas as pd

import build_team_unit_metrics as um
import ratings_v3 as rv3


def test_team_pct_ties_share_value_and_missing_stays_missing() -> None:
    um._SHRINK_W = 1.0
    p = um.pct_map({"Arsenal": 0.0, "Brighton": 0.0, "Chelsea": 0.0, "Everton": 0.0}, True)
    assert len(set(p.values())) == 1                      # 전원 동률 → 같은 값(예전엔 알파벳 순 99·94…)
    assert um.pct_map({"A": None, "B": None, "C": None}, True) == {"A": None, "B": None, "C": None}
    assert um.idx(None) is None
    assert um.sum_or_none(None, None) is None


def test_team_pct_reflects_magnitude_and_shrinks_early_season() -> None:
    um._SHRINK_W = 1.0
    full = um.pct_map({"A": 3.0, "B": 1.0, "C": 1.1, "D": 0.9}, True)
    assert full["A"] > 0.9 and abs(full["B"] - full["C"]) < 0.1   # 근소한 차이는 근소하게
    um._SHRINK_W = 0.6
    early = um.pct_map({"A": 3.0, "B": 1.0, "C": 1.1, "D": 0.9}, True)
    assert 0.5 < early["A"] < full["A"]
    um._SHRINK_W = 1.0


def test_class_rating_discounts_weaker_league_and_small_samples() -> None:
    epl = rv3.class_ss(8.44, 658, 6.97, 1540, "ATT", league_level=100)
    por = rv3.class_ss(8.44, 658, 6.97, 1540, "ATT", league_level=90.7)
    assert por < epl < 8.0                                  # 600분 고평점이 그대로 반영되지 않음


def test_line_of_accepts_its_own_labels() -> None:
    # ovr_of_row 는 line_of_row 결과를 다시 넣는다 — "DEF"·"ATT" 가 MID 로 바뀌면 안 된다
    assert [rv3.line_of(x) for x in ("GK", "DEF", "MID", "ATT")] == ["GK", "DEF", "MID", "ATT"]


def test_prev_season_from_weaker_league_counts_less() -> None:
    # Tzolis: EPL 362분 6.90 + 직전 시즌 벨기에 3,068분 7.71
    moved = rv3.class_ss(6.90, 362, 7.71, 3068, "ATT", league_level=100, prev_league_level=88.5)
    stayed = rv3.class_ss(6.90, 362, 7.71, 3068, "ATT", league_level=100, prev_league_level=100)
    assert moved < stayed - 0.15


def test_gk_small_sample_and_age_premium() -> None:
    # 3연속 골든글러브 31세 €30M vs 6경기 선방률 75% 24세 €40M — 예전엔 89 vs 90
    raya = rv3.absolute_ovr(value=30e6, ss_rating=7.28, minutes=540, age=31, pos_group="GK",
                            gk_save_pct=70.6, gk_cs_pct=50.0, prev_minutes=3330,
                            prev_gk_save_pct=69.8, prev_gk_cs_pct=51.4)
    verb = rv3.absolute_ovr(value=40e6, ss_rating=7.58, minutes=540, age=24, pos_group="GK",
                            gk_save_pct=75.0, gk_cs_pct=66.7, prev_minutes=3420,
                            prev_gk_save_pct=71.7, prev_gk_cs_pct=26.3)
    assert raya > verb


def test_missing_market_value_uses_fallback() -> None:
    no_val = rv3.absolute_ovr(value=None, ss_rating=6.9, minutes=900, age=28, pos_group="GK")
    prev_val = rv3.absolute_ovr(value=None, ss_rating=6.9, minutes=900, age=28, pos_group="GK", prev_value=22e6)
    assert no_val >= 70 and prev_val > no_val           # 예전엔 60 에서 시작해 62


def test_form_percentile_scale() -> None:
    rows = [{"player": f"p{i}", "pos": "FW", "tm_position": "Centre-Forward", "ss_rating": 6.4 + i * 0.02,
             "minutes": 600, "goals": 0, "assists": 0} for i in range(100)]
    rows += [{"player": f"g{i}", "pos": "GK", "tm_position": "Goalkeeper", "ss_rating": 6.9 + i * 0.01,
              "minutes": 600, "goals": 0, "assists": 0} for i in range(20)]
    out = rv3.add_form_column(pd.DataFrame(rows))
    att = out[out.pos == "FW"]["_form"]
    gk = out[out.pos == "GK"]["_form"]
    assert att.max() == 99 and (att >= 99).sum() == 1        # 99 는 포지션 최상위만
    assert 70 <= att.median() <= 74 and 68 <= gk.median() <= 76   # GK 도 같은 척도(예전 중앙값 96)
