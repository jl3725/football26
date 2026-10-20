"""리그 누적(골·도움·분)을 FotMob 경기별 기록으로 — 더 최신일 때만, 리그 경기만."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import season_totals as st  # noqa: E402

MR = pd.DataFrame([
    # 홀란 — 리그 2경기 3골 + 챔스 2골(리그 합산에서 빠져야)
    {"date": "2026-10-11", "comp_code": "eng.1", "squad": "Manchester City", "fotmob_id": 737066, "player": "Erling Haaland", "minutes": 80, "goals": 1, "assists": 0},
    {"date": "2026-10-17", "comp_code": "eng.1", "squad": "Manchester City", "fotmob_id": 737066, "player": "Erling Haaland", "minutes": 90, "goals": 2, "assists": 1},
    {"date": "2026-10-14", "comp_code": "uefa.champions", "squad": "Manchester City", "fotmob_id": 737066, "player": "Erling Haaland", "minutes": 90, "goals": 2, "assists": 0},
    # FotMob 이 한 경기를 빠뜨린 선수 — 분이 FBref 보다 적으면 FBref 유지
    {"date": "2026-10-17", "comp_code": "eng.1", "squad": "Arsenal", "fotmob_id": 1, "player": "Bukayo Saka", "minutes": 90, "goals": 0, "assists": 1},
    # FotMob id 없는 선수는 (팀, 이름)으로
    {"date": "2026-10-18", "comp_code": "eng.1", "squad": "Fulham", "fotmob_id": None, "player": "Joshua King", "minutes": 70, "goals": 1, "assists": 0},
])
FRAME = pd.DataFrame([
    {"player": "Erling Haaland", "squad": "Manchester City", "fm_id": 737066, "goals": 1, "assists": 0, "minutes": 80},
    {"player": "Bukayo Saka", "squad": "Arsenal", "fm_id": 1, "goals": 3, "assists": 2, "minutes": 450},
    {"player": "Joshua King", "squad": "Fulham", "fm_id": None, "goals": 0, "assists": 0, "minutes": 0},
])


def test_live_totals_league_only_and_newer_only() -> None:
    out = st.apply_live_totals(FRAME, MR, "EPL").set_index("player")
    h = out.loc["Erling Haaland"]
    assert (h["goals"], h["assists"], h["minutes"], h["_stats_src"], h["_stats_asof"]) == (3, 1, 170, "fotmob", "2026-10-17")
    s = out.loc["Bukayo Saka"]
    assert (s["goals"], s["minutes"], s["_stats_src"]) == (3, 450, "fbref")
    assert out.loc["Joshua King", "goals"] == 1 and out.loc["Joshua King", "_stats_src"] == "fotmob"


def test_no_match_table_keeps_fbref() -> None:
    out = st.apply_live_totals(FRAME, None, "EPL")
    assert list(out["goals"]) == [1, 3, 0] and set(out["_stats_src"]) == {"fbref"}
