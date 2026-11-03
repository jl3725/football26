"""xG 계열 대체 원천(FotMob) — Understat 가 없거나 낡을 때(2026-11-03 사용자 '대체 사이트')."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import fetch_match_stats as fms  # noqa: E402
import season_totals as st  # noqa: E402


def _mr():
    rows = []
    for d, (xg, npxg, xa) in (("2026-10-20", (0.5, 0.5, 0.2)), ("2026-10-27", (0.7, 0.3, 0.1)), ("2026-11-02", (0.3, 0.3, 0.4))):
        rows.append({"match_id": d, "date": d, "comp_code": "eng.1", "squad": "Arsenal", "opponent": "Chelsea", "home_away": "home",
                     "fotmob_id": "7", "player": "Bukayo Saka", "minutes": 90, "det": 1, "xg": xg, "npxg": npxg, "xa": xa,
                     "chances": 2, "shots": 3})
        rows.append({"match_id": d, "date": d, "comp_code": "eng.1", "squad": "Chelsea", "opponent": "Arsenal", "home_away": "away",
                     "fotmob_id": "9", "player": "Cole Palmer", "minutes": 90, "det": 1, "xg": 0.4, "npxg": 0.4, "xa": 0.2,
                     "chances": 1, "shots": 2})
    rows.append({"match_id": "x", "date": "2026-10-27", "comp_code": "eng.league_cup", "squad": "Arsenal", "opponent": "Hull",
                 "home_away": "home", "fotmob_id": "7", "player": "Bukayo Saka", "minutes": 90, "det": 1, "xg": 2.0, "npxg": 2.0,
                 "xa": 1.0, "chances": 5, "shots": 6})                                 # 컵 경기는 리그 xG 에 안 들어감
    return pd.DataFrame(rows)


def test_fotmob_xg_replaces_stale_weekly_but_not_understat_live() -> None:
    frame = pd.DataFrame([
        {"player": "Bukayo Saka", "squad": "Arsenal", "minutes": 90.0, "fm_id": 7, "_xg_src": "weekly",
         "xg_p90": 0.9, "npxg_p90": 0.9, "xa_p90": 0.1, "kp_p90": 1.0, "shots_p90": 2.0},
        {"player": "Cole Palmer", "squad": "Chelsea", "minutes": 270.0, "fm_id": 9, "_xg_src": "understat_live",
         "xg_p90": 0.55, "npxg_p90": 0.55, "xa_p90": 0.3, "kp_p90": 1.5, "shots_p90": 2.5},
        {"player": "No Record", "squad": "Arsenal", "minutes": 0.0, "fm_id": None, "_xg_src": "weekly",
         "xg_p90": None, "npxg_p90": None, "xa_p90": None, "kp_p90": None, "shots_p90": None},
    ])
    out = st.apply_fotmob_xg(frame, _mr(), "EPL")
    saka, palmer, nobody = out.iloc[0], out.iloc[1], out.iloc[2]
    assert saka["_xg_src"] == "fotmob"                                  # 주간 90′ < FotMob 270′ → 대체
    assert abs(saka["xg_p90"] - 0.5) < 1e-6 and abs(saka["xa_p90"] - round(0.7 / 3, 3)) < 1e-6   # 리그 3경기 합 / 270 × 90
    assert palmer["_xg_src"] == "understat_live" and palmer["xg_p90"] == 0.55   # Understat 최신값은 그대로
    assert nobody["_xg_src"] == "weekly" and nobody["xg_p90"] != nobody["xg_p90"]   # FotMob 기록 없는 선수는 그대로


def test_match_xg_filled_from_fotmob_when_understat_missing() -> None:
    df = pd.DataFrame([
        {"event_id": "1", "date": "2026-11-02", "comp_code": "eng.1", "squad": "Arsenal", "opponent": "Chelsea", "home_away": "H",
         "xg": None, "xga": None, "npxg": None, "npxga": None},
        {"event_id": "2", "date": "2026-10-20", "comp_code": "eng.1", "squad": "Arsenal", "opponent": "Chelsea", "home_away": "H",
         "xg": 1.9, "xga": 0.8, "npxg": 1.9, "npxga": 0.8},                            # Understat 값은 그대로
    ])
    out = fms._attach_fotmob_xg(df, "EPL", _mr())
    a, b = out.iloc[0], out.iloc[1]
    assert a["xg_src"] == "fotmob" and abs(a["xg"] - 0.3) < 1e-6 and abs(a["xga"] - 0.4) < 1e-6
    assert b["xg_src"] == "understat" and b["xg"] == 1.9
