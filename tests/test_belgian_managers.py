"""벨기에 감독 — 클럽 위키 인포박스 manager·head coach 칸 읽기."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch_belgian_managers as b  # noqa: E402


def test_infobox_manager_forms() -> None:
    assert b.infobox_manager("| ground = Jan Breydel\n| manager = [[Ivan Leko]]\n") == ("Ivan Leko", "Ivan Leko")
    assert b.infobox_manager("| manager = [[Vítor Bruno (football manager)|Vítor Bruno]]<ref>x</ref>\n") == \
        ("Vítor Bruno", "Vítor Bruno (football manager)")
    assert b.infobox_manager("| manager = [[Michael Beale (football coach)]]\n") == \
        ("Michael Beale", "Michael Beale (football coach)")                     # 괄호 설명은 이름에서 뗀다
    assert b.infobox_manager("| head coach = Frédéric De Meyer (interim)\n") == ("Frédéric De Meyer", "Frédéric De Meyer")
    assert b.infobox_manager("| manager = TBA\n") is None and b.infobox_manager("| capacity = 29,000\n") is None
