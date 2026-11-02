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


def test_merge_updates_market_value_and_age(tmp_path):
    """클라우드 TM 이 시장가치·나이도 선수 표에 넣는다 — 예전엔 로컬 주간 빌드에서만(2026-11-02)."""
    import pandas as pd
    import sync_transfermarkt_contracts as sc
    p = tmp_path / "players_full.csv"
    pd.DataFrame([{"squad": "Arsenal", "player": "Ezri Konsa", "norm_key": "ezri konsa", "age": 28.0, "market_value_eur": 45e6,
                   "tm_photo": "", "tm_contract_until": ""}]).to_csv(p, index=False)
    snap = pd.DataFrame([{"squad": "Arsenal", "player": "Ezri Konsa", "norm_key": "ezri konsa", "tm_id": "413403",
                          "contract_until": "2029-06-30", "age": 29, "market_value_eur": 50e6, "detected_at": "2026-11-02"}])
    assert sc.merge_contracts(p, snap) == 1
    row = pd.read_csv(p).iloc[0]
    assert (row["age"], row["market_value_eur"]) == (29.0, 50e6)
    snap.loc[0, "market_value_eur"] = None                              # 값이 없으면 그대로
    sc.merge_contracts(p, snap)
    assert pd.read_csv(p).iloc[0]["market_value_eur"] == 50e6
