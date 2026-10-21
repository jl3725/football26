"""클럽 라이벌 자동 판정 — 이름 낱말 집합 맞추기, 라이벌·더비 섹션의 링크만 뽑기."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import club_rivals as cr  # noqa: E402


def test_key_ignores_prefixes_and_suffixes() -> None:
    assert cr.key("RSC Anderlecht") == cr.key("Anderlecht")
    assert cr.key("Royal Antwerp F.C.") == cr.key("Antwerp")
    assert cr.key("Tottenham Hotspur F.C.") == cr.key("Tottenham Hotspur")
    assert cr.key("Cercle Brugge KSV") == cr.key("Cercle Brugge") != cr.key("Club Brugge")
    assert cr.key("FC Bayern Munich") == cr.key("Bayern Munich")


def test_section_links_only_rivalry_sections() -> None:
    text = ("== History ==\n[[Chelsea F.C.]] won.\n"
            "== Rivalries ==\n[[File:x.jpg]] Main rivals are [[Tottenham Hotspur F.C.|Spurs]] in the [[North London derby]].\n"
            "=== Other ===\nAlso [[Manchester United F.C.]].\n"
            "== Honours ==\n[[FA Cup]]\n")
    links = cr._section_links(text)
    assert "Tottenham Hotspur F.C." in links and "North London derby" in links
    assert "Chelsea F.C." not in links and "FA Cup" not in links and not any(x.startswith("File:") for x in links)
