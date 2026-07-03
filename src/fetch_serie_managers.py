"""
Serie A 감독 프로필 수집기 — EPL/LaLiga 파이프라인 재사용.

위키 "2026-27 Serie A"(추적 시즌, 최신 감독) 우선 + "2025-26 Serie A"(현재 표시 데이터의
20팀) 폴백으로 병합 → 현재 리그 전 팀이 감독 카드를 갖되, 교체된 팀은 최신 감독 반영.
manager_profiles_SerieA_2025_2026.json 생성.

카드: name · photo_url(위키→TM 폴백) · formation · bio_ko · tactics_ko · appointed
사용: python src/fetch_serie_managers.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from sync_manager_profiles import (fetch_source_managers, fetch_photo_urls,  # noqa: E402
                                   fetch_appointment_dates, save_profiles, tracking_season_title)
from enrich_manager_profiles import enrich_one  # noqa: E402
from fetch_manager_photos import _search_photo, _tm_photo  # noqa: E402
from leagues import data_path  # noqa: E402

SOURCE_NEXT = tracking_season_title().replace("Premier League", "Serie A")   # 예: 2026-27 Serie A
SOURCE_CUR = "2025-26 Serie A"                                               # 현재 표시 데이터 팀

OUR = ["Atalanta", "Bologna", "Cagliari", "Como", "Cremonese", "Fiorentina", "Genoa",
       "Hellas Verona", "Inter", "Juventus", "Lazio", "Lecce", "Milan", "Napoli",
       "Parma", "Pisa", "Roma", "Sassuolo", "Torino", "Udinese"]
ALIAS = {"Inter Milan": "Inter", "Internazionale": "Inter", "FC Internazionale Milano": "Inter",
         "AC Milan": "Milan", "Associazione Calcio Milan": "Milan", "Verona": "Hellas Verona"}


def to_squad(wiki: str) -> str:
    if wiki in ALIAS:
        return ALIAS[wiki]
    if wiki in OUR:
        return wiki
    wl = wiki.lower()
    # 'inter' 를 'milan' 보다 먼저 검사 — 'Inter Milan' 오매칭 방지
    if "inter" in wl:
        return "Inter"
    if "milan" in wl:
        return "Milan"
    for s in OUR:
        if s.lower() in wl or wl in s.lower():
            return s
    for s in OUR:
        if any(tok in wl for tok in s.lower().split() if len(tok) > 3):
            return s
    return wiki


def _mapped(title: str) -> dict:
    try:
        return {to_squad(k): v for k, v in fetch_source_managers(title).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"[serie-mgr] {title} 파싱 실패: {exc}", file=sys.stderr)
        return {}


def main() -> int:
    nxt = _mapped(SOURCE_NEXT)
    cur = _mapped(SOURCE_CUR)
    if not cur and not nxt:
        print("[serie-mgr] 위키 감독표 파싱 실패", file=sys.stderr)
        return 1
    # 현재 표시 팀(25/26) 전부 커버 — 최신(26/27) 감독 우선, TBA/공란이면 25/26 폴백.
    def _clean(v):
        v = str(v or "").strip()
        return "" if v.upper() == "TBA" else v
    teams = set(cur) | (set(nxt) & set(OUR))
    managers = {}
    for t in teams:
        m = _clean(nxt.get(t)) or _clean(cur.get(t))
        if m:
            managers[t] = m

    appts = {}
    for title in (SOURCE_NEXT, SOURCE_CUR):
        try:
            appts.update({to_squad(k): v for k, v in fetch_appointment_dates(title).items()})
        except Exception:  # noqa: BLE001
            pass

    profiles: dict = {}
    for sq, mgr in managers.items():
        if not mgr or str(mgr).upper() == "TBA":
            continue
        profiles[sq] = {"name": mgr, "wiki_title": mgr, "appointed": appts.get(sq, ""),
                        "nationality": "", "style": "", "formation": "", "focus": ""}
    print(f"[serie-mgr] 감독 {len(profiles)}팀 — 사진·전술 보강 중…")

    photos = fetch_photo_urls([p["name"] for p in profiles.values()])
    for sq, p in profiles.items():
        ph = photos.get(p["name"], "")
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
        mark = "O" if p["photo_url"] else "X"
        print(f"  {sq:16} {p['name']:24} 사진{mark} {p.get('formation') or ''}")

    out = data_path("manager_profiles", "SerieA", ext="json")
    save_profiles(out, profiles)
    n_ph = sum(1 for p in profiles.values() if p["photo_url"])
    print(f"[OK] {out.name} · {len(profiles)}팀 · 사진 {n_ph}/{len(profiles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
