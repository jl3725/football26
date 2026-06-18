"""
뉴스 탭 — ESPN 축구 뉴스 API + 무료 번역(deep-translator).

ESPN /news 엔드포인트(키 불필요)에서 EPL 기사를 받아 팀 태그로 필터링하고,
영어 헤드라인·요약을 한국어로 번역해 카드로 렌더한다. 기사 전문이 아니라
헤드라인+요약+원문 링크만 표시(저작권 안전). RSS 보강·LLM 요약은 후속 단계.
"""
from __future__ import annotations

import html

import requests

from .common import team_color

ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/news?limit=50"
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


def fetch_espn_news() -> list[dict]:
    """ESPN EPL 뉴스 50건 → [{headline, desc, published, image, link, teams}]."""
    try:
        r = requests.get(ESPN_NEWS_URL, headers=_HEADERS, timeout=15)
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
        })
    return out


def has_team_news(articles: list[dict], team: str) -> bool:
    """해당 팀 전용 태그 기사가 하나라도 있는지."""
    tag = SQUAD_TO_NEWSTAG.get(team)
    return bool(tag and any(tag in a["teams"] for a in articles))


def team_articles(articles: list[dict], team: str, limit: int = 12) -> list[dict]:
    """팀 태그로 필터. 매칭 기사가 없으면 EPL 일반 뉴스 상위로 폴백."""
    tag = SQUAD_TO_NEWSTAG.get(team)
    hit = [a for a in articles if tag and tag in a["teams"]]
    return (hit or articles)[:limit]


def translate_articles(articles: list[dict]) -> list[dict]:
    """헤드라인·요약을 한국어로 번역해 headline_ko·desc_ko 추가. 실패 시 원문 유지."""
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="en", target="ko")
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
    """뉴스 카드 그리드 — 썸네일·번역 헤드라인(+원문)·요약·발행일·원문 링크."""
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
        cards.append(
            f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;overflow:hidden;"
            f"box-shadow:0 1px 3px rgba(16,24,40,.04),0 8px 22px rgba(16,24,40,.06)'>"
            f"{thumb}"
            f"<div style='padding:13px 15px 15px'>"
            f"<div style='font-size:10.5px;color:#9aa3b2;font-weight:800;margin-bottom:6px'>"
            f"ESPN · {pub}</div>"
            f"<div style='font-size:14.5px;font-weight:900;color:#1a1f2e;line-height:1.32'>{head_ko}</div>"
            f"<div style='font-size:11px;color:#9aa3b2;margin-top:3px;line-height:1.3'>{head_en}</div>"
            f"<div style='font-size:12.5px;color:#5a6273;margin-top:9px;line-height:1.5'>{desc_ko}</div>"
            f"{link_btn}</div></div>"
        )
    return (
        f"<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:16px;"
        f"font-family:-apple-system,BlinkMacSystemFont,sans-serif'>{''.join(cards)}</div>"
    )
