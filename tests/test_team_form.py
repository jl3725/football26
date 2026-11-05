"""TEAM FORM(v3.15) — 팀 승점이 스쿼드 수준 대비 초과·미달이면 선수 OVR ±2(출전·경기 수 비례). 2026-11-05 사용자: 라치오·맨유."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import ratings_v3 as rv3  # noqa: E402


def test_team_form_adj_scales_and_caps() -> None:
    assert rv3.team_form_adj(None, 900, 10) == 0.0
    assert rv3.team_form_adj(0.8, 900, 10) == 2.0                         # 0.8 ppg 초과 × 2.5 = 2 (상한)
    assert rv3.team_form_adj(-1.5, 900, 10) == -2.0                       # 하한
    assert abs(rv3.team_form_adj(0.4, 450, 8) - 0.5) < 1e-9               # 1.0 × 출전 절반
    assert abs(rv3.team_form_adj(0.4, 900, 4) - 0.5) < 1e-9               # 경기 수 절반(시즌 초)


def test_team_residuals_from_standings() -> None:
    teams = [f"T{i}" for i in range(10)]
    rows = []
    for i, t in enumerate(teams):
        for k in range(14):
            rows.append({"squad": t, "minutes": 900, "_ovr_base": 70 + i})
    frame = pd.DataFrame(rows)
    st = pd.DataFrame([{"squad": t, "played": 10, "points": 10 + 2 * i} for i, t in enumerate(teams)])
    st.loc[st["squad"] == "T0", "points"] = 25                             # 약한 스쿼드가 승점을 많이 땀
    st.loc[st["squad"] == "T9", "points"] = 10                             # 강한 스쿼드가 못 땀
    r = rv3.team_residuals(frame, st)
    assert r["T0"][0] > 0.5 and r["T9"][0] < -0.5 and r["T0"][1] == 10
    assert rv3.team_residuals(frame, st.head(5)) == {}                     # 팀 수 모자람


def test_absolute_ovr_includes_team_part() -> None:
    # 몸값 낮고 평점 높은 선수(라치오형) — 올릴 '몫'(평점 수준까지)이 넉넉해 +2 전부
    kw = dict(value=5e6, ss_rating=7.45, minutes=900, age=27, pos_group="MF", prev_minutes=2000, prev_ss_rating=7.2)
    base = rv3.absolute_ovr(exact=True, **kw)
    parts: list = []
    up = rv3.absolute_ovr(exact=True, team_resid=0.9, team_games=10, _parts=parts, **kw)
    assert up > base and dict(parts).get("team") == 2.0
    down = rv3.absolute_ovr(exact=True, team_resid=-0.9, team_games=10, **kw)
    assert down < base
    # 이미 평점 수준 이상인 비싼 선수(에제형) — 팀이 잘해도 더 안 올리고, 못하면 그대로 내린다
    kw2 = dict(value=80e6, ss_rating=6.85, minutes=900, age=27, pos_group="MF", prev_minutes=2000, prev_ss_rating=6.9)
    base2 = rv3.absolute_ovr(exact=True, **kw2)
    parts2: list = []
    assert rv3.absolute_ovr(exact=True, team_resid=0.9, team_games=10, _parts=parts2, **kw2) == base2 and "team" not in dict(parts2)
    assert rv3.absolute_ovr(exact=True, team_resid=-0.9, team_games=10, **kw2) < base2
