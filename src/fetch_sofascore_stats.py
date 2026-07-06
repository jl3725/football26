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

from leagues import ACTIVE_LEAGUE, data_path, league_config

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = data_path("players_sofascore_stats")

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept": "application/json",
     "Referer": "https://www.sofascore.com/"}
BASE = "https://api.sofascore.com/api/v1"
PL_UT_ID = 17
SOFASCORE_UT_IDS = {
    "EPL": 17,
    "LaLiga": 8,
    "Bundesliga": 35,
    "SerieA": 23,
    "Ligue1": 34,
    "LigaPortugal": 238,
}
UT_ID = SOFASCORE_UT_IDS.get(ACTIVE_LEAGUE, PL_UT_ID)

TEAM_ALIASES = {
    "EPL": {
        "Brighton & Hove Albion": "Brighton",
        "Liverpool FC": "Liverpool",
        "Manchester United": "Manchester Utd",
        "Wolverhampton": "Wolves",
    },
    "LaLiga": {
        "Deportivo Alavés": "Alavés",
        "FC Barcelona": "Barcelona",
        "Girona FC": "Girona",
        "Levante UD": "Levante",
        "Real Oviedo": "Oviedo",
    },
    "SerieA": {
        "AC Milan": "Milan",
        "AS Roma": "Roma",
        "Como 1907": "Como",
        "Inter Milan": "Inter",
        "Internazionale": "Inter",
        "SSC Napoli": "Napoli",
        "Pisa SC": "Pisa",
        "SS Lazio": "Lazio",
        "US Cremonese": "Cremonese",
        "US Lecce": "Lecce",
        "US Sassuolo": "Sassuolo",
    },
    "Bundesliga": {
        "1. FC Heidenheim": "Heidenheim",
        "1. FC Heidenheim 1846": "Heidenheim",
        "1. FC Köln": "Köln",
        "1. FC Koln": "Köln",
        "1. FC Union Berlin": "Union Berlin",
        "1. FSV Mainz 05": "Mainz 05",
        "Bayer 04 Leverkusen": "Leverkusen",
        "Bayer Leverkusen": "Leverkusen",
        "Borussia Dortmund": "Dortmund",
        "Borussia M'gladbach": "Gladbach",
        "Borussia Monchengladbach": "Gladbach",
        "Borussia Mönchengladbach": "Gladbach",
        "Eintracht Frankfurt": "Frankfurt",
        "FC Augsburg": "Augsburg",
        "FC Bayern München": "Bayern Munich",
        "FC Bayern Munich": "Bayern Munich",
        "FC St. Pauli": "St Pauli",
        "Hamburger SV": "Hamburger SV",
        "RB Leipzig": "RB Leipzig",
        "SC Freiburg": "Freiburg",
        "SV Werder Bremen": "Werder Bremen",
        "TSG Hoffenheim": "Hoffenheim",
        "VfB Stuttgart": "Stuttgart",
        "VfL Wolfsburg": "Wolfsburg",
    },
    "Ligue1": {
        "AJ Auxerre": "Auxerre",
        "AS Monaco": "Monaco",
        "Angers": "Angers",
        "Angers SCO": "Angers",
        "Brest": "Brest",
        "FC Lorient": "Lorient",
        "FC Metz": "Metz",
        "FC Nantes": "Nantes",
        "Le Havre": "Le Havre",
        "Le Havre AC": "Le Havre",
        "Lille": "Lille",
        "LOSC Lille": "Lille",
        "Olympique Lyon": "Lyon",
        "Olympique Lyonnais": "Lyon",
        "Olympique de Marseille": "Marseille",
        "Olympique Marseille": "Marseille",
        "OGC Nice": "Nice",
        "Paris FC": "Paris FC",
        "Paris Saint-Germain": "PSG",
        "PSG": "PSG",
        "RC Lens": "Lens",
        "Rennes": "Rennes",
        "Stade Rennais": "Rennes",
        "Stade Rennais FC": "Rennes",
        "Stade Brestois": "Brest",
        "Stade Brestois 29": "Brest",
        "Strasbourg": "Strasbourg",
        "RC Strasbourg": "Strasbourg",
        "RC Strasbourg Alsace": "Strasbourg",
        "Toulouse": "Toulouse",
        "Toulouse FC": "Toulouse",
    },
    "LigaPortugal": {
        "AVS - Futebol SAD": "AVS Futebol",
        "AVS Futebol SAD": "AVS Futebol",
        "Benfica": "Benfica",
        "Casa Pia": "Casa Pia",
        "Casa Pia AC": "Casa Pia",
        "CD Nacional": "Nacional",
        "CF Estrela Amadora": "Estrela",
        "Estoril Praia": "Estoril",
        "FC Alverca": "Alverca",
        "FC Arouca": "Arouca",
        "FC Famalicão": "Famalicão",
        "FC Famalicao": "Famalicão",
        "FC Porto": "Porto",
        "Gil Vicente": "Gil Vicente FC",
        "Gil Vicente FC": "Gil Vicente FC",
        "Moreirense": "Moreirense",
        "Moreirense FC": "Moreirense",
        "Nacional": "Nacional",
        "Rio Ave": "Rio Ave",
        "Rio Ave FC": "Rio Ave",
        "Santa Clara": "Santa Clara",
        "Sporting Braga": "Braga",
        "Sporting": "Sporting CP",
        "Sporting CP": "Sporting CP",
        "Tondela": "Tondela",
        "Vitória SC": "Vit. Guimarães",
        "Vitória Guimarães": "Vit. Guimarães",
        "Vitoria SC": "Vit. Guimarães",
        "Alverca": "Alverca",
        "Estrela Amadora": "Estrela",
    },
}


