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

2026-10-20부터 IDENTITY 에이전트(src/identity.py, daily_data)가 모든 출처 파일의 클럽 표기를 매일 대조해
확신이 높은 별칭은 data/club_aliases_auto.csv 에 자동 등록한다(여기 ALIASES 다음으로 읽음). 애매한 것만
watchdog 이 '확인 필요'로 알리고, 사람이 확인한 것은 아래 ALIASES 에 적는다.
"""
from __future__ import annotations

import re
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
        "Real Racing Club": "Racing Santander",          # Sofascore — 자동 대조가 애매(Real Sociedad 와 동점)해 사람이 확인
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


# 2군·유스 표시(TM 클럽 표기 끝·앞) — 'Arsenal U21', 'B. Dortmund II', 'Benfica B', 'Jong Ajax', 'Juve Next Gen'
_RESERVE = re.compile(r"(\s+(u1[5-9]|u2[0-3]|ii|b|youth|academy|reserves|primavera|next gen|juvenil|sub-?\d+)$)|(^jong\s+)", re.I)


@lru_cache(maxsize=1)
def _reserve_table() -> dict[str, str]:
    """이름만으로 모구단을 알 수 없는 2군(Club NXT·Barça Atlètic·RM Castilla) — data/club_reserves.csv."""
    import csv
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "data" / "club_reserves.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return {_fold(r["reserve"]): r["parent"] for r in csv.DictReader(f)}


def reserve_parent(club, candidates) -> str | None:
    """2군·유스 팀이면 모구단(우리 표기, candidates 중) — 아니면 None. 'Willem II' 같은 실제 클럽 이름은
    표시를 떼면 모구단이 안 맞아(후보 중 'Willem' 이 없음) None 이 아니라 자기 자신이 될 수 있어 호출부가 팀과 대조한다."""
    c = str(club or "").strip()
    hit = _reserve_table().get(_fold(c))
    if hit:
        return hit
    if not _RESERVE.search(c):
        return None
    import team_names as tn
    base = _RESERVE.sub("", c).strip()
    if not base:
        return None
    # 'B. Dortmund' 처럼 머리글자 줄임은 떼고 한 번 더
    return tn.best(base, list(candidates)) or tn.best(re.sub(r"\b[A-Z]\.\s*", "", base).strip(), list(candidates))


def is_own_reserve(club, team: str, candidates=None) -> bool:
    """이 팀의 2군·유스에서 올라온 것(내부 승격)인가 — 이적 정책·IN 목록·출신 렌즈에서 '영입'으로 세지 않는다."""
    if not club or str(club).strip() == team:
        return False
    return reserve_parent(club, candidates or [team]) == team


@lru_cache(maxsize=None)
def _canon_by_fold(league: str) -> dict[str, str]:
    """악센트·대소문자 무시 키 → 표준 표기 (ESPN 매핑 표준명 기준)."""
    from espn_common import LEAGUE_DISPLAY
    return {_fold(v): v for v in LEAGUE_DISPLAY.get(league, {}).values()}


@lru_cache(maxsize=1)
def _auto_aliases() -> dict[str, dict[str, str]]:
    """IDENTITY 에이전트가 자동 등록한 별칭(data/club_aliases_auto.csv)."""
    import csv
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "data" / "club_aliases_auto.csv"
    out: dict[str, dict[str, str]] = {}
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out.setdefault(r["league"], {})[r["source_name"]] = r["canonical"]
    return out


def canonical_squad(name, league: str) -> str:
    """소스 표기 → 표준 표기(모르는 이름은 그대로). 수동 ALIASES → 자동 별칭 → 악센트 무시 비교."""
    s = str(name or "").strip()
    if s in ALIASES.get(league, {}):
        return ALIASES[league][s]
    auto = _auto_aliases().get(league, {})
    if s in auto:
        return auto[s]
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
