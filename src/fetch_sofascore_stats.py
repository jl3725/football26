"""
Sofascore 비공식 API로 25/26 EPL 선수 시즌 통계(고급 지표 포함) 수집.

FBref가 25/26 시즌 advanced 컬럼(공중볼·패스성공률·캐리·키퍼 PSxG 등)을 비워둔
이슈를 해결하기 위해 Sofascore에서 직접 수집한다.

수집 흐름:
  1) EPL 25/26 season id 조회
  2) 시즌 standings 에서 20개 팀 ID 확보
  3) 팀별 선수 목록(`/team/{id}/players`) 조회
  4) 선수별 시즌 통계(`/player/{id}/unique-tournament/17/season/{sid}/statistics/overall`)
     수집 → 평탄화 CSV 저장

출력: data/players_sofascore_stats.csv (선수 키: norm_key = unidecode(name).lower())

실행:
    python src/fetch_sofascore_stats.py
※ 약 480명 × 0.6초 ≈ 5분 소요. 도중 끊겨도 다시 실행하면 처음부터 재시도.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import tls_requests
from unidecode import unidecode

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "players_sofascore_stats.csv"

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept": "application/json",
     "Referer": "https://www.sofascore.com/"}
BASE = "https://api.sofascore.com/api/v1"
PL_UT_ID = 17

# 수집할 Sofascore 통계 키 — 평탄화 후 컬럼명도 그대로 사용
STAT_KEYS = [
    # 메타
    "rating", "appearances", "matchesStarted", "minutesPlayed",
    # 공격 (이미 FBref/Understat에도 있지만 평점/빅찬스는 Sofascore만)
    "goals", "expectedGoals", "assists", "expectedAssists",
    "bigChancesCreated", "bigChancesMissed",
    "totalShots", "shotsOnTarget", "goalConversionPercentage",
    # 패스
    "accuratePasses", "totalPasses", "accuratePassesPercentage",
    "accurateLongBalls", "totalLongBalls", "accurateLongBallsPercentage",
    "keyPasses", "accurateFinalThirdPasses",
    "accurateChippedPasses", "totalChippedPasses",
    # 드리블·캐리·터치
    "successfulDribbles", "totalContest", "successfulDribblesPercentage",
    "totalCross", "accurateCrosses", "accurateCrossesPercentage",
    "touches", "possessionLost", "possessionWonAttThird",
    "ballRecovery", "dispossessed",
    # 듀얼
    "groundDuelsWon", "groundDuelsWonPercentage",
    "aerialDuelsWon", "aerialLost", "aerialDuelsWonPercentage",
    "totalDuelsWon", "totalDuelsWonPercentage",
    # 수비
    "tackles", "tacklesWon", "tacklesWonPercentage",
    "interceptions", "clearances", "blockedShots", "outfielderBlocks",
    "errorLeadToGoal", "errorLeadToShot", "dribbledPast",
    "fouls", "wasFouled", "yellowCards", "redCards",
    # GK
    "saves", "savesCaught", "savesParried", "cleanSheet", "goalsConceded",
    "savedShotsFromInsideTheBox", "savedShotsFromOutsideTheBox",
    "goalsConcededInsideTheBox", "goalsConcededOutsideTheBox",
    "punches", "runsOut", "successfulRunsOut", "highClaims", "crossesNotClaimed",
    "penaltyFaced", "penaltySave",
]


def get(path: str, retries: int = 3, delay: float = 0.6):
    for i in range(retries):
        time.sleep(delay)
        try:
            r = tls_requests.get(BASE + path, headers=H, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None  # 출전 없는 선수 등
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def find_season_id() -> int | None:
    d = get("/unique-tournament/{}/seasons".format(PL_UT_ID), delay=0.2)
    if not d:
        return None
    for s in d.get("seasons", []):
        if s.get("year") == "25/26":
            return s["id"]
    return None


def fetch_teams(season_id: int) -> list[dict]:
    d = get(f"/unique-tournament/{PL_UT_ID}/season/{season_id}/standings/total", delay=0.2)
    if not d:
        return []
    rows = d.get("standings", [{}])[0].get("rows", [])
    return [{"id": r["team"]["id"], "name": r["team"]["name"]} for r in rows]


def fetch_team_players(team_id: int) -> list[dict]:
    d = get(f"/team/{team_id}/players")
    return [p["player"] for p in (d or {}).get("players", [])]


def fetch_player_stats(player_id: int, season_id: int) -> dict:
    d = get(f"/player/{player_id}/unique-tournament/{PL_UT_ID}"
            f"/season/{season_id}/statistics/overall")
    return (d or {}).get("statistics", {})


def main(argv=None) -> int:
    season_id = find_season_id()
    if season_id is None:
        print("EPL 25/26 시즌 id 조회 실패")
        return 1
    print(f"EPL 25/26 season id = {season_id}")

    teams = fetch_teams(season_id)
    if not teams:
        print("팀 목록 조회 실패")
        return 1
    print(f"{len(teams)} 팀 발견")

    rows = []
    for ti, t in enumerate(teams, 1):
        print(f"\n[{ti}/{len(teams)}] {t['name']} (id={t['id']})")
        players = fetch_team_players(t["id"])
        print(f"  선수 {len(players)}명")
        for pi, p in enumerate(players, 1):
            stats = fetch_player_stats(p["id"], season_id)
            if not stats or stats.get("appearances", 0) == 0:
                continue
            row = {
                "sofascore_id": p["id"],
                "player": p["name"],
                "squad": t["name"],
                "norm_key": unidecode(str(p["name"])).lower().strip(),
            }
            for k in STAT_KEYS:
                row[k] = stats.get(k)
            rows.append(row)
            print(f"    [{pi:>2}/{len(players)}] {p['name']:25} "
                  f"앱={stats.get('appearances', 0):>2}  "
                  f"평점={stats.get('rating') or 0:.2f}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {OUT.name} — {len(df)}명")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
