"""
세 번째 평점 원천 — 365Scores 경기별 선수 평점(공개 JSON, 클라우드에서 열림) → 시즌 평점.

2026-11-05 사용자: '평점이 객관적인지 모르겠다, 원천 3곳 평균이면 신빙성이 오르지 않나'. 지금 평점 = Sofascore + FotMob 평균
(src/rating_blend.py). WhoScored 는 봇 차단이라 쓰지 않는다. 365Scores 는 경기마다 선수 평점(ranking)·출전 시간이 있고
13개 리그를 다 덮는다.

  1) 리그 경기 목록: /web/games/results/?competitions=<id> 를 previousPage 로 넘기며 시즌 시작(7/1)까지
  2) 끝난 경기마다 /web/game/?gameId=<id> — 양 팀 라인업 members 의 ranking(평점, 없으면 −1)·Minutes, 이름은 game.members
  3) data/s365_match_ratings_<리그>_<시즌>.csv(경기·선수 한 줄, 받은 경기는 다시 안 받음)
     → data/s365_ratings_<리그>_<시즌>.csv(선수 시즌 평점 = 평점 있는 리그 경기의 출전 가중 평균 · 출전 분 · 경기 수)
  리그 경기만(컵·유럽은 FotMob 경기별 기록이 따로 맡는다). 팀 표기는 순위표 이름으로(squads.to_ours).

    python src/fetch_365_ratings.py [--league EPL] [--max 400]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, SEASON_START, data_path, season_window  # noqa: E402

BASE = "https://webws.365scores.com"
Q = "appTypeId=5&langId=1&timezoneName=UTC&userCountryId=1"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
      "Accept": "application/json"}
PAUSE = 0.4
MAX_PAGES = 40
EX_SOURCE_DOWN = 75
MATCH_COLS = ["match_id", "date", "squad", "opponent", "home_away", "athlete_id", "player", "minutes", "rating"]
SEASON_COLS = ["squad", "player", "athlete_id", "apps", "minutes", "rating"]


def _get(path: str, tries: int = 3) -> dict | None:
    url = path if path.startswith("http") else BASE + path
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                print(f"  ! {url[:90]} {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(2 * (i + 1))
    return None


def season_games(comp_id: int, since: str) -> list[dict]:
    """끝난 리그 경기(시즌 시작 since 이후) — 결과 목록을 과거 쪽으로 넘긴다."""
    d = _get(f"/web/games/results/?{Q}&competitions={comp_id}")
    if not d:
        return []
    games: dict[int, dict] = {}
    pages = 0
    while d and pages < MAX_PAGES:
        pages += 1
        for g in d.get("games") or []:
            if int(g.get("statusGroup") or 0) == 4 and str(g.get("startTime") or "")[:10] >= since:
                games[int(g["id"])] = g
        dates = [str(g.get("startTime") or "")[:10] for g in d.get("games") or []]
        prev = (d.get("paging") or {}).get("previousPage")
        if not prev or (dates and min(dates) < since):
            break
        time.sleep(PAUSE)
        d = _get(prev)
    return sorted(games.values(), key=lambda g: str(g.get("startTime")))


def _minutes(member: dict) -> int:
    for s in member.get("stats") or []:
        if s.get("name") == "Minutes" or s.get("type") == 30:
            m = re.match(r"(\d+)", str(s.get("value") or ""))
            return int(m.group(1)) if m else 0
    return 0


def match_rows(game: dict, ours: list[str], league: str) -> list[dict]:
    """끝난 경기 상세 → 선수 행(평점 있는 선수만)."""
    from squads import to_ours  # noqa: PLC0415
    names = {int(m["id"]): m for m in game.get("members") or [] if m.get("id") is not None}
    date = str(game.get("startTime") or "")[:10]
    sides = {"home": game.get("homeCompetitor") or {}, "away": game.get("awayCompetitor") or {}}
    team = {k: (to_ours(v.get("name"), league, ours) or str(v.get("name") or "")) for k, v in sides.items()}
    rows = []
    for side, comp in sides.items():
        other = "away" if side == "home" else "home"
        for m in ((comp.get("lineups") or {}).get("members") or []):
            r = m.get("ranking")
            try:
                r = float(r)
            except (TypeError, ValueError):
                continue
            if r <= 0:
                continue                                   # 평점 없음(짧은 교체·벤치)
            who = names.get(int(m.get("id") or 0)) or {}
            rows.append({"match_id": str(game.get("id")), "date": date, "squad": team[side], "opponent": team[other],
                         "home_away": side, "athlete_id": str(who.get("athleteId") or ""), "player": str(who.get("name") or ""),
                         "minutes": _minutes(m), "rating": r})
    return rows


def season_table(mr: pd.DataFrame) -> pd.DataFrame:
    """경기별 → 선수 시즌 평점(출전 가중 평균). 출전 시간이 없으면 경기당 90분으로 본다."""
    if mr is None or mr.empty:
        return pd.DataFrame(columns=SEASON_COLS)
    d = mr.copy()
    d["minutes"] = pd.to_numeric(d["minutes"], errors="coerce").fillna(0)
    d["rating"] = pd.to_numeric(d["rating"], errors="coerce")
    d = d[d["rating"].notna() & (d["rating"] > 0)]
    d["w"] = d["minutes"].where(d["minutes"] > 0, 90.0)
    d = d.sort_values("date")
    key = d["athlete_id"].astype(str).where(d["athlete_id"].astype(str).str.len() > 0, d["squad"] + "|" + d["player"])
    out = []
    for _, g in d.groupby(key):
        last = g.iloc[-1]
        out.append({"squad": last["squad"], "player": last["player"], "athlete_id": last["athlete_id"], "apps": int(len(g)),
                    "minutes": int(g["minutes"].sum()), "rating": round(float((g["rating"] * g["w"]).sum() / g["w"].sum()), 3)})
    return pd.DataFrame(out, columns=SEASON_COLS).sort_values(["squad", "minutes"], ascending=[True, False])


def run_league(league: str, max_new: int) -> int:
    cfg = LEAGUES[league]
    cid = getattr(cfg, "s365_id", 0)
    if not cid:
        return 0
    since = season_window(league)[0]                  # 달력 연도 리그(MLS 2026)는 1월부터
    try:
        ours = list(pd.read_csv(data_path("standings", league))["squad"].astype(str))
    except (FileNotFoundError, KeyError):
        ours = []
    mp = data_path("s365_match_ratings", league)
    old = pd.read_csv(mp, dtype={"match_id": str, "athlete_id": str}) if mp.exists() else pd.DataFrame(columns=MATCH_COLS)
    have = set(old["match_id"].astype(str))
    games = season_games(cid, since)
    todo = [g for g in games if str(g["id"]) not in have][:max_new]
    new = []
    for g in todo:
        d = _get(f"/web/game/?{Q}&gameId={g['id']}")
        if d and d.get("game"):
            new += match_rows(d["game"], ours, league)
        time.sleep(PAUSE)
    allr = pd.concat([old, pd.DataFrame(new, columns=MATCH_COLS)], ignore_index=True) if new else old
    if allr.empty:
        print(f"  {league:18} 경기 {len(games)} · 받은 평점 없음")
        return 0
    allr = allr.drop_duplicates(["match_id", "athlete_id", "player"], keep="last")
    allr.to_csv(mp, index=False, encoding="utf-8", lineterminator="\n")
    st = season_table(allr)
    st.to_csv(data_path("s365_ratings", league), index=False, encoding="utf-8", lineterminator="\n")
    print(f"  {league:18} 시즌 경기 {len(games)} · 새로 {len(todo)} · 선수 {len(st)} · 경기별 {len(allr)}줄", flush=True)
    return len(todo)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append")
    ap.add_argument("--max", type=int, default=400, help="리그마다 새로 받을 경기 수 상한(첫 백필 분할용)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not _get(f"/web/games/results/?{Q}&competitions=7"):
        print("[365] 365Scores 에 닿지 않음 — 원천 중단(기존 파일 유지)")
        return EX_SOURCE_DOWN
    for lg in a.league or [k for k, c in LEAGUES.items() if getattr(c, "s365_id", 0)]:
        try:
            run_league(lg, a.max)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패는 나머지를 막지 않는다
            print(f"  ! {lg} 실패 {type(e).__name__}: {str(e)[:120]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
