"""FotMob 클럽 표기 → 우리 표기(squads.to_ours) · 이미 쌓인 파일 정리(fix_frame) — 하부 리그 컵 상대는 건드리지 않음."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import fix_fotmob_team_names as fx  # noqa: E402
from squads import to_ours  # noqa: E402

EREDIV = ["PSV", "Ajax", "Feyenoord", "Sparta R.", "NEC Nijmegen", "Excelsior"]


def test_to_ours_abbreviated_names() -> None:
    assert to_ours("Sparta Rotterdam", "Eredivisie", EREDIV) == "Sparta R."              # 유사도만으론 0.33 — 못 맞추던 것
    assert to_ours("N.E.C.", "Eredivisie", EREDIV) == "NEC Nijmegen"
    assert to_ours("Union St.Gilloise", "BelgianProLeague", ["Club Brugge", "Union SG", "Sint-Truiden"]) == "Union SG"
    assert to_ours("St.Truiden", "BelgianProLeague", ["Club Brugge", "Union SG", "Sint-Truiden"]) == "Sint-Truiden"
    assert to_ours("Manchester United", "EPL", ["Manchester Utd", "Manchester City"]) == "Manchester Utd"
    assert to_ours("Somewhere FC", "EPL", ["Arsenal"]) is None


def test_fix_frame_squad_only_not_cup_opponents() -> None:
    df = pd.DataFrame([
        {"squad": "Sparta Rotterdam", "opponent": "Excelsior Maassluis"},   # 컵 — 상대는 아마추어 클럽(우리 Excelsior 아님)
        {"squad": "Ajax", "opponent": "Sparta Rotterdam"},
    ])
    new, m = fx.fix_frame(df, "Eredivisie", EREDIV)
    assert m == {"Sparta Rotterdam": "Sparta R."}
    assert new["squad"].tolist() == ["Sparta R.", "Ajax"]
    assert new["opponent"].tolist() == ["Excelsior Maassluis", "Sparta R."]
