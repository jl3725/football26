from __future__ import annotations

import datetime as dt

import pytest

from leagues import parse_season_start
from season_context import current_window, season_label


@pytest.mark.parametrize(
    ("date", "state", "season_id"),
    [
        (dt.date(2026, 7, 24), "summer", 2026),
        (dt.date(2027, 1, 15), "winter", 2026),
        (dt.date(2027, 4, 10), "closed", 2026),
    ],
)
def test_current_window(date: dt.date, state: str, season_id: int) -> None:
    result = current_window(date)
    assert result["state"] == state
    assert result["season_id"] == season_id


def test_season_label() -> None:
    assert season_label(2025) == "25/26"


@pytest.mark.parametrize("value", ["x", "1999", "2101"])
def test_invalid_season_start(value: str) -> None:
    with pytest.raises(RuntimeError):
        parse_season_start(value)
