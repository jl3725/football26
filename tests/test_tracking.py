"""TRACKING(영입 후보 소식, 2026-10-23) — 이적 완료 · 우리 팀 연결/다른 구단 · 경기 활약 · 부상 아닌 결장 · 결장 상태."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def test_tracking_alerts(monkeypatch, tmp_path) -> None:
    import api.main as M
    import leagues
    import rumor_map as rm
    today = M._today_kst()
    d = lambda n: (today - datetime.timedelta(days=n)).isoformat()   # noqa: E731
    dmy = lambda n: (today - datetime.timedelta(days=n)).strftime("%d/%m/%Y")   # noqa: E731
    where = {rm.norm("Rio Ngumoha"): [{"name": "Rio Ngumoha", "club": "Liverpool", "league": "EPL", "photo": "", "minutes": 900}],
             rm.norm("Gabriel Martinelli"): [{"name": "Gabriel Martinelli", "club": "Arsenal", "league": "EPL", "photo": "", "minutes": 300}],
             rm.norm("Mile Svilar"): [{"name": "Mile Svilar", "club": "Roma", "league": "SerieA", "photo": "", "minutes": 450}]}
    tables = {
        "transfer_rumors": pd.DataFrame([{"player": "Rio Ngumoha", "target_club": "Real Madrid", "probability": 40, "date": dmy(1)},
                                         {"player": "Rio Ngumoha", "target_club": "Arsenal", "probability": None, "date": dmy(30)}]),
        "transfers": pd.DataFrame([{"squad": "Arsenal", "direction": "out", "player": "Gabriel Martinelli", "club": "Al-Hilal",
                                    "fee_text": "€70.00m"}]),
        "fotmob_match_ratings": pd.DataFrame([
            {"match_id": 1, "date": d(3), "squad": "Liverpool", "opponent": "Villarreal", "player": "Rio Ngumoha", "rating": 8.92, "goals": 0, "assists": 2},
            {"match_id": 2, "date": d(6), "squad": "Liverpool", "opponent": "Everton", "player": "Rio Ngumoha", "rating": 6.5, "goals": 0, "assists": 0},
            {"match_id": 3, "date": d(2), "squad": "Roma", "opponent": "Lazio", "player": "Other", "rating": 7.0, "goals": 0, "assists": 0},
            {"match_id": 4, "date": d(5), "squad": "Roma", "opponent": "Milan", "player": "Other", "rating": 7.0, "goals": 0, "assists": 0}]),
    }
    monkeypatch.setattr(M, "_rumor_links", lambda: ({}, where, {}))
    monkeypatch.setattr(M.ds, "read_table", lambda name, league=None, **k: tables.get(name))
    monkeypatch.setattr(M, "_active_injuries", lambda team, lg: {"mile svilar": {"injury": "손가락 골절", "until": "09/11/2026"}} if team == "Roma" else {})
    monkeypatch.setattr(M, "_injury_events", lambda lg, days=60: [])
    monkeypatch.setattr(M, "_pf", lambda lg: None)
    pd.DataFrame([{"date": d(4), "player": "Rio Ngumoha", "dest": "Arsenal", "stage": "agreed", "source": "Football365"},
                  {"date": d(3), "player": "Rio Ngumoha", "dest": "Arsenal", "stage": "agreed", "source": "TEAMtalk"}]
                 ).to_csv(tmp_path / "news_claims.csv", index=False)
    monkeypatch.setattr(leagues, "DATA_DIR", tmp_path)
    want = [{"player": "Rio Ngumoha", "club": "Liverpool", "league": "EPL"},
            {"player": "Gabriel Martinelli", "club": "Arsenal", "league": "EPL"},
            {"player": "Mile Svilar", "club": "Roma", "league": "SerieA"}]
    out = M.tracking.__wrapped__("Arsenal", json.dumps(want), "EPL")
    got = {(a["player"], a["type"], a["title"]) for a in out["alerts"]}
    assert ("Gabriel Martinelli", "moved", "Al-Hilal 이적") in got
    assert ("Rio Ngumoha", "rivals", "Real Madrid 관심 40%") in got
    assert ("Rio Ngumoha", "linked", "Arsenal 합의 보도") in got          # 매체 둘은 한 줄('외 1곳')
    assert ("Rio Ngumoha", "match", "평점 8.92 · 2도움") in got
    assert not any(t == "linked" and "관심" in ti for _, t, ti in got)  # 30일 전 TM 루머는 14일 밖
    linked = next(a for a in out["alerts"] if a["type"] == "linked")
    assert linked["detail"] == "Football365 외 1곳"
    sv = next(p for p in out["players"] if p["player"] == "Mile Svilar")
    assert sv["status"][0]["k"] == "out" and "손가락 골절" in sv["status"][0]["tip"]
    assert not any(a["player"] == "Mile Svilar" and a["type"] == "absent" for a in out["alerts"])   # 부상 결장은 '출전 없음' 아님
    mt = next(p for p in out["players"] if p["player"] == "Gabriel Martinelli")
    assert mt["top"] and mt["top"].startswith("moved|")
