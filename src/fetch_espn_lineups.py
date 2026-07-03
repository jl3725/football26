"""
ESPN 공개 JSON API → EPL 경기별 라인업(선발 XI + 교체 + 포메이션) 스크래퍼.

football-lineups 경기 페이지는 라인업이 정적 이미지라 파싱 불가 → ESPN으로 대체.
ESPN site API는 키 불필요·빠른 JSON 단일 호출로 다음을 제공한다:
    formation(예 "4-3-3") · 선수별 starter/jersey/displayName
    position.abbreviation(G·CD-R·CM-L·AM·RF 등 좌우 구분 포함) · formationPlace(1~11)

ESPN position 토큰 → 우리 슬롯 매핑은 app.py(렌더링) 쪽에서 처리하므로,
여기선 raw(espn_pos)만 저장한다 — 매핑 로직 변경 시 재스크래핑 불필요.

저장: data/espn_lineups_2025_2026.csv  (전 경기 일괄)

사용:
    python src/fetch_espn_lineups.py            # 전 시즌 수집
    python src/fetch_espn_lineups.py --dry      # 저장 안 함(샘플 출력)
    python src/fetch_espn_lineups.py 740602     # 특정 event만(디버그)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

from leagues import ACTIVE_LEAGUE, data_path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = data_path("espn_lineups")
ESPN_CODES = {
    "EPL": "eng.1",
    "LaLiga": "esp.1",
    "Bundesliga": "ger.1",
    "SerieA": "ita.1",
    "Ligue1": "fra.1",
}
ESPN = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{ESPN_CODES.get(ACTIVE_LEAGUE, 'eng.1')}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ESPN abbreviation → 우리 squad 표기
SQUAD_BY_ABBR: dict[str, str] = {
    "ARS": "Arsenal", "AVL": "Aston Villa", "BOU": "Bournemouth", "BRE": "Brentford",
    "BHA": "Brighton", "BUR": "Burnley", "CHE": "Chelsea", "CRY": "Crystal Palace",
    "EVE": "Everton", "FUL": "Fulham", "LEE": "Leeds United", "LIV": "Liverpool",
    "MNC": "Manchester City", "MAN": "Manchester Utd", "NEW": "Newcastle United",
    "NFO": "Nottingham Forest", "SUN": "Sunderland", "TOT": "Tottenham Hotspur",
    "WHU": "West Ham United", "WOL": "Wolves",
}

TEAM_ALIASES = {
    "Deportivo Alavés": "Alavés",
    "Athletic Bilbao": "Athletic Club",
    "Atlético Madrid": "Atlético Madrid",
    "Barcelona": "Barcelona",
    "Celta Vigo": "Celta Vigo",
    "Elche": "Elche",
    "Espanyol": "Espanyol",
    "Getafe": "Getafe",
    "Girona": "Girona",
    "Levante": "Levante",
    "Mallorca": "Mallorca",
    "Osasuna": "Osasuna",
    "Real Betis": "Real Betis",
    "Real Madrid": "Real Madrid",
    "Real Oviedo": "Oviedo",
    "Real Sociedad": "Real Sociedad",
    "Rayo Vallecano": "Rayo Vallecano",
    "Sevilla": "Sevilla",
    "Valencia": "Valencia",
    "Villarreal": "Villarreal",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "Atalanta": "Atalanta",
    "Bologna": "Bologna",
    "Cagliari": "Cagliari",
    "Como": "Como",
    "Cremonese": "Cremonese",
    "Fiorentina": "Fiorentina",
    "Genoa": "Genoa",
    "Hellas Verona": "Hellas Verona",
    "Internazionale": "Inter",
    "Inter Milan": "Inter",
    "Juventus": "Juventus",
    "Lazio": "Lazio",
    "Lecce": "Lecce",
    "Napoli": "Napoli",
    "Parma": "Parma",
    "Pisa": "Pisa",
    "Roma": "Roma",
    "Sassuolo": "Sassuolo",
    "Torino": "Torino",
    "Udinese": "Udinese",
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
    "FC Bayern Munich": "Bayern Munich",
    "FC Bayern München": "Bayern Munich",
    "FC Cologne": "Köln",
    "FC St Pauli": "St Pauli",
    "FC St. Pauli": "St Pauli",
    "Hamburg SV": "Hamburger SV",
    "Hamburger SV": "Hamburger SV",
    "Mainz": "Mainz 05",
    "RB Leipzig": "RB Leipzig",
    "SC Freiburg": "Freiburg",
    "SV Werder Bremen": "Werder Bremen",
    "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart",
    "VfL Wolfsburg": "Wolfsburg",
    "Werder Bremen": "Werder Bremen",
    "St. Pauli": "St Pauli",
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
    "Lorient": "Lorient",
    "Lyon": "Lyon",
    "Marseille": "Marseille",
    "Metz": "Metz",
    "Monaco": "Monaco",
    "Nantes": "Nantes",
    "Nice": "Nice",
    "Olympique Lyon": "Lyon",
    "Olympique Lyonnais": "Lyon",
    "Olympique Marseille": "Marseille",
    "OGC Nice": "Nice",
    "Paris FC": "Paris FC",
    "Paris Saint-Germain": "PSG",
    "PSG": "PSG",
    "RC Lens": "Lens",
    "RC Strasbourg": "Strasbourg",
    "RC Strasbourg Alsace": "Strasbourg",
    "Rennes": "Rennes",
    "Stade Brestois": "Brest",
    "Stade Brestois 29": "Brest",
    "Stade Rennais": "Rennes",
    "Stade Rennais FC": "Rennes",
    "Strasbourg": "Strasbourg",
    "Toulouse": "Toulouse",
    "Toulouse FC": "Toulouse",
}

COLS = ["squad", "date", "opponent", "home_away", "formation",
        "starter", "jersey", "player", "espn_pos", "formation_place", "event_id"]


def normalize_team(team: dict | str | None) -> str:
    if isinstance(team, dict):
        raw = team.get("displayName") or team.get("name") or team.get("shortDisplayName") or team.get("abbreviation") or ""
        abbr = team.get("abbreviation")
    else:
        raw = str(team or "")
        abbr = raw
    return TEAM_ALIASES.get(raw, SQUAD_BY_ABBR.get(abbr, raw))


def _get(url: str, tries: int = 3) -> dict | None:
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.ok:
                return r.json()
        except Exception as e:
            print(f"  [재시도 {i+1}] {e}")
        time.sleep(0.6)
    return None


def calendar_dates() -> list[str]:
    """시즌 전체 매치데이 날짜(YYYYMMDD) 목록. 첫 scoreboard의 calendar에서."""
    data = _get(f"{ESPN}/scoreboard?dates=20250816")
    cal = (data or {}).get("leagues", [{}])[0].get("calendar", [])
    return [c[:10].replace("-", "") for c in cal]


def events_for_date(yyyymmdd: str) -> dict[str, str]:
    """해당 날짜의 EPL 경기 {event_id: date(YYYY-MM-DD)}."""
    data = _get(f"{ESPN}/scoreboard?dates={yyyymmdd}")
    out: dict[str, str] = {}
    for e in (data or {}).get("events", []):
        eid = e.get("id")
        date = (e.get("date") or "")[:10]
        if eid:
            out[eid] = date
    return out


def parse_lineup(summary: dict, date: str, event_id: str) -> list[dict]:
    """summary JSON → 선수별 행 리스트(선발+교체 모두)."""
    rosters = summary.get("rosters", [])
    if len(rosters) < 2:
        return []
    # 양팀 abbreviation으로 상대팀 산출
    by_ha = {t.get("homeAway"): t.get("team", {}) for t in rosters}
    rows: list[dict] = []
    for t in rosters:
        ha = t.get("homeAway")
        squad = normalize_team(t.get("team", {}))
        opp_team = by_ha.get("away" if ha == "home" else "home")
        opponent = normalize_team(opp_team)
        formation = t.get("formation", "")
        for p in t.get("roster", []):
            pos = p.get("position", {}) or {}
            ath = p.get("athlete", {}) or {}
            rows.append({
                "squad": squad, "date": date, "opponent": opponent,
                "home_away": ha, "formation": formation,
                "starter": bool(p.get("starter")),
                "jersey": p.get("jersey", ""),
                "player": ath.get("displayName", ""),
                "espn_pos": pos.get("abbreviation", ""),
                "formation_place": p.get("formationPlace", ""),
                "event_id": event_id,
            })
    return rows


def fetch_event(event_id: str, date: str = "") -> list[dict]:
    summary = _get(f"{ESPN}/summary?event={event_id}")
    if not summary:
        return []
    if not date:
        date = (summary.get("header", {}).get("competitions", [{}])[0].get("date") or "")[:10]
    return parse_lineup(summary, date, event_id)


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    if dry:
        args.remove("--dry")

    # 특정 event만(디버그)
    if args:
        rows = fetch_event(args[0])
        for r in rows:
            if r["starter"]:
                print(f"  {r['squad']:18} {r['formation']:8} {r['espn_pos']:5} "
                      f"#{str(r['jersey']):>2} {r['player']}")
        print(f"  총 {len(rows)}행")
        return 0

    dates = calendar_dates()
    print(f"매치데이 {len(dates)}일 — event 수집 중...")
    events: dict[str, str] = {}
    for i, d in enumerate(dates):
        events.update(events_for_date(d))
        time.sleep(0.12)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(dates)}일 · event {len(events)}개")
    print(f"총 event {len(events)}개 — 라인업 수집 중...")

    all_rows: list[dict] = []
    for i, (eid, date) in enumerate(sorted(events.items(), key=lambda x: x[1])):
        rows = fetch_event(eid, date)
        all_rows += rows
        time.sleep(0.12)
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(events)}경기 · {len(all_rows)}행")

    if not all_rows:
        print("수집된 라인업이 없습니다.")
        return 1

    df = pd.DataFrame(all_rows)[COLS]
    n_games = df["event_id"].nunique()
    n_starters = df[df["starter"]].shape[0]
    print(f"\n경기 {n_games} · 선수행 {len(df)}(선발 {n_starters}) · 팀 {df['squad'].nunique()}")
    if dry:
        print("[DRY] 저장 안 함.")
        print(df[df["starter"]].head(15).to_string())
    else:
        df.to_csv(OUT, index=False, encoding="utf-8")
        print(f"[OK] 저장: {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
