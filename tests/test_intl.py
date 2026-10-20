"""INTERNATIONAL 에이전트 — 대표팀 명단 파싱·명단 날짜·A매치 기간(휴식기/대회)·팀 화면·대회 결장."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import fetch_intl as fi  # noqa: E402

T = dt.date(2026, 10, 20)

WIKI = """==Players==
===Current squad===
The following players were named in the squad for the [[2026–27 UEFA Nations League]] matches against
[[Spain national football team|Spain]] and [[Croatia national football team|Croatia]] between 26 September and 6 October.
<!-- caps correct as of October 2026 -->
{{nat fs g start}}
{{nat fs g player|no=1|pos=GK|name=[[Jordan Pickford]]|age={{Birth date and age|1994|3|7|df=y}}|caps=93|goals=0|club=[[Everton F.C.|Everton]]|clubnat=ENG}}
{{nat fs g player|no=7|pos=FW|name=[[Bukayo Saka]]|caps=59|goals=14|club=[[Arsenal F.C.|Arsenal]]|clubnat=ENG}}
{{nat fs g player|no=9|pos=FW|name={{sortname|Harry|Kane}}|caps=110|goals=78|club=[[FC Bayern Munich|Bayern Munich]]|clubnat=GER}}
{{nat fs end}}
===Recent call-ups===
{{nat fs r player|no=|pos=MF|name=[[Declan Rice]]|club=[[Arsenal F.C.|Arsenal]]}}
"""


def test_parse_current_squad_and_date() -> None:
    rows, when = fi.parse_current_squad(WIKI, T)
    assert [r["player"] for r in rows] == ["Jordan Pickford", "Bukayo Saka", "Harry Kane"]   # 최근 소집 표는 제외
    assert rows[1]["club"] == "Arsenal" and rows[1]["caps"] == 59 and rows[2]["goals"] == 78
    assert when == "2026-10-06"                                    # 'October 2026' 의 20 을 날로 읽지 않는다


def test_squad_for_formats() -> None:
    assert fi.squad_for("on September 26 and 29 and October 3 and 6, 2026 respectively", T) == "2026-10-06"
    assert fi.squad_for("against Cameroon on 24, 29 September and 3 October 2026; respectively", T) == "2026-10-03"
    assert fi.squad_for("matches on 12 and 15 November 2026", T) == "2026-11-15"
    assert fi.squad_for("no dates here", T) is None


def test_windows_break_vs_tournament() -> None:
    days = [f"2026-11-{d:02d}" for d in (12, 13, 14, 15, 16, 17)] + [f"2027-01-{d:02d}" for d in (8, 9, 10, 11, 12)]
    m = pd.DataFrame([{"date": d, "comp_code": "x", "event_id": f"{d}-{i}"} for d in days for i in range(8)])
    club = {"2027-01-10": 9, "2027-01-11": 8, "2027-01-12": 9}          # 1월엔 리그가 계속된다(아시안컵)
    ws = fi.windows(m, club)
    assert [(w["first_match"], w["end"], w["kind"]) for w in ws] == [
        ("2026-11-12", "2026-11-17", "break"), ("2027-01-08", "2027-01-12", "tournament")]
    assert ws[0]["start"] == "2026-11-09"                          # 소집은 첫 경기 사흘 전


def test_nation_keys_match_espn_names() -> None:
    assert "ivory coast" in fi.nation_keys("Cote d'Ivoire") and "czechia" in fi.nation_keys("Czech Republic")
    assert "united states" in fi.nation_keys("United States") and "south korea" in fi.nation_keys("Korea, South")


def _svc(monkeypatch, wins, calls, matches):
    from api.services import intl
    monkeypatch.setattr(intl, "windows", lambda: wins)
    monkeypatch.setattr(intl, "callups", lambda: pd.DataFrame(calls))
    monkeypatch.setattr(intl, "matches", lambda: pd.DataFrame(matches))
    return intl


BREAK_OCT = {"start": "2026-09-21", "first_match": "2026-09-24", "end": "2026-10-06", "kind": "break", "label": "9월"}
BREAK_NOV = {"start": "2026-11-09", "first_match": "2026-11-12", "end": "2026-11-17", "kind": "break", "label": "11월"}
CALL = {"our_squad": "Arsenal", "our_league": "EPL", "nation_conf": "UEFA", "flag": "", "fifa_rank": 4, "caps": 59,
        "goals": 14, "pos": "FW"}


def test_team_payload_previous_then_announced(monkeypatch) -> None:
    calls = [{**CALL, "our_player": "Bukayo Saka", "nation": "England", "squad_for": "2026-10-06"},
             {**CALL, "our_player": "Gabriel Magalhães", "nation": "Brazil", "nation_conf": "CONMEBOL", "squad_for": "2026-10-03"}]
    mts = [{"date": "2026-11-12", "home": "England", "away": "Croatia", "comp_code": "uefa.nations", "state": "pre", "hg": None, "ag": None},
           {"date": "2026-09-29", "home": "Australia", "away": "Brazil", "comp_code": "fifa.friendly", "state": "post", "hg": 2, "ag": 4}]
    svc = _svc(monkeypatch, [BREAK_OCT, BREAK_NOV], calls, mts)
    d = svc.team_payload("Arsenal", "EPL", T)
    assert d["state"] == "upcoming" and d["days_to"] == 20 and d["squad_state"] == "previous"
    assert d["summary"] == {"n": 2, "far": 1, "nations": 2}
    gab = next(p for p in d["players"] if p["nation"] == "Brazil")
    assert gab["far"] and gab["last_results"][0]["score"] == "4-2"     # 브라질 기준 스코어(원정 4-2 승)
    saka = next(p for p in d["players"] if p["nation"] == "England")
    assert saka["fixtures"][0]["opp"] == "Croatia" and saka["fixtures"][0]["home"]
    # 11월 명단 발표 → 이번 기간 명단만
    calls[0]["squad_for"] = "2026-11-15"
    d = svc.team_payload("Arsenal", "EPL", T)
    assert d["squad_state"] == "announced" and [p["player"] for p in d["players"]] == ["Bukayo Saka"]


def test_tournament_absent_and_return(monkeypatch) -> None:
    cup = {"start": "2027-01-05", "first_match": "2027-01-08", "end": "2027-02-05", "kind": "tournament", "label": "대회"}
    calls = [{**CALL, "our_squad": "Brighton", "our_player": "Kaoru Mitoma", "nation": "Japan", "nation_conf": "AFC",
              "squad_for": "2027-01-20"}]
    mts = [{"date": "2027-01-10", "home": "Japan", "away": "Syria", "comp_code": "afc.asian.cup", "state": "post", "hg": 2, "ag": 0},
           {"date": "2027-01-15", "home": "Iran", "away": "Japan", "comp_code": "afc.asian.cup", "state": "pre", "hg": None, "ag": None}]
    svc = _svc(monkeypatch, [cup], calls, mts)
    assert svc.in_tournament("2027-01-12") and not svc.in_tournament("2026-12-30")
    assert {s for s, _ in svc.tournament_absent("EPL", "2027-01-12")} == {"Brighton"}
    mts[1]["state"] = "post"                                       # 일본 탈락(남은 경기 없음) → 마지막 경기 +3일 뒤 복귀
    svc = _svc(monkeypatch, [cup], calls, mts)
    assert svc.tournament_absent("EPL", "2027-01-17") and not svc.tournament_absent("EPL", "2027-01-19")


def test_returnees_after_break(monkeypatch) -> None:
    calls = [{**CALL, "our_player": "Bukayo Saka", "nation": "England", "squad_for": "2026-11-15"},
             {**CALL, "our_player": "Gabriel Magalhães", "nation": "Brazil", "nation_conf": "CONMEBOL", "squad_for": "2026-11-17"}]
    svc = _svc(monkeypatch, [BREAK_NOV], calls, [])
    assert svc.returnees("Arsenal", "EPL", "2026-11-21") == {"n": 2, "far": 1, "window_end": "2026-11-17"}
    assert svc.returnees("Arsenal", "EPL", "2026-12-01") is None   # 휴식기 끝나고 7일 넘으면 해당 없음
