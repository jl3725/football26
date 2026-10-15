from __future__ import annotations

import api.main as M


def test_league_units_uses_build_snapshot_only_when_stamp_matches(monkeypatch) -> None:
    snap = {"stamp": "S1", "leagues": {"EPL": {"Arsenal": {"overall": 99, "attack": 99, "midfield": 99, "defense": 99}}}}
    monkeypatch.setattr(M, "_units_snapshot", lambda: snap)
    monkeypatch.setattr(M, "_compute_league_units", lambda lg: {"computed": lg})
    monkeypatch.setattr(M, "_units_stamp", lambda: "S1")
    assert M._league_units.__wrapped__("EPL") == snap["leagues"]["EPL"]       # 빌드 스냅샷 그대로
    assert M._league_units.__wrapped__("LaLiga") == {"computed": "LaLiga"}    # 스냅샷에 없는 리그는 즉석 계산
    monkeypatch.setattr(M, "_units_stamp", lambda: "S2")
    assert M._league_units.__wrapped__("EPL") == {"computed": "EPL"}          # DB 가 바뀌면 스냅샷 무시
