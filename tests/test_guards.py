from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_season_literals import _season_like, _strip_ts_comments  # noqa: E402


@pytest.mark.parametrize("text", ["25/26", "시즌 2025-26", "2025/26 SEASON", "2025–26", "data_2025_2026.csv", "99/00"])
def test_season_like_catches_season_labels(text: str) -> None:
    assert _season_like(text)


@pytest.mark.parametrize("text", ["10/13", "1/2", "2026-10-13", "3/5 경기", "https://x.com/2025/12/a", "24/7"])
def test_season_like_ignores_dates_and_ratios(text: str) -> None:
    assert not _season_like(text)


def test_ts_comments_stripped_but_strings_kept() -> None:
    src = 'const a = "25/26"; // 26/27\n/* 27/28 */ const u = "https://a.b";'
    lines = _strip_ts_comments(src)
    assert "25/26" in lines[0] and "26/27" not in lines[0]
    assert "27/28" not in lines[1] and "https://a.b" in lines[1]
