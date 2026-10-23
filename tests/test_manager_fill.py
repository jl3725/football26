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
