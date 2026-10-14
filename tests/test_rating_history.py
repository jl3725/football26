from __future__ import annotations

import pandas as pd

import rating_history as rh


def test_record_keeps_only_changes_and_baseline_reads_past(monkeypatch, tmp_path) -> None:
    path = tmp_path / "hist.csv"
    monkeypatch.setattr(rh, "history_path", lambda league: path)
    state = {"rows": [{"squad": "A", "player": "P1", "norm_key": "p1", "pid": "tm1", "ovr": 80, "form": 70, "pot": 85},
                      {"squad": "A", "player": "P2", "norm_key": "p2", "pid": "tm2", "ovr": 75, "form": None, "pot": 75}]}
    monkeypatch.setattr(rh, "current_ratings", lambda league: pd.DataFrame(state["rows"]))

    assert rh.record("EPL", "2026-10-01") == 2
    assert rh.record("EPL", "2026-10-01") == 2            # 같은 날 재실행 → 갈아 끼움(중복 없음)
    state["rows"][0]["ovr"] = 83                            # P1 만 변화
    assert rh.record("EPL", "2026-10-15") == 1
    hist = rh.load("EPL")
    assert len(hist) == 3
    now = rh.state_at(hist, "2026-10-15").set_index("pid")
    assert now.loc["tm1", "ovr"] == 83 and now.loc["tm2", "ovr"] == 75

    monkeypatch.setattr(rh, "_today", lambda: "2026-10-15")
    base = rh.trend_baseline("EPL", days=14)                # 10-01 시점
    assert base["tm1"]["ovr"] == 80 and base["tm2"]["form"] is None
