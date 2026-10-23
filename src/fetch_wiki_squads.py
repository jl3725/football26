"""
위키백과 클럽 문서의 스쿼드 표 → 주장단(주장·부주장·3·4번째 주장)과 등번호 — 8개 리그 전체.

예전 주장 정보는 EPL 20팀만 코드에 적어 둔 값(teammeta.TEAM_CAPTAINS)과 25/26 football-lineups '(c)'
기록뿐이라 다른 리그 팀은 주장단이 비었다(2026-10-15 사용자 요청: 주장단 강조).
클럽 문서의 {{Fs player|no=|nat=|pos=|name=|other=captain}} 틀을 읽는다 — 무료 MediaWiki API,
클라우드(GH Actions)에서 돈다. 문서 제목은 data/team_profiles.json 의 wiki_title.

출력: data/wiki_squads_<리그>_<시즌>.csv
  squad, section(first|loan), no, nat, pos, player, role(captain|vice-captain|3rd captain|4th captain|""),
  role_rank(1~4, 없으면 빈칸), wiki_title, fetched
사용: FB_LEAGUE=EPL python src/fetch_wiki_squads.py   (FB_LEAGUE=ALL 이면 8개 리그)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "football26/1.0 (squad captains; github.com/jl3725/football26)"}
FIELDS = ["squad", "section", "no", "nat", "pos", "player", "role", "role_rank", "wiki_title", "fetched"]
# 안쪽 틀 한 겹({{ill|이름|nl}} 등)까지 — 예전 (.*?) 는 안쪽 '}}' 에서 끊겨 이름이 '{{ill|Pascal Kuiper|nl' 로 남았다
_TPL = re.compile(r"\{\{\s*(?:fs player|football squad player)\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", re.I | re.S)
_HEAD = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.M)


# 글자를 감싸기만 하는 틀 — 안쪽 글자를 남긴다. {{small|[[Captain (association football)|captain]]}} 를 통째로 지워
# 분데스리가 주장 18→10팀, 에레디비시 11→6팀으로 줄었다(2026-10-18 daily_data 실패).
_WRAP = {"small", "smaller", "nowrap", "big", "center", "sup", "sub", "nobold", "resize", "em", "strong", "lang",
         "tooltip", "abbr", "small caps", "smallcaps", "noitalic", "bold", "b", "i"}


def _split_args(body: str) -> list[str]:
    """틀 본문을 | 로 나누되 [[a|b]] 안의 | 는 그대로."""
    parts, cur, depth = [], "", 0
    for i, ch in enumerate(body):
        if body.startswith("[[", i):
            depth += 1
        elif body.startswith("]]", i) and depth:
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _tpl_text(m) -> str:
    """이름을 담은 틀만 글자로 — {{ill|이름|nl|…}}(다른 언어 위키 링크) → 이름, {{sortname|이름|성}} → '이름 성',
    감싸는 틀({{small|…}}·{{nowrap|…}}) → 안쪽 글자. 나머지 틀(국기·각주 등)은 지운다."""
    parts = _split_args(m.group(1))
    kind = parts[0].strip().lower()
    args = [a.strip() for a in parts[1:] if "=" not in a.split("[[")[0]]
    if kind in ("ill", "interlanguage link", "interlanguage link multi") and args:
        return args[0]
    if kind == "sortname" and len(args) >= 2:
        return f"{args[0]} {args[1]}"
    if kind in _WRAP and args:
        return args[-1] if kind in ("abbr", "tooltip") else args[0]
    return ""


def clean_name(v: str) -> str:
    """수집된 이름 정리 — 닫히지 않은 '{{ill|이름|nl' (예전 파서가 남긴 값)도 이름만."""
    v = str(v or "")
    m = re.match(r"^\{\{\s*(?:ill|interlanguage link(?: multi)?)\s*\|([^|{}]+)", v, re.I)
    return m.group(1).strip() if m else v


def _link_text(v: str) -> str:
    """'[[A (footballer)|A]]' → 'A', '[[B]]' → 'B', 꾸밈 틀·참조 제거(이름을 담은 틀은 이름으로)."""
    v = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"\{\{([^{}]*)\}\}", _tpl_text, v)
    m = re.search(r"\[\[([^\]]+)\]\]", v)
    if m:
        v = m.group(1).split("|")[-1]
    return re.sub(r"\s+", " ", v.replace("'''", "").replace("''", "")).strip()


def _fields(body: str) -> dict:
    out = {}
    depth, cur = 0, ""
    parts = []
    for ch in body:                                       # 중첩 [[a|b]] 안의 | 는 나누지 않는다
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def role_of(other: str) -> tuple[str, int | None]:
    # 보이는 글자 우선(링크 대상 'Vice-captain (…)|3rd captain' 은 3번째), 거기에 없으면 원문으로 —
    # 처음 보는 감싸는 틀이 생겨도 'captain' 글자는 원문에 남아 있다
    t = _link_text(other).lower()
    if "captain" not in t:
        t = str(other or "").lower()
    if "captain" not in t:
        return "", None
    # 서수는 숫자로 — 예전엔 2nd·3rd·4th 만 알아 '5th captain'(바르사 야말)이 그냥 'captain'(1순위)으로 읽혔다(2026-10-20)
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", t)
    words = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}
    n = int(m.group(1)) if m else next((v for k, v in words.items() if k in t), None)
    if n is None and "vice" in t:
        n = 2
    if n is None or n <= 1:
        return "captain", 1
    if n == 2:
        return "vice-captain", 2
    return f"{n}{'rd' if n == 3 else 'th'} captain", n


def parse_squad(wikitext: str) -> list[dict]:
    """1군 스쿼드(+임대 보낸 선수) 행. 섹션 제목에 'loan' 이 있으면 loan, 'youth'·'academy'·'reserve' 등은 건너뛴다."""
    heads = [(m.start(), m.group(2).lower()) for m in _HEAD.finditer(wikitext)]

    def section_at(pos: int) -> str:
        h = ""
        for s, t in heads:
            if s > pos:
                break
            h = t
        return h

    rows = []
    for m in _TPL.finditer(wikitext):
        h = section_at(m.start())
        if any(k in h for k in ("youth", "academy", "reserve", "under-", "u21", "u23", "u19", "women", "retired",
                                "former", "notable", "hall of fame", "record")):
            continue
        f = _fields(m.group(1))
        name = _link_text(f.get("name", ""))
        if not name:
            continue
        role, rank = role_of(f.get("other", ""))
        rows.append({"section": "loan" if "loan" in h else "first", "no": _link_text(f.get("no", "")),
                     "nat": f.get("nat", "").strip().upper(), "pos": f.get("pos", "").strip().upper(),
                     "player": name, "role": role, "role_rank": rank})
    # 같은 선수 중복(문서 안 두 표)은 첫 행만
    seen, out = set(), []
    for r in rows:
        if r["player"] in seen:
            continue
        seen.add(r["player"])
        out.append(r)
    return out


def _get(params: dict) -> dict:
    """429(익명 요청 제한)는 Retry-After 만큼 기다렸다 다시 — 최대 4번."""
    for i in range(4):
        r = requests.get(API, params={**params, "format": "json", "formatversion": 2}, headers=HEADERS, timeout=60)
        if r.status_code == 429:
            time.sleep(min(60, int(r.headers.get("retry-after") or 10) + 2))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def wikitexts(titles: list[str]) -> dict[str, str]:
    """문서 여러 개를 한 요청에(10개씩) — 팀마다 1요청이면 20팀 만에 429 가 났다. {요청 제목: 위키텍스트}."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 10):
        chunk = titles[i:i + 10]
        j = _get({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                  "titles": "|".join(chunk), "redirects": 1})
        q = j.get("query", {})
        back = {t: t for t in chunk}
        for m in q.get("normalized", []) + q.get("redirects", []):
            for k, v in list(back.items()):
                if v == m["from"]:
                    back[k] = m["to"]
        text = {pg["title"]: (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("content", "")
                for pg in q.get("pages", [])}
        for k, v in back.items():
            out[k] = text.get(v, "")
        time.sleep(1.0)
    return out


# 클럽 문서가 아닌 검색 결과 — 시즌·목록·여자팀·유스·리저브 문서, '도시, 나라' 꼴의 지명 문서
_NOT_CLUB_TITLE = re.compile(r"\bseason\b|\blist of\b|\bwomen\b|w\.f\.c\.|\bladies\b|\bfemin|\bkvinder\b|\bfrauen\b|\bkadin\b|"
                             r"\breserves?\b|\bacademy\b|\bu-?\d{2}\b|,\s", re.I)
# 클럽 인포박스('Infobox football club season' 은 시즌 문서라 아님)
_CLUB_BOX = re.compile(r"\{\{\s*(?:infobox (?:football|soccer) club|football club infobox)\s*[|\n}]", re.I)  # 같은 틀의 다른 이름
# 위키 스쿼드 표 ↔ 우리 명단 성(姓) 겹침이 이보다 낮으면 다른 구단 문서. 2026-10-23 표본: 맞는 구단 0.68 이상,
# 잘못 잡은 문서(여자팀·다른 구단) 0.13 이하
MIN_OVERLAP = 0.35


_SEASON_TITLE = re.compile(r"^\d{4}[–-]\d{2,4} (.+?) season$")


def candidates(team: str, country: str, limit: int = 8) -> list[tuple[str, bool]]:
    """위키 검색 결과 중 클럽 문서 후보 [(제목, 이름 낱말이 제목에 있나)] — 나라를 붙인 검색 + 안 붙인 검색.
    시즌 문서('2024–25 Gaziantep F.K. season')는 클럽 문서 제목으로 바꿔 넣는다. 'Türkiye' 를 붙이면 선수·리그 문서만
    나오던 쉬페르리그 클럽이 있었다(2026-10-23)."""
    seen: list[str] = []
    for q in (f"{team} {country} football club", f"{team} football club"):
        j = _get({"action": "query", "list": "search", "srsearch": q, "srlimit": limit})
        for hit in j.get("query", {}).get("search", []):
            t = hit.get("title", "")
            m = _SEASON_TITLE.match(t)
            t = m.group(1) if m else t
            if t and t not in seen and not _NOT_CLUB_TITLE.search(_fold(t)):
                seen.append(t)
    toks = [w for w in re.findall(r"[a-z]{3,}", _fold(team))]
    return [(t, any(w in _fold(t) for w in toks)) for t in seen]


def search_title(team: str, country: str) -> str | None:
    """문서 제목이 없는 팀(벨기에 등) — 이름 낱말이 제목에 있는 첫 후보('Union SG' 가 선수 문서,
    'Charleroi' 가 다른 클럽 문서를 물던 것 방지). 수집 때 resolve() 가 문서 내용으로 다시 검증한다."""
    return next((t for t, hit in candidates(team, country, limit=3) if hit), None)


def _surname(name: str) -> str:
    w = re.sub(r"[^a-z ]", " ", _fold(str(name or "")).replace("-", " ")).split()
    return w[-1] if w else ""


def rosters(league: str) -> dict[str, set[str]]:
    """{우리 클럽: 선수 성 집합} — 위키 문서가 맞는 구단인지 대조용(선수 표 → FotMob 명단 순)."""
    import pandas as pd  # noqa: PLC0415
    for name in ("players_full", "players", "fotmob_squads"):
        p = data_path(name, league)
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, usecols=lambda c: c in ("squad", "player"))
        except (OSError, ValueError):
            continue
        if {"squad", "player"} <= set(df.columns):
            return {str(sq): {s for s in g["player"].map(_surname) if s} for sq, g in df.groupby("squad")}
    return {}


