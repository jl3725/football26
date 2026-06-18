"""
Transfermarkt Premier League injury sync.

Writes:
  data/transfermarkt_injuries_2025_2026.csv

The app reads this CSV only. Run this script daily with Task Scheduler or any
agent runner to refresh active injuries and remove recovered players.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from fetch_transfermarkt import H, TEAM_TM, parse_mv
except ImportError:
    from .fetch_transfermarkt import H, TEAM_TM, parse_mv


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "transfermarkt_injuries_2025_2026.csv"
CHANGES_OUT = DATA / "transfermarkt_injury_changes_2025_2026.csv"
URL = "https://www.transfermarkt.com/premier-league/verletztespieler/wettbewerb/GB1"

_VID_TO_SQUAD = {vid: squad for squad, (_slug, vid) in TEAM_TM.items()}
_TEAM_ALIASES = {
    "Arsenal FC": "Arsenal",
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Burnley FC": "Burnley",
    "Chelsea FC": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton FC": "Everton",
    "Fulham FC": "Fulham",
    "Leeds United": "Leeds United",
    "Liverpool FC": "Liverpool",
    "Manchester City": "Manchester City",
    "Manchester United": "Manchester Utd",
    "Newcastle United": "Newcastle United",
    "Nottingham Forest": "Nottingham Forest",
    "Sunderland AFC": "Sunderland",
    "Tottenham Hotspur": "Tottenham Hotspur",
    "West Ham United": "West Ham United",
    "Wolverhampton Wanderers": "Wolves",
}


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def checked_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def player_id_from_href(href: str) -> str:
    match = re.search(r"/spieler/(\d+)", href or "")
    return match.group(1) if match else ""


def normalize_team(img) -> str:
    if not img:
        return ""
    src = img.get("src", "") or ""
    match = re.search(r"/wappen/(?:tiny|head)/(\d+)\.png", src)
    if match:
        squad = _VID_TO_SQUAD.get(int(match.group(1)), "")
        if squad:
            return squad
    raw = clean_text(img.get("alt") or img.get("title"))
    return _TEAM_ALIASES.get(raw, raw)


def parse_injury_rows(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    rows: list[dict] = []
    for tr in soup.select("table.items tbody > tr.odd, table.items tbody > tr.even"):
        name_a = tr.select_one("td.posrela a[href*='/spieler/']") or tr.select_one("a[href*='/spieler/']")
        if not name_a:
            continue
        player = clean_text(name_a.get_text(" ", strip=True))
        tm_player_id = player_id_from_href(name_a.get("href", ""))

        position = ""
        inline_rows = tr.select("td.posrela table.inline-table tr")
        if len(inline_rows) > 1:
            position = clean_text(inline_rows[1].get_text(" ", strip=True))

        club_img = tr.select_one("img[src*='/wappen/']")
        squad = normalize_team(club_img)

        tds = tr.select("td")
        if not position and len(tds) > 3:
            position = clean_text(tds[3].get_text(" ", strip=True))
        injury = clean_text(tds[5].get_text(" ", strip=True)) if len(tds) > 5 else ""
        until = clean_text(tds[6].get_text(" ", strip=True)) if len(tds) > 6 else ""
        market_value = clean_text(tds[-1].get_text(" ", strip=True)) if tds else ""
        market_value_eur = parse_mv(market_value)

        photo = ""
        player_img = tr.select_one("img.bilderrahmen-fixed")
        if player_img:
            photo = clean_text(player_img.get("data-src") or player_img.get("src"))
            if photo.startswith("data:"):
                photo = ""

        if player and squad:
            rows.append({
                "squad": squad,
                "player": player,
                "position": position,
                "injury": injury,
                "until": until,
                "market_value_eur": market_value_eur or "",
                "tm_player_id": tm_player_id,
                "tm_photo": photo,
                "last_checked": checked_date(),
                "active": "true",
            })
    return rows


def fetch_page() -> str:
    response = requests.get(URL, headers=H, timeout=30)
    response.raise_for_status()
    return response.text


def write_csv(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    fields = [
        "squad", "player", "position", "injury", "until", "market_value_eur",
        "tm_player_id", "tm_photo", "last_checked", "active",
    ]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def row_key(row: dict) -> str:
    return str(row.get("tm_player_id") or f"{row.get('squad')}::{row.get('player')}")


def read_previous_rows() -> list[dict]:
    if not OUT.exists():
        return []
    with OUT.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def detect_changes(previous: list[dict], current: list[dict]) -> list[dict]:
    checked = checked_date()
    prev_map = {row_key(row): row for row in previous}
    curr_map = {row_key(row): row for row in current}
    changes: list[dict] = []

    for key, row in curr_map.items():
        old = prev_map.get(key)
        if old is None:
            changes.append({
                "run_date": checked,
                "event_type": "new_injury",
                "squad": row.get("squad", ""),
                "player": row.get("player", ""),
                "old_injury": "",
                "new_injury": row.get("injury", ""),
                "old_until": "",
                "new_until": row.get("until", ""),
            })
            continue
        if clean_text(old.get("injury")) != clean_text(row.get("injury")) or clean_text(old.get("until")) != clean_text(row.get("until")):
            changes.append({
                "run_date": checked,
                "event_type": "updated",
                "squad": row.get("squad", ""),
                "player": row.get("player", ""),
                "old_injury": old.get("injury", ""),
                "new_injury": row.get("injury", ""),
                "old_until": old.get("until", ""),
                "new_until": row.get("until", ""),
            })

    for key, row in prev_map.items():
        if key not in curr_map:
            changes.append({
                "run_date": checked,
                "event_type": "recovered_or_removed",
                "squad": row.get("squad", ""),
                "player": row.get("player", ""),
                "old_injury": row.get("injury", ""),
                "new_injury": "",
                "old_until": row.get("until", ""),
                "new_until": "",
            })
    return changes


def append_changes(changes: list[dict]) -> None:
    if not changes:
        return
    DATA.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_date", "event_type", "squad", "player",
        "old_injury", "new_injury", "old_until", "new_until",
    ]
    exists = CHANGES_OUT.exists()
    with CHANGES_OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(changes)


def main() -> int:
    previous = read_previous_rows()
    rows = parse_injury_rows(fetch_page())
    rows.sort(key=lambda r: (r["squad"], r["player"]))
    changes = detect_changes(previous, rows)
    write_csv(rows)
    append_changes(changes)
    print(f"Wrote {len(rows)} active injury rows to {OUT}")
    print(f"Detected {len(changes)} injury changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
