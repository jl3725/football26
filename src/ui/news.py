"""
뉴스 탭 — ESPN 뉴스 API + Guardian/BBC RSS + 무료 번역(deep-translator).

ESPN /news(키 불필요) + The Guardian·BBC Sport 팀별 RSS를 합쳐 기사량을 확보하고,
영어 헤드라인·요약을 한국어로 번역해 카드로 렌더한다. 기사 전문이 아니라
헤드라인+요약+원문 링크만 표시(저작권 안전). LLM 요약/분류는 후속 단계.
"""
from __future__ import annotations

import html
import re
import time

import requests

from .common import team_color

ESPN_NEWS_CODES = {"EPL": "eng.1", "LaLiga": "esp.1", "SerieA": "ita.1",
                   "Bundesliga": "ger.1", "Ligue1": "fra.1"}
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 우리 squad 표기 → ESPN 뉴스 팀 태그(longName)
SQUAD_TO_NEWSTAG = {
    "Arsenal": "Arsenal", "Aston Villa": "Aston Villa", "Bournemouth": "Bournemouth",
    "Brentford": "Brentford", "Brighton": "Brighton & Hove Albion", "Burnley": "Burnley",
    "Chelsea": "Chelsea", "Crystal Palace": "Crystal Palace", "Everton": "Everton",
    "Fulham": "Fulham", "Leeds United": "Leeds United", "Liverpool": "Liverpool",
    "Manchester City": "Manchester City", "Manchester Utd": "Manchester United",
    "Newcastle United": "Newcastle United", "Nottingham Forest": "Nottingham Forest",
    "Sunderland": "Sunderland", "Tottenham Hotspur": "Tottenham Hotspur",
    "West Ham United": "West Ham United", "Wolves": "Wolverhampton Wanderers",
}

# LaLiga squad → ESPN esp.1 뉴스 팀 태그 (Guardian/BBC RSS 없음 → ESPN만)
LALIGA_NEWSTAG = {
    "Alavés": "Deportivo Alavés", "Athletic Club": "Athletic Bilbao",
    "Atlético Madrid": "Atlético Madrid", "Barcelona": "Barcelona", "Celta Vigo": "Celta Vigo",
    "Elche": "Elche", "Espanyol": "Espanyol", "Getafe": "Getafe", "Girona": "Girona",
    "Levante": "Levante", "Mallorca": "Mallorca", "Osasuna": "Osasuna", "Oviedo": "Real Oviedo",
    "Rayo Vallecano": "Rayo Vallecano", "Real Betis": "Real Betis", "Real Madrid": "Real Madrid",
    "Real Sociedad": "Real Sociedad", "Sevilla": "Sevilla", "Valencia": "Valencia",
    "Villarreal": "Villarreal",
}

NEWSTAG_BY_LEAGUE = {"EPL": SQUAD_TO_NEWSTAG, "LaLiga": LALIGA_NEWSTAG}
_ALL_NEWSTAG = {**SQUAD_TO_NEWSTAG, **LALIGA_NEWSTAG}


def newstags(league: str = "EPL") -> dict:
    return NEWSTAG_BY_LEAGUE.get(league, SQUAD_TO_NEWSTAG)


# 스페인 리그 전체 와이어(팀별 RSS 없음 → 헤드라인 팀명 매칭). AS·Mundo Deportivo·Sport.
ES_WIRE_FEEDS = [
    ("AS", "https://as.com/rss/futbol/portada.xml"),
    ("Mundo Deportivo", "https://www.mundodeportivo.com/feed/rss/futbol/"),
    ("Sport", "https://www.sport.es/es/rss/futbol/rss.xml"),
]
# 팀 → 매칭 토큰(고유 별칭 우선, 모호한 'madrid' 단독 등은 제외)
ES_MATCH = {
    "Barcelona": ["barça", "barcelona", "barsa", "azulgrana", "culé"],
    "Real Madrid": ["real madrid", "madridista", "merengue", "blancos"],
    "Atlético Madrid": ["atlético", "atleti", "colchonero"],
    "Sevilla": ["sevilla", "sevillista", "nervionense"],
    "Real Betis": ["betis", "bético", "verdiblanco"],
    "Valencia": ["valencia", "valencianista"],
    "Villarreal": ["villarreal", "groguet", "submarino amarillo"],
    "Athletic Club": ["athletic", "bilbao", "leones"],
    "Real Sociedad": ["real sociedad", "txuri", "donostia", "erreala"],
    "Celta Vigo": ["celta", "celeste", "vigo"],
    "Espanyol": ["espanyol", "perico", "periquito"],
    "Getafe": ["getafe", "azulón"],
    "Girona": ["girona", "gironí"],
    "Osasuna": ["osasuna", "rojillo", "pamplona"],
    "Rayo Vallecano": ["rayo", "vallecano", "franjirrojo"],
    "Alavés": ["alavés", "alaves", "babazorro"],
    "Mallorca": ["mallorca", "bermellón"],
    "Elche": ["elche", "franjiverde"],
    "Levante": ["levante", "granota"],
    "Oviedo": ["oviedo", "carbayón"],
}


