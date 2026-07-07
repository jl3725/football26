"""
Eredivisie 감독 프로필 수집기 — fetch_ligaportugal_managers 와 동일 패턴.

위키 "2026-27 Eredivisie"(최신) 우선 + "2025-26 Eredivisie"(현재 18팀) 폴백 병합.
캐논 18팀만 남기고 manager_profiles_Eredivisie 생성.

사용: python src/fetch_eredivisie_managers.py
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

SOURCE_NEXT = tracking_season_title().replace("Premier League", "Eredivisie")
SOURCE_CUR = "2025-26 Eredivisie"

OUR = ["PSV", "Ajax", "Feyenoord", "AZ Alkmaar", "Utrecht", "Twente", "NEC Nijmegen",
       "Heerenveen", "Groningen", "Sparta R.", "Go Ahead Eagles", "Fortuna Sittard",
       "Zwolle", "Excelsior", "Volendam", "Heracles Almelo", "Telstar", "NAC Breda"]
ALIAS = {"PSV Eindhoven": "PSV", "PSV": "PSV", "AFC Ajax": "Ajax", "Ajax": "Ajax",
         "Ajax Amsterdam": "Ajax", "Feyenoord": "Feyenoord", "Feyenoord Rotterdam": "Feyenoord",
         "AZ": "AZ Alkmaar", "AZ Alkmaar": "AZ Alkmaar", "FC Utrecht": "Utrecht", "Utrecht": "Utrecht",
         "FC Twente": "Twente", "FC Twente '65": "Twente", "Twente": "Twente",
         "NEC": "NEC Nijmegen", "N.E.C.": "NEC Nijmegen", "NEC Nijmegen": "NEC Nijmegen",
         "SC Heerenveen": "Heerenveen", "Heerenveen": "Heerenveen",
         "FC Groningen": "Groningen", "Groningen": "Groningen",
         "Sparta Rotterdam": "Sparta R.", "Sparta": "Sparta R.",
         "Go Ahead Eagles": "Go Ahead Eagles", "Fortuna Sittard": "Fortuna Sittard",
         "PEC Zwolle": "Zwolle", "Zwolle": "Zwolle", "SBV Excelsior": "Excelsior",
         "Excelsior": "Excelsior", "Excelsior Rotterdam": "Excelsior",
         "FC Volendam": "Volendam", "Volendam": "Volendam",
         "Heracles Almelo": "Heracles Almelo", "Heracles": "Heracles Almelo",
         "SC Telstar": "Telstar", "Telstar": "Telstar", "NAC Breda": "NAC Breda", "NAC": "NAC Breda"}


def to_squad(wiki: str) -> str:
    if wiki in ALIAS:
        return ALIAS[wiki]
    if wiki in OUR:
        return wiki
    wl = wiki.lower()
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
        print(f"[erediv-mgr] {title} 파싱 실패: {exc}", file=sys.stderr)
        return {}


def main() -> int:
    nxt, cur = _mapped(SOURCE_NEXT), _mapped(SOURCE_CUR)
    if not cur and not nxt:
        print("[erediv-mgr] 위키 감독표 파싱 실패", file=sys.stderr)
        return 1

    def _clean(v):
        v = str(v or "").strip()
        return "" if v.upper() in ("TBA", "TBD", "N/A", "-") else v

    teams = (set(cur) | set(nxt)) & set(OUR)   # 캐논 18팀만
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
        profiles[sq] = {"name": mgr, "wiki_title": mgr, "appointed": appts.get(sq, ""),
                        "nationality": "", "style": "", "formation": "", "focus": ""}
    print(f"[erediv-mgr] 감독 {len(profiles)}팀 — 사진·전술 보강 중…")

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
        print(f"  {sq:16} {p['name']:24} 사진{'O' if p['photo_url'] else 'X'} {p.get('formation') or ''}")

    out = data_path("manager_profiles", "Eredivisie", ext="json")
    save_profiles(out, profiles)
    n_ph = sum(1 for p in profiles.values() if p["photo_url"])
    print(f"[OK] {out.name} · {len(profiles)}팀 · 사진 {n_ph}/{len(profiles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
