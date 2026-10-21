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

사용: python src/fetch_fotmob_matches.py [--league EPL] [--max 400] [--season prev]
"""
from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from fetch_fotmob_ratings import FOTMOB_ID, _get
from leagues import LEAGUES, SEASON_START, data_path
import team_names as tn

# FotMob 대회 id → 우리 대회 코드(ESPN 표기 — schedule_full comp_code 와 같은 축)
CUPS = {42: "uefa.champions", 73: "uefa.europa", 10216: "uefa.europa.conf",
        132: "eng.fa", 133: "eng.league_cup", 138: "esp.copa_del_rey", 141: "ita.coppa_italia",
        209: "ger.dfb_pokal", 134: "fra.coupe_de_france", 186: "por.taca.portugal", 235: "ned.cup",
        149: "bel.cup"}
LEAGUE_CODE = {"EPL": "eng.1", "LaLiga": "esp.1", "SerieA": "ita.1", "Bundesliga": "ger.1", "Ligue1": "fra.1",
               "LigaPortugal": "por.1", "Eredivisie": "ned.1", "BelgianProLeague": "bel.1"}
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


def player_rows(match: dict, comp: str, sides: dict) -> list[dict]:
    """sides: {fotmob 팀 id: (리그, 우리 팀 표기)} — 이 경기에서 우리 리그 팀만."""
    j = _get(f"https://www.fotmob.com/api/data/matchDetails?matchId={match['id']}") or {}
    ps = ((j.get("content") or {}).get("playerStats")) or {}
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


def _sides(leagues: list[str], season: str, fm_season: str | None, since: str) -> tuple[dict, list]:
    """리그 일정 → ({FotMob 팀 id: (리그, 우리 팀 표기)}, [(경기, 대회 코드)])."""
    sides: dict[str, tuple[str, str]] = {}
    jobs: list[tuple[dict, str]] = []
    for lg in leagues:
        try:
            ours = list(pd.read_csv(data_path("standings", lg, season))["squad"].astype(str))
        except (FileNotFoundError, KeyError):
            ours = []
        for m in finished(FOTMOB_ID[lg], fm_season, since):
            for side in ("home", "away"):
                t = m.get(side) or {}
                if str(t.get("id")) not in sides:
                    sides[str(t.get("id"))] = (lg, (tn.best(str(t.get("name")), ours) if ours else None) or str(t.get("name")))
            jobs.append((m, LEAGUE_CODE[lg]))
        time.sleep(0.5)
    return sides, jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--max", type=int, default=600, help="한 번에 새로 받을 경기 수 상한(첫 실행 백필 분할용)")
    ap.add_argument("--season", choices=["cur", "prev"], default="cur")
    a = ap.parse_args()
    leagues = [a.league] if a.league else [lg for lg in LEAGUES if lg in FOTMOB_ID]
    prev = a.season == "prev"
    y = SEASON_START - 1 if prev else SEASON_START
    season = f"{y}_{y + 1}"
    fm_season = f"{y}/{y + 1}" if prev else None
    since = "" if prev else f"{SEASON_START}-07-01"

    # 1) 리그 일정 → FotMob 팀 id ↔ 우리 팀 표기(지난 시즌이면 지난 시즌 순위표 표기)
    sides, jobs = _sides(leagues, season, fm_season, since)
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
    new: list[dict] = []
    bad = 0
    for i, (m, code) in enumerate(todo):
        try:
            rows = player_rows(m, code, sides)
        except Exception as e:  # noqa: BLE001 — 한 경기 실패가 전체를 멈추지 않게
            print(f"    [실패] {m.get('id')}: {e}")
            rows, bad = [], bad + 1
        new.extend(rows)
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(todo)} …")
        time.sleep(0.35)
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
