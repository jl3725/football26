"""
뉴스 STORY 묶음 — 한 팀 기사 중 같은 일(같은 선수 이적설·부상, 같은 제목)을 다룬 여러 매체 기사를 하나로.

묶는 규칙(가까운 날짜 STORY_DAYS 안):
  1) 같은 종류(이적·부상)이고 기사에 나온 선수가 겹친다 — 언어가 달라도 묶인다(HLN 의 네덜란드어 기사 + Football Italia 영어 기사)
  2) 제목 낱말이 많이 겹친다(접은 글, 4자 이상 낱말, 팀 이름·흔한 낱말 제외, 자카드 0.45 이상·3개 이상)
매체 2곳 이상인 묶음만 STORY. 단계는 가장 앞선 단계(관심 < 협상 < 합의 < 확정), 맨 마지막 기사가 '부인'이면 부인.
"""
from __future__ import annotations

import datetime as dt
import re

from unidecode import unidecode

STORY_DAYS = 4
STAGE_RANK = {"interest": 1, "talks": 2, "agreed": 3, "done": 4}
_STOP = {"with", "from", "after", "over", "into", "about", "their", "they", "this", "that", "what", "when", "will", "have",
         "been", "more", "than", "news", "latest", "update", "live", "transfer", "transfers", "report", "reports", "says",
         "como", "para", "pero", "tras", "sobre", "contra", "ante", "desde", "dopo", "della", "delle", "nach", "gegen",
         "apres", "pour", "avec", "contre", "voor", "naar", "tegen", "with", "club", "team", "football", "futbol", "calcio"}


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


def _toks(s: str, drop: set[str]) -> set[str]:
    return {w for w in _fold(s).split() if len(w) >= 4 and w not in _STOP and w not in drop}


def _day(a: dict) -> dt.date | None:
    for k in ("published", "first_seen"):
        try:
            return dt.date.fromisoformat(str(a.get(k) or "")[:10])
        except ValueError:
            continue
    return None


def cluster(arts: list[dict], team_words: set[str] | None = None, days: int = STORY_DAYS) -> list[dict]:
    """arts: [{link, headline(원문), headline_ko, source, published, first_seen, kind, stage, journalists[], all_players[]}]
    → STORY [{id, kind, stage, title, title_en, players, sources, journalists, first, last, links}] (최근순)."""
    drop = {w for t in (team_words or set()) for w in _fold(t).split()}
    n = len(arts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    toks = [_toks(a.get("headline") or "", drop) for a in arts]
    days_ = [_day(a) for a in arts]
    pls = [set(a.get("all_players") or []) for a in arts]
    for i in range(n):
        for j in range(i + 1, n):
            if days_[i] and days_[j] and abs((days_[i] - days_[j]).days) > days:
                continue
            ki, kj = arts[i].get("kind"), arts[j].get("kind")
            same = ki == kj and ki in ("transfer", "injury") and pls[i] & pls[j]
            if not same and toks[i] and toks[j]:
                inter = toks[i] & toks[j]
                same = len(inter) >= 3 and len(inter) / len(toks[i] | toks[j]) >= 0.45
            if same:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idx in groups.values():
        g = [arts[i] for i in idx]
        srcs = list(dict.fromkeys(str(a.get("source") or "") for a in g if a.get("source")))
        if len(srcs) < 2:
            continue
        g.sort(key=lambda a: (str(a.get("published") or ""), str(a.get("first_seen") or "")), reverse=True)
        kinds = [a.get("kind") for a in g if a.get("kind") not in (None, "", "other")]
        kind = max(set(kinds), key=kinds.count) if kinds else "other"
        stage = ""
        if kind == "transfer":
            ranked = [a for a in g if a.get("stage") in STAGE_RANK]
            stage = max(ranked, key=lambda a: STAGE_RANK[a["stage"]])["stage"] if ranked else ""
            # 마지막 날 기사에 '부인'이 있고 그날 합의·확정이 없으면 부인(발행일이 날짜 단위라 같은 날 순서는 모른다)
            last_day = _day(g[0])
            same_day = [a for a in g if _day(a) == last_day]
            if any(a.get("stage") == "denied" for a in same_day) and \
                    not any(STAGE_RANK.get(a.get("stage") or "", 0) >= STAGE_RANK["agreed"] for a in same_day):
                stage = "denied"
        # 제목 = 가장 앞선 단계 기사(같으면 최신) — 이적설은 '어디까지 왔나'가 제목
        head = max(g, key=lambda a: (STAGE_RANK.get(a.get("stage") or "", 0) if kind == "transfer" else 0,
                                     str(a.get("published") or "")))
        players: list[str] = []
        for a in g:
            for p in a.get("players") or []:
                if p not in players:
                    players.append(p)
        js: list[str] = []
        for a in g:
            for p in a.get("journalists") or []:
                if p not in js:
                    js.append(p)
        ds = [d for d in (_day(a) for a in g) if d]
        out.append({"id": head.get("link"), "kind": kind, "stage": stage,
                    "title": head.get("headline_ko") or head.get("headline") or "", "title_en": head.get("headline") or "",
                    "players": players[:4], "sources": srcs, "journalists": js[:3],
                    "first": min(ds).isoformat() if ds else "", "last": max(ds).isoformat() if ds else "",
                    "links": [a.get("link") for a in g]})
    out.sort(key=lambda s: (s["last"], len(s["sources"])), reverse=True)
    return out