def overlap(rows: list[dict], roster: set[str] | None) -> float | None:
    """위키 스쿼드 표 선수와 우리 명단의 성 겹침(작은 쪽 기준). 어느 쪽이든 8명 미만이면 판단 안 함(None)."""
    wiki = {s for r in rows if (s := _surname(r.get("player", "")))}
    if not roster or len(wiki) < 8 or len(roster) < 8:
        return None
    return len(wiki & roster) / min(len(wiki), len(roster))


def is_club_page(text: str, rows: list[dict], roster: set[str] | None) -> bool:
    """클럽 인포박스가 있고, 스쿼드 표가 있으면 우리 명단과 겹쳐야 한다."""
    if not _CLUB_BOX.search(text[:30000]):
        return False
    ov = overlap(rows, roster)
    return ov is None or ov >= MIN_OVERLAP


def resolve(team: str, country: str, roster: set[str] | None, exclude: set[str]) -> tuple[str, str] | None:
    """검색 후보를 하나씩 검증해 첫 '맞는 클럽 문서' (제목, 위키텍스트). 이름 낱말이 제목에 없는 후보
    ('AGF' → 'Aarhus Gymnastikforening')는 스쿼드 겹침이 실제로 확인될 때만."""
    cands = [(t, hit) for t, hit in candidates(team, country) if t not in exclude]
    texts = wikitexts([t for t, _ in cands]) if cands else {}
    ok = []
    for i, (t, hit) in enumerate(cands):
        text = texts.get(t, "")
        if not _CLUB_BOX.search(text[:30000]):
            continue
        ov = overlap(parse_squad(text), roster)
        if ov is not None and ov >= MIN_OVERLAP:
            ok.append((0, i, t))                     # 스쿼드가 우리 명단과 겹친다 — 가장 확실
        elif ov is None and hit:
            ok.append((1, i, t))                     # 스쿼드 표 없음 · 이름 맞음 — 'Çorumspor'(아마추어)를 잡던 약한 증거라 뒤로
    if not ok:
        return None
    t = min(ok)[2]
    return t, texts[t]


