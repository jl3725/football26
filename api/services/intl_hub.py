"""INTERNATIONAL 허브(국가대표 탭) — 대회 레지스트리(src/intl_comps.py) · A매치 기간 · 경기를 화면용으로.

- hub: 상태 불빛(진행 중·곧·없음) · 지금(A매치 기간·진행 대회) · 대륙별 대회 카드(보여 줄 회차 하나씩)
- match_list: A매치 목록 — 기본 '주요 경기'(우리 리그 선수 소집국·FIFA 30위 안), 대륙·종류·대회 필터
- comp_detail: 대회 한 회차 — 경기(단계별)·우승. 저장 범위 밖(유로 2024 등)은 ESPN 에서 그 회차만 받아 캐시
"""
from __future__ import annotations

import datetime as dt
import json
import time

import pandas as pd

import api.bootstrap  # noqa: F401
import fetch_intl as fi
import player_registry as preg
from api.services import intl

CONF_LABEL = {"GLOBAL": ("WORLD", "세계"), "UEFA": ("EUROPE", "유럽"), "AFC": ("ASIA", "아시아"), "CAF": ("AFRICA", "아프리카"),
              "CONMEBOL": ("SOUTH AMERICA", "남미"), "CONCACAF": ("NORTH & CENTRAL AMERICA", "북중미"), "OFC": ("OCEANIA", "오세아니아")}
KIND_LABEL = {"tournament": "본선", "nations_league": "네이션스리그", "qualifier": "예선", "friendly": "친선"}
_CACHE: dict = {}


def competitions() -> list[dict]:
    p = intl.DATA / "intl_competitions.json"
    if not p.exists():
        return []
    key = p.stat().st_mtime
    hit = _CACHE.get("comps")
    if hit and hit[0] == key:
        return hit[1]
    val = json.loads(p.read_text(encoding="utf-8")).get("competitions", [])
    _CACHE["comps"] = (key, val)
    return val


def focus_edition(c: dict) -> dict | None:
    """보여 줄 회차 — 진행 중 > 가장 가까운 예정 > 가장 최근 종료."""
    eds = c.get("editions") or []
    live = [e for e in eds if e["status"] == "live"]
    up = sorted([e for e in eds if e["status"] == "upcoming"], key=lambda e: e["start"])
    done = sorted([e for e in eds if e["status"] == "finished"], key=lambda e: e["end"], reverse=True)
    return (live or up or done or [None])[0]


def key_nations() -> set[str]:
    """'주요 경기' 기준 나라 — FIFA 랭킹 30위 안 + 우리 리그 선수가 4명 이상 소집된 대표팀(정규화 이름).
    한 명만 소집된 나라까지 넣으면 아루바–마르티니크 같은 경기가 '주요'로 섞였다."""
    keys: set[str] = set()
    c = intl.callups()
    if "nation" in c.columns:
        cnt = c["nation"].dropna().astype(str).value_counts()
        for n in cnt[cnt >= 4].index:
            keys |= fi.nation_keys(n)
    p = intl.DATA / "fifa_ranking.csv"
    if p.exists():
        fr = pd.read_csv(p)
        for t in fr[pd.to_numeric(fr["rank"], errors="coerce") <= 30]["team"].astype(str):
            keys.add(preg.norm(t))
            keys |= {preg.norm(k) for k, v in fi.FIFA_NAME.items() if v == t}   # FIFA 표기 ↔ ESPN 표기('Korea Republic' ↔ 'South Korea')
    return keys


