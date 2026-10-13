"""
ESPN 수집기 공용 — 리그별 팀명 매핑 · 대회 코드 · squad 판별.

fetch_comp_usage / fetch_schedule / fetch_cup_lineups 가 각자 갖고 있던 EPL 전용
팀맵·대회코드를 한 곳으로 모은다. 새 리그는 여기 dict 만 추가하면 3개 수집기가 함께 확장.

시즌 경기 조회는 `scoreboard_events` 로 통일한다. ESPN 이 2026-07경부터
`scoreboard?dates=YYYYMMDD-YYYYMMDD` 기간 조회에 400("Failed to get events endpoint")을
반환해, 연 단위(`dates=YYYY`)로 받아 날짜로 거르는 방식으로 바꿨다.
"""
from __future__ import annotations

import time
from functools import lru_cache

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_LIMIT = 1000

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
        # 26/27 승격
        "coventry": "Coventry City", "hull city": "Hull City", "ipswich": "Ipswich Town",
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
        # 26/27 승격 — ESPN 은 데포르티보를 'Deportivo' 로만 표기
        "deportivo": "Deportivo A Coruña", "málaga": "Málaga", "malaga": "Málaga",
        "racing santander": "Racing Santander",
    },
    "SerieA": {
        # 'inter' 를 'milan' 보다 먼저 — 'Inter Milan' 이 'milan' 에 먼저 걸리지 않게
        "inter": "Inter", "internazionale": "Inter", "milan": "Milan",
        "juventus": "Juventus", "napoli": "Napoli", "roma": "Roma", "lazio": "Lazio",
        "atalanta": "Atalanta", "fiorentina": "Fiorentina", "bologna": "Bologna",
        "torino": "Torino", "udinese": "Udinese", "genoa": "Genoa", "cagliari": "Cagliari",
        "como": "Como", "cremonese": "Cremonese", "verona": "Hellas Verona",
        "lecce": "Lecce", "parma": "Parma", "pisa": "Pisa", "sassuolo": "Sassuolo",
        # 26/27 승격
        "frosinone": "Frosinone", "monza": "Monza", "venezia": "Venezia",
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
        # 26/27 승격
        "paderborn": "SC Paderborn", "elversberg": "SV Elversberg", "schalke": "Schalke 04",
    },
    "Ligue1": {
        # 'paris fc' 를 'saint-germain'(PSG) 보다 구분되게 — 서로 부분문자열 아님
        "paris fc": "Paris FC", "saint-germain": "PSG", "psg": "PSG",
        "marseille": "Marseille", "monaco": "Monaco", "lyon": "Lyon", "lille": "Lille",
        "losc": "Lille", "nice": "Nice", "lens": "Lens", "rennes": "Rennes",
        "stade rennais": "Rennes",  # ESPN 26/27 표기 — 'rennes' 부분일치에 안 걸림
        # 26/27 승격
        "le mans": "Le Mans", "troyes": "Troyes",
        "strasbourg": "Strasbourg", "nantes": "Nantes", "toulouse": "Toulouse",
        "brest": "Brest", "auxerre": "Auxerre", "angers": "Angers", "havre": "Le Havre",
        "metz": "Metz", "lorient": "Lorient",
    },
    "LigaPortugal": {
        "avs": "AVS Futebol", "arouca": "Arouca", "benfica": "Benfica",
        "braga": "Braga", "casa pia": "Casa Pia", "estoril": "Estoril",
        "estrela": "Estrela", "famalic": "Famalicão", "gil vicente": "Gil Vicente FC",
        "moreirense": "Moreirense", "nacional": "Nacional", "porto": "Porto",
        "rio ave": "Rio Ave", "santa clara": "Santa Clara", "sporting": "Sporting CP",
        "tondela": "Tondela", "vitoria": "Vit. Guimarães", "vitória": "Vit. Guimarães",
        "alverca": "Alverca",
        # 26/27 승격
        "viseu": "Académico de Viseu", "maritimo": "Marítimo", "marítimo": "Marítimo",
    },
    "Eredivisie": {
        "ajax": "Ajax", "az alkmaar": "AZ Alkmaar", "alkmaar": "AZ Alkmaar",
        "excelsior": "Excelsior", "feyenoord": "Feyenoord",
        "fortuna": "Fortuna Sittard", "go ahead": "Go Ahead Eagles",
        "groningen": "Groningen", "heerenveen": "Heerenveen",
        "heracles": "Heracles Almelo", "nac breda": "NAC Breda",
        "nec nijmegen": "NEC Nijmegen", "nijmegen": "NEC Nijmegen", "psv": "PSV",
        "sparta": "Sparta R.", "telstar": "Telstar", "twente": "Twente",
        "utrecht": "Utrecht", "volendam": "Volendam", "zwolle": "Zwolle",
        # 26/27 승격
        "den haag": "ADO Den Haag", "cambuur": "Cambuur", "willem ii": "Willem II",
    },
    "BelgianProLeague": {
        "club brugge": "Club Brugge", "cercle brugge": "Cercle Brugge",
        "genk": "Genk", "union st": "Union SG", "union saint": "Union SG",
        "union sg": "Union SG", "anderlecht": "Anderlecht",
        "antwerp": "Antwerp", "gent": "Gent", "westerlo": "Westerlo",
        "sint-truid": "Sint-Truiden", "st truid": "Sint-Truiden",
        "mechelen": "Mechelen", "standard": "Standard Liège",
        "charleroi": "Charleroi", "oud-heverlee": "OH Leuven",
        "oh leuven": "OH Leuven", "leuven": "OH Leuven",
        "zulte": "Zulte Waregem", "dender": "Dender",
        "la louvi": "La Louvière",
        # 26/27 승격 (16→18팀 확대) — 기존 표기 관례대로 클럽 접두사 생략
        "kortrijk": "Kortrijk", "lommel": "Lommel", "beveren": "Beveren",
    },
}

