"""수집 내용 신선도·팀 이름 맞추기 — 2026-11-03 '성공인데 이상한 수집' 전체 점검에서 나온 것들."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import content_progress as cp  # noqa: E402
import team_names as tn  # noqa: E402
from squads import canonical_squad  # noqa: E402


def _read(tables):
    return lambda t, lg: tables.get(t)


def test_progress_flags_stale_table_and_missing_team() -> None:
    sch = pd.DataFrame([{"comp_code": "eng.1", "status": "completed", "squad": s} for s in ("A", "B", "C") for _ in range(9)])
    stale = pd.DataFrame([{"squad": s, "minutes": 990 * 6} for s in ("A", "B", "C")])          # 팀당 6경기분(FBref 캐시)
    mapped = pd.DataFrame([{"squad": "A", "minutes": 990 * 9}, {"squad": "B", "minutes": 990 * 9},
                           {"squad": "C", "minutes": 990 * 2}])                                  # C 선수 대부분이 다른 팀으로
    got = cp.check_league("EPL", _read({"schedule_full": sch, "players": stale, "understat_players": mapped}))
    kinds = {(x["table"], x["kind"]) for x in got}
    assert ("players", "stale") in kinds and ("understat_players", "team") in kinds


def test_team_names_subset_tie_and_acronym() -> None:
    assert tn.best("Grasshopper Club Zürich", ["FC Zürich", "Grasshopper", "Basel"]) == "Grasshopper"
    assert tn.best("FC Zürich", ["FC Zürich", "Grasshopper"]) == "FC Zürich"
    assert tn.best("RZ Pellets WAC", ["Wolfsberger AC", "Austria Wien", "LASK"]) == "Wolfsberger AC"


def test_canonical_squad_takes_current_team_from_list() -> None:
    assert canonical_squad("Paris Saint Germain,Rennes", "Ligue1") == canonical_squad("Rennes", "Ligue1")