def hub(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    t = today.isoformat()
    soon = (today + dt.timedelta(days=14)).isoformat()
    w, last, wstate = intl._target(today)
    cards = []
    for c in competitions():
        e = focus_edition(c)
        if e:
            cards.append({"code": c["code"], "name": c["name"], "name_ko": c.get("name_ko") or c["name"], "conf": c["conf"],
                          "kind": c["kind"], "kind_ko": KIND_LABEL.get(c["kind"], c["kind"]), "edition": e,
                          "editions": len(c.get("editions") or [])})
    # 불빛: 본선이 진행 중이거나 A매치 기간 중 = live, 14일 안에 시작 = soon. 친선·네이션스리그는 '연중'이라 기간으로만 본다
    tour_live = [x for x in cards if x["kind"] == "tournament" and x["edition"]["status"] == "live"]
    tour_soon = [x for x in cards if x["kind"] == "tournament" and x["edition"]["status"] == "upcoming" and x["edition"]["start"] <= soon]
    status = "live" if tour_live or wstate == "now" else "soon" if tour_soon or (w and w["start"] <= soon) else "none"
    by_conf = []
    for conf, (en, ko) in CONF_LABEL.items():
        cs = [x for x in cards if x["conf"] == conf]
        if cs:
            by_conf.append({"conf": conf, "en": en, "ko": ko, "comps": cs})
    m = intl.matches()
    nxt_tour = sorted([x for x in cards if x["kind"] == "tournament" and x["edition"]["status"] == "upcoming"],
                      key=lambda x: x["edition"]["start"])
    return {"status": status, "today": t, "window": w, "window_state": wstate, "last_window": last,
            "live": tour_live, "next_tournament": nxt_tour[0] if nxt_tour else None,
            "today_matches": int((m["date"].astype(str) == t).sum()) if not m.empty else 0,
            "by_conf": by_conf, "callups": int(len(intl.callups()))}


def match_list(scope: str = "key", when: str = "upcoming", conf: str = "", kind: str = "", code: str = "",
               limit: int = 80, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    t = today.isoformat()
    m = intl.matches()
    if m.empty:
        return {"matches": [], "scope": scope, "when": when}
    meta = {c["code"]: c for c in competitions()}
    m = m.copy()
    m["conf"] = m["comp_code"].map(lambda x: (meta.get(x) or {}).get("conf", str(x).split(".")[0].upper()))
    m["kind"] = m["comp_code"].map(lambda x: (meta.get(x) or {}).get("kind", ""))
    if when == "upcoming":
        m = m[(m["date"].astype(str) >= t) & (m["state"] != "post")].sort_values(["date", "kickoff"])
    else:
        m = m[m["state"] == "post"].sort_values(["date", "kickoff"], ascending=False)
    if conf:
        m = m[m["conf"] == conf]
    if kind:
        m = m[m["kind"] == kind]
    if code:
        m = m[m["comp_code"] == code]
    keys = key_nations() if scope == "key" else set()
    out = []
    for r in m.to_dict("records"):
        hk, ak = preg.norm(r["home"]), preg.norm(r["away"])
        if keys and hk not in keys and ak not in keys:
            continue
        c = meta.get(r["comp_code"]) or {}
        num = lambda v: None if v is None or (isinstance(v, float) and v != v) else int(float(v))  # noqa: E731
        txt = lambda v: "" if v is None or (isinstance(v, float) and v != v) else str(v)  # noqa: E731
        out.append({"event_id": str(r["event_id"]), "date": r["date"], "kickoff": txt(r.get("kickoff")), "comp_code": r["comp_code"],
                    "comp": c.get("name_ko") or c.get("name") or r["comp_code"], "conf": r["conf"], "kind": r["kind"],
                    "stage": txt(r.get("stage")), "home": r["home"], "away": r["away"],
                    "home_logo": txt(r.get("home_logo")), "away_logo": txt(r.get("away_logo")), "state": r["state"],
                    "hg": num(r.get("hg")), "ag": num(r.get("ag"))})
        if len(out) >= limit:
            break
    return {"matches": out, "scope": scope, "when": when}


def comp_detail(code: str, season: str = "") -> dict:
    from espn_common import scoreboard_events  # noqa: PLC0415
    c = next((x for x in competitions() if x["code"] == code), None)
    if not c:
        return {"available": False, "code": code}
    eds = c.get("editions") or []
    e = next((x for x in eds if str(x["season"]) == str(season)), None) or focus_edition(c)
    if not e:
        return {"available": False, "code": code}
    key = ("comp", code, str(e["season"]))
    hit = _CACHE.get(key)
    if not hit or hit[0] < time.time():
        rows = []
        for ev in scoreboard_events(code, e["start"], e["end"]) or []:
            if str((ev.get("season") or {}).get("year") or "") not in ("", str(e["season"])):
                continue
            cc = (ev.get("competitions") or [{}])[0]
            side = {x.get("homeAway"): x for x in cc.get("competitors", [])}
            h, a = side.get("home", {}), side.get("away", {})
            st = ((ev.get("status") or {}).get("type") or {}).get("state", "pre")
            stage = " · ".join(n.get("headline", "") for n in cc.get("notes", []) if isinstance(n, dict) and n.get("headline"))
            rows.append({"event_id": str(ev.get("id")), "date": (ev.get("date") or "")[:10], "kickoff": ev.get("date") or "",
                         "stage": stage, "state": st,
                         "home": (h.get("team") or {}).get("displayName", ""), "away": (a.get("team") or {}).get("displayName", ""),
                         "home_logo": (h.get("team") or {}).get("logo", ""), "away_logo": (a.get("team") or {}).get("logo", ""),
                         "hg": None if st == "pre" else h.get("score"), "ag": None if st == "pre" else a.get("score"),
                         "winner": "home" if h.get("winner") else "away" if a.get("winner") else None})
        _CACHE[key] = (time.time() + (3600 if e["status"] == "live" else 86400), rows)
        hit = _CACHE[key]
    return {"available": True, "code": code, "name": c["name"], "name_ko": c.get("name_ko") or c["name"], "conf": c["conf"],
            "kind": c["kind"], "kind_ko": KIND_LABEL.get(c["kind"], c["kind"]), "edition": e,
            "editions": [{"season": x["season"], "status": x["status"], "champion": x.get("champion")} for x in eds],
            "matches": hit[1]}
