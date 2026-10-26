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


_WORD = re.compile(r"\w+", re.U)


def common_words(texts, terms, min_n: int = 5, share: float = 0.3) -> set[str]:
    """이 팀 기사 원문에서 소문자로 자주 쓰인 이름 낱말 = 흔한 말 — 팀을 가리키지 못한다.
    정식 이름의 'futbol'(Villarreal Club de Fútbol)·'clube'(Sporting Clube)·'1907'(Como 1907)이 그 낱말만으로 아무 기사나
    그 팀 기사로 만들었다(2026-10-26, 라리가 'futbol' 소문자 81~100%). 손으로 적은 목록 대신 그 팀 기사 묶음에서 잰다."""
    single = {t for t in terms if " " not in t}
    n: dict[str, int] = {}
    low: dict[str, int] = {}
    for s in texts:
        for w in _WORD.findall(str(s or "")):
            f = _fold(w)
            if f in single:
                n[f] = n.get(f, 0) + 1
                if not w[:1].isupper():
                    low[f] = low.get(f, 0) + 1
    return {w for w in single if n.get(w, 0) >= min_n and low.get(w, 0) / n[w] >= share}


def _proper(words: list[str], folded: list[str], term: str) -> bool:
    """원문에서 이름이 고유명사 꼴로 쓰였나 — 첫 낱말과 4자 이상 낱말은 대문자 시작('Vitória de Guimarães' 의 'de' 는 예외)."""
    tw = term.split()
    k = len(tw)
    for i in range(len(folded) - k + 1):
        if folded[i:i + k] == tw and all(w[:1].isupper() or w[:1].isdigit()
                                         for j, w in enumerate(words[i:i + k]) if j == 0 or len(w) >= 4):
            return True
    return False


def mentions(text, terms) -> bool:
    """이름이 원문에서 고유명사(대문자 시작)로 쓰였을 때만 — 'four boys'·'two young boys murdered' 같은 일반 기사가
    영보이스 기사가 됐다(2026-10-26). 접은 글자로 먼저 거르고(빠름), 맞는 것만 원문 대소문자를 본다."""
    t = f" {_fold(text)} "
    words = folded = None
    for x in terms:
        if f" {x} " not in t:
            continue
        if words is None:
            words = _WORD.findall(str(text or ""))
            folded = [_fold(w) for w in words]
        if _proper(words, folded, x):
            return True
    return False


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
