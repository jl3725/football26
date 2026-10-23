"""감독 프로필 빈칸 채우기(src/manager_fill.py) — 이름 맞추기·날짜 표기·FotMob 경력 해석·캐시 재사용."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import manager_fill as mf  # noqa: E402


def test_same_person():
    assert mf.same_person("Luis García", "Luis García Plaza")               # 스페인식 두 성
    assert mf.same_person("Claudio Giráldez", "Claudio Giráldez González")
    assert mf.same_person("Mikel Arteta", "Mikel Arteta Amatriain")
    assert mf.same_person("Slaviša Jokanović", "Slavisa Jokanovic")          # 악센트
    assert not mf.same_person("Vincent Wagner", "Horst Steffen")
    assert not mf.same_person("Luis García", "Luis Enrique")
    assert not mf.same_person("", "Luis Enrique")


def test_fmt():
    assert mf.fmt("2021-09-01", 11) == "Sep 2021"
    assert mf.fmt("2021-09-01", 10) == "Sep 2021"
    assert mf.fmt("2021-01-01", 9) == "2021"
    assert mf.fmt("", 11) == ""


def _player(name, entries):
    return {"name": name, "careerHistory": {"careerItems": {"coach": {"teamEntries": entries}}}}


def test_fotmob_start_picks_current_team():
    calls = []

    def get(url):
        calls.append(url)
        if "teams?id=7896" in url:
            return {"squad": {"squad": [{"title": "coach", "members": [{"id": 7692, "name": "Mattia Croci-Torti"}]}]}}
        if "playerData?id=7692" in url:
            return _player("Mattia Croci-Torti", [
                {"teamId": 7896, "startDate": "2021-09-01T00:00:00", "active": True},
                {"teamId": 6000, "startDate": "2019-07-01T00:00:00", "active": False},
            ])
        return None
    r = mf.fotmob_start({"name": "Mattia Croci-Torti"}, 7896, get)
    assert r == {"start": "2021-09-01", "precision": 11, "src": "fotmob"}
    assert len(calls) == 2


def test_fotmob_start_rejects_other_coach():
    # 팀 응답의 감독이 프로필 이름과 다르면(우리 프로필이 늦었거나 빠름) 그 사람 날짜를 쓰지 않는다
    def get(url):
        if "teams?id=1" in url:
            return {"squad": {"squad": [{"title": "coach", "members": [{"id": 9, "name": "Someone Else"}]}]}}
        return _player("Someone Else", [{"teamId": 1, "startDate": "2026-07-01T00:00:00", "active": True}])
    assert mf.fotmob_start({"name": "Vincent Wagner"}, 1, get) is None


def test_fotmob_start_two_active_needs_team_match():
    # 클럽 + 대표팀 겸임처럼 지금 팀이 둘이면 팀 id 가 맞는 것만
    def get(url):
        return _player("A Coach", [{"teamId": 5, "startDate": "2024-01-01T00:00:00", "active": True},
                                   {"teamId": 77, "startDate": "2025-03-01T00:00:00", "active": True}])
    assert mf.fotmob_start({"name": "A Coach", "fotmob_id": 3}, 5, get)["start"] == "2024-01-01"
    assert mf.fotmob_start({"name": "A Coach", "fotmob_id": 3}, None, get) is None


def test_fresh_cache():
    today = dt.date(2026, 10, 23)
    assert mf._fresh({"val": "Sep 2021", "at": "2025-01-01"}, 14, today)          # 찾은 값은 계속 쓴다
    assert mf._fresh({"val": "", "at": "2026-10-20"}, 14, today)                  # 못 찾음 — 14일 안엔 다시 안 받는다
    assert not mf._fresh({"val": "", "at": "2026-10-01"}, 14, today)
    assert not mf._fresh(None, 14, today)


def _team(cid, name):
    return {"squad": {"squad": [{"title": "coach", "members": [{"id": cid, "name": name, "cname": "Austria"}]}]}}


def test_newer_coach_needs_active_career():
    today = dt.date(2026, 10, 23)

    def get(url):
        if "teams?id=8571" in url:
            return _team(56932, "Daniel Beichler")
        return _player("Daniel Beichler", [{"teamId": 8571, "startDate": "2026-10-09T00:00:00", "active": True}])
    o = mf.newer_coach({"name": "Christophe Lepoint"}, 8571, get, today)
    assert o["name"] == "Daniel Beichler" and o["start"] == "2026-10-09" and o["from"] == "Christophe Lepoint"
    p = {"name": "Christophe Lepoint", "photo_url": "old.png", "bio_ko": "옛 감독 소개", "style": "x"}
    mf.apply_override(p, o)
    assert p["name"] == "Daniel Beichler" and p["previous_name"] == "Christophe Lepoint" and p["bio_ko"] == "" and p["style"] == ""
    assert p["appointed"] == "Oct 2026" and p["change_detected_at"] == "2026-10-09" and p["previous_photo"] == "old.png"


def test_newer_coach_ignores_stale_fotmob_slot():
    # FotMob 팀 감독 칸만 다르고 그 감독 경력엔 이 팀이 '지금'이 아니면(Estoril·Famalicão) 우리 프로필을 믿는다
    today = dt.date(2026, 10, 23)

    def get(url):
        if "teams?id=1634" in url:
            return _team(24590, "Ricardo Silva")
        return _player("Ricardo Silva", [{"teamId": 1634, "startDate": "2024-12-06T00:00:00", "endDate": "2024-12-10", "active": False}])
    assert mf.newer_coach({"name": "Carlos Carvalhal"}, 1634, get, today) is None

    def get_old(url):                                   # 오래전에 시작한 '지금' 기록 — 교체 신호로 보지 않는다
        if "teams?id=1" in url:
            return _team(9, "Old Coach")
        return _player("Old Coach", [{"teamId": 1, "startDate": "2023-01-01T00:00:00", "active": True}])
    assert mf.newer_coach({"name": "New Coach"}, 1, get_old, today) is None


def test_override_persists_on_own_write():
    # 이미 덮어 쓴 프로필(수집기가 안 돈 날)에도 다시 입히고, 옛 감독 사진을 새 사진으로 덮지 않는다
    o = {"name": "Daniel Beichler", "fotmob_id": 56932, "nationality": "Austria", "start": "2026-10-09",
         "from": "Christophe Lepoint", "at": "2026-10-23", "bio_ko": "소개"}
    p = {"name": "Christophe Lepoint", "photo_url": "lepoint.png"}
    mf.apply_override(p, o)
    assert p["previous_photo"] == "lepoint.png" and p["name_source"] == "fotmob"
    mf.apply_override(p, o)                              # 두 번째(이미 덮인 프로필)
    assert p["previous_photo"] == "lepoint.png" and p["bio_ko"] == "소개"
