"""
FotMob 경기별 선수 기록 → data/fotmob_match_ratings_{리그}_{시즌}.csv — '최근 폼'·전 대회 세부 지표·전 대회 평점용.

2026-10-19 사용자: "노팅엄전 사카가 엄청 못했는데 '폼 절정' — 시즌 전체 폼과 최근 3·5경기 폼을 나누자".
시즌 폼(_form)은 시즌 평균 평점이라 한두 경기 부진이 안 보인다. 경기별 평점은 FotMob 공개 JSON
(/api/data/matchDetails)에서 받는다(Sofascore 경기별 평점은 로컬 수집 전용이라 클라우드에서 못 받음).
2026-10-21 사용자: "리그 기준으로만 계산하나요? 챔스·컵도 포함해야 데이터가 늘고 신빙성이 늘지 않을까요".
같은 matchDetails 에 경기별 세부 기록(태클·인터셉트·경합·패스·xG …)이 있어 요청을 늘리지 않고 함께 저장한다
(DETAIL — src/allcomp_stats.py 가 대회별 가중으로 합친다).
- 대회: 우리 8개 리그 + UEFA 3개 대회 + 국내 컵. 리그 일정에서 FotMob 팀 id → (리그, 우리 팀 표기)를 먼저 만들고,
  유럽·컵 경기는 그 팀 id 가 있는 쪽만 남긴다(상대 팀이 우리 리그 밖이면 그 팀 선수 행은 버림).
- 이미 받은 경기(match_id)는 다시 받지 않는다 — 매일 새로 끝난 경기만(match_refresh).
  세부 기록 없이 받은 예전 경기(det 빈칸)는 남는 상한만큼 다시 받아 채운다(자동 백필).
- --season prev: 지난 시즌 유럽·컵 경기만(리그는 시즌 평점·FBref 표가 이미 있음) — 지난 시즌 전 대회 평점용. 끝난 시즌이라 한 번만.
- 행: match_id, date, comp_code, squad(우리 표기), opponent, home_away, fotmob_id, player, minutes, rating(FotMob 척도),
  goals, assists, det(세부 기록 있음=1), DETAIL 열들.
- 같은 matchDetails 의 슈팅맵에서 골 상황(오픈플레이·역습·코너·세트피스·프리킥·스로인·PK·자책골)도 함께
  data/fotmob_goals_{리그}_{시즌}.csv 로 — 팀 득점 구성(StatBunker 는 EPL·라리가·세리에A 만이라 나머지 5개 리그가 비었다,
  2026-10-22). 행: match_id, date, comp_code, squad(득점한 우리 팀), opponent, minute, player, situation, own_goal, xg.
  골 없는 경기는 situation=none 한 줄(받았다는 표시). 이미 받은 경기 중 골 파일에 없는 것은 --goals-max 만큼 다시 받아 채운다.
- 라이트 리그(챔피언십 …, 2026-10-22)는 같은 matchDetails 의 라인업·교체로 espn_lineups(_cups)·espn_subs(_cups) 표를 만든다
  (src/fotmob_lineups.py — ESPN 이 다루지 않거나 경기 id 가 FotMob 인 리그). 받은 경기 중 라인업이 없는 것은 같은 상한으로 백필.

사용: python src/fetch_fotmob_matches.py [--league EPL] [--max 400] [--season prev]
"""
from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from fetch_fotmob_ratings import FOTMOB_ID, _get
from leagues import LEAGUES, SEASON_START, data_path, fm_season as _fm_season, season_window
import team_names as tn  # noqa: F401 — 예전 호출부 호환
from squads import to_ours
import fotmob_lineups

# FotMob 대회 id → 우리 대회 코드(ESPN 표기 — schedule_full comp_code 와 같은 축)
CUPS = {42: "uefa.champions", 73: "uefa.europa", 10216: "uefa.europa.conf",
        # UEFA 예선(7~8월, 라이트 리그 팀이 많이 낀다) — 코드가 uefa. 로 시작해야 역할 축·OVR 표본이 유럽으로 센다
        10611: "uefa.champions_qual", 10613: "uefa.europa_qual", 10615: "uefa.europa.conf_qual",
        132: "eng.fa", 133: "eng.league_cup", 138: "esp.copa_del_rey", 141: "ita.coppa_italia",
        209: "ger.dfb_pokal", 134: "fra.coupe_de_france", 186: "por.taca.portugal", 235: "ned.cup",
        149: "bel.cup",
        # 라이트 리그 국내컵 — 없으면 lite_league 가 'fm.<id>' 로만 적고 여기선 받지 않았다(2026-11-03 점검)
        278: "aut.cup", 242: "den.cup", 164: "sui.cup", 151: "tur.cup"}
