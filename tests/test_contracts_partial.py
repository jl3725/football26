"""TM 계약 수집 — 구단 한 곳이 실패해도 리그 전체가 멈추지 않는다(2026-10-23 AS Roma 502 로 세리에A 전체 실패)."""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import sync_transfermarkt_contracts as sc  # noqa: E402


def test_one_team_failure_is_skipped(monkeypatch):
    calls = {"Roma": 0}

    def fake(team):
        if team == "Roma":
            calls["Roma"] += 1
            raise requests.HTTPError("502 Server Error: Bad Gateway")
        return [{"squad": team, "player": "P " + team, "contract_until": "2028-06-30"}]
    monkeypatch.setattr(sc, "scrape_team_contracts", fake)
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    df, failed = sc.collect_contracts(["Inter", "Roma", "Milan"], pause=0)
    assert failed == ["Roma"] and calls["Roma"] == 2          # 한 번 다시 시도한 뒤 건너뜀
    assert sorted(df["squad"]) == ["Inter", "Milan"]
