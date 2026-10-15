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
    one_min = rv3.absolute_ovr(value=None, ss_rating=0, minutes=1, age=None, pos_group="MID")
    regular = rv3.absolute_ovr(value=None, ss_rating=6.95, minutes=900, age=28, pos_group="DEF", prev_minutes=2400,
                               prev_ss_rating=6.95)
    prev_val = rv3.absolute_ovr(value=None, ss_rating=6.95, minutes=900, age=28, pos_group="DEF", prev_minutes=2400,
                                prev_ss_rating=6.95, prev_value=40e6)
    assert one_min <= 68 and regular >= 74 and prev_val > regular   # 1분 유망주 79·주전 62 같은 역전 없음


def test_proven_veteran_keeps_level() -> None:
    # 같은 평점·같은 시장가치 기준점이면 41세 주전(Modrić)이 시장가 나이 할인만큼 깎이지 않는다
    kw = dict(value=3.5e6, ss_rating=7.07, minutes=354, pos_group="MID", prev_minutes=2811, prev_ss_rating=7.53,
              league_level=96.1)
    old, young = rv3.absolute_ovr(age=41, **kw), rv3.absolute_ovr(age=27, **kw)
    assert old - young >= 8
    bench = rv3.absolute_ovr(age=41, value=3.5e6, ss_rating=7.07, minutes=200, pos_group="MID", league_level=96.1)
    assert bench < old                                   # 출전 검증이 없으면 나이 보정도 적다


def test_league_weight_applies_beyond_perf_cap() -> None:
    # 성능 보정 상한(+3.5)에 걸린 최상위도 약한 리그면 낮게 — 예전엔 상한에 리그 보정이 묻혔다
    kw = dict(value=40e6, ss_rating=7.9, minutes=720, age=26, pos_group="DEF", prev_minutes=2900, prev_ss_rating=7.8)
    epl, por = rv3.absolute_ovr(league_level=100, **kw), rv3.absolute_ovr(league_level=90.7, **kw)
    assert epl - por >= 2
    gk = dict(value=40e6, ss_rating=7.06, minutes=720, age=27, pos_group="GK", gk_save_pct=81, gk_cs_pct=50,
              prev_minutes=2906, prev_gk_save_pct=79.7, prev_gk_cs_pct=63.6)
    assert rv3.absolute_ovr(league_level=90.7, **gk) <= 88       # Diogo Costa 90 → 88


def test_expensive_breakout_is_not_a_proven_star() -> None:
    # 23세·€120M(직전 €75M)·한 시즌 활약 vs 27세·€120M(직전 €120M)·수년 검증 — 예전엔 둘 다 91
    kw = dict(value=120e6, minutes=503, pos_group="MID", league_level=100)
    anderson = rv3.absolute_ovr(age=23, ss_rating=7.55, prev_minutes=3331, prev_ss_rating=7.34, prev_value=75e6, **kw)
    rice = rv3.absolute_ovr(age=27, ss_rating=7.35, prev_minutes=3094, prev_ss_rating=7.46, prev_value=120e6, **kw)
    assert rice - anderson >= 2 and anderson <= 88          # v3.5: Rice 90 · Anderson 88


def test_value_jump_guard_ignores_tiny_prev_value() -> None:
    # 직전 시장가치 €150K(매칭 오류·1군 데뷔)는 '급등'으로 보지 않는다 — Cho 77→60 같은 폭락 방지
    kw = dict(value=15e6, ss_rating=6.93, minutes=76, age=22, pos_group="ATT", prev_minutes=1667,
              prev_ss_rating=6.78, league_level=100)
    assert rv3.absolute_ovr(prev_value=150e3, **kw) == rv3.absolute_ovr(prev_value=None, **kw)


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


def _squad_row(name, line, value, ss, minutes, form, age=27):
    return {"player": name, "squad": "X", "_line": line, "market_value_eur": value, "ss_rating": ss,
            "minutes": minutes, "prev_minutes": 2500, "prev_ss_rating": ss, "age": age, "_form": form,
            "_league_level": 100}


def test_team_ratings_one_gk_and_record_adjustment() -> None:
    rows = [_squad_row("GK1", "GK", 30e6, 7.0, 540, 98), _squad_row("GK2", "GK", 28e6, 7.0, 0, None)]
    rows += [_squad_row(f"D{i}", "DEF", 40e6, 7.0, 540, 70) for i in range(4)]
    rows += [_squad_row(f"M{i}", "MID", 40e6, 7.0, 540, 70) for i in range(4)]
    rows += [_squad_row(f"A{i}", "ATT", 40e6, 7.0, 540, 70) for i in range(3)]
    df = pd.DataFrame(rows)
    base = rv3.team_ratings(df, "X")
    # 수비 라인은 GK 1명까지 — 예전엔 상위 4명에 GK 둘(Alisson·Mamardashvili)이 들어갔다
    assert sum(1 for x in base["units"]["defense"] if x["player"].startswith("GK")) == 1
    # GK 는 폼(Sofascore)을 섞지 않는다 — 폼 98 이어도 OVR 그대로
    gk = next(x for x in base["units"]["defense"] if x["player"] == "GK1")
    assert gk["strength"] == rv3.ovr_of_row(pd.Series(rows[0]))
    # 실적 보정: 리그 평균(50) 은 0, 1 표준편차(70) 는 +1, 상한 ±2.5
    same = rv3.team_ratings(df, "X", perf={"attack": 50, "midfield": 50, "defense": 50})
    good = rv3.team_ratings(df, "X", perf={"attack": 50, "midfield": 50, "defense": 70})
    top = rv3.team_ratings(df, "X", perf={"attack": 50, "midfield": 50, "defense": 200})
    assert same["defense"] == base["defense"] and good["perf_adj"]["defense"] == 1.0
    assert top["perf_adj"]["defense"] == rv3.TEAM_PERF_MAX
