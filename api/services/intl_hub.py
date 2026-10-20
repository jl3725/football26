"""INTERNATIONAL 허브(국가대표 탭) — 대회 레지스트리(src/intl_comps.py) · A매치 기간 · 경기를 화면용으로.

- hub: 상태 불빛(진행 중·곧·없음) · 지금(A매치 기간·진행 대회) · 대륙별 대회 카드(보여 줄 회차 하나씩)
- match_list: A매치 목록 — 기본 '주요 경기'(우리 리그 선수 소집국·FIFA 30위 안), 대륙·종류·대회 필터
- comp_detail: 대회 한 회차 — 경기(단계별)·우승. 저장 범위 밖(유로 2024 등)은 ESPN 에서 그 회차만 받아 캐시
"""
from __future__ import annotations

import datetime as dt
import json
import re
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
    w, last, wstate = intl._target(today, kinds=("break",))   # 대회(아시안컵 등)는 아래 next_tournament 카드로 따로
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
                    "home_ko": nation_ko(r["home"]), "away_ko": nation_ko(r["away"]),
                    "home_logo": txt(r.get("home_logo")), "away_logo": txt(r.get("away_logo")), "state": r["state"],
                    "hg": num(r.get("hg")), "ag": num(r.get("ag"))})
        if len(out) >= limit:
            break
    return {"matches": out, "scope": scope, "when": when}


# 대회 단계(ESPN 경기 season.slug) — 영어 위주 + 한글. 모르는 단계는 slug 를 그대로 대문자로
ROUND_LABEL = {"group-stage": ("GROUP STAGE", "조별리그"), "round-of-32": ("ROUND OF 32", "32강"),
               "round-of-16": ("ROUND OF 16", "16강"), "quarterfinals": ("QUARTER-FINALS", "8강"),
               "semifinals": ("SEMI-FINALS", "4강"), "3rd-place": ("THIRD PLACE", "3·4위전"),
               "third-place": ("THIRD PLACE", "3·4위전"), "final": ("FINAL", "결승")}
_ROUND_ORDER = list(ROUND_LABEL)


def _cached(key, ttl: float, fn):
    hit = _CACHE.get(key)
    if not hit or hit[0] < time.time():
        _CACHE[key] = (time.time() + ttl, fn())
        hit = _CACHE[key]
    return hit[1]