LEAGUE_CODE = {"EPL": "eng.1", "LaLiga": "esp.1", "SerieA": "ita.1", "Bundesliga": "ger.1", "Ligue1": "fra.1",
               "LigaPortugal": "por.1", "Eredivisie": "ned.1", "BelgianProLeague": "bel.1"}
LEAGUE_CODE.update({k: c.espn for k, c in LEAGUES.items() if c.espn and k not in LEAGUE_CODE})   # 라이트 리그
# 세부 기록 — 우리 열: (FotMob stat key, 'v' 값 | 't' 시도 수). 출전한 선수에게 키가 없으면 0(FotMob 은 0 인 항목을 빼기도 한다)
DETAIL = {
    "xg": ("expected_goals", "v"), "npxg": ("expected_goals_non_penalty", "v"), "xa": ("expected_assists", "v"),
    "shots": ("total_shots", "v"), "sot": ("ShotsOnTarget", "v"), "chances": ("chances_created", "v"),
    "bigc": ("big_chance_created_team_title", "v"), "f3": ("passes_into_final_third", "v"),
    "pass_acc": ("accurate_passes", "v"), "pass_tot": ("accurate_passes", "t"),
    "long_acc": ("long_balls_accurate", "v"), "long_tot": ("long_balls_accurate", "t"),
    "drib_won": ("dribbles_succeeded", "v"), "drib_tot": ("dribbles_succeeded", "t"),
    "cross_acc": ("accurate_crosses", "v"), "cross_tot": ("accurate_crosses", "t"),
    "tackles": ("matchstats.headers.tackles", "v"), "ints": ("interceptions", "v"), "recov": ("recoveries", "v"),
    "clear": ("clearances", "v"), "blocks": ("shot_blocks", "v"),
    "aer_won": ("aerials_won", "v"), "aer_tot": ("aerials_won", "t"),
    "grd_won": ("ground_duels_won", "v"), "grd_tot": ("ground_duels_won", "t"),
    "duel_won": ("duel_won", "v"), "duel_lost": ("duel_lost", "v"), "fouls": ("fouls", "v"),
    "touches": ("touches", "v"), "touch_box": ("touches_opp_box", "v"), "disp": ("dispossessed", "v"),
    "saves": ("saves", "v"), "conceded": ("goals_conceded", "v"), "xgot_faced": ("expected_goals_on_target_faced", "v"),
    "high_claim": ("keeper_high_claim", "v"), "sweeper": ("keeper_sweeper", "v"), "punches": ("punches", "v"),
}
COLS = ["match_id", "date", "comp_code", "squad", "opponent", "home_away", "fotmob_id", "player",
        "minutes", "rating", "goals", "assists", "det", *DETAIL]


def finished(fid: int, season: str | None = None, since: str = "") -> list[dict]:
    """끝난 경기. season = 'YYYY/YYYY'(지난 시즌) | None(현재)."""
    q = f"&season={season.replace('/', '%2F')}" if season else ""
    d = _get(f"https://www.fotmob.com/api/data/leagues?id={fid}{q}") or {}
    out = []
    for m in ((d.get("fixtures") or {}).get("allMatches") or []):
        st = m.get("status") or {}
        t = str(st.get("utcTime") or "")
        if st.get("finished") and not st.get("cancelled") and t[:10] >= since:
            out.append(m)
    return out


def _stats(block: dict) -> dict:
    """{FotMob key·제목: (값, 시도 수)} — 여러 묶음(Top stats·Attack·Defense…)에 같은 항목이 겹쳐도 하나로."""
    out = {}
    for sec in block.get("stats") or []:
        for title, s in (sec.get("stats") or {}).items():
            st = s.get("stat") or {}
            v = (st.get("value"), st.get("total"))
            out.setdefault(title, v)
            if s.get("key"):
                out.setdefault(s["key"], v)
    return out


GOAL_COLS = ["match_id", "date", "comp_code", "squad", "opponent", "minute", "player", "situation", "own_goal", "xg"]


