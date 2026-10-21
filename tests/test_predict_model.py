from __future__ import annotations

import pandas as pd

import predict_model as pm


def _ms(rows):
    """(home, away, hg, ag, hxg, axg) → match_stats 형태(홈 행만으로 충분)."""
    out = []
    for i, (h, a, hg, ag, hx, ax) in enumerate(rows):
        out.append({"event_id": str(i), "date": f"2026-09-{i + 1:02d}", "comp_code": "eng.1", "squad": h, "opponent": a,
                    "home_away": "H", "gf": hg, "ga": ag, "xg": hx, "xga": ax, "shots": 12, "opp_shots": 10})
    return pd.DataFrame(out)


def test_probabilities_sum_to_one_and_extras_sane() -> None:
    r = pm.summarize(1.6, 0.9, -0.08)
    assert abs(r["h"] + r["d"] + r["a"] - 1) < 1e-6
    assert r["h"] > r["a"] and 0 < r["btts"] < 1 and 0 < r["o25"] < 1
    assert r["score"] in {"1-0", "1-1", "2-0", "2-1"}


def test_dixon_coles_raises_low_score_draws() -> None:
    plain = pm.score_matrix(1.2, 1.1, 0.0)
    dc = pm.score_matrix(1.2, 1.1, -0.1)
    assert dc[0][0] > plain[0][0] and dc[1][1] > plain[1][1]


def test_stronger_team_by_results_and_ovr_is_favoured() -> None:
    mt = pm.league_matches(_ms([
        ("A", "B", 3, 0, 2.5, 0.4), ("C", "A", 0, 2, 0.6, 1.9), ("B", "C", 1, 1, 1.0, 1.1),
        ("A", "C", 2, 0, 2.0, 0.5), ("B", "A", 0, 1, 0.5, 1.4), ("C", "B", 1, 0, 1.2, 0.8),
    ]))
    st = pm.build_state(mt, {"A": 86, "B": 76, "C": 77})
    ab = pm.predict(st, "A", None, "B")
    ba = pm.predict(st, "B", None, "A")
    assert ab["h"] > 0.5 and ba["a"] > ba["h"]          # 홈이든 원정이든 A 우세
    assert ab["xg_h"] > ab["xg_a"]


def test_cross_league_uses_ovr_gap(monkeypatch) -> None:
    monkeypatch.setattr(pm, "cross_calibration", lambda: {})     # 봇이 매일 다시 쓰는 data/model_cross.json 에 기대지 않게
    s1 = pm.build_state(pm.league_matches(_ms([("X", "Y", 1, 1, 1.2, 1.2)])), {"X": 90, "Y": 75})
    s2 = pm.build_state(pm.league_matches(_ms([("Z", "W", 1, 1, 1.2, 1.2)])), {"Z": 74, "W": 80})
    r = pm.predict(s1, "X", s2, "Z")
    assert r["h"] > 0.55                                 # OVR 90 홈 vs 74 원정


def test_unknown_team_returns_none() -> None:
    st = pm.build_state(pm.league_matches(_ms([("A", "B", 1, 0, 1.0, 0.5)])), {"A": 80, "B": 78})
    assert pm.predict(st, "A", None, "Nobody") is None


def test_draw_multiplier_and_cross_calibration(monkeypatch) -> None:
    """리그 간 — 무승부 배수(dk)는 무승부만 줄이고 합은 1, 보정 파일 값(기본 득점·dk)을 쓴다(2026-10-21 backtest_cross)."""
    a, b = pm.summarize(1.5, 1.2, 0.0), pm.summarize(1.5, 1.2, 0.0, dk=0.7)
    assert b["d"] < a["d"] and abs(b["h"] + b["d"] + b["a"] - 1) < 1e-3
    assert abs(b["h"] / b["a"] - a["h"] / a["a"]) < 0.02          # 승·패 비율은 그대로
    s1 = pm.build_state(pm.league_matches(_ms([("X", "Y", 1, 1, 1.2, 1.2)])), {"X": 80, "Y": 80})
    s2 = pm.build_state(pm.league_matches(_ms([("Z", "W", 1, 1, 1.2, 1.2)])), {"Z": 80, "W": 80})
    monkeypatch.setattr(pm, "cross_calibration", lambda: {"mu_h": 1.85, "mu_a": 1.36, "dk": 0.75, "n": 215})
    r = pm.predict(s1, "X", s2, "Z")
    base = pm.summarize(1.85, 1.36, pm.PARAMS["cross_rho"], 0.75)
    assert abs(r["d"] - base["d"]) < 0.02 and abs(r["xg_h"] - 1.85) < 0.1   # 같은 OVR·리그 평균 팀 = 학습 기본 득점
    monkeypatch.setattr(pm, "cross_calibration", lambda: {})
    r0 = pm.predict(s1, "X", s2, "Z")
    assert abs(r0["xg_h"] - pm.MU_CROSS[0]) < 0.1                    # 파일 없으면 기본값
    assert pm.predict(s1, "X", None, "Y")["d"] > r["d"]               # 같은 리그는 무승부 배수 없음
