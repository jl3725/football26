"""Understat 사이트 장애(2026-11-02~ understat.com 연결 시간 초과) — 매일 수집은 '원천 중단'(75)으로, 주간 빌드는 마지막
받은 파일로(빈 표로 진행하면 5대 리그 xG 가 0·대체값으로 덮였다)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import fetch_understat_live as ful  # noqa: E402


def test_live_returns_source_down_when_unreachable(monkeypatch):
    def boom(lg):
        raise RuntimeError('TLS Client Error: failed to do request: Get "https://understat.com/getStatData": dial tcp 45.90.32.72:443: i/o timeout')
    monkeypatch.setattr(ful, "fetch", boom)
    monkeypatch.setattr(ful, "reachable", lambda timeout=15.0: False)
    monkeypatch.setattr(ful, "register_soccerdata_custom_leagues", lambda: None)
    assert ful.main() == ful.EX_SOURCE_DOWN


def test_live_other_errors_stay_failures(monkeypatch):
    monkeypatch.setattr(ful, "fetch", lambda lg: (_ for _ in ()).throw(KeyError("player")))
    monkeypatch.setattr(ful, "reachable", lambda timeout=15.0: True)
    monkeypatch.setattr(ful, "register_soccerdata_custom_leagues", lambda: None)
    assert ful.main() == 1                                   # 사이트는 닿는데 형식이 바뀐 것 — 빨간불이어야


def test_weekly_falls_back_to_last_file(monkeypatch, tmp_path):
    try:
        import soccerdata  # noqa: F401, PLC0415
    except ImportError:                                      # CI 는 soccerdata 없이 테스트한다 — 빈 모듈로 대신(Understat 은 아래서 바꿔 끼움)
        import types  # noqa: PLC0415
        monkeypatch.setitem(sys.modules, "soccerdata", types.ModuleType("soccerdata"))
    import fetch_understat as fu
    last = tmp_path / "understat_players.csv"
    pd.DataFrame({"squad": ["Arsenal"] * 120, "player": [f"P{i}" for i in range(120)], "minutes": 900,
                  "xg": 1.0, "np_xg": 1.0, "xa": 0.5, "key_passes": 3, "shots": 4, "xg_chain": 2.0,
                  "goals": 1, "assists": 1}).to_csv(last, index=False)

    class Boom:
        def __init__(self, *a, **k):
            raise OSError("dial tcp 45.90.32.72:443: i/o timeout")
    monkeypatch.setattr(fu.sd, "Understat", Boom, raising=False)
    monkeypatch.setattr(fu, "ACTIVE_LEAGUE", "EPL")
    monkeypatch.setattr(fu, "data_path", lambda stem, *a, **k: last)
    u = fu.read_understat_or_empty(pd.DataFrame())
    assert len(u) == 120 and "team" in u.columns
