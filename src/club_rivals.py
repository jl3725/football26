"""
클럽 라이벌 자동 판정 — 영어 위키 클럽 문서의 라이벌·더비 섹션 → data/club_rivals.json (손으로 쓴 라이벌 표 없음).

  1) 클럽 문서(정식 이름 → 넘겨주기 따라감)에서 제목에 rival·derby·derbi 가 든 섹션의 [[링크]]
  2) 그 링크가 더비 문서('North London derby'·'Big Three (Belgium)'·'O Clássico')면 그 문서 앞부분의 클럽 링크까지
  3) 링크 이름을 우리 8개 리그 클럽으로 맞춘다(구별되는 낱말 집합 일치 — 'RSC Anderlecht' = 'Anderlecht')
  4) A 가 B 를 적었으면 B 도 A 의 라이벌(대칭)
  5) 같은 리그 안 쌍만 — 유럽 대회 상대(레알–스탕다르 리에주)는 이적 판단과 무관하고 섞이기 쉽다
이적 작업대에서 라이벌 구단 선수는 '거래 어려움'으로 표시한다. 7일 캐시(daily_data 에서 부르되 신선하면 건너뜀).

    python src/club_rivals.py [--force]
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "club_rivals.json"
FRESH_DAYS = 7
STOP = {"fc", "f", "c", "cf", "afc", "ac", "ssc", "sc", "ss", "us", "as", "rc", "rcd", "cd", "ud", "sd", "ca", "kv", "kaa", "krc", "ksv",
        "kvc", "rsc", "sv", "vfb", "vfl", "tsg", "bv", "bc", "fk", "sk", "club", "de", "la", "le", "del", "der", "the", "royal", "real",
        "calcio", "football", "futbol", "clube", "sporting", "1", "04", "05", "1899", "1900", "1907", "1909", "1913", "29"}
SECTION = re.compile(r"^(={2,4})\s*([^=\n]*?(?:rival|derby|derbi|derbies)[^=\n]*?)\s*\1\s*$", re.I | re.M)
DERBY_TITLE = re.compile(r"derby|derbi|rivalry|cl[aá]sic|classico|klassiker|big three|big four", re.I)
LINK = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
# 머리 안내문({{Redirect|…|the football team|X (football)}} · {{For|…}} · {{About|…}})의 축구팀 문서 제목
FOOTBALL_ARTICLE = re.compile(r"[|\[]\s*([^|{}\[\]\n]+?\((?:men's )?(?:association )?football(?: club| team)?\))\s*[|\]}]", re.I)


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


def key(name: str) -> frozenset:
    """구별되는 낱말 집합 — 접두·접미 약자(FC·RSC·KV…)와 흔한 말을 뺀다."""
    return frozenset(w for w in _fold(name).split() if w not in STOP and len(w) > 1)


LEAGUE_OF: dict[str, str] = {}


def our_clubs() -> dict[str, list[str]]:
    """{클럽(우리 표기): 이름 변형} — 우리 표기·정식 이름·ESPN 표기·현지 표기. LEAGUE_OF 에 리그도 채운다."""
    import news_sources  # noqa: PLC0415
    import teammeta as tm  # noqa: PLC0415
    from ui.news import newstags  # noqa: PLC0415
    out: dict[str, list[str]] = {}
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if not p.exists():
            continue
        tags = newstags(lg)
        for sq in pd.read_csv(p)["squad"].astype(str):
            LEAGUE_OF[sq] = lg
            out[sq] = list(dict.fromkeys(x for x in (sq, tm.team_fullname(sq), tags.get(sq), *news_sources.cached_local_names(sq)) if x))
    return out


def _section_links(text: str) -> list[str]:
    links = []
    for m in SECTION.finditer(text or ""):
        start = m.end()
        nxt = re.search(r"^={2," + str(len(m.group(1))) + r"}[^=]", text[start:], re.M)
        body = text[start:start + (nxt.start() if nxt else 4000)]
        links += [x.strip() for x in LINK.findall(body) if not x.lower().startswith(("file:", "image:", "category:"))]
    return list(dict.fromkeys(links))


def build() -> dict:
    import fetch_wiki_squads as wiki  # noqa: PLC0415
    clubs = our_clubs()
    by_key: dict[frozenset, str] = {}
    for c, names in clubs.items():
        for n in names:
            k = key(n)
            if k:
                by_key.setdefault(k, c)

    def match(name: str) -> str | None:
        k = key(name)
        return by_key.get(k) if k else None

    # 1) 클럽 문서 — 정식 이름부터, 없으면 다음 이름(넘겨주기·동음이의는 wikitexts 가 처리)
    texts: dict[str, str] = {}
    pending = {c: list(ns) for c, ns in clubs.items()}
    for _ in range(3):
        ask = {c: ns.pop(0) for c, ns in pending.items() if ns and c not in texts}
        if not ask:
            break
        got = wiki.wikitexts(list(dict.fromkeys(ask.values())))
        for c, t in ask.items():
            w = got.get(t) or ""
            if len(w) > 3000 and "football" in w.lower():
                texts[c] = w
    # 종합 스포츠 클럽 문서면 머리 안내문의 축구팀 문서로 — 'Galatasaray' 는 종합 클럽이고 축구는 'Galatasaray S.K. (football)'
    # 이라 라이벌 섹션이 없어 갈라타사라이–페네르바체 더비가 빠졌다(2026-10-23)
    hop = {c: m.group(1).strip() for c, w in texts.items()
           if (m := FOOTBALL_ARTICLE.search(w[:2500])) and m.group(1).strip().lower() not in {n.lower() for n in clubs[c]}}
    if hop:
        got = wiki.wikitexts(list(dict.fromkeys(hop.values())))
        for c, t in hop.items():
            w = got.get(t) or ""
            if len(w) > 3000:
                texts[c] = w
    rivals: dict[str, set[str]] = {c: set() for c in clubs}
    derby_pages: dict[str, set[str]] = {}
    for c, w in texts.items():
        for ln in _section_links(w):
            hit = match(ln)
            if hit and hit != c:
                rivals[c].add(hit)
            elif DERBY_TITLE.search(ln):
                derby_pages.setdefault(ln, set()).add(c)
    # 2) 더비 문서 — 앞부분(첫 섹션 전)의 클럽 링크
    if derby_pages:
        got = wiki.wikitexts(list(derby_pages))
        for title, owners in derby_pages.items():
            w = got.get(title) or ""
            lead = w[: (re.search(r"^==[^=]", w, re.M).start() if re.search(r"^==[^=]", w, re.M) else 6000)]
            teams = {m for m in (match(x) for x in LINK.findall(lead)) if m}
            teams |= {m for m in (match(re.sub(r"\[\[|\]\]", "", x)) for x in re.findall(r"\|\s*team\d+\s*=\s*([^\n|]+)", w)) if m}
            for o in owners:
                if o in teams or len(teams) <= 4:          # 그 클럽이 나오는 더비, 또는 작은 묶음(빅3 등)
                    rivals[o] |= {t for t in teams if t != o}
    # 3) 대칭 + 같은 리그만
    for a in list(rivals):
        rivals[a] = {b for b in rivals[a] if LEAGUE_OF.get(a) and LEAGUE_OF.get(a) == LEAGUE_OF.get(b)}
    for a in list(rivals):
        for b in list(rivals[a]):
            rivals.setdefault(b, set()).add(a)
    return {"updated": dt.date.today().isoformat(), "articles": len(texts),
            "rivals": {c: sorted(v) for c, v in sorted(rivals.items()) if v}}


def load() -> dict[str, list[str]]:
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("rivals", {})
    except (OSError, ValueError):
        return {}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(argv if argv is not None else sys.argv[1:])
    if OUT.exists() and "--force" not in args:
        try:
            upd = json.loads(OUT.read_text(encoding="utf-8")).get("updated", "")
            if upd >= (dt.date.today() - dt.timedelta(days=FRESH_DAYS)).isoformat():
                print(f"[rivals] {upd} 캐시 — 건너뜀(--force 로 다시)")
                return 0
        except (OSError, ValueError):
            pass
    data = build()
    if not data["rivals"]:
        print("[rivals] 라이벌 0 — 위키 응답 확인(기존 파일 유지)")
        return 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(data["rivals"])
    print(f"[rivals] 클럽 문서 {data['articles']}개 · 라이벌이 있는 클럽 {n}개 → {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
