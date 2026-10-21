"""포지션 템플릿 — 세부 포지션 분류(DM·CM·AM 분리), 시도 수 역산·표본 부족, 중간 순위 백분위, 템플릿별 축."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import position_templates as pt  # noqa: E402


def test_template_of_splits_midfield() -> None:
    assert pt.template_of("Defensive Midfield") == "DM"
    assert pt.template_of("Central Midfield") == "CM"
    assert pt.template_of("Attacking Midfield") == "AM"
    assert pt.template_of("Second Striker") == "AM"
    assert pt.template_of("Right Midfield") == "W" and pt.template_of("Left Winger") == "W"
    assert pt.template_of("Left-Back") == "FB" and pt.template_of("Centre-Back") == "CB"
    assert pt.template_of(None, "DF") == "CB" and pt.template_of(None, "FW,MF") == "ST" and pt.template_of("", "MF") == "CM"
    # 미드필더 셋은 서로 다른 축을 쓴다
    radars = {k: set(pt.TEMPLATES[k]["radar"]) for k in ("DM", "CM", "AM")}
    assert radars["DM"] != radars["CM"] != radars["AM"] and "tkl" in radars["DM"] and "bigc" in radars["AM"]
    assert all(len(v["radar"]) == 8 for v in pt.TEMPLATES.values())


def test_attempts_and_low_sample() -> None:
    row = {"minutes": 630, "successful_dribbles_per90": 0.143, "dribble_success_pct": 100.0,
           "aerial_won_per90": 2.429, "aerial_won_pct": 50.0, "crosses_per90": 4.0}
    assert round(pt.attempts(row, "dribble")) == 1                    # 시즌 1회 시도의 100%
    assert round(pt.attempts(row, "aerial")) == 34
    assert round(pt.attempts(row, "cross")) == 28
    assert pt.attempts(row, None) is None


def test_midrank_percentile_handles_ties_and_inverse() -> None:
    pool = pd.DataFrame({"errors_per90": [0, 0, 0, 0, 0, 0, 0, 0, 0.2, 0.4], "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    assert pt.percentile(pool, "errors_per90", 0.0, inv=True) == 60   # 실수 0 = 동률 8명 → 중간(20% 위 + 절반) — 예전엔 20
    assert pt.percentile(pool, "errors_per90", 0.4, inv=True) == 5
    assert pt.percentile(pool, "x", 10, inv=False) == 95


def test_profile_excludes_low_from_average() -> None:
    pool = pt.add_derived(pd.DataFrame({
        "minutes": [900] * 5, "tm_position": ["Centre-Back"] * 5,
        "aerial_won_per90": [1, 2, 3, 4, 5], "aerial_won_pct": [40, 50, 60, 70, 80],
        "tackles_won_per90_ss": [0.5] * 5, "tackles_won_pct": [50, 60, 70, 80, 90],
        "ground_duels_won_pct": [40, 45, 50, 55, 60], "ground_duels_won_per90": [2] * 5}))
    row = pt.add_derived(pd.DataFrame([{"minutes": 450, "tm_position": "Centre-Back", "aerial_won_per90": 5, "aerial_won_pct": 80,
                                       "tackles_won_per90_ss": 0.1, "tackles_won_pct": 100,
                                       "ground_duels_won_pct": 60, "ground_duels_won_per90": 3}])).iloc[0]
    prof = pt.profile(row, pool, "CB")
    duel = next(c for c in prof["categories"] if c["name"] == "경합")
    tkl = next(m for m in duel["metrics"] if m["key"] == "tklp")
    assert tkl["low"] and tkl["att"] == 0                             # 태클 0.5회 시도 → 표본 부족
    ok = [m["pct"] for m in duel["metrics"] if not m["low"]]
    assert duel["avg"] == round(sum(ok) / len(ok))                    # 평균에서 뺀다
    # CB 레이더는 시도가 많은 지상 경합%를 쓴다(태클 성공%는 묶음에만) — 표본 부족 축이 레이더를 흔들지 않게
    axes = [r["axis"] for r in prof["radar"]]
    assert "지상 경합%" in axes and "태클 성공%" not in axes and not any(r["low"] for r in prof["radar"])


def test_padj_and_blend() -> None:
    assert round(pt.padj_factor(50), 2) == 1.0
    assert round(pt.padj_factor(61.2), 2) == 1.51                    # 아스날 26/27 — 수비 횟수 ×1.51
    assert pt.padj_factor(None) == 1.0
    cur = pd.DataFrame([{"player": "Gabriel", "squad": "Arsenal", "minutes": 630, "tm_position": "Centre-Back",
                         "aerial_won_pct": 50.0, "interceptions_per90_ss": 1.0},
                        {"player": "New Guy", "squad": "Burnley", "minutes": 900, "tm_position": "Centre-Back",
                         "aerial_won_pct": 60.0, "interceptions_per90_ss": 1.0}], index=[7, 9])
    prev = pd.DataFrame([{"player": "Gabriel", "squad": "Arsenal", "league": "EPL", "minutes": 2751,
                          "aerial_won_pct": 62.0, "interceptions_per90_ss": 0.75}])
    out = pt.enrich(cur, prev, {"Arsenal": 61.2, "Burnley": 45.0}, {("EPL", "Arsenal"): 60.0}, str.lower)
    g, n = out.loc[7], out.loc[9]
    assert list(out.index) == [7, 9]                                   # 인덱스 그대로(선수 행 찾기)
    assert g["_prior_minutes"] == 1350 and n["_prior_minutes"] == 0   # 지난 시즌 최대 15경기치, 기록 없으면 0
    assert round(g["aerial_won_pct"], 1) == round((50 * 630 + 62 * 1350) / 1980, 1)
    want = (1.0 * pt.padj_factor(61.2) * 630 + 0.75 * pt.padj_factor(60.0) * 1350) / 1980
    assert round(g["interceptions_per90_ss"], 3) == round(want, 3)   # 시즌마다 그 시즌 점유율로 보정한 뒤 섞음
    assert round(n["interceptions_per90_ss"], 3) == round(pt.padj_factor(45.0), 3)
    season = pt.enrich(cur, prev, {"Arsenal": 61.2}, {}, str.lower, blend=False)
    assert season.loc[7, "aerial_won_pct"] == 50.0 and season.loc[7, "_prior_minutes"] == 0