# 리그 대회 코드
LEAGUE_CODE = {"EPL": ("eng.1", "리그"), "LaLiga": ("esp.1", "리그"),
               "SerieA": ("ita.1", "리그"), "Bundesliga": ("ger.1", "리그"),
               "Ligue1": ("fra.1", "리그"), "LigaPortugal": ("por.1", "리그"),
               "Eredivisie": ("ned.1", "리그"),
               "BelgianProLeague": ("bel.1", "리그")}

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
    # 2026 중 ESPN 이 컵 코드를 변경(por.taca→por.taca.portugal, ned.knvb_beker→ned.cup)하고
    # 타사 다 리가(por.taca_liga)는 제공 중단.
    "LigaPortugal": [("por.taca.portugal", "Taça de Portugal", "taca")],
    "Eredivisie": [("ned.cup", "KNVB Beker", "beker")],
}


def squad_of(team: dict | None, league: str) -> str | None:
    """ESPN team dict → 우리 squad 표기(해당 리그 소속 아니면 None)."""
    raw = ((team or {}).get("displayName") or (team or {}).get("name") or "").lower()
    for k, v in LEAGUE_DISPLAY.get(league, {}).items():
        if k in raw:
            return v
    return None


def get_json(url: str, tries: int = 3, pause: float = 0.6) -> dict | None:
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.ok:
                return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"    [재시도 {i+1}] {e}")
        time.sleep(pause)
    return None


def season_bounds(start_year: int) -> tuple[str, str]:
    """시즌(7/1~6/30) 경계 — ISO 날짜 문자열 쌍."""
    return f"{start_year}-07-01", f"{start_year + 1}-06-30"


_PERIOD_CACHE: dict[tuple[str, str], list[dict] | None] = {}


def _period_events(code: str, period: str) -> list[dict] | None:
    """`dates=YYYY` 또는 `dates=YYYYMM` 한 구간의 이벤트(프로세스 내 캐시). 실패 시 None."""
    key = (code, period)
    if key not in _PERIOD_CACHE:
        data = get_json(f"{BASE}/{code}/scoreboard?dates={period}&limit={_LIMIT}")
        _PERIOD_CACHE[key] = None if data is None else data.get("events", [])
    return _PERIOD_CACHE[key]


def scoreboard_events(code: str, start: str, end: str) -> list[dict] | None:
    """[start, end](ISO 날짜, 포함) 사이 대회 `code` 의 ESPN 이벤트 목록(날짜순).

    연 단위로 받고, 한 해가 limit 에 걸리면 그 해만 월 단위로 쪼갠다.
    요청이 하나라도 실패하면 None — 빈 결과(대회 미개최)와 구분해 호출부가 기존 파일을 지키게 한다.
    """
    out: dict[str, dict] = {}
    for year in range(int(start[:4]), int(end[:4]) + 1):
        events = _period_events(code, str(year))
        if events is None:
            return None
        if len(events) >= _LIMIT:
            events = []
            for month in range(1, 13):
                part = _period_events(code, f"{year}{month:02d}")
                if part is None:
                    return None
                events += part
        for e in events:
            day = (e.get("date") or "")[:10]
            if start <= day <= end and e.get("id"):
                out[str(e["id"])] = e
    return sorted(out.values(), key=lambda e: e.get("date") or "")


def league_members(league: str, start_year: int) -> set[str]:
    """해당 시즌 리그 경기에 실제로 나온 우리 squad 집합.

    LEAGUE_DISPLAY 는 여러 시즌의 팀을 함께 담고 있어(강등팀 포함) 컵·유럽 경기에서
    강등팀이 '우리 리그 팀'으로 잡힐 수 있다 — 시즌 리그 경기 출전 팀으로 걸러낸다.
    리그 일정이 아직 없으면 빈 집합(호출부는 필터를 생략).
    """
    code = LEAGUE_CODE[league][0]
    members: set[str] = set()
    for e in scoreboard_events(code, *season_bounds(start_year)) or []:
        for c in (e.get("competitions") or [{}])[0].get("competitors", []):
            sq = squad_of(c.get("team"), league)
            if sq:
                members.add(sq)
    return members


@lru_cache(maxsize=None)
def season_squad_of(league: str, start_year: int):
    """시즌 소속 팀만 인정하는 squad_of — `fn(team) -> squad | None`."""
    members = league_members(league, start_year)

    def _fn(team: dict | None) -> str | None:
        sq = squad_of(team, league)
        if sq and members and sq not in members:
            return None
        return sq

    return _fn
