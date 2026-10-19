"""
FotMob 경기별 선수 평점 → data/fotmob_match_ratings_{리그}_{시즌}.csv — '최근 폼'(최근 3·5경기)용.

2026-10-19 사용자: "노팅엄전 사카가 엄청 못했는데 '폼 절정' — 시즌 전체 폼과 최근 3·5경기 폼을 나누자".
시즌 폼(_form)은 시즌 평균 평점이라 한두 경기 부진이 안 보인다. 경기별 평점은 FotMob 공개 JSON
(/api/data/matchDetails)에서 받는다(Sofascore 경기별 평점은 로컬 수집 전용이라 클라우드에서 못 받음).
- 대회: 우리 8개 리그 + UEFA 3개 대회 + 국내 컵. 리그 일정에서 FotMob 팀 id → (리그, 우리 팀 표기)를 먼저 만들고,
  유럽·컵 경기는 그 팀 id 가 있는 쪽만 남긴다(상대 팀이 우리 리그 밖이면 그 팀 선수 행은 버림).
- 이미 받은 경기(match_id)는 다시 받지 않는다 — 매일 새로 끝난 경기만(match_refresh).
- 행: match_id, date, comp_code, squad(우리 표기), opponent, home_away, fotmob_id, player, minutes, rating(FotMob 척도), goals, assists.

사용: python src/fetch_fotmob_matches.py [--league EPL] [--max 400]
"""
from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from fetch_fotmob_ratings import FOTMOB_ID, _get
from leagues import LEAGUES, SEASON, SEASON_START, data_path
import team_names as tn

# FotMob 대회 id → 우리 대회 코드(ESPN 표기 — schedule_full comp_code 와 같은 축)
CUPS = {42: "uefa.champions", 73: "uefa.europa", 10216: "uefa.europa.conf",
        132: "eng.fa", 133: "eng.league_cup", 138: "esp.copa_del_rey", 141: "ita.coppa_italia",
        209: "ger.dfb_pokal", 134: "fra.coupe_de_france", 186: "por.taca.portugal", 235: "ned.cup",
        149: "bel.cup"}
LEAGUE_CODE = {"EPL": "eng.1", "LaLiga": "esp.1", "SerieA": "ita.1", "Bundesliga": "ger.1", "Ligue1": "fra.1",
               "LigaPortugal": "por.1", "Eredivisie": "ned.1", "BelgianProLeague": "bel.1"}
COLS = ["match_id", "date", "comp_code", "squad", "opponent", "home_away", "fotmob_id", "player",
        "minutes", "rating", "goals", "assists"]
SEASON_FROM = f"{SEASON_START}-07-01"


def finished(fid: int) -> list[dict]:
    d = _get(f"https://www.fotmob.com/api/data/leagues?id={fid}") or {}
    out = []
    for m in ((d.get("fixtures") or {}).get("allMatches") or []):
        st = m.get("status") or {}
        t = str(st.get("utcTime") or "")
        if st.get("finished") and not st.get("cancelled") and t[:10] >= SEASON_FROM:
            out.append(m)
    return out


def _stat(block: dict, title: str):
    for sec in block.get("stats") or []:
        s = (sec.get("stats") or {}).get(title)
        if s:
            return (s.get("stat") or {}).get("value")
    return None


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
        mn = _stat(p, "Minutes played")
        if not mn:
            continue                                   # 벤치(출전 없음)
        rows.append({"league": lg, "match_id": str(match["id"]), "date": date, "comp_code": comp, "squad": squad,
                     "opponent": opp, "home_away": "home" if tid == str(home.get("id")) else "away",
                     "fotmob_id": str(p.get("id") or pid), "player": p.get("name"), "minutes": mn,
                     "rating": _stat(p, "FotMob rating"), "goals": _stat(p, "Goals") or 0, "assists": _stat(p, "Assists") or 0})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--max", type=int, default=600, help="한 번에 새로 받을 경기 수 상한(첫 실행 백필 분할용)")
    a = ap.parse_args()
    leagues = [a.league] if a.league else [lg for lg in LEAGUES if lg in FOTMOB_ID]

    # 1) 리그 일정 → FotMob 팀 id ↔ 우리 팀 표기
    sides: dict[str, tuple[str, str]] = {}
    jobs: list[tuple[dict, str]] = []
    for lg in leagues:
        try:
            ours = list(pd.read_csv(data_path("standings", lg, SEASON))["squad"].astype(str))
        except (FileNotFoundError, KeyError):
            ours = []
        ms = finished(FOTMOB_ID[lg])
        for m in ms:
            for side in ("home", "away"):
                t = m.get(side) or {}
                if str(t.get("id")) not in sides:
                    sides[str(t.get("id"))] = (lg, (tn.best(str(t.get("name")), ours) if ours else None) or str(t.get("name")))
            jobs.append((m, LEAGUE_CODE[lg]))
        time.sleep(0.5)
    # 2) 유럽·컵 — 우리 팀이 낀 경기만
    for fid, code in CUPS.items():
        for m in finished(fid):
            if str((m.get("home") or {}).get("id")) in sides or str((m.get("away") or {}).get("id")) in sides:
                jobs.append((m, code))
        time.sleep(0.5)

    # 3) 이미 받은 경기는 건너뛰고 새 경기만
    have: dict[str, pd.DataFrame] = {}
    seen: set[str] = set()
    for lg in leagues:
        p = data_path("fotmob_match_ratings", lg, SEASON)
        if p.exists():
            df = pd.read_csv(p, dtype={"match_id": str, "fotmob_id": str})
            have[lg] = df
            seen |= set(df["match_id"].astype(str))
    todo = [(m, c) for m, c in jobs if str(m["id"]) not in seen]
    todo.sort(key=lambda x: str((x[0].get("status") or {}).get("utcTime") or ""), reverse=True)   # 최근 경기부터
    print(f"경기 {len(jobs)}개 중 새로 받을 경기 {len(todo)}개 (상한 {a.max})")
    new: list[dict] = []
    bad = 0
    for i, (m, code) in enumerate(todo[: a.max]):
        try:
            rows = player_rows(m, code, sides)
        except Exception as e:  # noqa: BLE001 — 한 경기 실패가 전체를 멈추지 않게
            print(f"    [실패] {m.get('id')}: {e}")
            rows, bad = [], bad + 1
        new.extend(rows)
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{min(len(todo), a.max)} …")
        time.sleep(0.35)
    if not new:
        print("새 경기 없음")
        return 0
    nd = pd.DataFrame(new)
    for lg, g in nd.groupby("league"):
        out = data_path("fotmob_match_ratings", lg, SEASON)
        df = pd.concat([have[lg], g[COLS]], ignore_index=True) if lg in have else g[COLS].copy()
        df = df.drop_duplicates(subset=["match_id", "fotmob_id"], keep="last").sort_values(["date", "match_id"])
        df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        print(f"  {lg:16} +{len(g)}행 → {len(df)}행 ({df['match_id'].nunique()}경기) -> {out.name}")
    return 1 if bad > max(3, len(todo[: a.max]) // 10) else 0


if __name__ == "__main__":
    sys.exit(main())
