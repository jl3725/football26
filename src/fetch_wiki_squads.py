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


def _tpl_text(m) -> str:
    """이름을 담은 틀만 글자로 — {{ill|이름|nl|…}}(다른 언어 위키 링크) → 이름, {{sortname|이름|성}} → '이름 성'. 나머지 틀은 지운다."""
    parts = m.group(1).split("|")
    kind = parts[0].strip().lower()
    args = [a.strip() for a in parts[1:] if "=" not in a]
    if kind in ("ill", "interlanguage link", "interlanguage link multi") and args:
        return args[0]
    if kind == "sortname" and len(args) >= 2:
        return f"{args[0]} {args[1]}"
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
    t = _link_text(other).lower()
    if "captain" not in t:
        return "", None
    if "vice" in t or "2nd" in t or "second" in t:
        return "vice-captain", 2
    if "3rd" in t or "third" in t:
        return "3rd captain", 3
    if "4th" in t or "fourth" in t:
        return "4th captain", 4
    return "captain", 1


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


def search_title(team: str, country: str) -> str | None:
    """문서 제목이 없는 팀(벨기에 등) — 위키 검색 첫 결과 중 '축구 클럽' 문서."""
    j = _get({"action": "query", "list": "search", "srsearch": f"{team} {country} football club", "srlimit": 3})
    toks = [w for w in re.findall(r"[a-z]{3,}", _fold(team))]
    for hit in j.get("query", {}).get("search", []):
        t = hit.get("title", "")
        if "season" in t.lower() or "list of" in t.lower():
            continue
        if any(w in _fold(t) for w in toks):          # 'Union SG' → 선수 문서, 'Charleroi' → 다른 클럽 문서를 물던 것 방지
            return t
    return None


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
    for team in teams:
        # data/wiki_titles.json(검색 결과·수동 지정)이 우선 — team_profiles 의 제목 중 동음이의·다른 문서가 있다
        t = cache.get(team) or (profiles.get(team) or {}).get("wiki_title")
        if not t:
            try:
                t = search_title(team, _COUNTRY.get(league, ""))
            except requests.RequestException:
                t = None
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
    for team, title in titles.items():
        rows = parse_squad(texts.get(title, ""))
        if not rows:
            miss.append(f"{team}(스쿼드 표 없음)")
        for r in rows:
            out.append({"squad": team, **r, "wiki_title": title, "fetched": today})
    path = data_path("wiki_squads", league)
    if out:
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(out)
    n_cap = len({r["squad"] for r in out if r["role_rank"] == 1})
    return len(teams), n_cap, miss


def main() -> int:
    profiles = json.loads((Path(__file__).resolve().parent.parent / "data" / "team_profiles.json")
                          .read_text(encoding="utf-8"))
    sel = os.getenv("FB_LEAGUE", "ALL")
    leagues = LEAGUES if sel.upper() == "ALL" else [sel]
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8")) if TITLE_CACHE.exists() else {}
    bad = 0
    for lg in leagues:
        n, n_cap, miss = run(lg, profiles, cache)
        TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print(f"[wiki_squads] {lg}: 주장 확인 {n_cap}/{n}팀" + (f" · 누락 {miss}" if miss else ""))
        bad += n and n_cap < n * 0.6                      # 대부분 비면 실패로 알림(문서 구조 변경 등)
    return 1 if bad else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
