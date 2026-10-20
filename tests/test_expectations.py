"""전문가 기대치 검사기 — 기대가 깨지면 실패로 잡는지(가짜 API로)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import eval_expectations as ev  # noqa: E402


def _fake(influence: dict, captains: list, pf: pd.DataFrame, similar: list):
    return SimpleNamespace(
        network=lambda team, lg: {"leadership": {"influence": influence, "captains": captains}},
        _pf=lambda lg: pf, _pos_bucket=lambda row: row["bucket"],
        similar=lambda p, same, a, lg: {"results": similar},
        fit=lambda p, team, role, src, lg: {"natural_role": "Central Midfield"})


def test_detects_regressions() -> None:
    pf = pd.DataFrame([{"player": "Erling Haaland", "goals": 6, "bucket": "ST"},
                       {"player": "Khvicha Kvaratskhelia", "goals": 3, "bucket": "CM"}])
    m = _fake({"Gabriel Magalhães": 85, "Bukayo Saka": 84, "Martin Ødegaard": 84, "Declan Rice": 71},
              [{"captain_rank": 1, "name": "Lamine Yamal"}], pf,
              [{"player": "Johan Manzambi", "pos": "AM"}, {"player": "Bryan Mbeumo", "pos": "RW"}])
    rows = {
        "influence_top": {"kind": "influence_top", "league": "EPL", "team": "Arsenal", "player": "Martin Ødegaard|Declan Rice", "expect": "3"},
        "captain_not": {"kind": "captain_not", "league": "LaLiga", "team": "Barcelona", "player": "Lamine Yamal", "expect": "1"},
        "bucket_in": {"kind": "bucket_in", "league": "Ligue1", "team": "", "player": "Khvicha Kvaratskhelia", "expect": "LW"},
        "fit_natural": {"kind": "fit_natural", "league": "Ligue1", "team": "Arsenal", "player": "Khvicha Kvaratskhelia", "expect": "Left Winger"},
        "similar_not": {"kind": "similar_not", "league": "EPL", "team": "", "player": "Bukayo Saka", "expect": "Johan Manzambi"},
        "similar_bucket": {"kind": "similar_bucket", "league": "EPL", "team": "", "player": "Bukayo Saka", "expect": "RW|LW"},
        "stat_ge": {"kind": "stat_ge", "league": "EPL", "team": "", "player": "Erling Haaland", "expect": "goals:8", "season": "2026_2027"},
    }
    for k, r in rows.items():
        ok, msg = ev.check_one(m, r, "2026_2027")
        assert ok is False, (k, msg)
    ok, _ = ev.check_one(m, {**rows["stat_ge"], "season": "2025_2026"}, "2026_2027")
    assert ok is None                                             # 다른 시즌 누적은 건너뜀


def test_golden_file_kinds_are_known() -> None:
    g = pd.read_csv(ev.GOLDEN, dtype=str)
    known = {"influence_top", "captain", "captain_not", "bucket_in", "fit_natural", "similar_not", "similar_bucket", "stat_ge"}
    assert set(g["kind"]) <= known and len(g) >= 10
