"""감독 공석 — FotMob 감독 칸이 빈 팀은 공석 기록(watchdog 빠짐 아님), 서버는 감독으로 안 씀(2026-11-10 MLS 몽레알·뉴잉글랜드)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import lite_league as ll  # noqa: E402


def test_vacant_record_written_and_filtered(tmp_path, monkeypatch) -> None:
    p = tmp_path / "manager_profiles_MLS.json"
    p.write_text(json.dumps({"CF Montréal": {"name": "Old Coach", "nationality": "FRA"}}), encoding="utf-8")
    monkeypatch.setattr(ll, "data_path", lambda *a, **k: p)
    coaches = {"Los Angeles FC": {"name": "Marc Dos Santos", "nationality": "CAN", "photo_url": "", "fotmob_id": 1}}
    ll.write_managers("MLS", coaches, ["Los Angeles FC", "CF Montréal"])
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["CF Montréal"]["vacant"] is True and d["CF Montréal"]["previous_name"] == "Old Coach" and d["CF Montréal"]["name"] == ""
    assert d["Los Angeles FC"]["name"] == "Marc Dos Santos"
    import api.main as m
    monkeypatch.setattr(m, "data_path", lambda *a, **k: p)
    assert set(m._managers("MLS")) == {"Los Angeles FC"}          # 공석은 감독이 아님