def _standings(code: str, season: str) -> list[dict]:
    """ESPN 조별 순위 — [{name, rows:[{team, logo, rank, p, w, d, l, gf, ga, gd, pts}]}]. 조가 없는 대회는 []."""
    import requests  # noqa: PLC0415
    try:
        r = requests.get(f"https://site.api.espn.com/apis/v2/sports/soccer/{code}/standings", params={"season": season},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        kids = r.json().get("children") or [] if r.ok else []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for ch in kids:
        rows = []
        for en in (ch.get("standings") or {}).get("entries") or []:
            t = en.get("team") or {}
            s = {x.get("name"): x.get("value") for x in en.get("stats") or []}
            n = lambda k: int(s.get(k) or 0)  # noqa: E731
            rows.append({"team": t.get("displayName", ""), "logo": ((t.get("logos") or [{}])[0]).get("href", ""),
                         "rank": n("rank"), "p": n("gamesPlayed"), "w": n("wins"), "d": n("ties"), "l": n("losses"),
                         "gf": n("pointsFor"), "ga": n("pointsAgainst"), "gd": n("pointDifferential"), "pts": n("points")})
        rows.sort(key=lambda x: (x["rank"] or 99, -x["pts"], -x["gd"], -x["gf"]))
        if rows:
            out.append({"name": ch.get("name") or ch.get("abbreviation") or "", "rows": rows})
    return out


def fill_tbd(groups: list[dict], pairs) -> list[dict]:
    """순위표의 'TBD' 자리를 일정으로 채운다 — 조 안의 나라와 경기가 잡혔는데 어느 조에도 없는 나라(아시안컵 E조 예멘).
    pairs = [(홈, 원정)] (그 대회·회차 경기)."""
    in_any = {preg.norm(r["team"]) for g in groups for r in g["rows"]}
    out = []
    for g in groups:
        members = {preg.norm(r["team"]) for r in g["rows"]}
        found: list[str] = []
        for h, a in pairs:
            for me, opp in ((h, a), (a, h)):
                if preg.norm(me) in members and preg.norm(opp) not in in_any and not re.search(
                        r"winner|loser|place|group|tbd|runner|/", str(opp), re.I) and opp not in found:
                    found.append(opp)
        rows = []
        for r in g["rows"]:
            if str(r["team"]).strip().upper() == "TBD" and found:
                r = {**r, "team": found.pop(0), "logo": r.get("logo") or ""}
            rows.append(r)
        out.append({**g, "rows": rows})
    return out


def _club_matches(start: str, end: str) -> dict[tuple[str, str], int]:
    """(리그, 클럽) → start~end 사이 클럽 경기 수(전 대회, schedule_full)."""
    from leagues import LEAGUES, data_path  # noqa: PLC0415
    out: dict[tuple[str, str], int] = {}
    for lg in LEAGUES:
        p = data_path("schedule_full", lg)
        if not p.exists():
            continue
        d = pd.read_csv(p, usecols=["squad", "date", "event_id"])
        d = d[(d["date"].astype(str) >= start) & (d["date"].astype(str) <= end)].drop_duplicates(["squad", "event_id"])
        for sq, n in d.groupby("squad").size().items():
            out[(lg, str(sq))] = int(n)
    return out


def latest_squads(nation_names) -> pd.DataFrame:
    """나라마다 가장 최근 소집 명단(intl_callups — 위키 Current squad)."""
    c = intl.callups()
    if c.empty or "nation" not in c.columns:
        return c
    want = set()
    for n in nation_names:
        want |= {preg.norm(n)} | fi.nation_keys(n)
    c = c[c["nation"].astype(str).map(lambda n: bool(fi.nation_keys(n) & want))].copy()
    if c.empty:
        return c
    last = c.groupby("nation")["squad_for"].transform("max")
    return c[c["squad_for"] == last]


def nation_ko(nation: str) -> str:
    """나라 한글 이름(data/intl_nations_ko.json — src/intl_comps.py 가 위키 언어 간 링크로 채움). 없으면 원래 표기."""
    p = intl.DATA / "intl_nations_ko.json"
    try:
        key = p.stat().st_mtime
        if _CACHE.get("ko", (None,))[0] != key:
            _CACHE["ko"] = (key, json.loads(p.read_text(encoding="utf-8")))
        return _CACHE["ko"][1].get(nation) or nation
    except (OSError, ValueError):
        return nation


def _num(v):
    return None if v is None or (isinstance(v, float) and v != v) else int(float(v))


def comp_detail(code: str, season: str = "") -> dict:
    from espn_common import scoreboard_events  # noqa: PLC0415
    import teammeta as tm  # noqa: PLC0415
    c = next((x for x in competitions() if x["code"] == code), None)
    if not c:
        return {"available": False, "code": code}
    eds = c.get("editions") or []
    e = next((x for x in eds if str(x["season"]) == str(season)), None) or focus_edition(c)
    if not e:
        return {"available": False, "code": code}
    ttl = 3600 if e["status"] == "live" else 86400

    def load_rows() -> list[dict]:
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
                         "stage": stage, "state": st, "round": str((ev.get("season") or {}).get("slug") or ""),
                         "venue": ((cc.get("venue") or {}).get("fullName") or ""),
                         "home": (h.get("team") or {}).get("displayName", ""), "away": (a.get("team") or {}).get("displayName", ""),
                         "home_logo": (h.get("team") or {}).get("logo", ""), "away_logo": (a.get("team") or {}).get("logo", ""),
                         "hg": None if st == "pre" else h.get("score"), "ag": None if st == "pre" else a.get("score"),
                         "winner": "home" if h.get("winner") else "away" if a.get("winner") else None})
        return rows

    rows = [{**r, "home_ko": nation_ko(r["home"]), "away_ko": nation_ko(r["away"])}
            for r in _cached(("comp", code, str(e["season"])), ttl, load_rows)]
    groups = _cached(("groups", code, str(e["season"])), ttl, lambda: _standings(code, str(e["season"]))) \
        if c["kind"] in ("tournament", "nations_league") else []
    groups = fill_tbd(groups, [(r["home"], r["away"]) for r in rows])
    groups = [{**g, "rows": [{**r, "team_ko": nation_ko(r["team"])} for r in g["rows"]]} for g in groups]
    # 경기에 조 붙이기 — 두 팀이 같은 조면 그 조(조별리그 경기)
    team_group = {preg.norm(r["team"]): g["name"] for g in groups for r in g["rows"]}
    for r in rows:
        gh, ga = team_group.get(preg.norm(r["home"])), team_group.get(preg.norm(r["away"]))
        # 순위표에 아직 'TBD' 로 남은 나라(아시안컵 E조 예멘)와의 조별리그 경기는 상대 쪽 조로
        r["group"] = gh if gh and gh == ga else ((gh or ga) if r["round"] == "group-stage" and not (gh and ga) else "")
    seen = list(dict.fromkeys(r["round"] for r in rows if r["round"]))
    seen.sort(key=lambda s: _ROUND_ORDER.index(s) if s in _ROUND_ORDER else 50)
    rounds = [{"slug": s, "en": ROUND_LABEL.get(s, (s.replace("-", " ").upper(), ""))[0],
               "ko": ROUND_LABEL.get(s, ("", ""))[1], "n": sum(1 for r in rows if r["round"] == s)} for s in seen]

    # 우리 리그 선수 — 출전국의 가장 최근 소집 명단 중 8개 리그 소속(대회 명단 발표 전이면 '지난 소집 기준')
    nations = {r["team"] for g in groups for r in g["rows"]} | {r["home"] for r in rows} | {r["away"] for r in rows}
    sq = latest_squads(nations)
    sq = sq[sq["our_player"].notna() & (sq["our_player"].astype(str) != "")] if not sq.empty and "our_player" in sq.columns else sq.iloc[0:0]
    camp = (dt.date.fromisoformat(e["start"]) - dt.timedelta(days=45)).isoformat()
    by_nation = []
    for nat, g in sq.groupby("nation"):
        by_nation.append({"nation": str(nat), "nation_ko": nation_ko(str(nat)), "flag": str(g["flag"].iloc[0]) if isinstance(g["flag"].iloc[0], str) else "",
                          "fifa_rank": _num(g["fifa_rank"].iloc[0]),
                          "announced": str(g["squad_for"].iloc[0]) >= camp, "squad_for": str(g["squad_for"].iloc[0]),
                          "players": [{"player": str(r.our_player), "club": str(r.our_squad), "league": str(r.our_league),
                                       "pos": r.pos if isinstance(r.pos, str) else "", "caps": _num(r.caps)}
                                      for r in g.sort_values("caps", ascending=False).itertuples()]})
    by_nation.sort(key=lambda x: (-len(x["players"]), x["fifa_rank"] or 999))
    cm = _club_matches(e["start"], e["end"]) if e["status"] != "finished" else {}
    impact: dict = {}
    for n in by_nation:
        for p in n["players"]:
            k = (p["league"], p["club"])
            it = impact.setdefault(k, {"club": p["club"], "league": p["league"], "logo": tm.team_logo(p["club"]),
                                       "players": [], "club_matches": cm.get(k)})
            it["players"].append({"player": p["player"], "nation": n["nation"], "nation_ko": n["nation_ko"]})
    club_impact = sorted(impact.values(), key=lambda x: (-len(x["players"]), -(x["club_matches"] or 0)))
    return {"available": True, "code": code, "name": c["name"], "name_ko": c.get("name_ko") or c["name"], "conf": c["conf"],
            "kind": c["kind"], "kind_ko": KIND_LABEL.get(c["kind"], c["kind"]), "edition": e,
            "editions": [{"season": x["season"], "status": x["status"], "champion": x.get("champion")} for x in eds],
            "matches": rows, "groups": groups, "rounds": rounds,
            "players": by_nation, "club_impact": club_impact[:16]}


