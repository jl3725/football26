"""
Transfermarkt per-player INJURY HISTORY → season games missed.

Unlike fetch_transfermarkt_injuries.py (which only scrapes currently-injured
players), this walks each squad player's injury-history page and sums the
"Games missed" column for the 2025/26 season. This is what powers the Analytics
"시즌 부상 결장" block: how many league/cup matches a player sat out injured.

Writes (merge, per squad):
  data/tm_injury_history_2025_2026.csv
    squad, player, tm_player_id, season, games_missed, spells, days_out,
    injuries, last_checked

Usage:
  python -m src.fetch_tm_injury_history                 # all 20 squads (~10 min)
  python -m src.fetch_tm_injury_history Arsenal         # one squad
  python -m src.fetch_tm_injury_history "Arsenal" "Chelsea"
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from leagues import data_path  # noqa: E402  (리그 인지 — FB_LEAGUE 로 EPL/LaLiga 전환)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA_PATH = data_path("players_full")           # 활성 리그 players_full
OUT = data_path("tm_injury_history")            # 활성 리그 tm_injury_history
SEASON = "25/26"

H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
FIELDS = ["squad", "player", "tm_player_id", "season", "games_missed",
          "spells", "days_out", "injuries", "spells_json", "last_checked"]


def checked_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def tm_id_from_photo(url) -> str:
    m = re.search(r"/portrait/\w+/(\d+)-", str(url or ""))
    return m.group(1) if m else ""


def parse_history(page_html: str) -> dict:
    """Sum the SEASON rows of a player's injury-history table."""
    soup = BeautifulSoup(page_html, "lxml")
    table = soup.select_one("table.items")
    games = days = spells = 0
    injuries: list[str] = []
    spell_rows: list[dict] = []
    if not table:
        return {"games_missed": 0, "spells": 0, "days_out": 0, "injuries": "", "spells_json": "[]"}
    for tr in table.select("tbody tr"):
        tds = tr.select("td")
        if len(tds) < 6:
            continue
        if tds[0].get_text(strip=True) != SEASON:
            continue
        spells += 1
        injury = tds[1].get_text(" ", strip=True)
        injuries.append(injury)
        frm = tds[2].get_text(" ", strip=True)
        until = tds[3].get_text(" ", strip=True)
        dtxt = re.sub(r"[^0-9]", "", tds[4].get_text(strip=True))
        gtxt = tds[5].get_text(strip=True)
        gnum = int(gtxt) if gtxt.isdigit() else 0
        if dtxt:
            days += int(dtxt)
        games += gnum
        spell_rows.append({"injury": injury, "from": frm, "until": until, "games": gnum})
    import json
    return {
        "spells_json": json.dumps(spell_rows, ensure_ascii=False),
        "games_missed": games,
        "spells": spells,
        "days_out": days,
        "injuries": " · ".join(dict.fromkeys(injuries)),
    }


def fetch_player(tm_id: str) -> dict:
    url = f"https://www.transfermarkt.com/-/verletzungen/spieler/{tm_id}"
    resp = requests.get(url, headers=H, timeout=30)
    resp.raise_for_status()
    return parse_history(resp.text)


def read_existing() -> dict:
    if not OUT.exists():
        return {}
    with OUT.open("r", newline="", encoding="utf-8") as f:
        return {f"{r['squad']}::{r['player']}": r for r in csv.DictReader(f)}


def write_rows(rowmap: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    rows = sorted(rowmap.values(), key=lambda r: (r["squad"], -int(r.get("games_missed") or 0)))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    df = pd.read_csv(DATA_PATH)
    if "tm_player_id" in df.columns:
        df["__tmid"] = df["tm_player_id"].apply(lambda v: str(int(v)) if pd.notna(v) and str(v).strip() not in {"", "nan"} else "")
    else:
        df["__tmid"] = ""
    need = df["__tmid"] == ""
    if "tm_photo" in df.columns:
        df.loc[need, "__tmid"] = df.loc[need, "tm_photo"].map(tm_id_from_photo)

    teams = argv or sorted(df["squad"].dropna().astype(str).unique().tolist())
    rowmap = read_existing()
    today = checked_date()
    done = skipped = 0

    for team in teams:
        squad = df[df["squad"].astype(str) == team]
        if squad.empty:
            print(f"  ! no players for '{team}'")
            continue
        print(f"[{team}] {len(squad)} players")
        for _, p in squad.iterrows():
            tm_id = str(p["__tmid"])
            player = str(p["player"])
            if not tm_id:
                skipped += 1
                continue
            try:
                info = fetch_player(tm_id)
            except Exception as e:  # noqa: BLE001
                print(f"    x {player} ({tm_id}): {e}")
                skipped += 1
                time.sleep(1.0)
                continue
            rowmap[f"{team}::{player}"] = {
                "squad": team, "player": player, "tm_player_id": tm_id,
                "season": SEASON, "last_checked": today, **info,
            }
            done += 1
            if info["games_missed"]:
                print(f"    · {player}: {info['games_missed']}경기 결장 ({info['spells']}회)")
            time.sleep(1.2)
        write_rows(rowmap)  # checkpoint after each team

    print(f"Done. scraped={done} skipped={skipped} → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
