"""포지션별 OVR(src/position_ovr.py) — 실제로 뛴 자리만, 땜질 자리는 낮게, 오래 뛴 자리로 대표가 서서히 옮겨 간다.

2026-11-02 사용자: 베르나르두처럼 AM·CM 둘 다 되는 선수는 포지션마다 OVR, 레위스스켈리처럼 LB → DM 으로 옮긴 선수는
오래 뛸수록 그 자리가 대표가 되게(A안). 숙련도는 깎이지 않게. 에제는 DM 을 뛴 적이 없는데 DM 84, 소보슬라이 땜질 RB 가
대표와 거의 같은 건 이상하다(1씩만 깎이는 식).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import position_ovr as po  # noqa: E402
import position_templates as ptpl  # noqa: E402

ZERO = {"CB": 0.0, "FB": 0.0, "DM": 0.0, "CM": 0.0, "AM": 0.0, "W": 0.0, "ST": 0.0}


def test_only_positions_actually_played() -> None:
    # 에제: FotMob 목록 CAM·LW·CM·CDM 이지만 DM 선발은 지난 시즌 1경기(0.5경기치) — DM 은 후보가 아니다
    ex = po.experience({"LW": 8.0, "AM": 8.0, "CM": 7.0, "DM": 0.5}, ["AM"])
    assert "DM" not in ex and {"LW", "AM", "CM"} <= set(ex)


def test_stopgap_position_is_clearly_lower() -> None:
    # 소보슬라이: DM 14 · AM 9.5 · RB 5(지난 시즌 10경기) — RB 는 대표보다 3 이상 낮아야
    prim = ["DM", "AM"]
    res = po.choose(89.0, po.experience({"DM": 14.0, "AM": 9.5, "RB": 5.0}, prim), ZERO, prim)
    assert res["main"] in {"DM", "AM"}
    assert res["ovr"] - res["by_role"]["RB"] >= 3
    two = po.choose(80.0, po.experience({"CB": 25.0, "RB": 2.0}, ["CB"]), ZERO, ["CB"])
    assert two["ovr"] - two["by_role"]["RB"] >= 5               # 두어 경기치 땜질은 더 낮게


def test_main_moves_to_new_position_gradually() -> None:
    early = po.choose(82.0, po.experience({"LB": 17.0, "DM": 3.0}, []), ZERO)
    later = po.choose(82.0, po.experience({"LB": 17.0, "DM": 30.0}, []), ZERO)
    assert early["main"] == "LB" and later["main"] == "DM"
    assert later["by_role"]["LB"] == later["ovr"]                 # 예전 자리 익숙함은 줄지 않는다


def test_familiarity_only_grows() -> None:
    vals = [po.choose(80.0, po.experience({"CM": 20.0, "AM": s}, []), ZERO)["by_role"]["AM"] for s in (2, 4, 8, 16)]
    assert vals == sorted(vals)


def test_main_ovr_has_no_familiarity_penalty() -> None:
    res = po.choose(80.0, po.experience({"CB": 3.0}, ["CB"]), {"CB": 0.0}, ["CB"])
    assert res["main"] == "CB" and res["ovr"] == 80 and res["fam"]["CB"] == 1.0


def test_tie_prefers_current_position() -> None:
    # 레위스스켈리: LB 를 더 많이 뛰었어도 TM·FotMob 둘 다 DM — 같은 OVR 이면 지금 쓰이는 자리
    prim = ["DM"]
    res = po.choose(82.0, po.experience({"LB": 14.0, "DM": 10.0}, prim), ZERO, prim)
    assert res["by_role"]["LB"] == res["by_role"]["DM"] and res["main"] == "DM"


def test_neighbour_share_does_not_create_positions() -> None:
    ex = po.experience({"DM": 30.0, "CB": 1.0}, ["DM"])
    assert set(ex) == {"DM"}                                      # CM·AM·CB 는 실제로 안 뛰었으면 없음
    ex = po.experience({"CM": 10.0, "AM": 4.0}, ["CM"])
    assert ex["AM"] == 4.0 + 4.0                                 # 같은 라인 이웃 몫은 이미 뛴 자리에, 직접 뛴 만큼까지


def test_contribution_is_scale_neutral() -> None:
    """잘하는 선수는 지표도 높다 — 같은 OVR 의 보통 백분위를 빼면 상위권만 오르는 일이 없다."""
    rng = np.random.default_rng(0)
    n = 400
    common = rng.uniform(60, 90, n)
    keys = ptpl.TEMPLATES["CM"]["radar"]
    data = {"minutes": np.full(n, 2000.0), "_eff_minutes": np.full(n, 2000.0), "_template": ["CM"] * n}
    for k in keys:
        _label, col, inv, _rule = ptpl.M[k]
        v = common + rng.normal(0, 5, n)
        data[col] = -v if inv else v
    f = pd.DataFrame(data)
    out = po.contributions({"X": f}, {"X": pd.Series(common)}, templates=["CM"])["X"]["CM"]
    top = out[common >= 85]
    assert abs(float(top.mean())) < 0.4 and abs(float(out.mean())) < 0.1
    raw = po.contributions({"X": f}, None, templates=["CM"])["X"]["CM"]
    assert float(raw[common >= 85].mean()) > 1.0                  # 보통 백분위를 안 빼면 상위권이 크게 오른다
