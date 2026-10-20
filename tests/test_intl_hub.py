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
    monkeypatch.setattr(intl, "_target", lambda t, **k: ({"start": "2026-11-09", "end": "2026-11-17"}, None, "upcoming"))
    h = intl_hub.hub(today)
    assert h["status"] == "none" and h["next_tournament"]["code"] == "afc.asian.cup"
    # A매치 기간 중 → 초록
    monkeypatch.setattr(intl, "_target", lambda t, **k: ({"start": "2026-10-15", "end": "2026-10-23"}, None, "now"))
    assert intl_hub.hub(today)["status"] == "live"
    # 본선이 진행 중 → 초록 / 14일 안 → 노랑
    monkeypatch.setattr(intl, "_target", lambda t, **k: (None, None, "none"))
    monkeypatch.setattr(intl_hub, "competitions", lambda: [_comp("afc.asian.cup", "tournament", "live", "2026-10-10", "2026-11-05")])
    assert intl_hub.hub(today)["status"] == "live"
    monkeypatch.setattr(intl_hub, "competitions", lambda: [_comp("afc.asian.cup", "tournament", "upcoming", "2026-10-30", "2026-11-25")])
    assert intl_hub.hub(today)["status"] == "soon"


def test_fill_tbd_from_fixtures() -> None:
    from api.services import intl_hub
    g = [{"name": "Group E", "rows": [{"team": "South Korea"}, {"team": "TBD"}, {"team": "Vietnam"}]},
         {"name": "Group F", "rows": [{"team": "Japan"}, {"team": "Qatar"}]}]
    pairs = [("South Korea", "Yemen"), ("Vietnam", "South Korea"), ("Japan", "Qatar"), ("Group E Winner", "Group F 2nd Place")]
    out = intl_hub.fill_tbd(g, pairs)
    assert [r["team"] for r in out[0]["rows"]] == ["South Korea", "Yemen", "Vietnam"]   # 일정의 상대로 채움
    assert [r["team"] for r in out[1]["rows"]] == ["Japan", "Qatar"]                   # 빈자리 이름은 안 씀


def test_tournament_windows_from_registry(tmp_path, monkeypatch) -> None:
    import json

    import fetch_intl as fi
    reg = {"competitions": [{"code": "afc.asian.cup", "name": "AFC Asian Cup", "name_ko": "AFC 아시안컵", "kind": "tournament",
                             "editions": [{"season": "2027", "start": "2027-01-07", "end": "2027-02-05", "matches": 51}]},
                            {"code": "fifa.friendly", "name": "Friendly", "kind": "friendly",
                             "editions": [{"season": "2026", "start": "2026-11-12", "end": "2026-11-17", "matches": 40}]}]}
    (tmp_path / "intl_competitions.json").write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(fi, "DATA", tmp_path)
    breaks = [{"start": "2026-11-09", "first_match": "2026-11-12", "end": "2026-11-17", "kind": "break"}]
    w = fi.tournament_windows(breaks, {"2027-01-10": 9}, dt.date(2026, 10, 20))
    assert len(w) == 1 and w[0]["kind"] == "tournament" and w[0]["comps"] == ["afc.asian.cup"]
    assert w[0]["start"] == "2026-12-31" and w[0]["club_matches"] == 9   # 소집은 첫 경기 일주일 전, 대회 중 클럽 경기
    # 이미 겹치는 기간이 있으면 더하지 않는다
    assert fi.tournament_windows([{"first_match": "2027-01-07", "end": "2027-02-05", "kind": "break"}], {}, dt.date(2026, 10, 20)) == []


def test_team_payload_skips_tournament_without_its_nations(monkeypatch) -> None:
    import pandas as pd

    from api.services import intl
    ws = [{"start": "2026-12-31", "first_match": "2027-01-07", "end": "2027-02-05", "kind": "tournament", "comps": ["afc.asian.cup"],
           "label": "AFC 아시안컵 2027", "matches": 51},
          {"start": "2027-03-22", "first_match": "2027-03-25", "end": "2027-03-31", "kind": "break", "comps": ["fifa.friendly"],
           "label": "3월 A매치 기간", "matches": 90}]
    monkeypatch.setattr(intl, "windows", lambda: ws)
    monkeypatch.setattr(intl, "matches", lambda: pd.DataFrame([
        {"date": "2027-01-10", "home": "South Korea", "away": "Yemen", "comp_code": "afc.asian.cup", "state": "pre", "hg": None, "ag": None}]))
    calls = pd.DataFrame([
        {"nation": "Korea, South", "nation_conf": "AFC", "fifa_rank": 24, "flag": "", "squad_for": "2026-10-06", "player": "Kim Min-jae",
         "club": "Bayern Munich", "pos": "DF", "caps": 85, "goals": 4, "our_player": "Kim Min-jae", "our_squad": "Bayern Munich",
         "our_league": "Bundesliga"},
        {"nation": "England", "nation_conf": "UEFA", "fifa_rank": 4, "flag": "", "squad_for": "2026-10-06", "player": "Harry Kane",
         "club": "Bayern Munich", "pos": "FW", "caps": 110, "goals": 75, "our_player": "Harry Kane", "our_squad": "Bayern Munich",
         "our_league": "Bundesliga"},
        {"nation": "England", "nation_conf": "UEFA", "fifa_rank": 4, "flag": "", "squad_for": "2026-10-06", "player": "Bukayo Saka",
         "club": "Arsenal", "pos": "FW", "caps": 50, "goals": 12, "our_player": "Bukayo Saka", "our_squad": "Arsenal", "our_league": "EPL"}])
    monkeypatch.setattr(intl, "callups", lambda: calls)
    today = dt.date(2026, 12, 1)
    bay = intl.team_payload("Bayern Munich", "Bundesliga", today)
    assert bay["window"]["label"] == "AFC 아시안컵 2027"                 # 한국 선수가 있는 클럽 → 아시안컵
    ars = intl.team_payload("Arsenal", "EPL", today)
    assert ars["window"]["label"] == "3월 A매치 기간"                     # 아시아 선수가 없으면 대회를 건너뛴다
