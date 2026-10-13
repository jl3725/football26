"""시즌 표시와 이적시장 날짜 계산을 한곳에서 관리한다."""
from __future__ import annotations

import datetime as dt

from leagues import SEASON_START


def current_window(today: dt.date | None = None) -> dict:
    """날짜 기준 현재 이적시장 상태를 반환한다.

    여름은 6월 14일~9월 1일, 겨울은 1월 1일~2월 3일로 본다.
    데이터 시즌과 실제 달력 시즌은 다를 수 있으므로 둘을 별도로 노출한다.
    """
    today = today or dt.date.today()
    year, month, day = today.year, today.month, today.day

    if (month == 6 and day >= 14) or month in (7, 8) or (month == 9 and day == 1):
        season_start = year
        state, is_open, window, label_kr = "summer", True, "summer", "여름"
    elif month == 1 or (month == 2 and day <= 3):
        season_start = year - 1
        state, is_open, window, label_kr = "winter", True, "winter", "겨울"
    else:
        season_start = year if month >= 7 else year - 1
        state, is_open, window, label_kr = "closed", False, "summer", None

    return {
        "season_id": season_start,
        "window": window,
        "label": season_label(season_start),
        "state": state,
        "is_open": is_open,
        "kr": label_kr,
        "phase": season_phase(season_start, state),
        "data_season_id": SEASON_START,
    }


def season_phase(calendar_season: int, state: str, data_season: int | None = None) -> str:
    """데이터 시즌(FB_SEASON_START)과 달력상 시즌의 관계.

    - ``in_season`` : 달력 시즌 == 데이터 시즌 → 이번 시즌 순위·라인업 중심, '다음 시즌' 뷰 숨김
    - ``offseason`` : 달력 시즌이 한 시즌 앞서고 여름 창이 열림(6/14~9/1) → 다음 시즌 로스터·예상 XI
    - ``stale``     : 달력 시즌이 앞섰는데 이적시장도 닫힘 → 새 시즌이 시작됐는데 데이터 전환이 안 됨
    """
    data_season = SEASON_START if data_season is None else data_season
    gap = calendar_season - data_season
    if gap <= 0:
        return "in_season"
    if gap == 1 and state == "summer":
        return "offseason"
    return "stale"


def season_label(start_year: int = SEASON_START) -> str:
    """2025 -> ``25/26`` 표시 문자열."""
    return f"{start_year % 100:02d}/{(start_year + 1) % 100:02d}"
