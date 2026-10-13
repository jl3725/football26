"""
소스별 클럽 표기 → 앱 표준 squad 표기.

앱 표준은 순위표·teammeta·ESPN 매핑(espn_common.LEAGUE_DISPLAY)이 함께 쓰는 이름이다
(예: "Newcastle United", "Manchester Utd"). FBref(soccerdata)가 2026-27 시즌부터 일부 클럽을
다르게 표기해("Newcastle", "Tottenham") 순위·선수·일정이 서로 연결되지 않는 문제가 생겨,
soccerdata 산출물(fetch_standings·fetch_fbref·fetch_understat)은 저장 전에 여기서 표준화한다.
Understat 은 원래부터 표기가 달라(예 "Manchester United", "Borussia Dortmund") 25/26 데이터에서
19개 팀 선수 xG 가 전부 0 으로 병합된 문제도 같은 표로 해결한다. 악센트만 다른 표기("Malaga")는
표준명과 악센트 무시 비교로 자동 처리한다.

새 시즌에 표기가 또 바뀌면 `python src/squads.py` 로 순위표와 ESPN 소속팀을 대조해
빠진 별칭을 확인하고 ALIASES 에 추가한다.
"""
from __future__ import annotations

from functools import lru_cache

# 리그 → {소스 표기(FBref·Understat): 표준 표기}
ALIASES: dict[str, dict[str, str]] = {
    "EPL": {
        "Newcastle": "Newcastle United",
        "Newcastle Utd": "Newcastle United",
        "Nottingham": "Nottingham Forest",
        "Nott'ham Forest": "Nottingham Forest",
        "Tottenham": "Tottenham Hotspur",
        "West Ham": "West Ham United",
        "Coventry": "Coventry City",
        "Hull": "Hull City",
        "Ipswich": "Ipswich Town",
        # Understat
        "Leeds": "Leeds United",
        "Manchester United": "Manchester Utd",
        "Wolverhampton Wanderers": "Wolves",
    },
    "LaLiga": {
        "Dep. A Coruña": "Deportivo A Coruña",
        "Deportivo La Coruña": "Deportivo A Coruña",
        "Racing Sant": "Racing Santander",
        "Deportivo La Coruna": "Deportivo A Coruña",
        "Real Oviedo": "Oviedo",
    },
    "SerieA": {
        "AC Milan": "Milan",
        "Parma Calcio 1913": "Parma",
        "Verona": "Hellas Verona",
    },
    "Bundesliga": {
        "Elversberg": "SV Elversberg",
        "Paderborn 07": "SC Paderborn",
        "Paderborn": "SC Paderborn",
        # Understat
        "Bayer Leverkusen": "Leverkusen",
        "Borussia Dortmund": "Dortmund",
        "Borussia M.Gladbach": "Gladbach",
        "Eintracht Frankfurt": "Frankfurt",
        "FC Cologne": "Köln",
        "FC Heidenheim": "Heidenheim",
        "RasenBallsport Leipzig": "RB Leipzig",
        "St. Pauli": "St Pauli",
        "VfB Stuttgart": "Stuttgart",
    },
    "Ligue1": {
        "Paris SG": "PSG",
        "Paris S-G": "PSG",
        "Paris Saint-Germain": "PSG",
        "Paris Saint Germain": "PSG",
    },
    "LigaPortugal": {
        "Acad. Viseu": "Académico de Viseu",
    },
}


def _fold(s: str) -> str:
    from unidecode import unidecode
    return unidecode(s).lower().strip()


@lru_cache(maxsize=None)
def _canon_by_fold(league: str) -> dict[str, str]:
    """악센트·대소문자 무시 키 → 표준 표기 (ESPN 매핑 표준명 기준)."""
    from espn_common import LEAGUE_DISPLAY
    return {_fold(v): v for v in LEAGUE_DISPLAY.get(league, {}).values()}


def canonical_squad(name, league: str) -> str:
    """소스 표기 → 표준 표기(모르는 이름은 그대로)."""
    s = str(name or "").strip()
    if s in ALIASES.get(league, {}):
        return ALIASES[league][s]
    return _canon_by_fold(league).get(_fold(s), s)


def _report() -> int:
    """활성 시즌 순위표 squad 를 ESPN 시즌 소속팀(표준)과 대조해 불일치를 출력."""
    import pandas as pd

    from espn_common import league_members
    from leagues import LEAGUES, SEASON_START, data_path

    bad = 0
    for lg in LEAGUES:
        path = data_path("standings", lg)
        if not path.exists():
            print(f"{lg:18s} standings 없음")
            continue
        got = {canonical_squad(s, lg) for s in pd.read_csv(path)["squad"]}
        want = league_members(lg, SEASON_START)
        missing, extra = sorted(want - got), sorted(got - want)
        bad += bool(missing or extra)
        print(f"{lg:18s} {'OK' if not (missing or extra) else 'MISMATCH'}"
              + (f"  표준에만: {missing}  순위표에만: {extra}" if (missing or extra) else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_report())
