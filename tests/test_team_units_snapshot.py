from __future__ import annotations

import api.main as M
from api.services import player_data as P


def test_league_units_uses_build_snapshot_only_for_same_build(monkeypatch) -> None:
    snap = {"season": M.SEASON_START, "db_mtime": 1.0, "db_size": 10,
            "leagues": {"EPL": {"Arsenal": {"overall": 99, "attack": 99, "midfield": 99, "defense": 99}}}}
    monkeypatch.setattr(M, "_units_snapshot", lambda: snap)
    monkeypatch.setattr(M, "_compute_league_units", lambda lg: {"computed": lg})
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setattr(M.ds, "_db_mtime", lambda: 1.0)
    assert M._league_units.__wrapped__("EPL") == snap["leagues"]["EPL"]       # 같은 DB → 빌드 스냅샷
    assert M._league_units.__wrapped__("LaLiga") == {"computed": "LaLiga"}    # 스냅샷에 없는 리그 → 즉석 계산
    monkeypatch.setattr(M.ds, "_db_mtime", lambda: 2.0)
    assert M._league_units.__wrapped__("EPL") == {"computed": "EPL"}          # 로컬에서 DB 가 바뀌면 무시
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(P, "_db_size", lambda: 10)
    assert M._league_units.__wrapped__("EPL") == snap["leagues"]["EPL"]       # Render: 시각이 달라도 같은 크기면 같은 배포본
    monkeypatch.setattr(P, "_db_size", lambda: 11)
    assert M._league_units.__wrapped__("EPL") == {"computed": "EPL"}
