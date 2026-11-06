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


def test_same_games_counted_few_minutes_apart_follow_fotmob() -> None:
    # Thijs Jansen — 같은 11경기를 FBref 990′ · FotMob 982′(한 경기 82′) → SEASON LOG 와 같은 982′
    mr = pd.DataFrame([{"date": "2026-10-31", "comp_code": "ned.1", "squad": "Cambuur", "fotmob_id": 7, "player": "Thijs Jansen",
                        "minutes": 82, "goals": 0, "assists": 0},
                       {"date": "2026-10-31", "comp_code": "ned.1", "squad": "Sevilla", "fotmob_id": 8, "player": "Auba",
                        "minutes": 82, "goals": 0, "assists": 0}])
    frame = pd.DataFrame([{"player": "Thijs Jansen", "squad": "Cambuur", "fm_id": 7, "goals": 0, "assists": 0, "minutes": 90},
                          {"player": "Auba", "squad": "Sevilla", "fm_id": 8, "goals": 1, "assists": 0, "minutes": 90}])
    out = st.apply_live_totals(frame, mr, "Eredivisie").set_index("player")
    assert out.loc["Thijs Jansen", "minutes"] == 82 and out.loc["Thijs Jansen", "_stats_src"] == "fotmob"
    assert out.loc["Auba", "minutes"] == 90 and out.loc["Auba", "_stats_src"] == "fbref"     # 골이 덜하면 경기를 빠뜨린 것


def test_no_match_table_keeps_fbref() -> None:
    out = st.apply_live_totals(FRAME, None, "EPL")
    assert list(out["goals"]) == [1, 3, 0] and set(out["_stats_src"]) == {"fbref"}
