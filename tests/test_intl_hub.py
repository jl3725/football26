"""국가대표 대회 레지스트리·허브 — 자동 분류 규칙과 불빛 상태(끝난 월드컵에 초록불이 남지 않게)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import intl_comps as ic  # noqa: E402


def test_kind_and_placeholder_rules() -> None:
    assert ic.kind_of("afc.asian.cup", "AFC Asian Cup", True) == "tournament"
    assert ic.kind_of("afc.cupq", "AFC Asian Cup Qualifying", True) == "qualifier"
    assert ic.kind_of("uefa.nations", "UEFA Nations League", True) == "nations_league"
    assert ic.kind_of("fifa.friendly", "International Friendly", False) == "friendly"
    assert ic.PLACEHOLDER.search("Group A Winner") and ic.PLACEHOLDER.search("3rd Place Group B")
    assert not ic.PLACEHOLDER.search("South Korea")
    assert ic.NOT_SENIOR.search("FIFA Under-20 World Cup") and ic.NOT_SENIOR.search("FIFA Women's World Cup")
    assert not ic.NOT_SENIOR.search("AFC Asian Cup")


def _comp(code, kind, status, start, end, champ=None):
    return {"code": code, "name": code, "name_ko": code, "conf": "AFC", "kind": kind,
            "editions": [{"season": start[:4], "start": start, "end": end, "matches": 10, "played": 10 if status == "finished" else 0,
                          "status": status, "champion": champ, "runner_up": None}]}


def test_hub_status_light(monkeypatch) -> None:
    from api.services import intl, intl_hub
    today = dt.date(2026, 10, 20)
    monkeypatch.setattr(intl, "callups", lambda: __import__("pandas").DataFrame())
    monkeypatch.setattr(intl, "matches", lambda: __import__("pandas").DataFrame(columns=["date"]))
    # 끝난 월드컵 + 79일 뒤 아시안컵 + A매치 기간 20일 뒤 → 불 끔
    comps = [_comp("fifa.world", "tournament", "finished", "2026-06-11", "2026-07-19", "Spain"),
             _comp("afc.asian.cup", "tournament", "upcoming", "2027-01-07", "2027-02-05")]
    monkeypatch.setattr(intl_hub, "competitions", lambda: comps)
    monkeypatch.setattr(intl, "_target", lambda t: ({"start": "2026-11-09", "end": "2026-11-17"}, None, "upcoming"))
    h = intl_hub.hub(today)
    assert h["status"] == "none" and h["next_tournament"]["code"] == "afc.asian.cup"
    # A매치 기간 중 → 초록
    monkeypatch.setattr(intl, "_target", lambda t: ({"start": "2026-10-15", "end": "2026-10-23"}, None, "now"))
    assert intl_hub.hub(today)["status"] == "live"
    # 본선이 진행 중 → 초록 / 14일 안 → 노랑
    monkeypatch.setattr(intl, "_target", lambda t: (None, None, "none"))
    monkeypatch.setattr(intl_hub, "competitions", lambda: [_comp("afc.asian.cup", "tournament", "live", "2026-10-10", "2026-11-05")])
    assert intl_hub.hub(today)["status"] == "live"
    monkeypatch.setattr(intl_hub, "competitions", lambda: [_comp("afc.asian.cup", "tournament", "upcoming", "2026-10-30", "2026-11-25")])
    assert intl_hub.hub(today)["status"] == "soon"
