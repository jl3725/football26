"""
Collect Transfermarkt contract expiry dates for Premier League squads.

Usage:
    python src/sync_transfermarkt_contracts.py --write
    python src/sync_transfermarkt_contracts.py Arsenal --write
    python src/sync_transfermarkt_contracts.py Arsenal --snapshot-only --write

The script writes data/transfermarkt_contracts_2025_2026.csv and, unless
--snapshot-only is used, merges tm_contract_until/tm_id into the app player CSVs.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import data_path  # noqa: E402
from fetch_transfermarkt import H, SEASON, TEAM_TM, norm  # noqa: E402

PLAYERS_FULL = data_path("players_full")
PLAYERS_BASE = data_path("players")
SNAPSHOT = data_path("transfermarkt_contracts")

MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
TEXT_DATE_RE = re.compile(
    rf"\b(?:{'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}\b"
)
DMY_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
CONTRACT_ALIAS = {
    "gabriel magalhaes": "gabriel",
    "savio": "savinho",
}


def _clean_date(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text or text in {"-", "?"}:
        return ""
    dmy = DMY_DATE_RE.search(text)
    if dmy:
        day, month, year = dmy.groups()
        return f"{year}-{month}-{day}"
    match = TEXT_DATE_RE.search(text)
    return match.group(0) if match else ""


def _player_id_from_href(href: str) -> str:
    match = re.search(r"/spieler/(\d+)", href or "")
    return match.group(1) if match else ""


def _parse_contract_from_row(tr) -> str:
    # In detailed squad pages the contract cell is usually a centered td.
    # DOB/age cells also contain dates, so skip cells that include "(age)".
    centered = [td.get_text(" ", strip=True) for td in tr.select("td.zentriert")]
    for text in reversed(centered):
        if re.search(r"\(\d{1,2}\)", text):
            continue
        contract = _clean_date(text)
        if contract:
            return contract

    # Fallback: inspect direct cells from the end, still avoiding DOB cells.
    cells = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
    for text in reversed(cells):
        if re.search(r"\(\d{1,2}\)", text):
            continue
        contract = _clean_date(text)
        if contract:
            return contract
    return ""


def _parse_joined_from_row(tr) -> str:
    cells = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
    if len(cells) > 6:
        joined = _clean_date(cells[6])
        if joined:
            return joined

    # Fallback for slightly different table layouts: first non-DOB date from the left.
    for text in [td.get_text(" ", strip=True) for td in tr.select("td.zentriert")]:
        if re.search(r"\(\d{1,2}\)", text):
            continue
        joined = _clean_date(text)
        if joined:
            return joined
    return ""


def scrape_team_contracts(team: str) -> list[dict]:
    slug, vid = TEAM_TM[team]
    url = f"https://www.transfermarkt.com/{slug}/kader/verein/{vid}/saison_id/{SEASON}/plus/1"
    response = requests.get(url, headers=H, timeout=25)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    table = soup.select_one("table.items")
    if not table:
        raise RuntimeError(f"{team}: could not find Transfermarkt squad table")

    checked_at = datetime.now().isoformat(timespec="seconds")
    rows = []
    for tr in table.select("tbody > tr.odd, tbody > tr.even"):
        name_a = tr.select_one("td.posrela .hauptlink a") or tr.select_one("td.hauptlink a")
        if not name_a:
            continue
        name = name_a.get_text(strip=True)
        href = name_a.get("href", "")
        tm_id = _player_id_from_href(href)
        img = tr.select_one("img.bilderrahmen-fixed")
        photo = (img.get("data-src") or img.get("src") or "") if img else ""
        contract = _parse_contract_from_row(tr)
        joined = _parse_joined_from_row(tr)
        rows.append(
            {
                "detected_at": checked_at,
                "squad": team,
                "player": name,
                "norm_key": norm(name),
                "tm_id": tm_id,
                "joined_date": joined,
                "contract_until": contract,
                "contract_signal": "",
                "tm_photo": photo,
                "source": url,
            }
        )
    return rows


def collect_contracts(teams: list[str], pause: float) -> pd.DataFrame:
    all_rows: list[dict] = []
    for i, team in enumerate(teams):
        if i:
            time.sleep(pause)
        rows = scrape_team_contracts(team)
        with_contract = sum(1 for row in rows if row.get("contract_until"))
        print(f"[{team}] {with_contract}/{len(rows)} contracts")
        all_rows.extend(rows)
    return pd.DataFrame(all_rows)


def merge_contracts(player_path: Path, contracts: pd.DataFrame) -> int:
    if not player_path.exists() or contracts.empty:
        return 0

    df = pd.read_csv(player_path)
    if "squad" not in df.columns or "player" not in df.columns:
        return 0

    if "norm_key" not in df.columns:
        df["norm_key"] = df["player"].map(norm)
    for col in (
        "tm_contract_until", "tm_id", "tm_contract_checked_at",
        "tm_joined_date", "tm_contract_signal", "tm_photo",
    ):
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = df[col].astype("object")

    contracts = contracts.copy()
    contracts = contracts.dropna(subset=["squad", "norm_key"])
    contracts = contracts.drop_duplicates(["squad", "norm_key"], keep="last")
    contract_map = {
        (str(row["squad"]), str(row["norm_key"])): row
        for _, row in contracts.iterrows()
    }

    def same_text(current, incoming: str) -> bool:
        cur = "" if pd.isna(current) else str(current).strip()
        inc = str(incoming or "").strip()
        if cur.endswith(".0") and cur[:-2].isdigit():
            cur = cur[:-2]
        if inc.endswith(".0") and inc[:-2].isdigit():
            inc = inc[:-2]
        return cur == inc

    changed = 0
    for idx, row in df.iterrows():
        row_norm = str(row["norm_key"])
        key = (str(row["squad"]), CONTRACT_ALIAS.get(row_norm, row_norm))
        rec = contract_map.get(key)
        if rec is None:
            continue
        row_changed = False
        contract = str(rec.get("contract_until") or "").strip()
        tm_id = str(rec.get("tm_id") or "").strip()
        checked_at = str(rec.get("detected_at") or "").strip()
        joined = str(rec.get("joined_date") or "").strip()
        signal = str(rec.get("contract_signal") or "").strip()
        photo = str(rec.get("tm_photo") or "").strip()

        if contract and not same_text(df.at[idx, "tm_contract_until"], contract):
            df.at[idx, "tm_contract_until"] = contract
            row_changed = True
        if tm_id and not same_text(df.at[idx, "tm_id"], tm_id):
            df.at[idx, "tm_id"] = tm_id
            row_changed = True
        if checked_at:
            df.at[idx, "tm_contract_checked_at"] = checked_at
        if joined and not same_text(df.at[idx, "tm_joined_date"], joined):
            df.at[idx, "tm_joined_date"] = joined
            row_changed = True
        if not same_text(df.at[idx, "tm_contract_signal"], signal):
            df.at[idx, "tm_contract_signal"] = signal
            row_changed = True
        current_photo = "" if pd.isna(df.at[idx, "tm_photo"]) else str(df.at[idx, "tm_photo"]).strip()
        if photo and (not current_photo or current_photo.endswith(".png") or "?lm=" not in current_photo):
            df.at[idx, "tm_photo"] = photo
            row_changed = True
        if row_changed:
            changed += 1

    df.to_csv(player_path, index=False, encoding="utf-8")
    return changed


def _date_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    return tuple(map(int, match.groups()))


def _active_transfer_window_start(detected_at: str) -> pd.Timestamp:
    detected = pd.to_datetime(detected_at, errors="coerce")
    if pd.isna(detected):
        detected = pd.Timestamp.now()
    year = int(detected.year)
    # Summer window tracking starts June 1; winter window tracking starts January 1.
    if int(detected.month) >= 6:
        return pd.Timestamp(year=year, month=6, day=1)
    return pd.Timestamp(year=year, month=1, day=1)


def _is_active_window_join(joined_date: str, detected_at: str) -> bool:
    joined = _date_tuple(joined_date)
    if joined is None:
        return False
    window_start = _active_transfer_window_start(detected_at)
    return pd.Timestamp(*joined) >= window_start


def _is_recent_registration(joined_date: str, detected_at: str) -> bool:
    try:
        joined = pd.to_datetime(joined_date, errors="coerce")
        detected = pd.to_datetime(detected_at, errors="coerce")
    except Exception:
        return False
    if pd.isna(joined) or pd.isna(detected):
        return False
    delta_days = (detected.normalize() - joined.normalize()).days
    return 0 <= delta_days <= 90


def add_contract_signals(contracts: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    contracts = contracts.copy()
    if "contract_signal" not in contracts.columns:
        contracts["contract_signal"] = ""

    previous_map = {}
    if (
        previous is not None
        and not previous.empty
        and {"squad", "norm_key", "contract_until"}.issubset(previous.columns)
    ):
        previous_map = {
            (str(row["squad"]), str(row["norm_key"])): str(row.get("contract_until") or "").strip()
            for _, row in previous.iterrows()
        }

    signals = []
    for _, row in contracts.iterrows():
        key = (str(row.get("squad")), str(row.get("norm_key")))
        contract = str(row.get("contract_until") or "").strip()
        previous_contract = previous_map.get(key)
        joined_date = str(row.get("joined_date") or "")
        detected_at = str(row.get("detected_at") or "")
        if _is_active_window_join(joined_date, detected_at):
            signal = "NEW"
        elif contract and previous_contract and contract != previous_contract:
            signal = "RENEW"
        elif _is_recent_registration(joined_date, detected_at):
            signal = "RENEW"
        else:
            signal = ""
        signals.append(signal)
    contracts["contract_signal"] = signals
    return contracts


def write_snapshot(contracts: pd.DataFrame, fetched_teams: list[str]) -> pd.DataFrame:
    if SNAPSHOT.exists():
        try:
            previous = pd.read_csv(SNAPSHOT)
        except pd.errors.EmptyDataError:
            previous = pd.DataFrame()
    else:
        previous = pd.DataFrame()

    contracts = add_contract_signals(contracts, previous)

    if not previous.empty and "squad" in previous.columns:
        previous = previous[~previous["squad"].astype(str).isin(set(fetched_teams))]

    merged = pd.concat([previous, contracts], ignore_index=True)
    if {"squad", "norm_key", "detected_at"}.issubset(merged.columns):
        merged = merged.drop_duplicates(["squad", "norm_key"], keep="last")
    merged.to_csv(SNAPSHOT, index=False, encoding="utf-8")
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Transfermarkt contract expiry dates.")
    parser.add_argument("teams", nargs="*", help="Team names to fetch. Defaults to all EPL teams.")
    parser.add_argument("--write", action="store_true", help="Write snapshot and merge player CSVs.")
    parser.add_argument("--snapshot-only", action="store_true", help="Do not merge into player CSVs.")
    parser.add_argument("--pause", type=float, default=2.0, help="Seconds between team requests.")
    args = parser.parse_args(argv)

    teams = args.teams or list(TEAM_TM)
    unknown = [team for team in teams if team not in TEAM_TM]
    if unknown:
        raise SystemExit(f"Unknown team(s): {', '.join(unknown)}")

    contracts = collect_contracts(teams, pause=args.pause)
    if contracts.empty:
        print("[contracts] no rows collected")
        return 1

    if not args.write:
        print(contracts[["squad", "player", "contract_until"]].head(20).to_string(index=False))
        print("[DRY] Run with --write to save the snapshot.")
        return 0

    snapshot = write_snapshot(contracts, teams)
    print(f"[OK] wrote {SNAPSHOT.relative_to(ROOT)} ({len(snapshot)} rows)")

    if args.snapshot_only:
        return 0

    changed_full = merge_contracts(PLAYERS_FULL, snapshot)
    changed_base = merge_contracts(PLAYERS_BASE, snapshot)
    print(f"[OK] merged contracts: players_full={changed_full}, players={changed_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