def _fold(s: str) -> str:
    import unicodedata  # noqa: PLC0415
    return "".join(ch for ch in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(ch))


def teams_of(league: str) -> list[str]:
    p = data_path("standings", league)
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return sorted({r["squad"] for r in csv.DictReader(fh) if r.get("squad")})


_COUNTRY = {"EPL": "England", "LaLiga": "Spain", "SerieA": "Italy", "Bundesliga": "Germany", "Ligue1": "France",
            "LigaPortugal": "Portugal", "Eredivisie": "Netherlands", "BelgianProLeague": "Belgium"}
TITLE_CACHE = Path(__file__).resolve().parent.parent / "data" / "wiki_titles.json"


def run(league: str, profiles: dict, cache: dict) -> tuple[int, int, list[str]]:
    today = dt.date.today().isoformat()
    out, miss = [], []
    teams = teams_of(league)
    titles: dict[str, str] = {}
    ros = rosters(league)
    country = _COUNTRY.get(league) or LEAGUES[league].country           # 라이트 리그는 리그 설정의 나라
    for team in teams:
        # data/wiki_titles.json(검색 결과·수동 지정)이 우선 — team_profiles 의 제목 중 동음이의·다른 문서가 있다
        t = cache.get(team) or (profiles.get(team) or {}).get("wiki_title")
        if not t:
            try:
                r = resolve(team, country, ros.get(team), set())                # 검색 후보를 문서 내용으로 검증
            except requests.RequestException:
                r = None
            t = r[0] if r else None
            if t:
                cache[team] = t
        if t:
            titles[team] = t
        else:
            miss.append(f"{team}(문서 없음)")
    try:
        texts = wikitexts(sorted(set(titles.values())))
    except requests.RequestException as e:
        return len(teams), 0, [f"전체({type(e).__name__})"]
    # 저장해 둔 제목이 다른 문서면(여자팀·도시·시즌·다른 구단) 다시 찾는다 — 검색 첫 결과를 이름 낱말 하나로 받던 때
    # 'Birmingham City W.F.C.'·'Viborg, Denmark'·'SV Austria Salzburg'·Gaziantep→'Erzurumspor F.K.' 가 저장돼 있었다(2026-10-23)
    for team, title in list(titles.items()):
        text = texts.get(title, "")
        if not text or is_club_page(text, parse_squad(text), ros.get(team)):
            continue
        try:
            alt = resolve(team, country, ros.get(team), {title})
        except requests.RequestException:
            alt = None
        if alt:
            print(f"[wiki_squads] {team}: 문서 제목 고침 '{title}' → '{alt[0]}'")
            titles[team] = cache[team] = alt[0]
            texts[alt[0]] = alt[1]
        else:
            print(f"[wiki_squads] {team}: '{title}' 는 클럽 문서가 아님 — 맞는 문서를 못 찾음")
            titles.pop(team)
            cache.pop(team, None)
            miss.append(f"{team}(문서 확인 실패)")
    for team, title in titles.items():
        rows = parse_squad(texts.get(title, ""))
        if not rows:
            miss.append(f"{team}(스쿼드 표 없음)")
        for r in rows:
            out.append({"squad": team, **r, "wiki_title": title, "fetched": today})
    path = data_path("wiki_squads", league)
    prev_cap = 0                                          # 지난 수집의 주장 확인 팀 수(회귀 판단 기준)
    if path.exists():
        try:
            with path.open(encoding="utf-8") as fh:
                prev_cap = len({r["squad"] for r in csv.DictReader(fh) if str(r.get("role_rank")) == "1"})
        except (OSError, csv.Error, KeyError):
            prev_cap = 0
    if out:
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(out)
    n_cap = len({r["squad"] for r in out if r["role_rank"] == 1})
    return len(teams), n_cap, miss, prev_cap


