"""
Fetch FBref set-piece related 2025/26 Premier League stats.

Outputs:
  data/fbref_setpieces_players_2025_2026.csv
  data/fbref_setpieces_teams_2025_2026.csv

FBref blocks simple requests, so this uses seleniumbase's undetected Chrome
driver and then parses the rendered tables with pandas.
"""
from __future__ import annotations

import os
import time
from io import StringIO
from pathlib import Path

import pandas as pd
from seleniumbase import Driver
from unidecode import unidecode


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_PLAYERS = DATA / "fbref_setpieces_players_2025_2026.csv"
OUT_TEAMS = DATA / "fbref_setpieces_teams_2025_2026.csv"
SEASON_SLUG = "2025-2026"
COMP = "9"
BASE = "https://fbref.com/en/comps"
WAIT_SECONDS = 35


def norm_name(value: str) -> str:
    return unidecode(str(value)).lower().strip()


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        cols = []
        seen: dict[str, int] = {}
        for parent, child in out.columns:
            parent = "" if str(parent).startswith("Unnamed") else str(parent)
            child = str(child)
            base = child if not parent else f"{parent}_{child}"
            base = (
                base.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
                .replace("%", "pct")
            )
            count = seen.get(base, 0)
            seen[base] = count + 1
            cols.append(base if count == 0 else f"{base}_{count + 1}")
        out.columns = cols
    else:
        out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
    return out


def load_tables(path: str) -> list[pd.DataFrame]:
    url = f"{BASE}/{COMP}/{SEASON_SLUG}/{path}/{SEASON_SLUG}-Premier-League-Stats"
    driver = Driver(uc=True, headless=True, incognito=True)
    try:
        driver.get(url)
        time.sleep(WAIT_SECONDS)
        html = driver.page_source
        title = driver.title or ""
    finally:
        driver.quit()
    if "잠시만 기다리십시오" in title or "Just a moment" in html:
        raise RuntimeError(f"FBref challenge did not clear for {path}")
    return [flatten_columns(t) for t in pd.read_html(StringIO(html))]


def pick_table(tables: list[pd.DataFrame], key_cols: set[str], player: bool) -> pd.DataFrame:
    candidates = []
    for t in tables:
        cols = set(t.columns)
        if key_cols.issubset(cols):
            if player and "player" in cols:
                candidates.append(t)
            elif not player and "squad" in cols and "player" not in cols:
                candidates.append(t)
    if not candidates:
        raise RuntimeError(f"Could not find table with columns: {sorted(key_cols)}")
    return max(candidates, key=len).copy()


def numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def per90(df: pd.DataFrame, source: str, target: str) -> None:
    if source not in df.columns or "90s" not in df.columns:
        df[target] = pd.NA
        return
    n90 = pd.to_numeric(df["90s"], errors="coerce").replace(0, pd.NA)
    df[target] = pd.to_numeric(df[source], errors="coerce") / n90


def clean_player_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["player"].notna() & (df["player"] != "Player")].copy()
    df["norm_key"] = df["player"].map(norm_name)
    numeric_cols = [
        "90s", "pass_types_dead", "pass_types_fk", "pass_types_ti",
        "pass_types_ck", "corner_kicks_in", "corner_kicks_out",
        "corner_kicks_str", "sca_sca", "sca_sca90", "sca_types_passdead",
        "gca_gca", "gca_gca90", "gca_types_passdead",
        "performance_fls", "performance_fld", "performance_pkwon", "performance_pkcon",
    ]
    return numeric(df, numeric_cols)


def clean_team_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["squad"].notna() & (df["squad"] != "Squad")].copy()
    numeric_cols = [
        "90s", "pass_types_dead", "pass_types_fk", "pass_types_ti",
        "pass_types_ck", "corner_kicks_in", "corner_kicks_out",
        "corner_kicks_str", "sca_sca", "sca_sca90", "sca_types_passdead",
        "gca_gca", "gca_gca90", "gca_types_passdead",
        "performance_fls", "performance_fld", "performance_pkwon", "performance_pkcon",
    ]
    return numeric(df, numeric_cols)


