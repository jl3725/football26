"""ClubElo 봇 확인 페이지 알아보기 — 막혔으면 우회하지 않고 '외부 원천 중단'(75)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch_clubelo as fc  # noqa: E402


class R:
    def __init__(self, code, text):
        self.status_code, self.text = code, text


def test_blocked_detection():
    assert fc._blocked(R(403, "<title>Just a moment...</title> window._cf_chl_opt"))
    assert not fc._blocked(R(200, "<table>fixtures</table>"))
    assert not fc._blocked(R(404, "not found"))


def test_main_returns_75_when_blocked(monkeypatch, tmp_path):
    def blocked():
        raise fc.SourceBlocked("HTTP 403 봇 확인 페이지")
    monkeypatch.setattr(fc, "from_page", blocked)
    monkeypatch.setattr(fc, "OUT", tmp_path / "clubelo_fixtures.csv")
    assert fc.main() == 75
