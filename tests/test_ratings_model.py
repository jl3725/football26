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