def select_player_cols(df: pd.DataFrame) -> pd.DataFrame:
    for src, dst in [
        ("pass_types_dead", "dead_ball_passes_per90"),
        ("pass_types_fk", "free_kick_passes_per90"),
        ("pass_types_ti", "throw_ins_per90"),
        ("pass_types_ck", "corner_kicks_per90"),
        ("corner_kicks_in", "inswing_corners_per90"),
        ("corner_kicks_out", "outswing_corners_per90"),
        ("corner_kicks_str", "straight_corners_per90"),
        ("sca_types_passdead", "dead_ball_sca_per90"),
        ("gca_types_passdead", "dead_ball_gca_per90"),
        ("performance_fls", "fouls_per90_fbref"),
        ("performance_fld", "fouled_per90_fbref"),
        ("performance_pkwon", "pens_won_per90_fbref"),
        ("performance_pkcon", "pens_conceded_per90_fbref"),
    ]:
        per90(df, src, dst)
    keep = [
        "player", "norm_key", "squad", "pos", "90s",
        "dead_ball_passes_per90", "free_kick_passes_per90",
        "throw_ins_per90", "corner_kicks_per90",
        "inswing_corners_per90", "outswing_corners_per90",
        "straight_corners_per90", "sca_sca90", "dead_ball_sca_per90",
        "gca_gca90", "dead_ball_gca_per90",
        "fouls_per90_fbref", "fouled_per90_fbref",
        "pens_won_per90_fbref", "pens_conceded_per90_fbref",
    ]
    return df[[c for c in keep if c in df.columns]].round(4)


def select_team_cols(df: pd.DataFrame) -> pd.DataFrame:
    for src, dst in [
        ("pass_types_dead", "dead_ball_passes_per90"),
        ("pass_types_fk", "free_kick_passes_per90"),
        ("pass_types_ti", "throw_ins_per90"),
        ("pass_types_ck", "corner_kicks_per90"),
        ("corner_kicks_in", "inswing_corners_per90"),
        ("corner_kicks_out", "outswing_corners_per90"),
        ("corner_kicks_str", "straight_corners_per90"),
        ("sca_types_passdead", "dead_ball_sca_per90"),
        ("gca_types_passdead", "dead_ball_gca_per90"),
        ("performance_fls", "fouls_per90_fbref"),
        ("performance_fld", "fouled_per90_fbref"),
        ("performance_pkwon", "pens_won_per90_fbref"),
        ("performance_pkcon", "pens_conceded_per90_fbref"),
    ]:
        per90(df, src, dst)
    keep = [
        "squad", "90s", "dead_ball_passes_per90", "free_kick_passes_per90",
        "throw_ins_per90", "corner_kicks_per90", "inswing_corners_per90",
        "outswing_corners_per90", "straight_corners_per90", "sca_sca90",
        "dead_ball_sca_per90", "gca_gca90", "dead_ball_gca_per90",
        "fouls_per90_fbref", "fouled_per90_fbref",
        "pens_won_per90_fbref", "pens_conceded_per90_fbref",
    ]
    return df[[c for c in keep if c in df.columns]].round(4)


def main() -> int:
    os.environ.setdefault("SOCCERDATA_DIR", str(ROOT / ".soccerdata"))
    DATA.mkdir(parents=True, exist_ok=True)

    passing = load_tables("passing_types")
    gca = load_tables("gca")
    misc = load_tables("misc")

    passing_players = clean_player_rows(
        pick_table(passing, {"player", "squad", "pass_types_ck"}, player=True)
    )
    gca_players = clean_player_rows(
        pick_table(gca, {"player", "squad", "sca_types_passdead"}, player=True)
    )
    misc_players = clean_player_rows(
        pick_table(misc, {"player", "squad", "performance_fls", "performance_fld"}, player=True)
    )

    passing_teams = clean_team_rows(
        pick_table(passing, {"squad", "pass_types_ck"}, player=False)
    )
    gca_teams = clean_team_rows(
        pick_table(gca, {"squad", "sca_types_passdead"}, player=False)
    )
    misc_teams = clean_team_rows(
        pick_table(misc, {"squad", "performance_fls", "performance_fld"}, player=False)
    )

    players = (
        passing_players
        .merge(gca_players, on=["player", "norm_key", "squad", "pos"], how="outer", suffixes=("", "_gca"))
        .merge(misc_players, on=["player", "norm_key", "squad", "pos"], how="outer", suffixes=("", "_misc"))
    )
    teams = (
        passing_teams
        .merge(gca_teams, on=["squad"], how="outer", suffixes=("", "_gca"))
        .merge(misc_teams, on=["squad"], how="outer", suffixes=("", "_misc"))
    )

    select_player_cols(players).to_csv(OUT_PLAYERS, index=False, encoding="utf-8")
    select_team_cols(teams).to_csv(OUT_TEAMS, index=False, encoding="utf-8")

    print(f"[OK] {OUT_PLAYERS.name}: {len(players)} rows")
    print(f"[OK] {OUT_TEAMS.name}: {len(teams)} rows")
    print(select_team_cols(teams).sort_values("corner_kicks_per90", ascending=False).head(8).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
