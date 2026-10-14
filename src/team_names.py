"""
팀 이름 맞추기 — 외부 출처(Sofascore 팬 투표·ClubElo 예측)의 표기를 우리 표기(standings 의 squad)로.

출처마다 'Man City' · 'Manchester City' · 'Liverpool FC' 처럼 다르게 쓴다. 정규화(악센트·FC 류 접두/접미 제거) 후
같으면 1.0, 한쪽이 다른 쪽을 포함하면 0.9, 아니면 단어 겹침 비율로 점수를 매겨 가장 높은 후보(0.5 이상)를 고른다.
"""
from __future__ import annotations

import re

from unidecode import unidecode

_DROP = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "fk", "sk", "cd", "ud", "rc", "rcd", "club", "de", "the", "calcio",
         "1", "1.", "vfb", "vfl", "tsg", "bsc", "sv", "ssc", "acf", "us", "ogc", "losc", "stade", "kv", "krc", "rsc", "sporting", "and"}
# 흔한 줄임말 → 우리 표기에 가까운 형태
_ALIAS = {
    "man city": "manchester city", "man united": "manchester utd", "man utd": "manchester utd", "manchester united": "manchester utd",
    "forest": "nottingham forest", "nottm forest": "nottingham forest", "nott'm forest": "nottingham forest", "spurs": "tottenham",
    "wolves": "wolverhampton", "newcastle": "newcastle united", "brighton & hove albion": "brighton", "west ham united": "west ham",
    "paris sg": "psg", "paris saint-germain": "psg", "paris saint germain": "psg", "inter milan": "inter", "internazionale": "inter",
    "atletico": "atletico madrid", "atlético": "atletico madrid", "athletic": "athletic club", "bilbao": "athletic club",
    "bayern": "bayern munich", "bayern münchen": "bayern munich", "bayern munchen": "bayern munich", "leverkusen": "leverkusen",
    "gladbach": "gladbach", "monchengladbach": "gladbach", "dortmund": "dortmund", "frankfurt": "frankfurt",
    "psv eindhoven": "psv", "az alkmaar": "az", "sporting lisbon": "sporting cp", "sporting": "sporting cp",
    "bayern munchen": "bayern munich", "borussia dortmund": "dortmund", "bayer 04 leverkusen": "leverkusen",
    "bayer leverkusen": "leverkusen", "borussia monchengladbach": "gladbach", "eintracht frankfurt": "frankfurt",
    "wolverhampton wanderers": "wolverhampton", "tottenham hotspur": "tottenham", "nottingham": "nottingham forest",
    "olympique lyonnais": "lyon", "olympique de marseille": "marseille", "olympique marseille": "marseille",
    "inter": "inter", "ac milan": "milan", "milan": "milan", "atletico de madrid": "atletico madrid",
}


def norm(name: str) -> str:
    s = unidecode(str(name or "")).lower().strip()
    s = _ALIAS.get(s, s)
    s = s.replace("&", " and ").replace("utd", "united")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _DROP]
    j = " ".join(toks)
    # 'FC Bayern München' → 'bayern munchen' 처럼 접두어를 뗀 뒤에야 줄임말 표에 걸리는 경우
    return _ALIAS.get(j, j) if j in _ALIAS else j


def score(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) / len(ta | tb)


def best(name: str, candidates) -> str | None:
    """후보(우리 표기) 중 가장 비슷한 것 — 0.5 미만이면 None."""
    top, top_s = None, 0.0
    for c in candidates:
        s = score(name, c)
        if s > top_s:
            top, top_s = c, s
    return top if top_s >= 0.5 else None
