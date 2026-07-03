"""
Fetch public StatBunker Premier League 2025/26 team stats.

Outputs:
  data/statbunker_team_stats_2025_2026.csv
  data/statbunker_penalty_takers_2025_2026.csv

StatBunker's team goal-type table has malformed row starts, so the parser reads
the table body by closed-row chunks instead of relying on pandas.read_html.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from leagues import ACTIVE_LEAGUE, data_path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COMP_IDS = {
    "EPL": 776,
    "LaLiga": 777,
    "SerieA": 785,
}
COMP_ID = COMP_IDS.get(ACTIVE_LEAGUE)
BASE = "https://www.statbunker.com/competitions/{slug}?comp_id={comp_id}"
OUT_TEAMS = data_path("statbunker_team_stats")
OUT_PENALTY_TAKERS = data_path("statbunker_penalty_takers")


TEAM_ALIASES = {
    "Manchester United": "Manchester Utd",
    "Wolverhampton Wanderers": "Wolves",
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Deportivo Alavés": "Alavés",
    "Atlético Madrid": "Atlético Madrid",
    "Atlético de Madrid": "Atlético Madrid",
    "Athletic Bilbao": "Athletic Club",
    "FC Barcelona": "Barcelona",
    "Celta Vigo": "Celta Vigo",
    "Celta de Vigo": "Celta Vigo",
    "Villarreal CF": "Villarreal",
    "Real Betis Balompie": "Real Betis",
    "Real Betis Balompié": "Real Betis",
    "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia",
    "RCD Espanyol": "Espanyol",
    "Espanyol Barcelona": "Espanyol",
    "Elche CF": "Elche",
    "Levante UD": "Levante",
    "CA Osasuna": "Osasuna",
    "Getafe CF": "Getafe",
    "RCD Mallorca": "Mallorca",
    "Real Oviedo": "Oviedo",
    "AC Milan": "Milan",
    "ACF Fiorentina": "Fiorentina",
    "AS Roma": "Roma",
    "Atalanta BC": "Atalanta",
    "Bologna FC": "Bologna",
    "Bologna FC 1909": "Bologna",
    "Cagliari Calcio": "Cagliari",
    "Como 1907": "Como",
    "FC Internazionale Milano": "Inter",
    "Genoa CFC": "Genoa",
    "Inter Milan": "Inter",
    "Internazionale": "Inter",
    "Juventus FC": "Juventus",
    "Parma Calcio 1913": "Parma",
    "Pisa SC": "Pisa",
    "SSC Napoli": "Napoli",
    "SS Lazio": "Lazio",
    "Torino FC": "Torino",
    "Udinese Calcio": "Udinese",
    "US Cremonese": "Cremonese",
    "US Lecce": "Lecce",
    "US Sassuolo": "Sassuolo",
    "1. FC Heidenheim": "Heidenheim",
    "1. FC Heidenheim 1846": "Heidenheim",
    "1. FC Köln": "Köln",
    "1. FC Koln": "Köln",
    "1. FC Union Berlin": "Union Berlin",
    "1. FSV Mainz 05": "Mainz 05",
    "Bayer Leverkusen": "Leverkusen",
    "Bayer 04 Leverkusen": "Leverkusen",
    "Borussia Dortmund": "Dortmund",
    "Borussia M'gladbach": "Gladbach",
    "Borussia Monchengladbach": "Gladbach",
    "Borussia Mönchengladbach": "Gladbach",
    "Bayern Munich": "Bayern Munich",
    "Eintracht Frankfurt": "Frankfurt",
    "FC Augsburg": "Augsburg",
    "FC Bayern Munich": "Bayern Munich",
    "FC Bayern München": "Bayern Munich",
    "FC St Pauli": "St Pauli",
    "FC St. Pauli": "St Pauli",
    "Hamburger SV": "Hamburger SV",
    "RB Leipzig": "RB Leipzig",
    "SC Freiburg": "Freiburg",
    "SV Werder Bremen": "Werder Bremen",
    "TSG 1899 Hoffenheim": "Hoffenheim",
    "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart",
    "VfL Wolfsburg": "Wolfsburg",
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def as_int(value: str) -> int:
    value = clean_text(value).replace(",", "")
    if value in {"", "-"}:
        return 0
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else 0


def as_float(value: str) -> float:
    value = clean_text(value).replace(",", "")
    if value in {"", "-"}:
        return 0.0
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else 0.0


def normalize_team(team: str) -> str:
    return TEAM_ALIASES.get(clean_text(team), clean_text(team))


def fetch_html(slug: str) -> str:
    if COMP_ID is None:
        raise RuntimeError(f"No StatBunker comp_id configured for {ACTIVE_LEAGUE}")
    url = BASE.format(slug=slug, comp_id=COMP_ID)
    response = requests.get(
        url,
        timeout=90,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    return response.text


def parse_table_rows(html: str) -> list[list[str]]:
    match = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    chunks = match.group(1).split("</tr>")
    rows: list[list[str]] = []
    for chunk in chunks:
        cells = BeautifulSoup(chunk, "html.parser").select("td")
        if not cells:
            continue
        values = [clean_text(cell.get_text(" ", strip=True).replace("More", "")) for cell in cells]
        values = values[:-1] if values and values[-1] == "" else values
        if values:
            rows.append(values)
    return rows


def merge_team_row(rows: dict[str, dict], team: str, values: dict) -> None:
    team = normalize_team(team)
    if not team:
        return
    rows.setdefault(team, {"squad": team}).update(values)


def build_team_stats() -> list[dict]:
    teams: dict[str, dict] = {}

    for row in parse_table_rows(fetch_html("TeamsGoalScorersTypeOfPlay")):
        if len(row) < 10:
            continue
        merge_team_row(teams, row[0], {
            "goals_statbunker": as_int(row[1]),
            "open_play_goals": as_int(row[2]),
            "cross_goals": as_int(row[3]),
            "free_kick_goals": as_int(row[4]),
            "direct_free_kick_goals": as_int(row[5]),
            "throw_in_goals": as_int(row[6]),
            "penalty_goals_type": as_int(row[7]),
            "corner_goals": as_int(row[8]),
            "other_goals": as_int(row[9]),
        })

    for row in parse_table_rows(fetch_html("ForPenalty")):
        if len(row) < 7:
            continue
        merge_team_row(teams, row[0], {
            "penalties_for": as_int(row[1]),
            "penalties_for_home": as_int(row[2]),
            "penalties_for_away": as_int(row[3]),
            "penalties_scored_for": as_int(row[4]),
            "penalties_missed_for": as_int(row[5]),
            "penalties_saved_for": as_int(row[6]),
        })

    for row in parse_table_rows(fetch_html("AgainstPenalty")):
        if len(row) < 7:
            continue
        merge_team_row(teams, row[0], {
            "penalties_against": as_int(row[1]),
            "penalties_against_home": as_int(row[2]),
            "penalties_against_away": as_int(row[3]),
            "penalties_scored_against": as_int(row[4]),
            "penalties_missed_against": as_int(row[5]),
            "penalties_saved_against": as_int(row[6]),
        })

    for row in parse_table_rows(fetch_html("ClubBookings")):
        if len(row) < 13:
            continue
        merge_team_row(teams, row[0], {
            "matches_statbunker": as_int(row[1]),
            "yellow_cards": as_int(row[2]),
            "second_yellow_reds": as_int(row[3]),
            "red_cards": as_int(row[4]),
            "yellow_cards_per_match": as_float(row[5]),
            "first_half_yellows": as_int(row[6]),
            "second_half_yellows": as_int(row[7]),
            "home_yellows": as_int(row[8]),
            "away_yellows": as_int(row[9]),
            "wins_with_cards": as_int(row[10]),
            "draws_with_cards": as_int(row[11]),
            "losses_with_cards": as_int(row[12]),
        })

    for row in teams.values():
        non_pen_set_piece = (
            row.get("corner_goals", 0)
            + row.get("free_kick_goals", 0)
            + row.get("direct_free_kick_goals", 0)
            + row.get("throw_in_goals", 0)
        )
        row["non_penalty_set_piece_goals"] = non_pen_set_piece
        row["dead_ball_goals_including_pens"] = non_pen_set_piece + row.get("penalty_goals_type", 0)

    return sorted(teams.values(), key=lambda r: r["squad"])


def build_penalty_takers() -> list[dict]:
    rows = []
    for row in parse_table_rows(fetch_html("Penalties")):
        if len(row) < 8:
            continue
        rows.append({
            "player": row[0],
            "squad": normalize_team(row[1]),
            "penalties_taken": as_int(row[2]),
            "home": as_int(row[3]),
            "away": as_int(row[4]),
            "scored": as_int(row[5]),
            "missed": as_int(row[6]),
            "saved": as_int(row[7]),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows parsed for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["squad"] if "squad" in rows[0] else []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    team_rows = build_team_stats()
    penalty_takers = build_penalty_takers()
    write_csv(OUT_TEAMS, team_rows)
    write_csv(OUT_PENALTY_TAKERS, penalty_takers)
    print(f"[OK] wrote {OUT_TEAMS} ({len(team_rows)} teams)")
    print(f"[OK] wrote {OUT_PENALTY_TAKERS} ({len(penalty_takers)} players)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