def _details(match: dict) -> dict:
    return _get(f"https://www.fotmob.com/api/data/matchDetails?matchId={match['id']}") or {}


def goal_rows(j: dict, match: dict, comp: str, sides: dict) -> list[dict]:
    """슈팅맵의 골 → 득점한 우리 팀 기준 행. 자책골은 상대 팀 득점(situation=OwnGoal). 우리 팀이 골이 없으면 none 한 줄."""
    shots = (((j.get("content") or {}).get("shotmap")) or {}).get("shots") or []
    home, away = match.get("home") or {}, match.get("away") or {}
    hid, aid = str(home.get("id")), str(away.get("id"))
    date = str((match.get("status") or {}).get("utcTime") or "")[:10]
    name_of = {hid: home.get("name"), aid: away.get("name")}
    rows = []
    for s in shots:
        if s.get("eventType") != "Goal":
            continue
        tid = str(s.get("teamId") or "")
        og = bool(s.get("isOwnGoal"))
        for_id = (aid if tid == hid else hid) if og else tid
        if for_id not in sides:
            continue
        opp_id = aid if for_id == hid else hid
        rows.append({"league": sides[for_id][0], "match_id": str(match["id"]), "date": date, "comp_code": comp,
                     "squad": sides[for_id][1], "opponent": sides.get(opp_id, (None, name_of.get(opp_id) or ""))[1],
                     "minute": s.get("min"), "player": s.get("playerName") or "",
                     "situation": "OwnGoal" if og else str(s.get("situation") or ""), "own_goal": int(og),
                     "xg": s.get("expectedGoals")})
    if not shots:
        return []                                        # 슈팅맵 없는 경기(하부 컵 등) — 받았다는 표시도 안 남겨 다음에 다시
    for tid in (hid, aid):
        if tid in sides and not any(r["squad"] == sides[tid][1] for r in rows):
            opp_id = aid if tid == hid else hid
            rows.append({"league": sides[tid][0], "match_id": str(match["id"]), "date": date, "comp_code": comp,
                         "squad": sides[tid][1], "opponent": sides.get(opp_id, (None, name_of.get(opp_id) or ""))[1],
                         "minute": None, "player": "", "situation": "none", "own_goal": 0, "xg": None})
    return rows


def _sub_times(j: dict) -> tuple[dict, dict]:
    """교체 이벤트 → ({들어온 선수 이름·id: 분}, {나간 선수 이름·id: 분})."""
    ev = ((((j.get("content") or {}).get("matchFacts") or {}).get("events") or {}).get("events")) or []
    sub_in: dict = {}
    sub_out: dict = {}
    for e in ev:
        if e.get("type") != "Substitution" or not isinstance(e.get("time"), (int, float)):
            continue
        sw = e.get("swap") or []
        for k, d in ((0, sub_in), (1, sub_out)):
            if len(sw) > k and isinstance(sw[k], dict):
                for key in (sw[k].get("name"), sw[k].get("id")):
                    if key is not None:
                        d[str(key)] = float(e["time"])
    return sub_in, sub_out


def lineup_player_rows(j: dict, match: dict, comp: str, sides: dict) -> list[dict]:
    """playerStats 가 없는 경기(하부 컵 — FotMob 'simple' 라인업: 타사 드 포르투갈·벨기에컵 초반, 스위스·튀르키예컵)
    → 라인업·교체로 출전 분만(평점·세부 기록 없음, det=0). 예전엔 행이 안 생겨 그 경기를 매번 다시 받았고 컵 출전이
    어디에도 안 잡혔다(2026-11-03 점검). 분 = 선발 90(교체로 나가면 그때까지) · 교체 투입 90−투입 분."""
    lu = ((j.get("content") or {}).get("lineup")) or {}
    home, away = match.get("home") or {}, match.get("away") or {}
    date = str((match.get("status") or {}).get("utcTime") or "")[:10]
    name_of = {str(home.get("id")): home.get("name"), str(away.get("id")): away.get("name")}
    sub_in, sub_out = _sub_times(j)
    rows = []
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team = lu.get(key) or {}
        tid = str(team.get("id") or (match.get(side) or {}).get("id") or "")
        if tid not in sides:
            continue
        lg, squad = sides[tid]
        opp_id = str(away.get("id")) if side == "home" else str(home.get("id"))
        opp = sides.get(opp_id, (None, name_of.get(opp_id) or ""))[1]
        for starter, plist in ((True, team.get("starters") or []), (False, team.get("subs") or [])):
            for p in plist:
                keys = [str(x) for x in (p.get("name"), p.get("id")) if x is not None]
                t_out = next((sub_out[k] for k in keys if k in sub_out), None)
                t_in = next((sub_in[k] for k in keys if k in sub_in), None)
                if starter:
                    mn = t_out if t_out is not None else 90.0
                elif t_in is not None:
                    mn = max(0.0, (t_out if t_out is not None else 90.0) - t_in)
                else:
                    continue                           # 벤치(출전 없음)
                if mn <= 0:
                    continue
                row = {"league": lg, "match_id": str(match["id"]), "date": date, "comp_code": comp, "squad": squad,
                       "opponent": opp, "home_away": side, "fotmob_id": str(p.get("id") or ""), "player": p.get("name"),
                       "minutes": int(round(mn)), "rating": None, "goals": 0, "assists": 0, "det": 0}
                for col in DETAIL:
                    row[col] = None
                rows.append(row)
    return rows


