"""
벨기에 프로리그 감독 프로필 수집기 — 클럽 위키 문서 인포박스(manager·head coach)에서.

다른 리그 수집기(fetch_eredivisie_managers 등)는 위키 시즌 문서의 감독표를 읽는데, 벨기에 시즌 문서
('2026–27 Belgian Pro League')에는 감독표가 없어 지금까지 벨기에만 감독 프로필이 비었다(2026-10 시즌 전환 메모).
클럽 문서 제목은 data/wiki_titles.json(위키 스쿼드 수집기가 찾아 둔 것), 없으면 위키 검색으로 찾아(인포박스가
축구 클럽일 때만) 캐시에 더한다. 이후 사진·전술·한글 소개 보강은 다른 리그와 같다(enrich_one).
출력: data/manager_profiles_BelgianProLeague_<시즌>.json. 시즌 문서 감독표가 없어 detect_manager_changes 대신
직전 프로필과 비교해 바뀐 감독을 data/manager_changes_BelgianProLeague_<시즌>.csv 에 남긴다(Inbox·홈 감독 변화).

사용: python src/fetch_belgian_managers.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from enrich_manager_profiles import enrich_one  # noqa: E402
from fetch_manager_photos import _search_photo, _tm_photo  # noqa: E402
from leagues import data_path  # noqa: E402
from sync_manager_profiles import (append_change_log, current_teams, fetch_json, fetch_photo_urls,  # noqa: E402
                                   load_profiles, save_profiles)

LEAGUE = "BelgianProLeague"
API = "https://en.wikipedia.org/w/api.php"
TITLES = Path(__file__).resolve().parent.parent / "data" / "wiki_titles.json"
FALLBACK = ["Club Brugge", "Genk", "Union SG", "Anderlecht", "Antwerp", "Gent", "Westerlo", "Sint-Truiden", "Mechelen",
            "Standard Liège", "Charleroi", "Cercle Brugge", "OH Leuven", "Zulte Waregem", "Dender", "La Louvière"]
FIELD = re.compile(r"^\s*\|\s*(manager|head[ _]?coach|coach)\s*=\s*(.*)$", re.I | re.M)


def _api(**params) -> dict:
    return fetch_json(f"{API}?{urllib.parse.urlencode({'format': 'json', 'formatversion': 2, **params})}")


def infobox_manager(wikitext: str) -> tuple[str, str] | None:
    """인포박스 manager(또는 head coach) 칸 → (표시 이름, 위키 문서 제목). 비었거나 TBA 면 None."""
    m = FIELD.search(wikitext or "")
    if not m:
        return None
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|\{\{[^{}]*\}\}|<!--.*?-->", "", m.group(2), flags=re.S).strip()
    link = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", v)
    if link:
        title = link.group(1).strip()
        name = (link.group(2) or re.sub(r"\s*\([^)]*\)$", "", title)).strip()
    else:
        name = re.sub(r"\s*\((caretaker|interim)\)", "", v, flags=re.I).strip(" ,'\"")
        title = name
    if not name or name.upper() in ("TBA", "TBD", "N/A", "-", "VACANT"):
        return None
    return name, title


def club_titles(teams: list[str], country: str = "Belgium") -> dict[str, str]:
    """{클럽: 위키 문서 제목} — 캐시, 없으면 검색 첫 결과 중 축구 클럽 인포박스가 있는 문서(캐시에 더한다).
    country — 검색어에 붙이는 나라(라이트 리그 감독 보강이 같이 쓴다, src/lite_league.enrich_managers)."""
    cache = json.loads(TITLES.read_text(encoding="utf-8")) if TITLES.exists() else {}
    out, added = {}, False
    for t in teams:
        if cache.get(t):
            out[t] = cache[t]
            continue
        res = _api(action="query", list="search", srsearch=f"{t} football club {country}", srlimit=3)
        for hit in (res.get("query") or {}).get("search") or []:
            txt = _wikitext([hit["title"]]).get(hit["title"], "")
            if re.search(r"\{\{\s*Infobox football club", txt, re.I):
                out[t] = cache[t] = hit["title"]
                added = True
                break
    if added:
        TITLES.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return out


def _wikitext(titles: list[str]) -> dict[str, str]:
    """{요청 제목: 첫 절 wikitext} — 넘겨주기 따라감, 50개씩."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        q = _api(action="query", prop="revisions", rvprop="content", rvslots="main", rvsection=0,
                 titles="|".join(chunk), redirects=1).get("query", {})
        back = {t: t for t in chunk}
        for m in q.get("normalized", []) + q.get("redirects", []):
            for k, v in list(back.items()):
                if v == m["from"]:
                    back[k] = m["to"]
        got = {p["title"]: ((p.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("content", ""))
               for p in q.get("pages", [])}
        out.update({req: got.get(fin, "") for req, fin in back.items()})
    return out


def main() -> int:
    teams = current_teams(LEAGUE, FALLBACK)
    titles = club_titles(teams)
    texts = _wikitext(list(titles.values()))
    profiles: dict = {}
    for sq in teams:
        mg = infobox_manager(texts.get(titles.get(sq, ""), ""))
        if mg:
            profiles[sq] = {"name": mg[0], "wiki_title": mg[1], "appointed": "", "nationality": "", "style": "",
                            "formation": "", "focus": ""}
    if not profiles:
        print("[belgian-mgr] 인포박스 감독을 하나도 못 읽음", file=sys.stderr)
        return 1
    print(f"[belgian-mgr] 감독 {len(profiles)}/{len(teams)}팀 — 사진·전술 보강 중…")
    photos = fetch_photo_urls([p["wiki_title"] for p in profiles.values()])
    for p in profiles.values():
        ph = photos.get(p["wiki_title"], "") or photos.get(p["name"], "")
        if not ph.startswith("http"):
            ph = _search_photo(p["name"]) or _tm_photo(p["name"])
        p["photo_url"] = ph if ph.startswith("http") else ""
    for sq, p in profiles.items():
        try:
            e = enrich_one(p)
            for k in ("formation", "bio_ko", "bio_source", "tactics_ko", "tactics_source"):
                if e.get(k):
                    p[k] = e[k]
        except Exception as exc:  # noqa: BLE001
            print(f"  [enrich 실패] {sq}: {exc}", file=sys.stderr)
        print(f"  {sq:16} {p['name']:24} 사진{'O' if p['photo_url'] else 'X'} {p.get('formation') or ''}")
    out = data_path("manager_profiles", LEAGUE, ext="json")
    prev = load_profiles(out) if out.exists() else {}
    changed = [{"team": sq, "local": (prev.get(sq) or {}).get("name", ""), "source": p["name"], "change_type": "infobox"}
               for sq, p in profiles.items() if (prev.get(sq) or {}).get("name") and prev[sq]["name"] != p["name"]]
    for c in changed:
        profiles[c["team"]]["previous_name"] = c["local"]
        print(f"  [감독 변화] {c['team']}: {c['local']} → {c['source']}")
    append_change_log(data_path("manager_changes", LEAGUE), changed, True)
    save_profiles(out, profiles)
    print(f"[OK] {out.name} · {len(profiles)}팀 · 사진 {sum(1 for p in profiles.values() if p['photo_url'])}/{len(profiles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
