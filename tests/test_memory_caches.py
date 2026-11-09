"""운영 메모리(512MB) — 다 쓴 원본 표를 캐시에 남기지 않기 · 응답 캐시는 오래 안 쓴 것부터 밀어내기(2026-11-09 점검)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import allcomp_stats as acs  # noqa: E402
from leagues import SEASON_START  # noqa: E402


def test_prev_season_rows_are_not_kept(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(acs, "season_rows", lambda read, season, version=None: calls.append((season, version)) or pd.DataFrame())
    monkeypatch.setattr(acs, "rating_table", lambda rows: ({}, {}))
    monkeypatch.setattr(acs, "_CACHE", {})
    prev, cur = f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"
    acs.x_tables(None, prev, 1.0)
    acs.x_tables(None, cur, 1.0)
    assert calls == [(prev, None), (cur, 1.0)]                 # 지난 시즌 행은 버전 없이(캐시 안 함), 이번 시즌만 캐시
    assert set(acs._CACHE) == {("tbl", prev, 1.0), ("tbl", cur, 1.0)}


def test_memo_evicts_least_recently_used(monkeypatch) -> None:
    import api.main as m
    monkeypatch.setattr(m, "_MEMO", {})
    monkeypatch.setattr(m, "_MEMO_LOCKS", {})
    monkeypatch.setattr(m, "_MEMO_MAX", 20)
    n = {"calls": 0}

    @m._memo(ttl=3600)
    def f(x):
        n["calls"] += 1
        return x

    f("shared")                                    # 데우기가 먼저 만든 공용 색인 같은 것
    for i in range(18):
        f(i)
        f("shared")                                # 계속 쓰이면 밀려나지 않는다
    for i in range(18, 40):
        f(i)
        f("shared")
    assert n["calls"] == 1 + 40 and len(m._MEMO) <= 20   # 공용 값은 한 번만 계산(예전 규칙은 '처음 넣은 것'을 밀어내 다시 계산)
