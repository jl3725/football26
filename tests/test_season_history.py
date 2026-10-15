from __future__ import annotations

import pandas as pd

import season_history as sh


def _table(rows):
    return pd.DataFrame([{"squad": s, "played": 38, "gf": gf, "ga": ga} for s, gf, ga in rows]
                        + [{"squad": f"T{i}", "played": 38, "gf": 50, "ga": 50} for i in range(12)])


def test_team_record_uses_available_past_seasons_with_decay(monkeypatch) -> None:
    monkeypatch.setattr(sh, "_history", lambda league: pd.DataFrame())
    tables = {"2025_2026": _table([("Arsenal", 71, 27), ("City", 77, 35)]),
              "2024_2025": _table([("Arsenal", 69, 34), ("City", 72, 44)])}
    rec = sh.team_record("EPL", "Arsenal", lambda lg, s: tables.get(s), current=2026)
    assert [r["label"] for r in rec] == ["25/26", "24/25"] and [r["w"] for r in rec] == [1.0, 0.5]
    city = sh.team_record("EPL", "City", lambda lg, s: tables.get(s), current=2026)
    # 실점이 적은 쪽이 수비 z 가 높다 — 두 시즌 모두 아스날이 적게 내줬다
    assert sh.blended(rec, "ga_z") > sh.blended(city, "ga_z")
    # 다음 시즌으로 넘어가면 코드 수정 없이 26/27 이 직전 시즌, 25/26 이 가중 0.5 가 된다
    tables["2026_2027"] = _table([("Arsenal", 60, 30), ("City", 60, 30)])
    nxt = sh.team_record("EPL", "Arsenal", lambda lg, s: tables.get(s), current=2027)
    assert [(r["label"], r["w"]) for r in nxt] == [("26/27", 1.0), ("25/26", 0.5), ("24/25", 0.25)]


def test_small_playoff_tables_are_skipped(monkeypatch) -> None:
    monkeypatch.setattr(sh, "_history", lambda league: pd.DataFrame())
    small = pd.DataFrame([{"squad": f"T{i}", "played": 10, "gf": 10 + i, "ga": 10} for i in range(8)])
    assert sh.past_tables("BelgianProLeague", lambda lg, s: small, current=2026) == []