def fetch_es_wire() -> list[dict]:
    """AS·MD·Sport 리그 전체 축구 피드(스페인어) — 리그 실행당 1회. 팀은 이후 매칭."""
    try:
        import feedparser
    except Exception:
        return []
    out = []
    for source, url in ES_WIRE_FEEDS:
        try:
            f = feedparser.parse(url)
        except Exception:
            continue
        for e in f.entries[:60]:
            head = _clean(e.get("title", ""))
            if not head:
                continue
            pub = (time.strftime("%Y-%m-%d", e["published_parsed"]) if e.get("published_parsed") else "")
            out.append({"headline": head, "desc": _clean(e.get("summary", ""))[:400],
                        "published": pub, "image": "", "link": e.get("link", ""),
                        "teams": [], "source": source, "_text": (head + " " + _clean(e.get("summary", ""))).lower()})
    return out


def es_wire_for_team(wire: list[dict], team: str, limit: int = 6) -> list[dict]:
    """리그 와이어에서 팀명 토큰 매칭 기사만."""
    toks = ES_MATCH.get(team)
    if not toks:
        return []
    hit = [dict(a, teams=[team]) for a in wire if any(t in a.get("_text", "") for t in toks)]
    return hit[:limit]


# Marca 팀별 RSS 슬러그 (LaLiga — 스페인 원매체, Guardian/BBC 대응). 전 20팀 확인됨.
MARCA_SLUG = {
    "Alavés": "alaves", "Athletic Club": "athletic", "Atlético Madrid": "atletico",
    "Barcelona": "barcelona", "Celta Vigo": "celta", "Elche": "elche", "Espanyol": "espanyol",
    "Getafe": "getafe", "Girona": "girona", "Levante": "levante", "Mallorca": "mallorca",
    "Osasuna": "osasuna", "Oviedo": "oviedo", "Rayo Vallecano": "rayo", "Real Betis": "betis",
    "Real Madrid": "real-madrid", "Real Sociedad": "real-sociedad", "Sevilla": "sevilla",
    "Valencia": "valencia", "Villarreal": "villarreal",
}

# The Guardian 팀별 RSS slug (Brighton은 Guardian RSS 없음 → ESPN/BBC로 보완)
GUARDIAN_SLUG = {
    "Arsenal": "arsenal", "Aston Villa": "aston-villa", "Bournemouth": "bournemouth",
    "Brentford": "brentford", "Burnley": "burnley", "Chelsea": "chelsea",
    "Crystal Palace": "crystalpalace", "Everton": "everton", "Fulham": "fulham",
    "Leeds United": "leedsunited", "Liverpool": "liverpool", "Manchester City": "manchestercity",
    "Manchester Utd": "manchesterunited", "Newcastle United": "newcastleunited",
    "Nottingham Forest": "nottinghamforest", "Sunderland": "sunderland",
    "Tottenham Hotspur": "tottenham-hotspur", "West Ham United": "westhamunited",
    "Wolves": "wolves",
}

