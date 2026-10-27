"""
Google News 검색 RSS — 팀마다 현지 언어 기사 + 영어 이적 기사(무료·키 없음).

ESPN 리그 뉴스만 있던 6개 리그(브뤼헤 기사 18건 중 10건이 남의 기사, 2026-10-20)와 이적 루머·기자 발 기사를 채운다.
한 팀에 두 번 검색한다:
  local     리그 나라 언어로 그 팀(최근 2일) — HLN·Sporza·Mundo Deportivo·Gazzetta 같은 현지 매체
  transfer  영어로 그 팀 + 이적 낱말(최근 3일) — FootballTransfers·TEAMtalk·CaughtOffside 등 루머 매체(로마노 등 인용)
검색어 이름 = ESPN 표기(ui.news 의 팀 태그). 한 단어 이름(Nice·Lens·Como)은 현지어 '축구' 낱말을 붙여 동음이의어를 줄이고,
나머지 섞임은 화면 쪽 관련성 거르기(src/news_relevance.py)가 막는다.
링크는 Google News 주소(브라우저에서 원문으로 넘어감), 사진·요약은 없다(제목만).

    python src/news_sources.py "Club Brugge" BelgianProLeague     # 한 팀 시험
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES  # noqa: E402

VIA = "gnews"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
# 나라 → (hl, gl, ceid, 현지어 '축구')
LOCALE = {
    "England": ("en-GB", "GB", "GB:en", "football"),
    "Spain": ("es", "ES", "ES:es", "fútbol"),
    "Italy": ("it", "IT", "IT:it", "calcio"),
    "Germany": ("de", "DE", "DE:de", "Fußball"),
    "France": ("fr", "FR", "FR:fr", "football"),
    "Portugal": ("pt-PT", "PT", "PT:pt-150", "futebol"),
    "Netherlands": ("nl", "NL", "NL:nl", "voetbal"),
    "Belgium": ("nl", "BE", "BE:nl", "voetbal"),
    # 라이트 리그(2026-10-22)
    "Türkiye": ("tr", "TR", "TR:tr", "futbol"),
    "Austria": ("de", "AT", "AT:de", "Fußball"),
    "Denmark": ("da", "DK", "DK:da", "fodbold"),
    "Switzerland": ("de", "CH", "CH:de", "Fussball"),
}
EN = LOCALE["England"]
# 두 언어 언론이 나뉜 나라 — 현지 검색을 언어마다(벨기에 프랑스어권 Standard·Charleroi 는 네덜란드어 검색에 거의 안 나온다)
EXTRA_LOCALES = {"Belgium": [("fr", "BE", "BE:fr", "football")],
                 "Switzerland": [("fr", "CH", "CH:fr", "football")]}     # 서부(세르베트·로잔·시옹)는 프랑스어 언론
# Google 뉴스에 그 나라 판이 없는 곳 — 영어판에서 검색하고 한 낱말 이름엔 리그 이름을 붙인다. 덴마크(DK:da)는 노르웨이판(NO:no)과
# 똑같은 결과를 주고 덴마크 매체가 하나도 없었다(2026-10-27: 덴마크 12팀 30일 구글 기사 0~7건, 'OB'·'AGF' 0건 ↔ 영어판 7~9건)
# 한정어는 OR 묶음 — 'Superliga' 하나면 AGF 0건, '(Superliga OR Superligaen OR Danish)'면 12건(14일)
NO_EDITION = {"Denmark": "(Superliga OR Superligaen OR Danish)"}
TRANSFER_Q = '(transfer OR signing OR "here we go" OR bid OR loan)'
PER_QUERY = 8                  # 검색 한 번에 최신순으로 이만큼까지
DAILY_CAP = 12                 # 팀당 하루 새 기사 상한(news.db 는 저장소에 커밋 — 크기 관리)
KEEP_DAYS = 30                 # Google 기사는 30일 뒤 지운다(뉴스 탭 STORY 14일·AI 요약 48시간 — news.db 는 저장소에 커밋된다)


class Breaker:
    """연속 실패(429·5xx·연결 오류)가 쌓이면 이번 실행에선 Google 을 그만 부른다."""

    def __init__(self, limit: int = 4):
        self.limit, self.fails, self.calls, self.errors = limit, 0, 0, []

    @property
    def open(self) -> bool:
        return self.fails >= self.limit

    def get(self, url: str) -> bytes | None:
        if self.open:
            return None
        self.calls += 1
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
        except requests.RequestException as e:
            self.fails += 1
            self.errors.append(type(e).__name__)
            return None
        if r.status_code != 200:
            self.fails += 1
            self.errors.append(f"HTTP {r.status_code}")
            return None
        self.fails = 0
        return r.content


def search_url(q: str, loc: tuple, days: int) -> str:
    hl, gl, ceid, _ = loc
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(f'{q} when:{days}d')}"
            f"&hl={hl}&gl={gl}&ceid={urllib.parse.quote(ceid)}")


def names_for(*names: str) -> list[str]:
    """검색에 쓸 이름 변형(중복·약자 표기 'Vit. Guimarães'·'Sparta R.' 제외)."""
    out: list[str] = []
    for n in names:
        n = re.sub(r"\s+", " ", str(n or "")).strip()
        # 약자 표기 제외 — 단 'St.'(Saint)는 정식 이름의 일부('FC St. Gallen' 이 빠져 프랑스어 'Saint-Gall' 만 검색됐다, 2026-10-27)
        if n and n not in out and not re.search(r"(^|\s)(?!St\.)[A-Za-zÀ-ÿ]{1,4}\.(\s|$)", n):
            out.append(n)
    return out


def query(names: list[str], loc: tuple, extra: str = "") -> str:
    """("이름1" OR "이름2") [현지어 '축구'] [extra] — 한 단어 이름(Nice·Lens·Como)이 있으면 '축구' 낱말로 좁힌다."""
    q = "(" + " OR ".join(f'"{n}"' for n in names) + ")"
    if any(len(n.split()) == 1 for n in names):
        q += f" {loc[3]}"
    return f"{q} {extra}".strip()


def _strip_outlet(title: str, outlet: str) -> str:
    """Google 제목 끝의 ' - 매체' 꼬리를 뗀다."""
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    if outlet and t.endswith(f" - {outlet}"):
        return t[: -len(outlet) - 3].strip()
    return re.sub(r"\s+[-–]\s+[^-–]{2,40}$", "", t).strip()


# 불법 중계·도박 홍보(해킹된 대학 사이트 등이 'Lens vs Troyes LIVE STREAM' 을 대량 게시) — 전각 문자·느낌표 뭉치도 같은 부류
SPAM = re.compile(r"live\s*-?\s*stream|livestream|streaming|watch\s*live|live\s*free|free\s*(tv|online|live)|en\s*direct|"
                  r"direct\s*gratuit|en\s*vivo|in\s*diretta|promo\s*code|bonus|betting\s*tips|[！-～]|[!@#~+]{2,}", re.I)
# 같은 클럽의 다른 종목·여자팀·유소년 — 1군 축구 기사만. 규칙은 화면 관련성과 한 곳(src/news_relevance.other_squad)
from news_relevance import other_squad  # noqa: E402


# 베팅 예측·배당 기사('Pronostic Bruges – RC Lens : prono, cotes', 'voorspelling - Odds') — 제목이나 매체 이름으로
BETTING = re.compile(r"\b(prono|pronostic|pronostico|pron[oó]stico|odds|cotes|betting|bet\s*tips|tipster|voorspelling|"
                     r"scommess|apuesta|wett(tipp|quote)|quote\s*e\s*pronostici|paris\s*sportifs|betmines|wincomparator)\w*", re.I)


def keep(headline: str, outlet: str) -> bool:
    return not (SPAM.search(headline) or other_squad(headline, outlet or "") or SPAM.search(outlet or "")
                or BETTING.search(headline) or BETTING.search(outlet or ""))


def parse(content: bytes, team: str, per_query: int = PER_QUERY) -> list[dict]:
    import feedparser  # noqa: PLC0415
    f = feedparser.parse(content)
    out = []
    for e in f.entries:
        outlet = ((e.get("source") or {}).get("title") or "").strip()
        home = ((e.get("source") or {}).get("href") or "").strip()      # 매체 홈 — 피드 자동 발견 후보(src/news_wires.py)
        head = _strip_outlet(e.get("title", ""), outlet)
        if not head or not e.get("link") or not keep(head, outlet):
            continue
        pp = e.get("published_parsed")
        out.append({"headline": head, "desc": "", "published": time.strftime("%Y-%m-%d", pp) if pp else "",
                    "_ts": time.mktime(pp) if pp else 0, "image": "", "link": e["link"], "teams": [team],
                    "source": outlet or "Google News", "via": VIA, "source_url": home})
    out.sort(key=lambda a: a["_ts"], reverse=True)          # Google 은 관련도순 — 최신순으로 잘라 쓴다
    for a in out:
        a.pop("_ts", None)
    return out[:per_query]


def fetch_team(team: str, names: list[str], league: str, br: Breaker, terms=None) -> list[dict]:
    """한 팀의 현지 언어 기사 + 영어 이적 기사(중복 제목 제거, 최신순).
    terms(news_relevance.team_terms) 를 주면 제목에 그 팀 이름이 나오는 기사만 — Google 은 본문만 맞아도 준다."""
    import news_relevance as nr  # noqa: PLC0415
    country = LEAGUES[league].country if league in LEAGUES else "England"
    locs = ([(*EN[:3], NO_EDITION[country])] if country in NO_EDITION
            else [LOCALE.get(country, EN), *EXTRA_LOCALES.get(country, [])])
    urls = [search_url(query(names, lc), lc, 2) for lc in locs] + [search_url(query(names, EN, TRANSFER_Q), EN, 3)]
    seen, out = set(), []
    for u in urls:
        body = br.get(u)
        if not body:
            continue
        took = 0
        for a in parse(body, team, per_query=100):
            k = re.sub(r"[^a-z0-9]", "", a["headline"].lower())[:55]
            if not k or k in seen or (terms and not nr.mentions(a["headline"], terms)):
                continue
            seen.add(k)
            out.append(a)
            took += 1
            if took >= PER_QUERY:
                break
        time.sleep(0.4)
    return sorted(out, key=lambda a: a["published"], reverse=True)


LOCAL_NAMES = Path(__file__).resolve().parent.parent / "data" / "club_local_names.json"
LOCAL_NAMES_DAYS = 7
_LN_CACHE: dict = {}


def _langlinks(titles: list[str], lang: str) -> dict[str, str]:
    """{요청 제목: lang 위키 제목} — 영어 위키 언어 간 링크(넘겨주기 따라감, 동음이의 문서 제외)."""
    import fetch_wiki_squads as wiki  # noqa: PLC0415
    out: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        q = wiki._get({"action": "query", "prop": "langlinks|pageprops", "lllang": lang, "lllimit": 500,   # noqa: SLF001
                       "ppprop": "disambiguation", "redirects": 1, "titles": "|".join(chunk)}).get("query", {})
        back = {t: t for t in chunk}
        for m in q.get("normalized", []) + q.get("redirects", []):
            for k, v in list(back.items()):
                if v == m["from"]:
                    back[k] = m["to"]
        got = {pg["title"]: pg["langlinks"][0]["title"] for pg in q.get("pages", [])
               if pg.get("langlinks") and "disambiguation" not in (pg.get("pageprops") or {})}
        out.update({req: got[fin] for req, fin in back.items() if fin in got})
        time.sleep(1.0)
    return out


def cached_local_names(team: str) -> list[str]:
    """캐시된 현지 표기만(수집 없이) — 화면 관련성 거르기가 'Standard Luik' 제목도 이 팀 기사로 알아보게."""
    import json  # noqa: PLC0415
    try:
        key = LOCAL_NAMES.stat().st_mtime
        if _LN_CACHE.get("key") != key:
            _LN_CACHE.update(key=key, data=json.loads(LOCAL_NAMES.read_text(encoding="utf-8")))
        cache = _LN_CACHE["data"]
    except (OSError, ValueError):
        return []
    for ent in cache.values():
        if team in (ent.get("teams") or {}):
            return [x for x in ent["teams"][team] if len(x.split()) <= 4]
    return []


def local_names(league: str, tags: dict) -> dict[str, list[str]]:
    """{팀: 현지 언어 표기} — 영어 위키 문서의 언어 간 링크(nl 'Standard Luik'·fr 'Standard de Liège'·de 'Inter Mailand').
    현지 언론이 쓰는 이름을 손으로 적지 않는다. data/club_local_names.json 에 리그·언어별 7일 캐시."""
    import datetime as dt  # noqa: PLC0415
    import json  # noqa: PLC0415

    import teammeta as tm  # noqa: PLC0415
    country = LEAGUES[league].country if league in LEAGUES else "England"
    langs = [lc[0][:2] for lc in [LOCALE.get(country, EN), *EXTRA_LOCALES.get(country, [])] if lc[0][:2] != "en"]
    if not langs:
        return {}
    cache = json.loads(LOCAL_NAMES.read_text(encoding="utf-8")) if LOCAL_NAMES.exists() else {}
    ent = cache.get(league) or {}
    fresh = ent.get("updated", "") >= (dt.date.today() - dt.timedelta(days=LOCAL_NAMES_DAYS)).isoformat()
    if not (fresh and set(langs) <= set(ent.get("langs", [])) and set(tags) <= set(ent.get("teams", {}))):
        teams: dict[str, list[str]] = {}
        try:
            cand = {t: [tm.team_fullname(t), tags.get(t) or t] for t in tags}
            for lang in langs:
                got = _langlinks(sorted({c for cs in cand.values() for c in cs if c}), lang)
                for t, cs in cand.items():
                    hit = next((got[c] for c in cs if c in got), None)
                    lst = teams.setdefault(t, [])
                    if hit and hit not in lst:
                        lst.append(hit)
        except Exception as e:  # noqa: BLE001 — 위키가 막히면 지난 캐시로
            print(f"[google] 현지 표기(위키) 실패: {type(e).__name__} — 지난 캐시 사용")
            return ent.get("teams", {})
        cache[league] = {"updated": dt.date.today().isoformat(), "langs": langs, "teams": teams}
        LOCAL_NAMES.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        ent = cache[league]
    return ent.get("teams", {})


def fetch_league(league: str, tags: dict, br: Breaker, workers: int = 3) -> dict[str, list[dict]]:
    """리그 전 팀 — {팀: 기사}. tags = ui.news.newstags(league)(팀 → ESPN 표기). 3개씩 나란히(팀당 검색 2번)."""
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    import news_relevance as nr  # noqa: PLC0415
    import teammeta as tm  # noqa: PLC0415

    local = local_names(league, tags)

    def one(team: str) -> tuple[str, list[dict]]:
        nm = names_for(tags.get(team) or team, team, tm.team_fullname(team),
                       *[x for x in local.get(team, []) if len(x.split()) <= 4])   # 'Borussia Verein für … 1900 …' 같은 정식명은 빼고
        return team, fetch_team(team, nm, league, br, nr.team_terms(team, tuple(nm)))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(one, list(tags)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import news_relevance as _nr
    import teammeta as _tm
    from ui.news import newstags
    t, lg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "EPL")
    nm = names_for(newstags(lg).get(t, t), t, _tm.team_fullname(t), *local_names(lg, newstags(lg)).get(t, []))
    b = Breaker()
    print("names", nm)
    for a in fetch_team(t, nm, lg, b, _nr.team_terms(t, tuple(nm))):
        print(a["published"], f"[{a['source']}]", a["headline"])
    print("calls", b.calls, "errors", b.errors)
