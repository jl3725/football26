"""나이 기준 맞추기 — 2026-11-05 사용자: 'FM 처럼 유망주는 크고 노장은 깎이나'.

① 지난 시즌 표 나이 = 시즌 끝(7/1) 나이(시장가치와 같은 때) ② 이름+국적이 같아도 tm id 가 다르면 다른 사람
③ AGE CURVE — 지난 시즌 평점을 나이만큼 옮겨 섞는다(v3.17)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import rating_history as rh  # noqa: E402
import ratings_v3 as rv3  # noqa: E402


def test_season_end_age_uses_birth_date_then_plus_one(monkeypatch) -> None:
    from api.services import player_data as pdat
    monkeypatch.setattr(pdat, "_birth_dates", lambda: {"1": "1995-09-15", "2": "2000-06-20"})
    f = pd.DataFrame({"tm_id": [1.0, 2.0, None], "age": [29.0, 25.0, 30.0]})
    got = list(pdat.season_end_age(f, "2025_2026"))
    # 1995-09-15 → 2026-07-01 30세 · 2000-06-20 → 26세 · 생년월일 없으면 시즌 시작 나이 + 1
    assert got == [30.0, 26.0, 31.0]


def test_lookup_prev_rejects_same_name_with_other_tm_id() -> None:
    wolves = {"ovr": 76, "minutes": 2500, "pid": "tm800176"}
    prev = {"tm800176": wolves, "nm:andre|brazil": wolves}
    goztepe = {"tm_id": 1024605, "norm_key": "andre", "nationality": "Brazil"}
    assert rh.lookup_prev(prev, goztepe) is None                       # 괴즈테페 André ≠ 울브스 André
    assert rh.lookup_prev(prev, {"tm_id": 800176, "norm_key": "andre", "nationality": "Brazil"}) is wolves
    assert rh.lookup_prev(prev, {"tm_id": None, "norm_key": "andre", "nationality": "Brazil"}) is wolves   # tm id 없으면 이름으로


def test_age_curve_moves_last_season_toward_now() -> None:
    assert rv3.age_drift(19) > 0.05 and rv3.age_drift(26) == 0.0 and rv3.age_drift(37) < -0.05
    args = dict(ss_rating=7.0, minutes=600, prev_ss_rating=7.0, prev_minutes=2500, ln="MID", league_level=100,
                prev_league_level=100)
    flat, _ = rv3._class_parts(**args)
    young, _ = rv3._class_parts(**args, age=19)
    prime, _ = rv3._class_parts(**args, age=26)
    old, _ = rv3._class_parts(**args, age=37)
    assert young > flat == prime > old                                  # 같은 두 시즌 평점이어도 19세는 위, 37세는 아래
    # 이번 시즌만 뛴 선수는 옮길 게 없다
    only_now = dict(args, prev_ss_rating=None, prev_minutes=None)
    assert rv3._class_parts(**only_now, age=19) == rv3._class_parts(**only_now)