def player_rows(match: dict, comp: str, sides: dict, j: dict | None = None) -> list[dict]:
    """sides: {fotmob 팀 id: (리그, 우리 팀 표기)} — 이 경기에서 우리 리그 팀만."""
    j = _details(match) if j is None else j
    ps = ((j.get("content") or {}).get("playerStats")) or {}
    if not ps:
        return lineup_player_rows(j, match, comp, sides)
    home, away = match.get("home") or {}, match.get("away") or {}
    date = str((match.get("status") or {}).get("utcTime") or "")[:10]
    name_of = {str(home.get("id")): home.get("name"), str(away.get("id")): away.get("name")}
    rows = []
    for pid, p in ps.items():
        tid = str(p.get("teamId") or "")
        if tid not in sides:
            continue
        lg, squad = sides[tid]
        opp_id = str(away.get("id")) if tid == str(home.get("id")) else str(home.get("id"))
        opp = sides.get(opp_id, (None, name_of.get(opp_id) or ""))[1]
        s = _stats(p)
        mn = (s.get("Minutes played") or (None,))[0]
        if not mn:
            continue                                   # 벤치(출전 없음)
        row = {"league": lg, "match_id": str(match["id"]), "date": date, "comp_code": comp, "squad": squad,
               "opponent": opp, "home_away": "home" if tid == str(home.get("id")) else "away",
               "fotmob_id": str(p.get("id") or pid), "player": p.get("name"), "minutes": mn,
               "rating": (s.get("FotMob rating") or (None,))[0], "goals": (s.get("Goals") or (0,))[0] or 0,
               "assists": (s.get("Assists") or (0,))[0] or 0, "det": 1}
        for col, (key, part) in DETAIL.items():
            v, t = s.get(key, (None, None))
            x = v if part == "v" else t
            row[col] = x if x is not None else 0
        rows.append(row)
    return rows


def _sides(leagues: list[str], season: str, y: int, prev: bool) -> tuple[dict, list]:
    """리그 일정 → ({FotMob 팀 id: (리그, 우리 팀 표기)}, [(경기, 대회 코드)]). FotMob 시즌 이름·시작일은 리그마다
    (달력 연도 리그 MLS 2026 = '2026'·1월부터, leagues.fm_season·season_window)."""
    sides: dict[str, tuple[str, str]] = {}
    jobs: list[tuple[dict, str]] = []
    for lg in leagues:
        try:
            ours = list(pd.read_csv(data_path("standings", lg, season))["squad"].astype(str))
        except (FileNotFoundError, KeyError):
            ours = []
        for m in finished(FOTMOB_ID[lg], _fm_season(lg, y) if prev else None, "" if prev else season_window(lg, y)[0]):
            for side in ("home", "away"):
                t = m.get(side) or {}
                if str(t.get("id")) not in sides:
                    sides[str(t.get("id"))] = (lg, to_ours(t.get("name"), lg, ours) or str(t.get("name")))
            jobs.append((m, playoff_code(LEAGUE_CODE[lg], m)))
        time.sleep(0.5)
    return sides, jobs


_KO_ROUND = ("round of", "final", "semi", "quarter", "play")


