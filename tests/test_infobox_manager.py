"""인포박스 감독 칸 — 비어 있으면 다음 줄('|league =')을 이름으로 읽지 않기(2026-11-16 라 루비에르 '|league   =')."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import fetch_belgian_managers as fbm  # noqa: E402


def test_empty_manager_field_is_vacant() -> None:
    wt = "{{Infobox football club\n| ground = Stade\n| manager    =\n|league   = [[Belgian Pro League]]\n}}"
    assert fbm.infobox_manager(wt) is None


def test_manager_field_parsed() -> None:
    wt = "{{Infobox football club\n| manager = [[Frédéric De Meyer]] (caretaker)\n| league = x\n}}"
    assert fbm.infobox_manager(wt) == ("Frédéric De Meyer", "Frédéric De Meyer")
    assert fbm.infobox_manager("| head coach = Pedro Caixinha\n") == ("Pedro Caixinha", "Pedro Caixinha")
