"""Elo 기준 예측(src/team_elo.wdl) · 예측 기록의 ClubElo → Elo 기준 옮기기(scripts/log_predictions.migrate_elo)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]

import team_elo as te  # noqa: E402


def test_wdl_keeps_expected_score_and_sums_to_one():
    for d in (-600, -200, -50, 0, 65, 300, 900):
        ph, pd_, pa = te.wdl(float(d), 0.27, 350.0)
        assert abs(ph + pd_ + pa - 1.0) < 1e-9
        assert abs((ph + pd_ / 2) - te.win_prob(float(d))) < 1e-9          # Elo 이길 기대치 그대로
        assert min(ph, pd_, pa) > 0
    assert te.wdl(0.0, 0.27, 350.0)[1] > te.wdl(500.0, 0.27, 350.0)[1]    # 차이가 작을수록 무승부가 크다


def test_fit_draw_recovers_draw_rate():
    samples = [(0.0, "D")] * 30 + [(0.0, "H")] * 35 + [(0.0, "A")] * 35 + [(400.0, "H")] * 80 + [(400.0, "D")] * 10 + [(400.0, "A")] * 10
    fit = te.fit_draw(samples)
    ph, pd_, pa = te.wdl(0.0, fit["draw_max"], fit["draw_width"])
    assert 0.24 <= pd_ <= 0.33 and fit["n"] == len(samples)


def test_migrate_moves_clubelo_and_fills_own(monkeypatch):
    import log_predictions as lp
    monkeypatch.setattr(lp.api, "_elo_pred", lambda h, a, d: {"h": 0.5, "d": 0.25, "a": 0.25} if h != "Nowhere FC" else None)
    rows = {"1": {"home": "Arsenal", "away": "Chelsea", "date": "2026-10-18", "elo_h": 0.4, "elo_d": 0.3, "elo_a": 0.3, "elo_ver": None},
            "2": {"home": "Nowhere FC", "away": "Chelsea", "date": "2026-10-18", "elo_h": None, "elo_d": None, "elo_a": None},
            "3": {"home": "Lyon", "away": "Nice", "date": "2026-10-27", "elo_h": 0.6, "elo_d": 0.2, "elo_a": 0.2, "elo_ver": "own-v1"}}
    moved, filled = lp.migrate_elo(rows)
    assert (moved, filled) == (1, 1)
    assert rows["1"]["clubelo_h"] == 0.4 and rows["1"]["elo_h"] == 0.5 and rows["1"]["elo_ver"] == "own-v1"
    assert rows["2"].get("elo_ver") is None                                   # Elo 없는 팀 — 비워 둠
    assert rows["3"]["elo_h"] == 0.6 and "clubelo_h" not in rows["3"]          # 이미 Elo 기준인 행은 그대로
    assert lp.migrate_elo(rows) == (0, 0)                                     # 두 번 돌려도 같다