def playoff_code(code: str, m: dict) -> str:
    """리그 일정 속 토너먼트 경기(MLS 플레이오프 'Round of 16'·결승, 챔피언십 승격 PO) → 'usa.1.playoffs' — 리그 경기로 세면
    시즌 평점·잠정 순위에 섞인다(2026-11-09). 숫자 라운드(정규·스플릿 라운드)는 그대로."""
    rn = str(m.get("roundName") or "").lower()
    return f"{code}.playoffs" if rn and not rn.isdigit() and any(w in rn for w in _KO_ROUND) else code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--max", type=int, default=600, help="한 번에 새로 받을 경기 수 상한(첫 실행 백필 분할용)")
    ap.add_argument("--season", choices=["cur", "prev"], default="cur")
    ap.add_argument("--goals-max", type=int, default=250, help="골 상황 백필 — 받은 경기 중 골 파일에 없는 것, 한 번에 이만큼")
    a = ap.parse_args()
    leagues = [a.league] if a.league else [lg for lg in LEAGUES if lg in FOTMOB_ID]
    prev = a.season == "prev"
    y = SEASON_START - 1 if prev else SEASON_START
    season = f"{y}_{y + 1}"
    fm_season = f"{y}/{y + 1}" if prev else None
    since = "" if prev else f"{SEASON_START}-07-01"

    # 1) 리그 일정 → FotMob 팀 id ↔ 우리 팀 표기(지난 시즌이면 지난 시즌 순위표 표기)
    sides, jobs = _sides(leagues, season, y, prev)
    if prev:
        jobs = []                                       # 지난 시즌 리그 경기는 시즌 평점·FBref 표로 충분
    # 2) 유럽·컵 — 우리 팀이 낀 경기만
    for fid, code in CUPS.items():
        for m in finished(fid, fm_season, since):
            if str((m.get("home") or {}).get("id")) in sides or str((m.get("away") or {}).get("id")) in sides:
                jobs.append((m, code))
        time.sleep(0.5)

    # 3) 이미 받은 경기는 건너뛰고 새 경기 먼저, 남는 상한으로 세부 기록 없는 예전 경기(det 빈칸) 다시 받기
    have: dict[str, pd.DataFrame] = {}
    seen: set[str] = set()
    stale: set[str] = set()
    for lg in leagues:
        p = data_path("fotmob_match_ratings", lg, season)
        if p.exists():
            df = pd.read_csv(p, dtype={"match_id": str, "fotmob_id": str})
            have[lg] = df
            seen |= set(df["match_id"].astype(str))
            det = pd.to_numeric(df["det"], errors="coerce") if "det" in df.columns else pd.Series(float("nan"), index=df.index)
            stale |= set(df.loc[det.isna(), "match_id"].astype(str))
    when = lambda x: str((x[0].get("status") or {}).get("utcTime") or "")   # noqa: E731
    fresh = sorted([(m, c) for m, c in jobs if str(m["id"]) not in seen], key=when, reverse=True)   # 최근 경기부터
    refill = sorted([(m, c) for m, c in jobs if str(m["id"]) in stale], key=when, reverse=True)
    todo = (fresh + refill)[: a.max]
    print(f"[{season}] 경기 {len(jobs)}개 중 새 경기 {len(fresh)}개 · 세부 기록 백필 대기 {len(refill)}개 (상한 {a.max})")
    goals_have: dict[str, pd.DataFrame] = {}
    goals_seen: set[str] = set()
    for lg in leagues:
        gp = data_path("fotmob_goals", lg, season)
        if gp.exists():
            goals_have[lg] = pd.read_csv(gp, dtype={"match_id": str})
            goals_seen |= set(goals_have[lg]["match_id"].astype(str))
    todo_ids = {str(m["id"]) for m, _ in todo}
    goal_only = sorted([(m, c) for m, c in jobs if str(m["id"]) in seen and str(m["id"]) not in goals_seen
                        and str(m["id"]) not in todo_ids], key=when, reverse=True)[: a.goals_max]
    # 라이트 리그 라인업·교체 — 받은 경기 중 라인업 표에 없는 것도 다시 받아 채운다
    lite = {lg for lg in leagues if LEAGUES[lg].lite} if not prev else set()
    lite_sides = {tid: v for tid, v in sides.items() if v[0] in lite}
    lu_have: dict[tuple[str, str], pd.DataFrame] = {}
    lu_seen: set[str] = set()
    ms_seen: set[str] = set()
    for lg in ([] if prev else leagues):
        # 풀 리그는 컵 라인업만(ESPN 명단이 비는 하부 컵 — 타사 드 포르투갈 14경기 중 1경기, 벨기에컵 0, 2026-11-03 점검)
        for stem in (("espn_lineups", "espn_lineups_cups", "espn_subs", "espn_subs_cups", "match_stats") if lg in lite
                     else ("espn_lineups_cups", "espn_subs_cups")):
            p = data_path(stem, lg, season)
            if p.exists():
                lu_have[(lg, stem)] = pd.read_csv(p, dtype={"event_id": str})
                if "lineups" in stem:
                    lu_seen |= set(lu_have[(lg, stem)]["event_id"].astype(str))
                if stem == "match_stats":
                    ms_seen |= set(lu_have[(lg, stem)]["event_id"].astype(str))
    is_lite = lambda m: any(str((m.get(s) or {}).get("id")) in lite_sides for s in ("home", "away"))   # noqa: E731
    goal_ids = {str(m["id"]) for m, _ in goal_only}
    lineup_only = sorted([(m, c) for m, c in jobs if is_lite(m) and str(m["id"]) in seen
                          and (str(m["id"]) not in lu_seen or str(m["id"]) not in ms_seen)
                          and str(m["id"]) not in todo_ids and str(m["id"]) not in goal_ids], key=when, reverse=True)[: a.goals_max]
    new_lu: list[dict] = []
    new_sub: list[dict] = []
    new_ms: list[dict] = []

    sched_cache: dict[str, dict] = {}

    def _espn_event(lg: str, squad: str, day: str) -> str | None:
        """풀 리그 컵 경기의 FotMob 경기 → 일정(schedule_full, ESPN id) event_id — 같은 팀·같은 날(±1일)."""
        if lg not in sched_cache:
            try:
                sc = pd.read_csv(data_path("schedule_full", lg, season), dtype={"event_id": str})
                sc = sc[~sc["comp_code"].astype(str).isin(set(LEAGUE_CODE.values()))]
                sched_cache[lg] = {(str(s), str(d)[:10]): str(e).replace(".0", "") for s, d, e in
                                   zip(sc["squad"], sc["date"], sc["event_id"]) if pd.notna(e)}
            except (FileNotFoundError, KeyError, ValueError):
                sched_cache[lg] = {}
        idx = sched_cache[lg]
        try:
            d0 = pd.Timestamp(day)
        except (TypeError, ValueError):
            return idx.get((squad, day))
        for off in (0, 1, -1):
            hit = idx.get((squad, (d0 + pd.Timedelta(days=off)).strftime("%Y-%m-%d")))
            if hit:
                return hit
        return None

    def _lineups(j: dict, m: dict, code: str, full_cup: bool = False) -> None:
        """라이트 리그 = 모든 경기. 풀 리그 = full_cup(컵·유럽인데 playerStats 가 없는 경기)만 — ESPN 명단이 비는 하부 컵."""
        use = dict(lite_sides)
        if full_cup and code not in set(LEAGUE_CODE.values()):
            for s in ("home", "away"):
                tid = str((m.get(s) or {}).get("id"))
                if tid in sides and sides[tid][0] not in lite:
                    use[tid] = sides[tid]
        if not use or not any(str((m.get(s) or {}).get("id")) in use for s in ("home", "away")):
            return
        day = str((m.get("status") or {}).get("utcTime") or "")[:10]
        for r in fotmob_lineups.lineup_rows(j, m, use):
            lg = next(v[0] for v in use.values() if v[1] == r["squad"])
            if lg not in lite:
                r = {**r, "event_id": _espn_event(lg, r["squad"], day) or r["event_id"]}
            new_lu.append({**r, "_key": (lg, "espn_lineups" if code == LEAGUE_CODE.get(lg) else "espn_lineups_cups")})
        for r in fotmob_lineups.sub_rows(j, m, use):
            side = str((m.get(r["home_away"]) or {}).get("id"))
            lg, squad = use[side]
            if lg not in lite:
                r = {**r, "event_id": _espn_event(lg, squad, day) or r["event_id"]}
            new_sub.append({**r, "_key": (lg, "espn_subs" if code == LEAGUE_CODE.get(lg) else "espn_subs_cups")})
        if lite_sides and is_lite(m):
            for r in fotmob_lineups.team_stat_rows(j, m, lite_sides, code):   # 팀 경기 기록(분석 탭) — 라이트 리그만
                lg = next(v[0] for v in lite_sides.values() if v[1] == r["squad"])
                new_ms.append({**r, "_key": (lg, "match_stats")})
    print(f"    골 상황 백필 {len(goal_only)}경기(남은 {sum(1 for m, _ in jobs if str(m['id']) not in goals_seen)})")
    new: list[dict] = []
    new_goals: list[dict] = []
    bad = 0
    for i, (m, code) in enumerate(todo):
        try:
            j = _details(m)
            rows = player_rows(m, code, sides, j)
            new_goals.extend(goal_rows(j, m, code, sides))
            _lineups(j, m, code, full_cup=not ((j.get("content") or {}).get("playerStats")))
        except Exception as e:  # noqa: BLE001 — 한 경기 실패가 전체를 멈추지 않게
            print(f"    [실패] {m.get('id')}: {e}")
            rows, bad = [], bad + 1
        new.extend(rows)
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(todo)} …")
        time.sleep(0.35)
    for m, code in goal_only:
        try:
            j = _details(m)
            new_goals.extend(goal_rows(j, m, code, sides))
            _lineups(j, m, code)
        except Exception as e:  # noqa: BLE001
            print(f"    [골 실패] {m.get('id')}: {e}")
        time.sleep(0.35)
    if lineup_only:
        print(f"    라인업·팀 기록 백필 {len(lineup_only)}경기")
    for m, code in lineup_only:
        try:
            _lineups(_details(m), m, code)
        except Exception as e:  # noqa: BLE001
            print(f"    [라인업 실패] {m.get('id')}: {e}")
        time.sleep(0.35)
    for rows_, cols in ((new_lu, fotmob_lineups.LINEUP_COLS), (new_sub, fotmob_lineups.SUB_COLS),
                        (new_ms, fotmob_lineups.STAT_COLS)):
        if not rows_:
            continue
        nd_ = pd.DataFrame(rows_)
        for (lg, stem), g in nd_.groupby("_key"):
            old = lu_have.get((lg, stem))
            g = g.reindex(columns=cols)
            if old is not None:
                old = old[~old["event_id"].astype(str).isin(set(g["event_id"].astype(str)))]
                g = pd.concat([old.reindex(columns=cols), g], ignore_index=True)
            out = data_path(stem, lg, season)
            g.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
            print(f"  {lg:16} {stem} {g['event_id'].nunique()}경기 -> {out.name}")
    if new_goals:
        gd = pd.DataFrame(new_goals)
        for lg, g in gd.groupby("league"):
            out = data_path("fotmob_goals", lg, season)
            old = goals_have.get(lg)
            if old is not None:
                old = old[~old["match_id"].astype(str).isin(set(g["match_id"].astype(str)))]
                df = pd.concat([old, g[GOAL_COLS]], ignore_index=True)
            else:
                df = g[GOAL_COLS].copy()
            df = df.reindex(columns=GOAL_COLS).sort_values(["date", "match_id", "minute"], na_position="last")
            df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
            print(f"  {lg:16} 골 상황 +{len(g)}행 → {len(df)}행 ({df['match_id'].nunique()}경기) -> {out.name}")
    if not new:
        print("새 경기 없음")
        return 0
    nd = pd.DataFrame(new)
    for lg, g in nd.groupby("league"):
        out = data_path("fotmob_match_ratings", lg, season)
        if lg in have:
            old = have[lg]
            old = old[~old["match_id"].astype(str).isin(set(g["match_id"].astype(str)))]   # 다시 받은 경기는 통째로 바꾼다
            df = pd.concat([old, g[COLS]], ignore_index=True)
        else:
            df = g[COLS].copy()
        df = df.reindex(columns=COLS)
        df = df.drop_duplicates(subset=["match_id", "fotmob_id"], keep="last").sort_values(["date", "match_id"])
        df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        n_det = int(pd.to_numeric(df["det"], errors="coerce").notna().sum())
        print(f"  {lg:16} +{len(g)}행 → {len(df)}행 ({df['match_id'].nunique()}경기 · 세부 기록 {n_det}행) -> {out.name}")
    return 1 if bad > max(3, len(todo) // 10) else 0


if __name__ == "__main__":
    sys.exit(main())
