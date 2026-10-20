"""세부 스탯 매일 — FBref 횟수 지표는 Sofascore 원본으로, xG 계열은 Understat 매일 수집으로(더 최신일 때만)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import merge_sofascore as ms  # noqa: E402
import season_totals as st  # noqa: E402


def test_fresh_fb_counts_only_when_newer() -> None:
    row = {"minutes": 450, "goals": 5, "npg_per90": 0.8}            # 페널티 골 = 5 − 0.8×5 = 1
    ss = {"minutesPlayed": 540, "totalShots": 24, "shotsOnTarget": 12, "totalCross": 6, "fouls": 3, "wasFouled": 9,
          "tacklesWon": 6, "interceptions": 3, "assists": 2, "goals": 7}
    out = ms.fresh_fb_counts(row, ss)
    assert out["sh_per90"] == 4.0 and out["ast_per90"] == round(2 / 6, 3)
    assert out["npg_per90"] == 1.0                                  # (7 − 1) / 6
    assert ms.fresh_fb_counts({**row, "minutes": 600}, ss) is None   # Sofascore 쪽이 오래됨 → FBref 유지


def test_understat_live_overlays_xg_when_newer() -> None:
    frame = pd.DataFrame([
        {"player": "Erling Haaland", "squad": "Manchester City", "minutes": 529, "xg_p90": 0.867, "xa_p90": 0.1},
        {"player": "Martin Ødegaard", "squad": "Arsenal", "minutes": 600, "xg_p90": 0.2, "xa_p90": 0.3},
        {"player": "Gabriel Jesus", "squad": "Arsenal", "minutes": 300, "xg_p90": 0.5, "xa_p90": 0.1},
    ])
    us = pd.DataFrame([
        {"squad": "Manchester City", "player": "Erling Haaland", "minutes": 621, "xg": 6.426, "np_xg": 6.426, "xa": 1.74,
         "key_passes": 4, "shots": 27, "xg_chain": 9.3},
        {"squad": "Arsenal", "player": "Martin Odegaard", "minutes": 540, "xg": 1.0, "np_xg": 1.0, "xa": 2.0,
         "key_passes": 20, "shots": 10, "xg_chain": 5.0},                       # 분이 적음 → 주간 값 유지
        {"squad": "Arsenal", "player": "G. Jesus", "minutes": 390, "xg": 2.6, "np_xg": 2.6, "xa": 0.4,
         "key_passes": 3, "shots": 12, "xg_chain": 3.0},                        # 성으로 매칭
    ])
    out = st.apply_understat_live(frame, us).set_index("player")
    assert out.loc["Erling Haaland", "xg_p90"] == round(6.426 / (621 / 90), 3)
    assert out.loc["Erling Haaland", "_xg_src"] == "understat_live"
    assert out.loc["Martin Ødegaard", "xg_p90"] == 0.2 and out.loc["Martin Ødegaard", "_xg_src"] == "weekly"
    assert out.loc["Gabriel Jesus", "_xg_src"] == "understat_live"
