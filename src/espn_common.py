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
    "SerieA": {
        # 'inter' 를 'milan' 보다 먼저 — 'Inter Milan' 이 'milan' 에 먼저 걸리지 않게
        "inter": "Inter", "internazionale": "Inter", "milan": "Milan",
        "juventus": "Juventus", "napoli": "Napoli", "roma": "Roma", "lazio": "Lazio",
        "atalanta": "Atalanta", "fiorentina": "Fiorentina", "bologna": "Bologna",
        "torino": "Torino", "udinese": "Udinese", "genoa": "Genoa", "cagliari": "Cagliari",
        "como": "Como", "cremonese": "Cremonese", "verona": "Hellas Verona",
        "lecce": "Lecce", "parma": "Parma", "pisa": "Pisa", "sassuolo": "Sassuolo",
    },
    "Bundesliga": {
        "bayern": "Bayern Munich", "leverkusen": "Leverkusen", "dortmund": "Dortmund",
        "leipzig": "RB Leipzig", "stuttgart": "Stuttgart", "frankfurt": "Frankfurt",
        "freiburg": "Freiburg", "gladbach": "Gladbach", "mönchengladbach": "Gladbach",
        "monchengladbach": "Gladbach", "wolfsburg": "Wolfsburg", "mainz": "Mainz 05",
        "augsburg": "Augsburg", "hoffenheim": "Hoffenheim", "union": "Union Berlin",
        "werder": "Werder Bremen", "bremen": "Werder Bremen", "köln": "Köln",
        "koln": "Köln", "cologne": "Köln", "pauli": "St Pauli", "hamburg": "Hamburger SV",
        "heidenheim": "Heidenheim",
    },
    "Ligue1": {
        # 'paris fc' 를 'saint-germain'(PSG) 보다 구분되게 — 서로 부분문자열 아님
        "paris fc": "Paris FC", "saint-germain": "PSG", "psg": "PSG",
        "marseille": "Marseille", "monaco": "Monaco", "lyon": "Lyon", "lille": "Lille",
        "losc": "Lille", "nice": "Nice", "lens": "Lens", "rennes": "Rennes",
        "strasbourg": "Strasbourg", "nantes": "Nantes", "toulouse": "Toulouse",
        "brest": "Brest", "auxerre": "Auxerre", "angers": "Angers", "havre": "Le Havre",
        "metz": "Metz", "lorient": "Lorient",
    },
}

# 리그 대회 코드
LEAGUE_CODE = {"EPL": ("eng.1", "리그"), "LaLiga": ("esp.1", "리그"),
               "SerieA": ("ita.1", "리그"), "Bundesliga": ("ger.1", "리그"),
               "Ligue1": ("fra.1", "리그")}

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
    "SerieA": [("ita.coppa_italia", "코파 이탈리아", "coppa")],
    "Bundesliga": [("ger.dfb_pokal", "DFB-포칼", "pokal")],
    "Ligue1": [("fra.coupe_de_france", "쿠프 드 프랑스", "coupe")],
}


def squad_of(team: dict | None, league: str) -> str | None:
    """ESPN team dict → 우리 squad 표기(해당 리그 소속 아니면 None)."""
    raw = ((team or {}).get("displayName") or (team or {}).get("name") or "").lower()
    for k, v in LEAGUE_DISPLAY.get(league, {}).items():
        if k in raw:
            return v
    return None
