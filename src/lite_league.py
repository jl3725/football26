"""
라이트 리그 뼈대 — FotMob 리그·팀 응답 → 순위표·일정·1군 명단·감독·팀 대조표

2026-10-22 1단계 리그 확장(챔피언십·쉬페르리그·오스트리아·덴마크·스위스). 라이트 리그는 FBref 가 없어 '우리 팀 표기'의
기준이 따로 필요하다 — FotMob 리그 표의 이름을 기준으로 삼는다(선수·평점·명단·부상이 모두 FotMob 이라 대조가 가장 적다).
일정도 FotMob 이다 — ESPN 은 스위스 리그를 26/27 이 되도록 지난 시즌에 멈춰 두었다(2026-10-22 확인: sui.1 이벤트 0건).
요청: 리그 1번 + 팀마다 1번(팀 응답 하나에 일정·명단·감독이 같이 온다).
- standings_{리그}: FotMob 리그 표(스플릿 리그는 그룹 표를 차례로 이어 순위를 매김).
- schedule_full_{리그}: 팀별 전 대회 일정(친선 제외) — schedule_full 과 같은 열. event_id 는 FotMob 경기 id,
  comp_code 는 리그=ESPN 코드(cfg.espn)·유럽=uefa.*·아는 컵=ESPN 코드·모르는 컵=fm.<FotMob 대회 id>.
- fotmob_squads_{리그}: 등록 1군 전원(src/fotmob_squads.py 와 같은 열 — 같은 응답을 다시 쓴다).
- manager_profiles_{리그}.json: FotMob 명단의 감독(이름·국적·사진). 바뀌면 previous_name·change_detected_at.
- lite_teams_{리그}.json: 팀 대조표 — FotMob id·색·로고 + ESPN 팀 id(이름 유사도 → 같은 날 같은 상대 경기로 확인·보정;
  'Rapid Vienna'↔'Rapid Wien', 'Odense Boldklub'↔'OB') + Transfermarkt verein(sync_transfermarkt_contracts 가 선수 명단
  겹침으로 정해 remember_tm 으로 적는다 — 'FC Copenhagen'↔'FC København', 'Grasshopper Club Zürich'≠'FC Zürich').
  teammeta(로고·색·verein)와 espn_common.squad_of 가 읽는다.

    python src/lite_league.py [--league Championship]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, LITE_LEAGUES, SEASON, SEASON_START, data_path  # noqa: E402

LOGO = "https://images.fotmob.com/image_resources/logo/teamlogo/{}.png"
PHOTO = "https://images.fotmob.com/image_resources/playerimages/{}.png"
STAND_COLS = ["rank", "squad", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points"]
SCHED_COLS = ["squad", "comp", "comp_code", "date", "kickoff", "home_away", "opponent", "gf", "ga", "score", "result",
              "status", "event_id", "opponent_logo"]
# FotMob 유럽 대회 id → (우리 코드, 화면 이름) — espn_common.EURO_COMPS 와 같은 축
EURO = {42: ("uefa.champions", "챔피언스리그"), 73: ("uefa.europa", "유로파리그"), 10216: ("uefa.europa.conf", "컨퍼런스리그")}


def _tables(d: dict) -> list[list[dict]]:
    """FotMob 리그 응답 → 표 묶음(단일 표면 1개, 스플릿·그룹이면 여러 개)."""
    out = []
    for t in d.get("table") or []:
        data = t.get("data") or {}
        groups = [sub["table"]["all"] for sub in data.get("tables") or [] if (sub.get("table") or {}).get("all")]
        # 스플릿 뒤엔 상·하위 그룹 표가 최종 순서 — 같은 목록에 정규 라운드 전체 표도 있어(오스트리아 25/26: 그룹 6+6 + 전체 12)
        # 다른 표를 통째로 품는 큰 표는 뺀다
        names = [{x.get("name") for x in g} for g in groups]
        groups = [g for i, g in enumerate(groups) if not any(j != i and names[j] < names[i] for j in range(len(groups)))] or groups
        if groups:
            out.extend(groups)
        elif (data.get("table") or {}).get("all"):
            out.append(data["table"]["all"])
    return out


def standings_rows(d: dict) -> list[dict]:
    rows, base = [], 0
    for tbl in _tables(d):
        for x in sorted(tbl, key=lambda r: r.get("idx") or 0):
            gf, _, ga = str(x.get("scoresStr") or "0-0").partition("-")
            rows.append({"rank": base + int(x.get("idx") or 0), "squad": x.get("name"), "played": x.get("played"),
                         "won": x.get("wins"), "drawn": x.get("draws"), "lost": x.get("losses"),
                         "gf": int(gf or 0), "ga": int(ga or 0), "gd": x.get("goalConDiff"), "points": x.get("pts"),
                         "_id": x.get("id")})
        base += len(tbl)
    return rows


def adopt_names(names: list[str]) -> dict[str, str]:
    """FotMob 표기 → 우리 표기. 다른 리그에서 이미 쓰던 표기(강등 클럽 — 'Wolverhampton Wanderers' → EPL 'Wolves')가 있으면
    그것을 쓴다 — 지난 시즌 기록·로고(teammeta)·이적 표가 같은 클럽으로 이어지게. 나머지는 FotMob 표기 그대로."""
    from leagues import FULL_LEAGUES  # noqa: PLC0415
    from squads import canonical_squad  # noqa: PLC0415
    known: dict[str, set[str]] = {}
    for lg in FULL_LEAGUES:
        for s in (SEASON, f"{SEASON_START - 1}_{SEASON_START}"):
            try:
                known.setdefault(lg, set()).update(pd.read_csv(data_path("standings", lg, s))["squad"].astype(str))
            except (OSError, KeyError, ValueError):
                pass
    out = {}
    for n in names:
        hit = next((c for lg, k in known.items() if (c := canonical_squad(n, lg)) in k), None)
        out[n] = hit or n
    return out


def _fm_fixtures(d: dict, rename: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
    """[(날짜, 홈, 원정)] — 우리 표기(rename 이 있으면)."""
    rename = rename or {}
    out = []
    for m in ((d.get("fixtures") or {}).get("allMatches") or []):
        day = str(((m.get("status") or {}).get("utcTime")) or "")[:10]
        h, a = (m.get("home") or {}).get("name"), (m.get("away") or {}).get("name")
        if day and h and a:
            out.append((day, rename.get(h, h), rename.get(a, a)))
    return out


def align_espn(events: list[dict], fixtures: list[tuple[str, str, str]], canon: list[str], league: str) -> dict[str, dict]:
    """ESPN 팀 id → {'squad', 'name'} — 이름 유사도로 시작해 같은 날 같은 상대 경기로 확인·보정(다수결)."""
    from squads import to_ours  # noqa: PLC0415
    names: dict[str, str] = {}
    games = []
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        side = {}
        for c in comp.get("competitors") or []:
            t = c.get("team") or {}
            if t.get("id"):
                names[str(t["id"])] = t.get("displayName") or t.get("name") or ""
                side[c.get("homeAway")] = str(t["id"])
        if "home" in side and "away" in side:
            games.append((str(e.get("date") or "")[:10], side["home"], side["away"]))
    guess = {i: to_ours(n, league, canon) for i, n in names.items()}
    by_day: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for day, h, a in fixtures:
        for k in (-1, 0, 1):                       # 시차로 하루 어긋남 허용
            dd = (dt.date.fromisoformat(day) + dt.timedelta(days=k)).isoformat()
            by_day[dd].append((h, a))
    for _ in range(3):                             # 확정된 팀이 늘면 다시
        votes: dict[str, Counter] = defaultdict(Counter)
        for day, h, a in games:
            for fh, fa in by_day.get(day, []):
                if guess.get(h) == fh:
                    votes[a][fa] += 1
                if guess.get(a) == fa:
                    votes[h][fh] += 1
        for i, c in votes.items():
            top, n = c.most_common(1)[0]
            if n >= 2 and (guess.get(i) != top) and (guess.get(i) is None or c[guess.get(i)] < n):
                guess[i] = top
    taken = Counter(v for v in guess.values() if v)
    return {i: {"squad": v, "name": names[i]} for i, v in guess.items() if v and taken[v] == 1}


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def teams_path(league: str, season: str | None = None) -> Path:
    return data_path("lite_teams", league, season, ext="json")


@lru_cache(maxsize=None)
def team_map(league: str) -> dict:
    """{'teams': {우리 표기: {fotmob_id, color, logo, tm_vid, tm_slug, tm_name}}, 'espn': {ESPN id: 우리 표기}, 'espn_names': {...}}."""
    return _load(teams_path(league))


@lru_cache(maxsize=None)
def all_teams() -> dict[str, dict]:
    """{우리 표기: 팀 정보} — 전 라이트 리그(teammeta 의 로고·색·verein 폴백)."""
    out: dict[str, dict] = {}
    for lg in LITE_LEAGUES:
        for sq, info in (team_map(lg).get("teams") or {}).items():
            out.setdefault(sq, {**info, "league": lg})
    return out


@lru_cache(maxsize=None)
def all_aliases() -> dict[str, str]:
    """{원천 표기(FotMob·ESPN·TM): 우리 표기} — 전 라이트 리그."""
    out: dict[str, str] = {}
    for lg in LITE_LEAGUES:
        out.update(team_map(lg).get("aliases") or {})
    return out


def espn_squad(team: dict | None, league: str) -> str | None:
    """ESPN team dict → 우리 표기(라이트 리그). 대조표에 없는 팀(컵·유럽 상대)은 None."""
    m = team_map(league)
    tid = str((team or {}).get("id") or "")
    if tid and tid in (m.get("espn") or {}):
        return m["espn"][tid]
    name = (team or {}).get("displayName") or (team or {}).get("name") or ""
    return (m.get("espn_names") or {}).get(name)


def espn_event_for(league: str, date: str, home: str, away: str) -> str | None:
    """라이트 리그 경기(일정은 FotMob 경기 id) → 같은 경기의 ESPN 경기 id — 같은 날(±1일) 두 팀의 ESPN 팀 id 가 모두 맞는 것.
    경기 리뷰가 ESPN 경기 상세를 쓰기 때문(2026-10-22 홈 결과 띠에서 덴마크 경기 리뷰가 502). ESPN 이 없는 리그(스위스)는 None."""
    from espn_common import scoreboard_events  # noqa: PLC0415
    code = LEAGUES[league].espn if league in LEAGUES else ""
    if not code or not date:
        return None
    ids: dict[str, set[str]] = {}
    for eid, sq in (team_map(league).get("espn") or {}).items():
        ids.setdefault(sq, set()).add(str(eid))
    if not ids.get(home) or not ids.get(away):
        return None
    d = dt.date.fromisoformat(date[:10])
    events = scoreboard_events(code, (d - dt.timedelta(days=1)).isoformat(), (d + dt.timedelta(days=1)).isoformat()) or []
    for e in events:
        teams = {str((c.get("team") or {}).get("id")) for c in ((e.get("competitions") or [{}])[0].get("competitors") or [])}
        if ids[home] & teams and ids[away] & teams:
            return str(e.get("id"))
    return None


def remember_tm(league: str, squad: str, slug: str, vid: int, tm_name: str) -> None:
    """Transfermarkt 클럽(verein id)을 우리 표기에 적어 둔다 — 다음 수집부터 season_clubs 가 이 표기로 돌려준다."""
    p = teams_path(league)
    m = _load(p)
    if not m.get("teams") or squad not in m["teams"]:
        return
    m["teams"][squad].update({"tm_vid": int(vid), "tm_slug": slug, "tm_name": tm_name})
    if tm_name != squad:
        m.setdefault("aliases", {})[tm_name] = squad
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    team_map.cache_clear()
    all_teams.cache_clear()


def tm_squad(league: str, tm_name: str, vid: int, players: list[str]) -> str | None:
    """TM 클럽 → 우리 표기: 적어 둔 verein id → 선수 명단 겹침(FotMob 1군 명단, 3명 이상) → 이름 유사도."""
    from player_registry import norm  # noqa: PLC0415
    from squads import to_ours  # noqa: PLC0415
    teams = team_map(league).get("teams") or {}
    for sq, info in teams.items():
        if info.get("tm_vid") and int(info["tm_vid"]) == int(vid):
            return sq
    try:
        fs = pd.read_csv(data_path("fotmob_squads", league), usecols=["squad", "player"])
    except (OSError, ValueError):
        fs = None
    if fs is not None and players:
        mine = {norm(p) for p in players}
        last = {n.split()[-1] for n in mine if n}
        best, score = None, 0.0
        for sq, g in fs.groupby("squad"):
            theirs = {norm(p) for p in g["player"]}
            s = len(mine & theirs) + 0.5 * len(last & {n.split()[-1] for n in theirs if n})
            if s > score:
                best, score = str(sq), s
        if best and score >= 3:
            return best
    return to_ours(tm_name, league, list(teams)) if teams else None


def _code(league: str, tour: dict, known_cups: dict[int, str]) -> tuple[str, str] | None:
    """FotMob 대회 → (comp_code, 화면 이름). 친선은 None."""
    lid = int(tour.get("leagueId") or 0)
    name = str(tour.get("name") or "")
    if "friendl" in name.lower():
        return None
    if lid == LEAGUES[league].fotmob_id:
        return LEAGUES[league].espn, "리그"
    if lid in EURO:
        return EURO[lid]
    if lid in known_cups:
        return known_cups[lid], name
    return f"fm.{lid}", name


def schedule_rows(squad: str, payload: dict, league: str, ours_by_id: dict[str, str]) -> list[dict]:
    """팀 응답의 전 대회 일정 → schedule_full 행(이번 시즌·친선 제외)."""
    from fetch_fotmob_matches import CUPS  # noqa: PLC0415
    lo, hi = f"{SEASON_START}-07-01", f"{SEASON_START + 1}-06-30"
    rows = []
    fx = (((payload.get("fixtures") or {}).get("allFixtures") or {}).get("fixtures")) or []
    for m in fx:
        st = m.get("status") or {}
        utc = str(st.get("utcTime") or "")
        day = utc[:10]
        if not (lo <= day <= hi) or st.get("cancelled"):
            continue
        cc = _code(league, m.get("tournament") or {}, CUPS)
        if not cc:
            continue
        home, away = m.get("home") or {}, m.get("away") or {}
        mine_home = ours_by_id.get(str(home.get("id"))) == squad
        me, opp = (home, away) if mine_home else (away, home)
        done = bool(st.get("finished"))
        gf, ga = (me.get("score"), opp.get("score")) if done else (None, None)
        result = ("W" if gf > ga else "L" if gf < ga else "D") if done and gf is not None and ga is not None else ""
        rows.append({"squad": squad, "comp": cc[1], "comp_code": cc[0], "date": day,
                     "kickoff": utc[:16] + "Z" if len(utc) >= 16 else utc,
                     "home_away": "H" if mine_home else "A",
                     "opponent": ours_by_id.get(str(opp.get("id"))) or opp.get("name") or "",
                     "gf": gf, "ga": ga, "score": f"{gf}-{ga}" if done and gf is not None else "", "result": result,
                     "status": "completed" if done else "scheduled", "event_id": str(m.get("id") or ""),
                     "opponent_logo": LOGO.format(opp.get("id")) if opp.get("id") else ""})
    return rows


def coach_of(payload: dict) -> dict | None:
    for g in (((payload.get("squad") or {}).get("squad")) or []):
        if str(g.get("title")) == "coach" and g.get("members"):
            m = g["members"][0]
            return {"name": m.get("name"), "fotmob_id": m.get("id"), "nationality": m.get("cname") or "",
                    "age": m.get("age"), "photo_url": PHOTO.format(m.get("id")) if m.get("id") else ""}
    return None


def write_managers(league: str, coaches: dict[str, dict]) -> int:
    """manager_profiles_{리그}.json — 이름·국적·사진(나머지 칸은 비움; 화면은 있는 칸만 그린다). 감독이 바뀌면 이전 이름을 남긴다."""
    p = data_path("manager_profiles", league, ext="json")
    old = _load(p)
    today = dt.date.today().isoformat()
    out = {}
    changed = 0
    for sq, c in coaches.items():
        prev = old.get(sq) or {}
        rec = {"appointed": "", "style": "", "formation": "", "focus": "", "bio_ko": "", "wiki_title": c["name"], **prev,
               "name": c["name"], "nationality": c["nationality"] or prev.get("nationality", ""),
               "photo_url": c["photo_url"] or prev.get("photo_url", ""), "fotmob_id": c["fotmob_id"], "source": "fotmob"}
        if prev.get("name") and prev["name"] != c["name"]:
            rec.update({"previous_name": prev["name"], "change_detected_at": today, "bio_ko": "", "appointed": ""})
            changed += 1
        out[sq] = rec
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return changed


def prev_standings(league: str, get) -> int:
    """지난 시즌 최종 순위표(한 번만) — 팀 화면 '지난 시즌 대비'·시즌 실적이 라이트 리그에서 비었다(2026-10-23)."""
    prev = f"{SEASON_START - 1}_{SEASON_START}"
    out = data_path("standings", league, prev)
    if out.exists():
        return 0
    d = get(f"https://www.fotmob.com/api/data/leagues?id={LEAGUES[league].fotmob_id}&season={SEASON_START - 1}/{SEASON_START}") or {}
    rows = standings_rows(d)
    if len(rows) < LEAGUES[league].teams - 4:
        return 0
    rename = adopt_names([r["squad"] for r in rows])
    st = pd.DataFrame([{**r, "squad": rename[r["squad"]]} for r in rows])
    st[STAND_COLS].to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
    return len(st)


def build(league: str, get=None) -> dict:
    import fotmob_squads as fsq  # noqa: PLC0415
    from espn_common import scoreboard_events, season_bounds  # noqa: PLC0415
    if get is None:
        from fetch_fotmob_ratings import _get as get  # noqa: PLC0415
    cfg = LEAGUES[league]
    d = get(f"https://www.fotmob.com/api/data/leagues?id={cfg.fotmob_id}") or {}
    rows = standings_rows(d)
    if len(rows) < cfg.teams - 2:
        raise RuntimeError(f"{league}: FotMob 리그 표 {len(rows)}팀 — 건너뜀")
    rename = adopt_names([r["squad"] for r in rows])
    for r in rows:
        r["squad"] = rename[r["squad"]]
    st = pd.DataFrame(rows)
    st[STAND_COLS].to_csv(data_path("standings", league), index=False, encoding="utf-8", lineterminator="\n")
    canon = list(st["squad"].astype(str))
    ids = {r["squad"]: int(r["_id"]) for r in rows}

    # 팀 응답(일정·명단·감독) — 팀마다 한 번
    payloads: dict[str, dict] = {}
    for sq, tid in ids.items():
        payloads[sq] = get(f"https://www.fotmob.com/api/data/teams?id={tid}") or {}
        time.sleep(0.4)
    cached = {f"https://www.fotmob.com/api/data/teams?id={ids[sq]}": p for sq, p in payloads.items()}
    squads = fsq.collect(league, ids, lambda u: cached.get(u) or get(u), sleep=0)
    if not squads.empty:
        squads.to_csv(data_path("fotmob_squads", league), index=False, encoding="utf-8", lineterminator="\n")

    # 일정 — 상대가 우리 클럽(어느 리그든)이면 우리 표기로
    try:
        from news_wires import fotmob_team_ids  # noqa: PLC0415
        ours_by_id = {str(v): k for k, v in fotmob_team_ids().items()}
    except Exception:  # noqa: BLE001
        ours_by_id = {}
    ours_by_id.update({str(v): k for k, v in ids.items()})
    sched = [r for sq, p in payloads.items() for r in schedule_rows(sq, p, league, ours_by_id)]
    if sched:
        sdf = pd.DataFrame(sched, columns=SCHED_COLS).drop_duplicates(["squad", "event_id"]).sort_values(["squad", "date"])
        sdf.to_csv(data_path("schedule_full", league), index=False, encoding="utf-8", lineterminator="\n")
    coaches = {sq: c for sq, p in payloads.items() if (c := coach_of(p))}
    changed = write_managers(league, coaches) if coaches else 0

    # 팀 대조표
    old = _load(teams_path(league))
    colors = {}
    for x in ((d.get("stats") or {}).get("players") or [])[:1]:            # 통계 파일 하나에 팀 색이 실려 있다
        j = get(x.get("fetchAllUrl")) or {}
        for r in ((j.get("TopLists") or [{}])[0].get("StatList") or []):
            colors.setdefault(str(r.get("TeamId")), r.get("TeamColor"))
    teams = {}
    for sq, tid in ids.items():
        prev = (old.get("teams") or {}).get(sq) or {}
        teams[sq] = {**prev, "fotmob_id": tid, "logo": LOGO.format(tid), "color": colors.get(str(tid)) or prev.get("color")}
    espn = {}
    if cfg.espn:
        events = scoreboard_events(cfg.espn, *season_bounds(SEASON_START)) or []
        espn = align_espn(events, _fm_fixtures(d, rename), canon, league)
    # 원천 표기 → 우리 표기(squads.canonical_squad 가 읽는다 — FotMob·ESPN·TM 수집기의 to_ours 가 같은 답을 내게)
    aliases = {k: v for k, v in (old.get("aliases") or {}).items() if v in teams}
    aliases.update({fm: ours for fm, ours in rename.items() if fm != ours})
    aliases.update({v["name"]: v["squad"] for v in espn.values() if v["name"] != v["squad"]})
    out = {"at": dt.date.today().isoformat(), "league": league, "season": SEASON, "teams": teams,
           "espn": {i: v["squad"] for i, v in espn.items()},
           "espn_names": {v["name"]: v["squad"] for v in espn.values()}, "aliases": aliases}
    teams_path(league).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    team_map.cache_clear()
    all_teams.cache_clear()
    all_aliases.cache_clear()
    n_prev = prev_standings(league, get)
    if n_prev:
        print(f"[{league}] 지난 시즌 순위표 {n_prev}팀")
    print(f"[{league}] 순위표 {len(st)}팀 · 일정 {len(sched)}행 · 명단 {len(squads)}명 · 감독 {len(coaches)}명"
          f"(교체 {changed}) · ESPN 대조 {len(out['espn'])}팀")
    return out


def _same_person(a: str, b: str) -> bool:
    from player_registry import norm  # noqa: PLC0415
    na, nb = norm(a).split(), norm(b).split()
    return bool(na and nb) and (na == nb or na[-1] == nb[-1])


def _football_bio(bio: str) -> bool:
    """축구 감독 소개인가 — 동음이의 문서('다음을 지칭할 수 있다', 'may refer to')·축구 밖 문서는 아니다(2026-10-23 버밍엄 크리스 데이비스)."""
    if not bio or any(w in bio for w in ("지칭할 수 있다", "may refer to", "동음이의", "다음과 같은 뜻")):
        return False
    return any(w in bio for w in ("축구", "감독", "football", "coach", "manager"))


def enrich_managers(league: str, limit: int = 40) -> int:
    """감독 소개·전술(위키) — FotMob 명단의 감독 이름은 그대로 두고, 클럽 위키 인포박스 감독이 같은 사람이면 그 문서로,
    아니면 이름 문서로 enrich_one(한글 위키 → 영어 위키 번역, 전술 섹션). 축구 감독 문서가 아니면(동명이인) 버린다.
    2026-10-23 사용자: 라이트 리그 내용이 빈약 — 팀 개요·분석의 감독 소개·전술이 비었다. 소개가 없는 감독만(하루 상한)."""
    from enrich_manager_profiles import enrich_one  # noqa: PLC0415
    import fetch_belgian_managers as fbm  # noqa: PLC0415
    p = data_path("manager_profiles", league, ext="json")
    prof = _load(p)
    todo = [sq for sq, r in prof.items() if r.get("name") and not r.get("bio_ko")][:limit]
    if not todo:
        return 0
    titles = fbm.club_titles(todo, LEAGUES[league].country)
    texts = fbm._wikitext(list(titles.values())) if titles else {}
    done = 0
    for sq in todo:
        r = prof[sq]
        mg = fbm.infobox_manager(texts.get(titles.get(sq, ""), ""))
        # 문서 후보: 클럽 인포박스의 감독 문서(같은 사람일 때) → '이름 (football manager)' → '이름 (footballer)' → 이름
        cands = ([mg[1]] if mg and _same_person(mg[0], r["name"]) else []) + [
            f"{r['name']} (football manager)", f"{r['name']} (footballer)", r["name"]]
        e, title = {}, ""
        for title in dict.fromkeys(cands):
            try:
                e = enrich_one({**r, "wiki_title": title})
            except Exception as ex:  # noqa: BLE001
                print(f"  [감독 보강 실패] {sq}: {type(ex).__name__}")
                e = {}
            if _football_bio(str(e.get("bio_ko") or "")):
                break
            e = {}
        bio = str(e.get("bio_ko") or "")
        if not bio:
            continue                                   # 동명이인·동음이의·축구 밖 문서
        r.update({k: e[k] for k in ("bio_ko", "bio_source", "tactics_ko", "tactics_source") if e.get(k)})
        if e.get("formation") and not r.get("formation"):
            r["formation"] = e["formation"]
        r["wiki_title"] = title
        done += 1
    p.write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{league}] 감독 소개 보강 {done}/{len(todo)}")
    return done


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--managers", action="store_true", help="감독 소개·전술 보강(위키)만")
    a = ap.parse_args(argv)
    bad = 0
    for lg in [a.league] if a.league else LITE_LEAGUES:
        try:
            if a.managers:
                enrich_managers(lg)
            else:
                build(lg)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패가 다른 리그를 멈추지 않게
            print(f"[{lg}] 실패 {type(e).__name__}: {e}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
