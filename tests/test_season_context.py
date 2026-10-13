from __future__ import annotations

import datetime as dt

import pytest

from leagues import parse_season_start
from season_context import current_window, season_label, season_phase


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


@pytest.mark.parametrize(
    ("calendar", "state", "data", "phase"),
    [
        (2026, "closed", 2026, "in_season"),   # 26/27 시즌 중, 데이터 26/27
        (2026, "winter", 2026, "in_season"),   # 겨울 이적시장도 시즌 중
        (2027, "summer", 2026, "offseason"),   # 27/28 여름 이적시장 — 다음 시즌 준비
        (2026, "closed", 2025, "stale"),       # 26/27 개막했는데 데이터는 25/26 (2026-10 상황)
        (2028, "summer", 2026, "stale"),
    ],
)
def test_season_phase(calendar: int, state: str, data: int, phase: str) -> None:
    assert season_phase(calendar, state, data) == phase
