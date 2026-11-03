"""하부 컵 경기(FotMob playerStats 없음) 출전 분 · UEFA 예선 코드 — 2026-11-03 '성공인데 비어 있던' 컵·예선 수집 점검."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import allcomp_stats as acs  # noqa: E402
import comp_usage_live as cu  # noqa: E402
import fetch_fotmob_matches as fm  # noqa: E402


def _match():
    return {"id": 555, "status": {"utcTime": "2026-10-18T14:00Z"}, "home": {"id": 1, "name": "Alverca"},
            "away": {"id": 2, "name": "Tondela"}}


def _details():
    starters = [{"id": 11, "name": "A GK"}, {"id": 12, "name": "B Out"}] + [{"id": 20 + i, "name": f"S{i}"} for i in range(9)]
    return {"content": {"lineup": {"homeTeam": {"id": 1, "starters": starters,
                                                "subs": [{"id": 13, "name": "C In"}, {"id": 14, "name": "D Bench"}]},
                                   "awayTeam": {"id": 2, "starters": [], "subs": []}},
                        "matchFacts": {"events": {"events": [
                            {"type": "Substitution", "time": 70, "isHome": True,
                             "swap": [{"id": 13, "name": "C In"}, {"id": 12, "name": "B Out"}]}]}}}}


def test_lineup_fallback_minutes_when_no_player_stats() -> None:
    rows = fm.player_rows(_match(), "por.taca.portugal", {"1": ("LigaPortugal", "Alverca")}, _details())
    by = {r["player"]: r for r in rows}
    assert by["A GK"]["minutes"] == 90 and by["B Out"]["minutes"] == 70 and by["C In"]["minutes"] == 20
    assert "D Bench" not in by                                   # 안 들어간 벤치는 행 없음
    assert all(r["det"] == 0 and r["rating"] is None and r["comp_code"] == "por.taca.portugal" for r in rows)
    assert len(rows) == 12                                      # 선발 11 + 교체 투입 1


def test_cups_cover_qualifiers_and_lite_cups() -> None:
    assert fm.CUPS[10611] == "uefa.champions_qual" and fm.CUPS[278] == "aut.cup" and fm.CUPS[151] == "tur.cup"
    assert cu.GROUP["uefa.champions_qual"] == "ucl" and cu.GROUP["uefa.europa.conf_qual"] == "conf"
    assert acs.kind("uefa.europa_qual") == "euro" and acs.kind("den.cup") == "cup"
