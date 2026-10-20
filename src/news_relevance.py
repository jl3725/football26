"""
팀 뉴스 관련성 — 팀 피드(ESPN·RSS)에 섞여 들어온 남의 기사를 거른다.

브뤼헤 뉴스 18건 중 10건이 미국 대학 경기·CAF 챔스·Oxford 기사, 7건이 2023~24년 기사였다(2026-10-20 점검).
기사 제목·요약(원문)에 팀 이름(또는 구별되는 낱말)이 나오거나, 선수 태그(src/news_tags.py)에 이 팀 선수가 있으면 관련.
기간은 발행일(없으면 처음 본 날) 기준 최근 MAX_DAYS 일.
"""
from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

from unidecode import unidecode

MAX_DAYS = 60
# 여러 클럽 이름에 흔한 낱말 — 이것만으로는 그 팀 기사라고 볼 수 없다
GENERIC = {"city", "united", "town", "club", "real", "sporting", "athletic", "atletico", "olympique", "inter", "racing",
           "deportivo", "union", "royal", "county", "rovers", "wanderers", "albion", "paris", "football", "calcio",
           "fc", "cf", "sc", "ac", "afc", "as", "sv", "vfb", "vfl", "fk", "sk", "kv", "kaa", "rsc", "rc", "cd", "ud", "sd",
           "de", "la", "le", "les", "del", "der", "und", "the", "and", "1.", "04", "05"}


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


@lru_cache(maxsize=512)
def team_terms(team: str, extra: tuple = ()) -> tuple[str, ...]:
    """팀을 가리키는 말(접은 소문자) — 전체 이름, 구별되는 낱말(4자+), 추가 별칭(정식 이름·애칭)."""
    out: set[str] = set()
    for name in (team, *extra):
        f = _fold(name)
        if not f:
            continue
        out.add(f)
        for w in f.split():
            if len(w) >= 4 and w not in GENERIC:
                out.add(w)
    return tuple(sorted(out, key=len, reverse=True))


def mentions(text, terms) -> bool:
    t = f" {_fold(text)} "
    return any(f" {x} " in t for x in terms)


def recent(published, first_seen, today: dt.date | None = None, days: int = MAX_DAYS) -> bool:
    today = today or dt.date.today()
    for v in (published, first_seen):
        d = str(v or "")[:10]
        try:
            return dt.date.fromisoformat(d) >= today - dt.timedelta(days=days)
        except ValueError:
            continue
    return True                                         # 날짜를 모르면 남긴다


def relevant(row: dict, terms, tagged: bool) -> bool:
    """기사 하나(dict: headline, descr, published, first_seen)가 이 팀 기사인가."""
    if not recent(row.get("published"), row.get("first_seen")):
        return False
    return tagged or mentions(f"{row.get('headline') or ''} {row.get('descr') or ''}", terms)