def main() -> int:
    profiles = json.loads((Path(__file__).resolve().parent.parent / "data" / "team_profiles.json")
                          .read_text(encoding="utf-8"))
    sel = os.getenv("FB_LEAGUE", "ALL")
    leagues = LEAGUES if sel.upper() == "ALL" else [sel]
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8")) if TITLE_CACHE.exists() else {}
    bad = 0
    for lg in leagues:
        res = run(lg, profiles, cache)
        n, n_cap, miss = res[:3]
        prev_cap = res[3] if len(res) > 3 else 0
        TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print(f"[wiki_squads] {lg}: 주장 확인 {n_cap}/{n}팀 (지난 수집 {prev_cap})" + (f" · 누락 {miss}" if miss else ""))
        # 실패 = 0팀이거나 지난 수집보다 크게 줄었을 때(문서 구조 변경 의심). 분데스·에레디비시 영문 위키는 원래 주장 표시가
        # 드물어(10/18·6/18) 예전 '60% 미만' 기준이면 매일 실패 → 워크플로가 늘 빨간불이라 진짜 고장이 묻혔다(2026-10-19 점검)
        # 라이트 리그(첫 수집·주장 표시가 드문 위키)는 0팀이어도 지난 수집에 있었을 때만 실패
        first_lite = LEAGUES[lg].lite and prev_cap == 0
        bad += bool(n) and ((n_cap == 0 and not first_lite) or (prev_cap >= 3 and n_cap < prev_cap * 0.6))
    return 1 if bad else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
