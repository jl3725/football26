"""지난 시즌 Understat 다시 채우기 — 못 붙었던 행(xG·xG Chain 둘 다 0)만, 붙었던 행은 그대로."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import backfill_prev_xg as b  # noqa: E402


def test_backfill_only_unmatched_rows() -> None:
    df = pd.DataFrame([
        {"player": "Bruno Fernandes", "squad": "Manchester Utd", "xg_p90": 0.0, "npxg_p90": 0.15, "xa_p90": 0.62,
         "kp_p90": 1.86, "shots_p90": 2.5, "xg_chain_p90": 0.0},                 # 지난번 미매칭 → 채움
        {"player": "Bukayo Saka", "squad": "Arsenal", "xg_p90": 0.35, "npxg_p90": 0.319, "xa_p90": 0.344,
         "kp_p90": 2.492, "shots_p90": 2.854, "xg_chain_p90": 0.768},            # 붙었던 행 → 그대로
        {"player": "Nobody", "squad": "Manchester Utd", "xg_p90": 0.0, "npxg_p90": 0.0, "xa_p90": 0.0,
         "kp_p90": 0.0, "shots_p90": 0.0, "xg_chain_p90": 0.0},                  # Understat 에 없음 → 그대로
    ])
    u = pd.DataFrame([
        {"_key": b._key("Manchester Utd", "Bruno Fernandes"), "xg_p90": 0.348, "npxg_p90": 0.215, "xa_p90": 0.519,
         "kp_p90": 4.001, "shots_p90": 2.482, "xg_chain_p90": 0.758},
        {"_key": b._key("Arsenal", "Bukayo Saka"), "xg_p90": 9.9, "npxg_p90": 9.9, "xa_p90": 9.9,
         "kp_p90": 9.9, "shots_p90": 9.9, "xg_chain_p90": 9.9},
    ])
    new, n = b.backfill(df, u)
    assert n == 1
    assert new.loc[0, "kp_p90"] == 4.001 and new.loc[0, "xg_p90"] == 0.348
    assert new.loc[1].tolist() == df.loc[1].tolist() and new.loc[2].tolist() == df.loc[2].tolist()
