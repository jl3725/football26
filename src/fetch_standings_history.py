"""
과거 시즌 최종 순위표(ESPN) → data/standings_history.csv — 팀 실적(득점·실점)을 여러 시즌 반영하는 데 쓴다.

우리 수집(standings_{리그}_{시즌}.csv)은 직전 시즌부터라, 그보다 오래된 시즌을 ESPN 순위표로 채운다.
- 이미 받은 (리그, 시즌)과 우리 파일이 있는 시즌은 다시 받지 않는다 → daily_data 에서 매일 돌려도 새 시즌만 받는다.
  시즌이 넘어가면(SEASON_START 증가) 새로 '과거'가 된 시즌 중 우리 파일이 없는 것만 자동으로 채운다.
- 팀 이름은 espn_common.squad_of 로 우리 표기에 맞춘다(지금 리그에 없는 강등 팀은 ESPN 표기 그대로 — z 계산 모집단용).
- 벨기에처럼 플레이오프 그룹으로 나뉜 리그는 그룹을 합쳐 경기당 값으로 쓴다.

사용: python src/fetch_standings_history.py [--back 4]
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from espn_common import LEAGUE_CODE, get_json, squad_of
from leagues import DATA_DIR, LEAGUES, SEASON_START, data_path

OUT = DATA_DIR / "standings_history.csv"
COLS = ["league", "season", "rank", "squad", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points", "source"]
URL = "https://site.api.espn.com/apis/v2/sports/soccer/{code}/standings?season={year}"


def parse(d: dict, league: str, season: str) -> list[dict]:
    rows = []
    groups = d.get("children") or [d]
    for g in groups:
        for e in (g.get("standings") or {}).get("entries", []):
            st = {s.get("name"): s.get("value") for s in e.get("stats", [])}
            team = e.get("team") or {}
            name = squad_of(team, league) or team.get("displayName") or team.get("name")
            if not name or not st.get("gamesPlayed"):
                continue
            rows.append({"league": league, "season": season, "squad": name,
                         "played": int(st.get("gamesPlayed") or 0), "won": int(st.get("wins") or 0),
                         "drawn": int(st.get("ties") or 0), "lost": int(st.get("losses") or 0),
                         "gf": int(st.get("pointsFor") or 0), "ga": int(st.get("pointsAgainst") or 0),
                         "points": int(st.get("points") or 0), "source": "espn"})
    if not rows:
        return []
    df = pd.DataFrame(rows).drop_duplicates(subset=["squad"])
    df["gd"] = df["gf"] - df["ga"]
    df["_ppg"] = df["points"] / df["played"].clip(lower=1)
    df = df.sort_values(["_ppg", "gd", "gf"], ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df[COLS].to_dict("records")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--back", type=int, default=4, help="현재 시즌 이전 몇 시즌까지")
    a = ap.parse_args()
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=COLS)
    have = set(zip(old["league"].astype(str), old["season"].astype(str)))
    new_rows: list[dict] = []
    for lg in LEAGUES:
        code = LEAGUE_CODE.get(lg, (None,))[0]
        if not code:
            continue
        for y in range(SEASON_START - a.back, SEASON_START):
            season = f"{y}_{y + 1}"
            if (lg, season) in have or data_path("standings", lg, season).exists():
                continue
            d = get_json(URL.format(code=code, year=y))
            rows = parse(d or {}, lg, season)
            print(f"  {lg:16} {season}: {len(rows)}팀")
            new_rows += rows
    if not new_rows:
        print("[OK] standings_history 새 시즌 없음")
        return 0
    out = pd.concat([old, pd.DataFrame(new_rows)], ignore_index=True)[COLS]
    out = out.sort_values(["league", "season", "rank"]).reset_index(drop=True)
    out.to_csv(OUT, index=False, encoding="utf-8", lineterminator="\n")
    print(f"[OK] {OUT.name} +{len(new_rows)}행 (총 {len(out)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