# BBC Sport 팀별 RSS slug (title이 팀명이라 summary를 헤드라인으로 사용)
BBC_SLUG = {
    "Arsenal": "arsenal", "Aston Villa": "aston-villa", "Bournemouth": "bournemouth",
    "Brentford": "brentford", "Brighton": "brighton-hove-albion", "Burnley": "burnley",
    "Chelsea": "chelsea", "Crystal Palace": "crystal-palace", "Everton": "everton",
    "Fulham": "fulham", "Leeds United": "leeds-united", "Liverpool": "liverpool",
    "Manchester City": "manchester-city", "Manchester Utd": "manchester-united",
    "Newcastle United": "newcastle-united", "Nottingham Forest": "nottingham-forest",
    "Sunderland": "sunderland", "Tottenham Hotspur": "tottenham-hotspur",
    "West Ham United": "west-ham-united", "Wolves": "wolverhampton-wanderers",
}


def _clean(text: str) -> str:
    """RSS summary의 HTML 태그·과잉 공백 제거."""
    t = re.sub(r"<[^>]+>", "", str(text or ""))
    return re.sub(r"\s+", " ", t).strip()


def fetch_espn_news(league: str = "EPL") -> list[dict]:
    """ESPN 리그 뉴스 50건 → [{headline, desc, published, image, link, teams, source}]."""
    code = ESPN_NEWS_CODES.get(league, "eng.1")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/news?limit=50"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if not r.ok:
            return []
        arts = r.json().get("articles", [])
    except Exception:
        return []
    out = []
    for a in arts:
        imgs = a.get("images") or []
        out.append({
            "headline": a.get("headline", "") or "",
            "desc": (a.get("description", "") or "")[:400],
            "published": (a.get("published", "") or "")[:10],
            "image": (imgs[0].get("url", "") if imgs else ""),
            "link": a.get("links", {}).get("web", {}).get("href", ""),
            "teams": [c.get("description") for c in a.get("categories", [])
                      if c.get("type") == "team"],
            "source": "ESPN",
        })
    return out


def fetch_rss_news(team: str, per_feed: int = 12) -> list[dict]:
    """팀별 Guardian + BBC RSS → ESPN과 동일 형식의 기사 리스트."""
    try:
        import feedparser
    except Exception:
        return []
    feeds = []
    if team in GUARDIAN_SLUG:
        feeds.append(("The Guardian",
                      f"https://www.theguardian.com/football/{GUARDIAN_SLUG[team]}/rss", False))
    if team in BBC_SLUG:
        feeds.append(("BBC Sport",
                      f"https://feeds.bbci.co.uk/sport/football/teams/{BBC_SLUG[team]}/rss.xml", True))
    if team in MARCA_SLUG:   # LaLiga — 스페인 원매체(팀별 RSS)
        feeds.append(("Marca",
                      f"https://e00-marca.uecdn.es/rss/futbol/{MARCA_SLUG[team]}.xml", False))
    out = []
    for source, url, is_bbc in feeds:
        try:
            f = feedparser.parse(url)
        except Exception:
            continue
        for e in f.entries[:per_feed]:
            # BBC는 <title>이 팀명이고 <summary>가 실제 헤드라인
            headline = _clean(e.get("summary", "")) if is_bbc else _clean(e.get("title", ""))
            desc = "" if is_bbc else _clean(e.get("summary", ""))[:400]
            pub = (time.strftime("%Y-%m-%d", e["published_parsed"])
                   if e.get("published_parsed") else "")
            img = ""
            if e.get("media_thumbnail"):
                img = e["media_thumbnail"][0].get("url", "")
            elif e.get("media_content"):
                img = e["media_content"][0].get("url", "")
            if not headline:
                continue
            out.append({
                "headline": headline, "desc": desc, "published": pub,
                "image": img, "link": e.get("link", ""), "teams": [team], "source": source,
            })
    return out


def has_team_news(articles: list[dict], team: str) -> bool:
    """해당 팀 전용 태그 기사가 하나라도 있는지(ESPN 기준)."""
    tag = _ALL_NEWSTAG.get(team)
    return bool(tag and any(tag in a["teams"] for a in articles))


def team_articles(articles: list[dict], team: str, limit: int = 12) -> list[dict]:
    """ESPN 기사에서 팀 태그로 필터(EPL·LaLiga). 매칭 없으면 일반 뉴스 상위로 폴백."""
    tag = _ALL_NEWSTAG.get(team)
    hit = [a for a in articles if tag and tag in a["teams"]]
    return (hit or articles)[:limit]


