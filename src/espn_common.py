"""
ESPN 수집기 공용 — 리그별 팀명 매핑 · 대회 코드 · squad 판별.

fetch_comp_usage / fetch_schedule / fetch_cup_lineups 가 각자 갖고 있던 EPL 전용
팀맵·대회코드를 한 곳으로 모은다. 새 리그는 여기 dict 만 추가하면 3개 수집기가 함께 확장.
"""
from __future__ import annotations

# ESPN displayName(소문자) 부분일치 → 우리 squad 표기 (리그별)
LEAGUE_DISPLAY: dict[str, dict[str, str]] = {
    "EPL": {
        "arsenal": "Arsenal", "aston villa": "Aston Villa", "bournemouth": "Bournemouth",
        "brentford": "Brentford", "brighton": "Brighton", "burnley": "Burnley",
        "chelsea": "Chelsea", "crystal palace": "Crystal Palace", "everton": "Everton",
        "fulham": "Fulham", "leeds": "Leeds United", "liverpool": "Liverpool",
        "manchester city": "Manchester City", "manchester united": "Manchester Utd",
        "newcastle": "Newcastle United", "nottingham forest": "Nottingham Forest",
        "sunderland": "Sunderland", "tottenham": "Tottenham Hotspur",
        "west ham": "West Ham United", "wolver": "Wolves", "wolves": "Wolves",
    },
    "LaLiga": {
        "alav": "Alavés", "athletic": "Athletic Club",
        "atlético madrid": "Atlético Madrid", "atletico madrid": "Atlético Madrid",
        "barcelona": "Barcelona", "celta": "Celta Vigo", "elche": "Elche",
        "espanyol": "Espanyol", "getafe": "Getafe", "girona": "Girona",
        "levante": "Levante", "mallorca": "Mallorca", "osasuna": "Osasuna",
        "oviedo": "Oviedo", "rayo": "Rayo Vallecano", "betis": "Real Betis",
        "real madrid": "Real Madrid", "sociedad": "Real Sociedad",
        "sevilla": "Sevilla", "valencia": "Valencia", "villarreal": "Villarreal",
    },
}

# 리그 대회 코드
LEAGUE_CODE = {"EPL": ("eng.1", "리그"), "LaLiga": ("esp.1", "리그")}

# 유럽 대회 (공통)
EURO_COMPS = [
    ("uefa.champions", "챔피언스리그", "ucl"),
    ("uefa.europa", "유로파리그", "uel"),
    ("uefa.europa.conf", "컨퍼런스리그", "conf"),
]

# 국내컵 (리그별) — (code, 라벨, usage 키)
DOMESTIC_CUPS = {
    "EPL": [("eng.fa", "FA컵", "facup"), ("eng.league_cup", "EFL컵", "lcup")],
    "LaLiga": [("esp.copa_del_rey", "코파델레이", "copa")],
}


def squad_of(team: dict | None, league: str) -> str | None:
    """ESPN team dict → 우리 squad 표기(해당 리그 소속 아니면 None)."""
    raw = ((team or {}).get("displayName") or (team or {}).get("name") or "").lower()
    for k, v in LEAGUE_DISPLAY.get(league, {}).items():
        if k in raw:
            return v
    return None
