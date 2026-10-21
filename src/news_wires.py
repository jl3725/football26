"""
뉴스 와이어 — 매체 RSS(요약·작성자) · FotMob 팀 뉴스 · 블루스카이 기자 계정을 받아 팀별 기사로 news.db 에 쌓는다.

2026-10-21 사용자: "무료 소스가 너무 적다 — 무료로 원천을 늘리고 KG 에도". 그때까지는 ESPN·몇몇 매체 RSS + 구글 뉴스(제목만)라
하루 약 700건, 루머 근거(뉴스) 23건이었다. 무료로 확인한 원천(같은 날 시험):
  wire    매체 RSS — 8개 리그 나라 28개 매체(talkSPORT·90min·TuttoMercatoWeb·Record·VI·HLN …), 요약 + 작성자(바이라인)
  fotmob  FotMob 팀 뉴스(/api/data/tlnews) — 팀마다 여러 매체 기사 20건, 리그 나라 언어
  bsky    블루스카이 공개 API — 기자 본인 계정(온스테인 등)·X 미러 계정. 글쓴이 = 기자
레딧은 키 없이 요청 제한(429)이라, X 는 유료라 뺐다.

매체 목록(data/news_feeds.json)은 손으로 늘리지 않는다 — 구글 뉴스 검색 결과에 자주 나오는 매체 도메인을 세어(note_sources)
주 1회 피드를 스스로 찾고(홈 rel=alternate · 흔한 경로), 우리 팀 기사 비율이 낮은 피드는 버린다(discover). 계속 실패하는 피드는 끈다.
기자 계정(data/news_insiders.json)도 학습한 기자 이름(news_journalists.csv)으로 블루스카이를 찾아 붙인다(refresh_insiders).

팀 판정(TeamIndex): 우리 클럽 이름·ESPN 표기의 고유 낱말(한 클럽에만 있는 말) + 위키 현지 표기 전체 + 선수 이름 전체.
현지 표기는 통째로만('Sport Lisboa e Benfica' 의 'Lisboa'·'Sporting Clube de Portugal' 의 'Portugal' 은 도시·나라 기사에 붙었다).
6자 미만이라도 원문이 대문자 약자(PSG·PSV)면 다른 나라 매체에서도 맞춘다.
한 낱말 별칭은 글에서 대문자로 시작할 때만(고유명사). 6자 미만(Nice·Lens·Roma)이거나, 이번에 받은 피드 글에서 소문자로도
쓰이는 낱말(영어 'standard'·스페인어 'sociedad' — 일반 낱말, 매번 피드 글에서 배운다)은 그 클럽 나라 매체에서만. 기사 하나에 클럽 최대 3개.
제목에 클럽이 있으면 제목 클럽만(요약에 지나가듯 나온 클럽은 딴 얘기 — 첫 시험에서 'Brentford …' 기사가 Liverpool 로 붙었다),
제목에 없을 때만 요약에서 — 그때는 두 낱말 이상 별칭·선수 이름 전체만, 클럽 1개.
사람 이름과 겹치는 한 낱말(선수 이름·성에 나오는 'Germain')도 일반 낱말처럼 다루고, 일반 낱말은 문장 첫 낱말이면 안 맞춘다
('Vitória épica de Angola' — 포르투갈어 '승리'). 도박·중계·여자팀·유소년 기사는 구글 뉴스와 같은 거르개(news_sources.keep).
보관: wire·fotmob·bsky 는 KEEP_DAYS 뒤 지운다(구글 뉴스와 같은 규칙). 크기 안전장치는 src/news_store.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_sources as gn  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / "data" / "news_feeds.json"
INSIDERS = ROOT / "data" / "news_insiders.json"
FM_IDS = ROOT / "data" / "fotmob_team_ids.json"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) football26-news"}
MAX_CLUBS = 3            # 기사 하나에 붙이는 클럽 상한
SHORT = 6                # 이보다 짧은 한 낱말 별칭은 그 클럽 나라 매체에서만
MAX_AGE_DAYS = 3         # 이보다 오래된 피드 항목은 넣지 않는다
WIRE_DAILY_CAP = 30      # 팀당 하루 wire 기사 상한
FOTMOB_GROUPS = 4        # FotMob 팀 뉴스 — 팀을 나눠 실행마다 한 묶음(2시간 실행 → 팀마다 8시간에 한 번)
KEEP_DAYS = 30
FM_LANG = {"England": "en", "Spain": "es", "Italy": "it", "Germany": "de", "France": "fr", "Portugal": "pt",
           "Netherlands": "nl", "Belgium": "nl"}
DISCOVER_EVERY_DAYS = 7
DISCOVER_BUDGET_S = 150
MIN_MATCH_RATE = 0.15    # 새 피드 — 항목 중 우리 팀 기사 비율이 이보다 낮으면 버림
FEED_PATHS = ["/rss", "/feed", "/rss.xml", "/feed/", "/rss/", "/feeds/rss", "/arc/outboundfeeds/rss/"]


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


def _clean(s, n: int = 400) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))
    return " ".join(t.split())[:n]


def _today() -> str:
    return dt.date.today().isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ── 팀 판정 ─────────────────────────────────────────────────────────────────
class TeamIndex:
    """기사 글 → 우리 클럽(들). 고유 별칭 낱말·선수 이름 전체의 n-gram 일치."""

    def __init__(self):
        import news_relevance as nr  # noqa: PLC0415
        from ui.news import newstags  # noqa: PLC0415
        self.country: dict[str, str] = {}
        term_clubs: dict[str, set] = defaultdict(set)
        for lg in LEAGUES:
            for squad, tag in newstags(lg).items():
                self.country[squad] = LEAGUES[lg].country
                for t in nr.team_terms(squad, (tag,) if tag and tag != squad else ()):
                    term_clubs[t].add(squad)
                for loc in gn.cached_local_names(squad):      # 현지 표기는 통째로만
                    f = _fold(loc)
                    if len(f) >= 4:
                        term_clubs[f].add(squad)
        self.terms = {t: next(iter(cs)) for t, cs in term_clubs.items() if len(cs) == 1}
        self.players: dict[str, str] = {}
        dup: set = set()
        for lg in LEAGUES:
            p = data_path("players_full", lg)
            if not p.exists():
                continue
            import pandas as pd  # noqa: PLC0415
            for name, sq in pd.read_csv(p, usecols=["player", "squad"]).itertuples(index=False):
                k = _fold(name)
                if len(k.split()) < 2 or sq not in self.country:
                    continue
                if k in self.players and self.players[k] != sq:
                    dup.add(k)
                self.players[k] = sq
        for k in dup:
            self.players.pop(k, None)
        self.maxn = max([len(t.split()) for t in [*self.terms, *self.players]] or [1])
        # 소문자로도 쓰이는 일반 낱말(learn_common) + 사람 이름 낱말(선수 이름·성) — 그 클럽 나라 매체에서만
        self.common: set[str] = {w for k in self.players for w in k.split()} & {t for t in self.terms if " " not in t}

    def learn_common(self, texts) -> None:
        """피드 글에서 소문자로 쓰인 낱말 — 한 낱말 별칭 중 이것들은 일반 낱말로 보고 그 클럽 나라 매체에서만 받는다."""
        one = {t for t in self.terms if " " not in t}
        for s in texts:
            for w in re.findall(r"[A-Za-z0-9]+", unidecode(str(s or ""))):
                if w.islower() and w in one:
                    self.common.add(w)

    def _grams(self, text: str) -> list[tuple[str, bool]]:
        """(접은 n-gram, 원문이 대문자로 시작) — 한 낱말 별칭은 고유명사로 쓰였을 때만 맞춘다."""
        raw = re.findall(r"[A-Za-z0-9]+", unidecode(str(text or "")))
        w = [x.lower() for x in raw]
        cap = [2 if len(x) >= 3 and x.isupper() else int(x[:1].isupper()) for x in raw]   # 2 = 대문자 약자
        out = []
        for n in range(1, self.maxn + 1):
            out += [(" ".join(w[i:i + n]), cap[i], i) for i in range(len(w) - n + 1)]
        return out

    def _find(self, text: str, country: str | None, strict: bool) -> list[tuple[str, str]]:
        """[(클럽, 맞은 말)] — strict 면 한 낱말 클럽 별칭은 안 쓴다(요약용)."""
        out: list[tuple[str, str]] = []
        for g, cap, i in self._grams(text):
            club = self.players.get(g)
            if club is None:
                club = self.terms.get(g)
                if club and " " not in g:
                    if strict or not cap or (i == 0 and g in self.common):
                        continue
                    acronym = cap == 2 and len(g) < SHORT and g not in self.common
                    if (len(g) < SHORT or g in self.common) and not acronym and self.country.get(club) != country:
                        continue
            if club and club not in {c for c, _ in out}:
                out.append((club, g))
        return out

    def why(self, head: str, desc: str = "", country: str | None = None) -> list[tuple[str, str]]:
        found = self._find(head, country, strict=False)
        return found[:MAX_CLUBS] if found else self._find(desc, country, strict=True)[:1]

    def match(self, head: str, desc: str = "", country: str | None = None) -> list[str]:
        return [c for c, _ in self.why(head, desc, country)]


# ── 매체 RSS ────────────────────────────────────────────────────────────────
def _parse_feed(content: bytes) -> list[dict]:
    import feedparser  # noqa: PLC0415
    f = feedparser.parse(content)
    out = []
    for e in f.entries:
        head = _clean(e.get("title"), 300)
        link = e.get("link") or ""
        if not head or not link:
            continue
        pp = e.get("published_parsed") or e.get("updated_parsed")
        author = _clean(e.get("author") or (e.get("authors") or [{}])[0].get("name", ""), 80)
        tags = " ".join(_clean(t.get("term"), 60) for t in (e.get("tags") or []) if t.get("term"))
        out.append({"headline": head, "desc": _clean(e.get("summary") or e.get("description"), 400),
                    "published": time.strftime("%Y-%m-%d", pp) if pp else "", "link": link, "author": author,
                    "_tags": tags, "image": ""})
    return out


def fetch_feed(url: str) -> list[dict] | None:
    try:
        r = requests.get(url, headers=H, timeout=25)
        if r.status_code != 200:
            return None
        return _parse_feed(r.content)
    except requests.RequestException:
        return None


def _fresh(published: str, days: int = MAX_AGE_DAYS) -> bool:
    if not published:
        return True
    try:
        return dt.date.fromisoformat(published[:10]) >= dt.date.today() - dt.timedelta(days=days)
    except ValueError:
        return True


def wire_articles(idx: TeamIndex, feeds: dict) -> tuple[dict[str, list[dict]], dict]:
    """{클럽: [기사]}, 피드별 통계. 피드 상태(ok·fail·items·match_rate)는 feeds 에 적는다."""
    out: dict[str, list[dict]] = defaultdict(list)
    stats = {}
    got: list[tuple[str, dict, list[dict]]] = []
    for url, f in feeds.get("feeds", {}).items():
        if f.get("off"):
            continue
        items = fetch_feed(url)
        if items is None:
            f["fail"] = int(f.get("fail", 0)) + 1
            if f["fail"] >= 12 and f.get("ok", "") < (dt.date.today() - dt.timedelta(days=7)).isoformat():
                f["off"] = _today()                 # 일주일 넘게 계속 실패 — 끈다(다음 발견 때 다시 시험)
            stats[f.get("outlet", url)] = "실패"
            continue
        f.update(fail=0, ok=_today(), items=len(items))
        got.append((url, f, items))
        time.sleep(0.3)
    idx.learn_common(f"{a['headline']} {a['desc']}" for _, _, items in got for a in items)
    for url, f, items in got:
        hit = 0
        for a in items:
            if not _fresh(a["published"]) or not gn.keep(a["headline"], f.get("outlet", "")):
                continue
            clubs = idx.match(a["headline"], f"{a['desc']} {a['_tags']}", f.get("country"))
            if not clubs:
                continue
            hit += 1
            a = {**a, "source": f.get("outlet") or urlparse(url).netloc, "via": "wire"}
            a.pop("_tags", None)
            for c in clubs:
                out[c].append(a)
        f["match_rate"] = round(hit / max(1, len(items)), 2)
        stats[f.get("outlet", url)] = hit
    return out, stats


# ── 피드 발견(구글 뉴스에 자주 나오는 매체) ─────────────────────────────────────
def note_sources(arts: list[dict], country: str, feeds: dict) -> None:
    """구글 뉴스 기사들의 매체 도메인을 센다 — 발견 후보."""
    cand = feeds.setdefault("candidates", {})
    for a in arts:
        u = a.get("source_url") or ""
        d = urlparse(u).netloc.lower().removeprefix("www.")
        if not d or "google." in d:
            continue
        c = cand.setdefault(d, {"outlet": a.get("source") or d, "country": country, "n": 0, "last": ""})
        c["n"] += 1
        c["last"] = _today()
    stale = (dt.date.today() - dt.timedelta(days=60)).isoformat()      # 두 달 안 보인 후보는 버린다(파일이 끝없이 크지 않게)
    for d in [d for d, c in cand.items() if c.get("last", "") < stale]:
        cand.pop(d)


def find_feed(domain: str) -> str | None:
    """홈의 rel=alternate RSS/Atom 링크, 없으면 흔한 경로 — 항목 5개 이상인 첫 피드. domain 은 'bbc.co.uk/sport/football' 처럼 경로 포함 가능."""
    home = f"https://{domain.strip('/')}"
    base = f"https://{domain.split('/')[0]}"
    cands = []
    try:
        r = requests.get(home, headers=H, timeout=20)
        if r.status_code == 200:
            for m in re.finditer(r'<link[^>]+(?:application/(?:rss|atom)\+xml)[^>]*>', r.text):
                hm = re.search(r'href="([^"]+)"', m.group(0))
                if hm:
                    cands.append(urljoin(home, html.unescape(hm.group(1))))
    except requests.RequestException:
        pass
    cands += [home + p for p in FEED_PATHS] + [base + p for p in FEED_PATHS]
    for u in dict.fromkeys(cands):
        items = fetch_feed(u)
        if items and len(items) >= 5:
            return u
    return None


def discover(idx: TeamIndex, feeds: dict, limit: int = 8) -> list[str]:
    """주 1회 — 구글 뉴스에서 5번 넘게 본 매체 중 아직 없는 것의 피드를 찾아 시험(우리 팀 기사 비율 MIN_MATCH_RATE 이상만)."""
    last = feeds.get("discovered_at", "")
    if last and last > (dt.date.today() - dt.timedelta(days=DISCOVER_EVERY_DAYS)).isoformat():
        return []
    known = {urlparse(u).netloc.lower().removeprefix("www.") for u in feeds.get("feeds", {})}
    rejected = feeds.setdefault("rejected", {})
    added = []
    cands = sorted(((d, c) for d, c in feeds.get("candidates", {}).items()
                    if c.get("n", 0) >= 5 and d not in known
                    and rejected.get(d, "") < (dt.date.today() - dt.timedelta(days=30)).isoformat()),
                   key=lambda x: -x[1]["n"])
    t0 = time.monotonic()
    for d, c in cands[:limit]:
        if time.monotonic() - t0 > DISCOVER_BUDGET_S:          # 응답 느린 매체가 수집 실행을 붙잡지 않게 — 나머지는 다음 주
            break
        u = find_feed(d)
        items = fetch_feed(u) if u else None
        rate = (sum(1 for a in items if idx.match(a["headline"], a["desc"], c.get("country"))) / len(items)) if items else 0.0
        if u and rate >= MIN_MATCH_RATE:
            feeds.setdefault("feeds", {})[u] = {"outlet": c.get("outlet") or d, "country": c.get("country", ""),
                                                "via": "discover", "added": _today(), "match_rate": round(rate, 2)}
            added.append(f"{d}({rate:.0%})")
        else:
            rejected[d] = _today()
        time.sleep(0.5)
    feeds["discovered_at"] = _today()
    return added


# ── FotMob 팀 뉴스 ───────────────────────────────────────────────────────────
def fotmob_team_ids(refresh_days: int = 7) -> dict[str, int]:
    """{우리 클럽: FotMob 팀 id} — 리그 일정에서(7일 캐시)."""
    cache = _load(FM_IDS, {})
    if cache.get("at", "") >= (dt.date.today() - dt.timedelta(days=refresh_days)).isoformat() and cache.get("ids"):
        return cache["ids"]
    import team_names as tn  # noqa: PLC0415
    from fetch_fotmob_ratings import FOTMOB_ID, _get  # noqa: PLC0415
    from ui.news import newstags  # noqa: PLC0415
    ids = dict(cache.get("ids") or {})
    for lg in LEAGUES:
        fid = FOTMOB_ID.get(lg)
        if not fid:
            continue
        d = _get(f"https://www.fotmob.com/api/data/leagues?id={fid}") or {}
        ours = list(newstags(lg))
        for m in ((d.get("fixtures") or {}).get("allMatches") or []):
            for side in ("home", "away"):
                t = m.get(side) or {}
                name = tn.best(str(t.get("name") or ""), ours)
                if name and t.get("id"):
                    ids[name] = int(t["id"])
        time.sleep(0.5)
    if ids:
        _save(FM_IDS, {"at": _today(), "ids": ids})
    return ids


def fotmob_articles(idx: TeamIndex, hour: int | None = None) -> tuple[dict[str, list[dict]], int]:
    """이번 실행 묶음 팀들의 FotMob 뉴스 → {클럽: [기사]} (그 팀 뉴스라 팀은 정해져 있고, 다른 우리 클럽도 언급되면 같이)."""
    ids = fotmob_team_ids()
    hour = dt.datetime.utcnow().hour if hour is None else hour
    grp = (hour // 2) % FOTMOB_GROUPS
    out: dict[str, list[dict]] = defaultdict(list)
    calls = 0
    for club, tid in sorted(ids.items()):
        if int(hashlib.md5(club.encode()).hexdigest(), 16) % FOTMOB_GROUPS != grp:
            continue
        lang = FM_LANG.get(idx.country.get(club, ""), "en")
        try:
            r = requests.get("https://www.fotmob.com/api/data/tlnews",
                             params={"id": tid, "type": "team", "language": lang, "startIndex": 0}, headers=H, timeout=20)
            data = (r.json() or {}).get("data") if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            data = None
        calls += 1
        for x in data or []:
            pub = str(x.get("gmtTime") or "")[:10]
            if not _fresh(pub):
                continue
            pg = x.get("page") or {}
            url = pg.get("url") if isinstance(pg, dict) else str(pg or "")
            if not url:
                continue
            link = url if url.startswith("http") else "https://www.fotmob.com" + url
            a = {"headline": _clean(x.get("title"), 300), "desc": _clean(x.get("lead"), 400), "published": pub,
                 "link": link.split("?utm")[0], "image": x.get("imageUrl") or "", "source": x.get("sourceStr") or "FotMob",
                 "via": "fotmob", "author": ""}
            if not a["headline"] or not gn.keep(a["headline"], a["source"]):
                continue
            clubs = [club] + [c for c in idx.match(a["headline"], a["desc"], idx.country.get(club)) if c != club]
            for c in clubs[:MAX_CLUBS]:
                out[c].append(a)
        time.sleep(0.4)
    return out, calls


# ── 블루스카이 기자 계정 ───────────────────────────────────────────────────────
BSKY = "https://public.api.bsky.app/xrpc"
INSIDER_CAP = 40         # 받는 계정 상한(팔로워순, 이름으로 찾은 계정은 늘 유지)
EXPAND_EVERY_DAYS = 7
# 팔로우 넓히기 — 소개글에 축구 낱말과 기자 낱말이 둘 다(역할 검색 'football journalist' 는 정치·과학 기자가 대부분이었다)
FOOT = re.compile(r"football|soccer|f[uú]tbol|calcio|fu(?:ß|ss)ball|voetbal|futebol|transfer|mercato|fichajes|premier league|"
                  r"la ?liga|serie a|bundesliga|ligue 1|eredivisie|the athletic|sky sports|\bfc\b|uefa", re.I)
ROLE = re.compile(r"journalist|reporter|correspondent|writer|columnist|insider|periodista|giornalista|journaliste|jornalista|"
                  r"redakteur|editor|chief|news", re.I)


def _bsky(method: str, **params):
    try:
        r = requests.get(f"{BSKY}/{method}", params=params, headers=H, timeout=20)
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _profiles(handles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(handles), 25):
        try:
            r = requests.get(f"{BSKY}/app.bsky.actor.getProfiles", params=[("actors", h) for h in handles[i:i + 25]],
                             headers=H, timeout=20)
            out += (r.json() or {}).get("profiles", []) if r.status_code == 200 else []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.2)
    return out


def _person(display: str) -> str:
    """표시 이름 → 사람 이름('Tom Bogert ⚽️' → 'Tom Bogert', 'Nizaar Kinsella | BBC' → 'Nizaar Kinsella')."""
    t = re.split(r"[|(\[•·,/]", str(display or ""))[0]
    t = re.sub(r"[^\w\s'’.\-]", " ", t)
    return " ".join(t.split())[:60]


def refresh_insiders(names: list[str], max_new: int = 10) -> dict:
    """기자 계정 목록(data/news_insiders.json) 갱신 — {accounts: {handle: {...}}, names: {이름: {handle, checked}}}.
    ① 학습한 기자 이름(news_journalists.csv — AI 가 '출처로 인용된 기자'만 뽑는다) → 표시 이름이 맞고 팔로워 2천+ 계정
       (공식 계정을 먼저, 'mirror' 표시 계정은 비공식). 이름마다 14일에 한 번.
    ② 주 1회 — 그 계정들이 팔로우하는 사람 중 팔로워 3천+, 소개글에 축구 낱말·기자 낱말이 둘 다 있는 계정.
    합쳐 INSIDER_CAP 개(팔로워순)."""
    reg = _load(INSIDERS, {})
    if "accounts" not in reg:                       # 옛 형식(이름 → 계정) 버림
        reg = {"accounts": {}, "names": {}}
    acc, nm = reg["accounts"], reg["names"]
    today = _today()
    stale = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    for name in [n for n in names if nm.get(n, {}).get("checked", "") < stale][:max_new]:
        res = _bsky("app.bsky.actor.searchActors", q=name, limit=10) or {}
        hs = [x["handle"] for x in res.get("actors") or [] if _fold(name) in _fold(x.get("displayName"))]
        best = None
        for pr in _profiles(hs):
            f = int(pr.get("followersCount") or 0)
            if f < 2000:
                continue
            cand = (("mirror" not in _fold(pr.get("displayName")) and "mirror" not in _fold(pr.get("description"))), f, pr["handle"])
            best = max(best, cand) if best else cand
        nm[name] = {"handle": best[2] if best else None, "checked": today}
        if best:
            acc[best[2]] = {"name": name, "followers": best[1], "official": best[0], "via": "name", "checked": today}
        time.sleep(0.3)
    if reg.get("expanded_at", "") < (dt.date.today() - dt.timedelta(days=EXPAND_EVERY_DAYS)).isoformat() and acc:
        seeds = sorted(acc, key=lambda h: (acc[h].get("via") != "name", -int(acc[h].get("followers") or 0)))[:5]
        for seed in seeds:
            cur, hs = None, []
            for _ in range(3):                      # 300명까지
                d = _bsky("app.bsky.graph.getFollows", actor=seed, limit=100, **({"cursor": cur} if cur else {})) or {}
                hs += [f["handle"] for f in d.get("follows") or []]
                cur = d.get("cursor")
                if not cur:
                    break
            for pr in _profiles([h for h in hs if h not in acc]):
                bio = f"{pr.get('displayName', '')} {pr.get('description') or ''}"
                f = int(pr.get("followersCount") or 0)
                nmx = _person(pr.get("displayName"))
                if f >= 3000 and FOOT.search(bio) and ROLE.search(bio) and len(nmx.split()) >= 2:
                    acc[pr["handle"]] = {"name": nmx, "followers": f, "official": "mirror" not in _fold(bio),
                                         "via": f"follows:{seed}", "checked": today}
        reg["expanded_at"] = today
    keep = sorted(acc, key=lambda h: (acc[h].get("via") != "name", -int(acc[h].get("followers") or 0)))[:INSIDER_CAP]
    reg["accounts"] = {h: acc[h] for h in keep}
    _save(INSIDERS, reg)
    return reg


def bsky_articles(idx: TeamIndex, reg: dict) -> tuple[dict[str, list[dict]], int]:
    """기자 계정의 최근 2일 글(답글·남의 글 다시 올림 제외) 중 우리 클럽이 나오는 것 → 기사(작성자 = 그 기자)."""
    out: dict[str, list[dict]] = defaultdict(list)
    n = 0
    for h, ent in (reg.get("accounts") or {}).items():
        name = ent.get("name") or h
        feed = _bsky("app.bsky.feed.getAuthorFeed", actor=h, limit=30, filter="posts_no_replies") or {}
        for it in feed.get("feed") or []:
            if it.get("reason"):                    # 남의 글 다시 올림
                continue
            p = it.get("post") or {}
            rec = p.get("record") or {}
            text = _clean(rec.get("text"), 600)
            pub = str(rec.get("createdAt") or "")[:10]
            if not text or not _fresh(pub, 2):
                continue
            rkey = str(p.get("uri", "")).rsplit("/", 1)[-1]
            a = {"headline": text[:220], "desc": text[:400], "published": pub, "image": "",
                 "link": f"https://bsky.app/profile/{h}/post/{rkey}", "author": name,
                 "source": f"Bluesky · {name}" + ("" if ent.get("official", True) else " (mirror)"), "via": "bsky"}
            for c in idx.match(text, "", None):
                out[c].append(a)
                n += 1
        ent["last_fetch"] = _today()
        time.sleep(0.3)
    return out, n


# ── 실행 ────────────────────────────────────────────────────────────────────
def _learned_journalists() -> list[str]:
    """AI 가 '출처로 인용된 기자'로 뽑은 이름(news_classify — 사람 이름 꼴만), 언급 많은 순."""
    import csv  # noqa: PLC0415

    import news_classify as nc  # noqa: PLC0415
    p = ROOT / "data" / "news_journalists.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: -int(r.get("mentions") or 0))
    # 매체 이름('The Guardian')이 기자로 학습된 경우 — 우리가 받는 기사의 매체 이름·'The …' 는 사람이 아니다
    outlets = {_fold(r.get("outlets", "")) for r in rows}
    try:
        import news_db  # noqa: PLC0415
        with news_db._conn() as c:   # noqa: SLF001
            outlets |= {_fold(x[0]) for x in c.execute("SELECT DISTINCT source FROM articles")}
    except Exception:  # noqa: BLE001
        pass
    return [r["name"] for r in rows if nc._person_like(r.get("name"))   # noqa: SLF001
            and _fold(r["name"]) not in outlets and not _fold(r["name"]).startswith("the ")][:60]


def run(fotmob: bool = True, bsky: bool = True, google_seen: dict | None = None) -> dict:
    """전 리그 한 번 — 와이어 기사 upsert(팀당 하루 상한), 피드 발견·기자 계정 갱신. 통계 dict."""
    import news_db  # noqa: PLC0415
    idx = TeamIndex()
    feeds = _load(FEEDS, {"feeds": {}})
    for country, arts in (google_seen or {}).items():
        note_sources(arts, country, feeds)
    added = discover(idx, feeds)
    wire, wstats = wire_articles(idx, feeds)
    _save(FEEDS, feeds)
    fm, fm_calls = fotmob_articles(idx) if fotmob else ({}, 0)
    reg = refresh_insiders(_learned_journalists()) if bsky else {}
    bs, bs_n = bsky_articles(idx, reg) if bsky else ({}, 0)
    today = _today()
    new = {"wire": 0, "fotmob": 0, "bsky": 0}
    for via, groups in (("wire", wire), ("fotmob", fm), ("bsky", bs)):
        for club, arts in groups.items():
            seen, uniq = set(), []
            for a in arts:
                if a["link"] not in seen:
                    seen.add(a["link"])
                    uniq.append(a)
            known = news_db.recent_heads(club, (dt.date.today() - dt.timedelta(days=7)).isoformat())
            uniq = [a for a in uniq if news_db.head_key(a["headline"]) not in known]
            if via == "wire":
                room = WIRE_DAILY_CAP - news_db.via_count(club, "wire", today)
                uniq = uniq[:max(0, room)]
            new[via] += news_db.upsert_articles(uniq, club)
    pruned = sum(news_db.prune(v, (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()) for v in new)
    return {"new": new, "feeds": len([f for f in feeds.get("feeds", {}).values() if not f.get("off")]),
            "feed_hits": wstats, "discovered": added, "fotmob_calls": fm_calls,
            "insiders": len(reg.get("accounts") or {}), "bsky_posts": bs_n, "pruned": pruned}


if __name__ == "__main__":
    import news_db  # noqa: E402

    news_db.init_db()
    print(json.dumps(run(), ensure_ascii=False, indent=1))
