"""v3.18 — 시즌 초 상승·부진 표본(1,800/3,000분) · 이적 직후 오른 몸값은 인정 안 함. 2026-11-06 사용자: 반 헤케·엔소·앤더슨."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import ratings_v3 as rv3  # noqa: E402


def _parts(**kw) -> dict:
    parts: list = []
    rv3.absolute_ovr(_parts=parts, exact=True, **kw)
    return dict(parts)


BASE = dict(value=60e6, age=26, pos_group="DEF", prev_value=45e6, league_level=100, prev_league_level=100,
            prev_ss_rating=7.1, prev_minutes=3200)


def test_moved_player_value_jump_not_credited() -> None:
    stay = _parts(ss_rating=7.0, minutes=800, **BASE)
    moved = _parts(ss_rating=7.0, minutes=800, moved=True, **BASE)
    jump = (rv3.value_ovr(60e6) or 0) - (rv3.value_ovr(45e6) or 0)
    assert abs(stay["jump"] + 0.5 * jump) < 0.11                       # 남은 선수 — 절반만 인정(예전 그대로)
    assert abs(moved["jump"] + min(3.0, jump)) < 0.11                  # 옮긴 선수 — 오른 몫 전부 빼기(최대 3)


def test_early_season_rise_needs_minutes() -> None:
    early = _parts(ss_rating=7.55, minutes=810, **BASE).get("rise", 0.0)    # 반 헤케 — 9경기 7.5 대
    later = _parts(ss_rating=7.55, minutes=2700, **BASE).get("rise", 0.0)
    assert early < 1.0 and later > early                                 # 9경기로는 작게, 같은 수준이 쌓이면 커진다
