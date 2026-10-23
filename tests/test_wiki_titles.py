"""구단 위키 문서 제목 검증(src/fetch_wiki_squads.py) — 여자팀·도시·시즌·다른 구단 문서를 거르고 다시 찾는다.

2026-10-23: 검색 첫 결과를 이름 낱말 하나로 받던 때 'Birmingham City W.F.C.'·'Viborg, Denmark'·'SV Austria Salzburg'·
Gaziantep→'Erzurumspor F.K.' 등 8곳이 저장돼 있었다(주장단·NETWORK·감독 부임일 보조 출처가 같이 씀).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch_wiki_squads as w  # noqa: E402

CLUB = "{{Infobox football club\n| clubname = X\n}}"


def _squad(names):
    return CLUB + "\n" + "\n".join(f"{{{{Fs player|no={i}|nat=ENG|pos=MF|name=[[{n}]]}}}}" for i, n in enumerate(names, 1))


ROSTER = [f"Player {s}" for s in ("Adams", "Brown", "Clark", "Davis", "Evans", "Fox", "Green", "Hall", "Irwin", "Jones")]
OTHER = [f"Player {s}" for s in ("Kane", "Lee", "Moss", "Nash", "Owen", "Park", "Quinn", "Reed", "Shaw", "Todd")]


def test_not_club_titles():
    for t in ("Birmingham City W.F.C.", "Viborg, Denmark", "AGF Fodbold (women)", "2026–27 Çorum F.K. season", "List of football clubs in Turkey"):
        assert w._NOT_CLUB_TITLE.search(w._fold(t)), t
    for t in ("Birmingham City F.C.", "Viborg FF", "FC Red Bull Salzburg", "Kasımpaşa S.K."):
        assert not w._NOT_CLUB_TITLE.search(w._fold(t)), t


def test_club_box_aliases_and_season():
    assert w._CLUB_BOX.search("{{Infobox football club\n| clubname = A")
    assert w._CLUB_BOX.search("{{Football club infobox\n| clubname = Çorum")         # 같은 틀의 다른 이름
    assert not w._CLUB_BOX.search("{{Infobox football club season\n| club = A")       # 시즌 문서
    assert not w._CLUB_BOX.search("{{Infobox settlement\n| name = Viborg")


def test_is_club_page_overlap():
    ros = {w._surname(n) for n in ROSTER}
    assert w.is_club_page(_squad(ROSTER), w.parse_squad(_squad(ROSTER)), ros)
    assert not w.is_club_page(_squad(OTHER), w.parse_squad(_squad(OTHER)), ros)      # 다른 구단(여자팀 등) 스쿼드
    assert w.is_club_page(CLUB, [], ros)                                              # 스쿼드 표 없음 — 판단 안 함
    assert not w.is_club_page("{{Infobox settlement}}", [], ros)


def test_resolve_prefers_squad_evidence(monkeypatch):
    # 'AGF' 처럼 이름 낱말이 제목에 없는 문서도 스쿼드가 겹치면 받는다. 스쿼드 표 없는 이름 맞는 후보(아마추어 동명 구단)보다 먼저
    monkeypatch.setattr(w, "candidates", lambda team, country: [("AGF Amateurs", True), ("Aarhus Gymnastikforening", False)])
    texts = {"AGF Amateurs": CLUB, "Aarhus Gymnastikforening": _squad(ROSTER)}
    monkeypatch.setattr(w, "wikitexts", lambda titles: {t: texts[t] for t in titles})
    ros = {w._surname(n) for n in ROSTER}
    assert w.resolve("AGF", "Denmark", ros, set())[0] == "Aarhus Gymnastikforening"
    # 이름 안 맞고 스쿼드도 다르면 받지 않는다
    texts["Aarhus Gymnastikforening"] = _squad(OTHER)
    assert w.resolve("AGF", "Denmark", ros, {"AGF Amateurs"}) is None
