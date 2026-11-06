"""기사 작성자(RSS 바이라인) → 사람 이름만 — 루머 주장 기자 칸(2026-11-06, 0% → 매체 RSS 작성자)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from news_classify import byline_names  # noqa: E402


def test_byline_keeps_people_drops_desks_and_outlets() -> None:
    assert byline_names("Alex Young", "Evening Standard") == ["Alex Young"]
    assert byline_names("By Sam Wilson and Peter Young", "Football Italia") == ["Sam Wilson", "Peter Young"]
    assert byline_names("redaction@walfoot.be (Scott Crabbé)", "Walfoot") == ["Scott Crabbé"]
    assert byline_names("Jeroen van Poppel", "Voetbalzone") == ["Jeroen van Poppel"]
    for desk, src in (("info@vi.nl (Voetbal International)", "Voetbal International"), ("Sportredactie", "AD"),
                      ("La Redazione", "Corriere dello Sport"), ("PA Media", "The Independent"), ("Evening Standard", "Evening Standard"),
                      ("Football Italia staff", "Football Italia"), ("", "BBC")):
        assert byline_names(desk, src) == [], desk
