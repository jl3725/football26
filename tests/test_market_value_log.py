"""시장가치 변경분 기록(scripts/snapshot_market_values.py, 2026-10-23 13개 리그) — 바뀐 선수만 · 두 구단 줄 안정 · 큰 변동 · 하루 두 번."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import snapshot_market_values as smv  # noqa: E402


def _snap(rows):
    return pd.DataFrame(rows, columns=["squad", "player", "tm_id", "market_value_eur"])


def test_diff_rows_only_changes() -> None:
    base = smv.diff_rows(None, _snap([["Arsenal", "A", 1, 10e6], ["Arsenal", "B", 2, 20e6]]), "2026-10-01")
    assert len(base) == 2                                                       # 처음 = 기준선 전원
    same = smv.diff_rows(base, _snap([["Arsenal", "A", 1, 10e6], ["Arsenal", "B", 2, 20e6]]), "2026-10-02")
    assert same.empty                                                           # 안 바뀌면 안 쓴다
    ch = smv.diff_rows(base, _snap([["Arsenal", "A", 1, 15e6], ["Chelsea", "B", 2, 20e6], ["Arsenal", "C", None, 1e6]]), "2026-10-03")
    assert set(ch["player"]) == {"A", "B", "C"}                                 # 값 변화 · 소속 변화 · 새 선수


def test_two_club_rows_do_not_flip() -> None:
    """임대·이적 선수가 원 소속·새 소속 표에 모두 있으면 하루씩 번갈아 '소속 변경'으로 찍혔다."""
    log = smv.diff_rows(None, _snap([["Aston Villa", "Guessand", 5, 25e6]]), "2026-08-01")
    for day in ("2026-08-02", "2026-08-03"):
        new = smv.diff_rows(log, _snap([["Aston Villa", "Guessand", 5, 25e6], ["Crystal Palace", "Guessand", 5, 25e6]]), day)
        assert new.empty
    # TM id 없는 동명이인은 이름+소속으로 따로
    two = smv.diff_rows(None, _snap([["Arsenal", "Rodri", None, 5e6], ["Moreirense", "Rodri", None, 1e6]]), "2026-08-01")
    assert len(two) == 2 and smv.diff_rows(two, _snap([["Arsenal", "Rodri", None, 5e6], ["Moreirense", "Rodri", None, 1e6]]), "2026-08-02").empty


def test_changes_from_big_moves_only() -> None:
    log = pd.DataFrame([
        ["2026-10-01", "Arsenal", "A", 1, 10e6], ["2026-10-14", "Arsenal", "A", 1, 15e6],
        ["2026-10-01", "Arsenal", "B", 2, 20e6], ["2026-10-14", "Arsenal", "B", 2, 20.5e6],          # €0.5M · 2.5% — 노이즈
        ["2026-10-01", "Arsenal", "C", 3, 30e6], ["2026-10-14", "Chelsea", "C", 3, 40e6],            # 이적 — 급등 아님
    ], columns=smv.LOG_COLS)
    out = smv.changes_from(log, "2026-10-14", None)
    assert list(out["player"]) == ["A"] and float(out["delta"].iloc[0]) == 5e6
    old = pd.DataFrame([{"run_date": "2026-09-01", "squad": "Arsenal", "player": "Z", "old_value": 1, "new_value": 2, "delta": 1, "pct": 100}])
    assert "Z" not in set(smv.changes_from(log, "2026-10-14", old)["player"])   # 14일 지난 변동은 버림


def test_snapshot_rerun_same_day_is_idempotent(tmp_path, monkeypatch) -> None:
    full = pd.DataFrame([{"squad": "Arsenal", "player": "A", "tm_id": 1, "market_value_eur": 10e6, "left_for": None},
                         {"squad": "Arsenal", "player": "Gone", "tm_id": 9, "market_value_eur": 5e6, "left_for": "Al-Hilal"}])
    monkeypatch.setattr(smv.ds, "read_table", lambda name, league=None, **k: full)
    monkeypatch.setattr(smv, "data_path", lambda stem, league=None, season=None: tmp_path / f"{stem}_{league}.csv")
    monkeypatch.setattr(smv, "_today", lambda: "2026-10-23")
    assert smv.snapshot("LaLiga") == 0
    log = pd.read_csv(tmp_path / "market_value_log_LaLiga.csv")
    assert list(log["player"]) == ["A"]                                         # 떠난 선수 줄은 빼고 기준선
    full.loc[0, "market_value_eur"] = 14e6
    monkeypatch.setattr(smv, "_today", lambda: "2026-10-24")
    smv.snapshot("LaLiga")
    smv.snapshot("LaLiga")                                                      # 같은 날 두 번 — 줄이 늘지 않는다
    log = pd.read_csv(tmp_path / "market_value_log_LaLiga.csv")
    assert len(log) == 2 and log["market_value_eur"].iloc[-1] == 14e6
    chg = pd.read_csv(tmp_path / "market_value_changes_LaLiga.csv")
    assert list(chg["player"]) == ["A"] and float(chg["pct"].iloc[0]) == 40.0