def merge_news(espn_team: list[dict], rss: list[dict], limit: int = 16) -> list[dict]:
    """ESPN(팀) + RSS 통합 → 헤드라인 중복 제거 + 발행일 내림차순."""
    seen: set[str] = set()
    out = []
    for a in sorted(espn_team + rss, key=lambda x: x.get("published", ""), reverse=True):
        h = a.get("headline", "")
        if not h:
            continue
        key = re.sub(r"[^a-z0-9]", "", h.lower())[:55]
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out[:limit]


def translate_articles(articles: list[dict]) -> list[dict]:
    """헤드라인·요약을 한국어로 번역해 headline_ko·desc_ko 추가. 실패 시 원문 유지."""
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="auto", target="ko")  # en(EPL)·es(Marca) 자동 감지
    except Exception:
        tr = None

    def _t(text: str) -> str:
        if not text or tr is None:
            return text
        try:
            return tr.translate(text) or text
        except Exception:
            return text

    out = []
    for a in articles:
        b = dict(a)
        b["headline_ko"] = _t(a["headline"])
        b["desc_ko"] = _t(a["desc"])
        out.append(b)
    return out


def news_cards_html(team: str, articles: list[dict]) -> str:
    """뉴스 카드 그리드 — 썸네일·번역 헤드라인(+원문)·요약·출처·발행일·원문 링크."""
    if not articles:
        return ("<div style='padding:28px;text-align:center;color:#8a93a5;"
                "font-family:sans-serif'>관련 기사를 찾지 못했습니다.</div>")
    tcol = team_color(team)
    cards = []
    for a in articles:
        head_ko = html.escape(a.get("headline_ko") or a.get("headline", ""))
        head_en = html.escape(a.get("headline", ""))
        desc_ko = html.escape(a.get("desc_ko") or a.get("desc", ""))
        pub = html.escape(a.get("published", ""))
        src = html.escape(a.get("source", ""))
        link = html.escape(a.get("link", ""))
        img = a.get("image", "")
        thumb = (
            f"<div style='height:150px;background:#0d1117 url(\"{img}\") center/cover no-repeat'></div>"
            if img else
            f"<div style='height:150px;background:linear-gradient(135deg,{tcol},#10151c);"
            f"display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5);"
            f"font-size:13px;font-weight:800'>📰</div>"
        )
        link_btn = (
            f"<a href='{link}' target='_blank' rel='noopener noreferrer' "
            f"style='display:inline-block;margin-top:9px;font-size:11.5px;font-weight:800;"
            f"color:{tcol};text-decoration:none'>원문 보기 ↗</a>" if link else ""
        )
        new_badge = (
            "<span style='display:inline-block;margin-left:6px;padding:1px 7px;border-radius:6px;"
            "background:#e8344e;color:#fff;font-size:9px;font-weight:950;letter-spacing:.5px;"
            "vertical-align:middle'>NEW</span>" if a.get("is_new") else ""
        )
        desc_html = (f"<div style='font-size:12.5px;color:#5a6273;margin-top:9px;"
                     f"line-height:1.5'>{desc_ko}</div>") if desc_ko else ""
        cards.append(
            f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;overflow:hidden;"
            f"box-shadow:0 1px 3px rgba(16,24,40,.04),0 8px 22px rgba(16,24,40,.06)'>"
            f"{thumb}"
            f"<div style='padding:13px 15px 15px'>"
            f"<div style='font-size:10.5px;color:#9aa3b2;font-weight:800;margin-bottom:6px'>"
            f"{src} · {pub}{new_badge}</div>"
            f"<div style='font-size:14.5px;font-weight:900;color:#1a1f2e;line-height:1.32'>{head_ko}</div>"
            f"<div style='font-size:11px;color:#9aa3b2;margin-top:3px;line-height:1.3'>{head_en}</div>"
            f"{desc_html}"
            f"{link_btn}</div></div>"
        )
    return (
        f"<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:16px;"
        f"font-family:-apple-system,BlinkMacSystemFont,sans-serif'>{''.join(cards)}</div>"
    )
