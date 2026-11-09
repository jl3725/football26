"""이변(SHOCK) = 경기 전 이길 확률 · 경기 요약 맥락 줄(2026-11-09 사용자 — UPSET 대신, 예측 적중 대신 경기 요소)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import match_center as mc  # noqa: E402
import match_review as mrv  # noqa: E402


def _m(hg, ag, **kw):
    return {"home": {"team": "Brest", "goals": hg, **kw.get("h", {})}, "away": {"team": "Lyon", "goals": ag, **kw.get("a", {})}}


def test_shock_uses_pre_match_probability_first() -> None:
    pre = {"model": {"h": 0.18, "d": 0.27, "a": 0.55}, "elo": {"h": 0.30, "d": 0.28, "a": 0.42}}
    assert mc.upset_note(_m(2, 0), pre) == "경기 전 이길 확률 18%(모델) · Brest 승"
    assert mc.upset_note(_m(0, 2), pre) == ""                                  # 이길 확률 55% 쪽 승리 — 이변 아님
    assert mc.upset_note(_m(2, 0), {"elo": {"h": 0.2, "d": 0.3, "a": 0.5}}).endswith("(Elo 기준) · Brest 승")
    assert mc.upset_note(_m(1, 1), pre) == ""                                  # 무승부는 이변 아님
    # 예측 기록이 없는 경기만 예전 규칙(OVR 5 이상 낮은 쪽이 이김)
    old = _m(2, 0, h={"ovr": 72}, a={"ovr": 78})
    assert mc.upset_note(old, None) == "전력 72 팀이 78 팀을 꺾음" and mc.upset_note(old, {"model": {"h": 0.4, "d": 0.3, "a": 0.3}}) == ""


def test_streak_words() -> None:
    from api.main import _streak
    assert _streak(list("LWWW")) == "3연승" and _streak(list("WLLL")) == "3연패"
    assert _streak(list("WDWDW")) == "5경기 무패" and _streak(list("WDLDL")) == "4경기 무승" and _streak(list("WL")) == ""


def _p():
    return {"state": "post", "detail": "FT", "score": {"home": 2, "away": 0},
            "goals": [{"side": "home", "m": 30, "minute": "30'", "scorer": "Del Castillo", "assist": "", "kind": "goal"},
                      {"side": "home", "m": 70, "minute": "70'", "scorer": "Ajorque", "assist": "", "kind": "goal"}],
            "cards": [], "pens": [], "stats": {}, "venue": "", "attendance": None}


def test_summary_has_match_factors_not_prediction_scoreboard() -> None:
    ctx = {"shock": "경기 전 이길 확률 18%(모델) · Brest 승", "xg": {"home": 0.7, "away": 1.9},
           "top": {"player": "Romain Del Castillo", "team": "Brest", "rating": 8.64},
           "form": {"home": {"streak": "3연승", "rank": 6}}, "absent": {"away": ["Corentin Tolisso", "Malick Fofana"]}}
    rv = mrv.build(_p(), "Brest", "Lyon", fans={"h": 0.2, "d": 0.2, "a": 0.6}, model={"h": 0.18, "d": 0.27, "a": 0.55}, ctx=ctx)
    lines = rv["lines"]
    assert lines[0] == "이변 — 경기 전 이길 확률 18%(모델) · Brest 승"
    assert "xG 0.7–1.9 · 내용은 Lyon 우세" in lines
    assert "평점 1위 Romain Del Castillo(Brest) 8.6 · FotMob" in lines
    assert "Brest 3연승 · 리그 6위" in lines and "Lyon 결장 — Corentin Tolisso, Malick Fofana" in lines
    assert not any("적중" in x or "빗나감" in x for x in lines)               # 예측 성적은 요약에서 빼고
    assert rv["predictions"]                                                  # predictions 칸엔 남는다