def normalize_team_name(name: str) -> str:
    return TEAM_ALIASES.get(ACTIVE_LEAGUE, {}).get(name, name)

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
    d = get("/unique-tournament/{}/seasons".format(UT_ID), delay=0.2)
    if not d:
        return None
    for s in d.get("seasons", []):
        if s.get("year") == "25/26":
            return s["id"]
    return None


def fetch_teams(season_id: int) -> list[dict]:
    d = get(f"/unique-tournament/{UT_ID}/season/{season_id}/standings/total", delay=0.2)
    if not d:
        return []
    rows = d.get("standings", [{}])[0].get("rows", [])
    return [{"id": r["team"]["id"], "name": r["team"]["name"]} for r in rows]


def fetch_team_players(team_id: int) -> list[dict]:
    d = get(f"/team/{team_id}/players")
    return [p["player"] for p in (d or {}).get("players", [])]


def fetch_player_stats(player_id: int, season_id: int) -> dict:
    d = get(f"/player/{player_id}/unique-tournament/{UT_ID}"
            f"/season/{season_id}/statistics/overall")
    return (d or {}).get("statistics", {})


def fetch_tournament_player_stats(season_id: int) -> list[dict]:
    rows: list[dict] = []
    fields = ",".join(STAT_KEYS)
    limit = 100
    offset = 0
    pages = None

    while pages is None or (offset // limit) < pages:
        d = get(
            f"/unique-tournament/{UT_ID}/season/{season_id}/statistics"
            f"?limit={limit}&offset={offset}&order=-minutesPlayed"
            f"&accumulation=total&fields={fields}",
            delay=0.25,
        )
        if not d:
            break
        results = d.get("results", [])
        page = d.get("page", offset // limit + 1)
        pages = d.get("pages", page)
        print(f"  tournament stats page {page}/{pages}: {len(results)} players")
        if not results:
            break

        for item in results:
            p = item.get("player") or {}
            t = item.get("team") or {}
            if item.get("appearances", 0) == 0:
                continue
            row = {
                "sofascore_id": p.get("id"),
                "player": p.get("name", ""),
                "squad": normalize_team_name(t.get("name", "")),
                "norm_key": unidecode(str(p.get("name", ""))).lower().strip(),
            }
            for k in STAT_KEYS:
                row[k] = item.get(k)
            rows.append(row)

        if page >= pages:
            break
        offset += limit

    return rows


def main(argv=None) -> int:
    cfg = league_config()
    season_id = find_season_id()
    if season_id is None:
        print("EPL 25/26 시즌 id 조회 실패")
        return 1
    print(f"{cfg.name} 25/26 season id = {season_id}")

    rows = fetch_tournament_player_stats(season_id)
    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(OUT, index=False, encoding="utf-8")
        print(f"\n[OK] saved {OUT.name} - {len(df)} players")
        return 0

    print("Tournament stats unavailable; falling back to team rosters.")

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
                "squad": normalize_team_name(t["name"]),
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