def nations() -> list[dict]:
    """MY NATION 고르기 목록 — 소집 명단이 있는 나라(우리 리그 선수 수·FIFA 순위)."""
    c = intl.callups()
    if c.empty or "nation" not in c.columns:
        return []
    out = []
    for nat, g in c.groupby("nation"):
        last = g[g["squad_for"] == g["squad_for"].max()]
        out.append({"nation": str(nat), "nation_ko": nation_ko(str(nat)),
                    "flag": str(g["flag"].iloc[0]) if isinstance(g["flag"].iloc[0], str) else "",
                    "conf": str(g["nation_conf"].iloc[0]) if isinstance(g["nation_conf"].iloc[0], str) else "",
                    "fifa_rank": _num(g["fifa_rank"].iloc[0]),
                    "ours": int(last["our_player"].notna().sum()) if "our_player" in last.columns else 0})
    return sorted(out, key=lambda x: (x["fifa_rank"] or 999, x["nation"]))


def nation_payload(nation: str, today: dt.date | None = None) -> dict:
    """한 나라 대표팀 — 다음 경기·최근 결과(폼)·나가는 대회(조 편성)·최근 소집 명단(우리 리그 선수 표시)."""
    today = today or dt.date.today()
    t = today.isoformat()
    keys = fi.nation_keys(nation) | {preg.norm(nation)}
    meta = {c["code"]: c for c in competitions()}
    m = intl.matches()
    rows = []
    if not m.empty:
        mine = m[[preg.norm(h) in keys or preg.norm(a) in keys for h, a in zip(m["home"].astype(str), m["away"].astype(str))]]
        for r in mine.sort_values(["date", "kickoff"]).to_dict("records"):
            home = preg.norm(r["home"]) in keys
            done = r["state"] == "post" and _num(r.get("hg")) is not None
            us, them = (_num(r.get("hg")), _num(r.get("ag"))) if home else (_num(r.get("ag")), _num(r.get("hg")))
            c = meta.get(r["comp_code"]) or {}
            rows.append({"event_id": str(r["event_id"]), "date": r["date"], "kickoff": str(r.get("kickoff") or ""),
                         "comp_code": r["comp_code"], "comp": c.get("name_ko") or c.get("name") or r["comp_code"],
                         "kind": c.get("kind", ""), "season": str(r.get("season") or ""),
                         "home": home, "opp": r["away"] if home else r["home"],
                         "opp_ko": nation_ko(r["away"] if home else r["home"]),
                         "opp_logo": str((r.get("away_logo") if home else r.get("home_logo")) or ""),
                         "logo": str((r.get("home_logo") if home else r.get("away_logo")) or ""),
                         "score": f"{us}-{them}" if done else None, "state": r["state"],
                         "result": None if not done else ("W" if us > them else "L" if us < them else "D")})
    display = next((r["home"] if preg.norm(r["home"]) in keys else r["away"] for r in (m.to_dict("records") if not m.empty else [])
                    if preg.norm(r["home"]) in keys or preg.norm(r["away"]) in keys), nation)
    upcoming = [r for r in rows if r["state"] != "post" and r["date"] >= t][:8]
    recent = [r for r in rows if r["state"] == "post"][::-1][:8]
    # 나가는 대회(예정·진행) — 본선이면 조와 같은 조 나라
    tours = []
    for (code, season), g in pd.DataFrame(upcoming or [{"comp_code": "", "season": ""}]).groupby(["comp_code", "season"]):
        c = meta.get(code)
        if not c:
            continue
        ed = next((x for x in c.get("editions") or [] if str(x["season"]) == str(season)), None) or focus_edition(c)
        grp = None
        if c["kind"] == "tournament" and ed:
            gs = _cached(("groups", code, str(ed["season"])), 86400, lambda: _standings(code, str(ed["season"])))
            same = m[(m["comp_code"] == code) & (m["season"].astype(str) == str(ed["season"]))] if not m.empty else m
            gs = fill_tbd(gs, list(zip(same["home"].astype(str), same["away"].astype(str))) if not same.empty else [])
            grp = next(({"name": x["name"], "rows": [{**r, "team_ko": nation_ko(r["team"])} for r in x["rows"]]} for x in gs
                        if any(preg.norm(r["team"]) in keys for r in x["rows"])), None)
        tours.append({"code": code, "name_ko": c.get("name_ko") or c["name"], "kind": c["kind"],
                      "kind_ko": KIND_LABEL.get(c["kind"], c["kind"]), "edition": ed, "group": grp,
                      "matches": int(len(g))})
    tours.sort(key=lambda x: (x["kind"] != "tournament", (x["edition"] or {}).get("start", "")))
    sq = latest_squads([nation])
    order = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
    squad = []
    if not sq.empty:
        for r in sq.itertuples():
            ours = isinstance(r.our_player, str) and bool(r.our_player)
            squad.append({"player": str(r.our_player if ours else r.player), "club": str(r.our_squad if ours else r.club),
                          "league": str(r.our_league) if ours else "", "ours": ours,
                          "pos": r.pos if isinstance(r.pos, str) else "", "caps": _num(r.caps), "goals": _num(r.goals)})
        squad.sort(key=lambda x: (order.get(x["pos"], 9), -(x["caps"] or 0)))
    head = sq.iloc[0] if not sq.empty else None
    form = [r["result"] for r in recent[:5]][::-1]
    return {"nation": nation, "display": display, "nation_ko": nation_ko(nation),
            "flag": str(head["flag"]) if head is not None and isinstance(head["flag"], str) else "",
            "conf": str(head["nation_conf"]) if head is not None and isinstance(head["nation_conf"], str) else "",
            "fifa_rank": _num(head["fifa_rank"]) if head is not None else None,
            "squad_for": str(head["squad_for"]) if head is not None else "",
            "form": form, "upcoming": upcoming, "recent": recent, "tournaments": tours,
            "squad": squad, "ours": sum(1 for x in squad if x["ours"])}
