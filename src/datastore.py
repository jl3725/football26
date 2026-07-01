"""
데이터 접근 계층 — DB(football.db) 우선, CSV 폴백.

앱/분석 코드는 파일명·경로를 직접 알 필요 없이 `read_table("standings")` 로
현재 활성 리그·시즌 데이터를 얻는다. DB 가 아직 없거나 테이블이 비면 기존
CSV 를 그대로 읽어 반환하므로, 점진 이관 중에도 앱이 깨지지 않는다.

    from datastore import read_table
    standings = read_table("standings")                 # 활성 리그/시즌
    laliga_tbl = read_table("standings", league="LaLiga")
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from leagues import (
    DATA_DIR, SEASON, ACTIVE_LEAGUE, PRIMARY_LEAGUE, data_path,
)

DB_PATH = DATA_DIR / "football.db"


def _db_mtime() -> float:
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def read_table(
    table: str,
    league: str | None = None,
    season: str | None = None,
) -> pd.DataFrame | None:
    """
    테이블 읽기. DB 에 있으면 league/season 으로 필터해서, 없으면 CSV 폴백.

    반환: DataFrame (없으면 None). league/season 컬럼은 필터 후 제거해
    기존 소비 코드와 스키마를 맞춘다.
    """
    league = league or ACTIVE_LEAGUE
    season = season or SEASON

    df = _read_from_db(table, league, season)
    if df is not None:
        return df
    return _read_from_csv(table, league, season)


def _read_from_db(table: str, league: str, season: str) -> pd.DataFrame | None:
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        if not _table_exists(conn, table):
            return None
        df = pd.read_sql(f'SELECT * FROM "{table}"', conn)
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()

    if df.empty:
        return None
    if "league" in df.columns:
        df = df[df["league"] == league]
    if "season" in df.columns:
        df = df[df["season"] == season]
    if df.empty:
        return None
    return df.drop(columns=[c for c in ("league", "season") if c in df.columns]).reset_index(drop=True)


def _read_from_csv(table: str, league: str, season: str) -> pd.DataFrame | None:
    path = data_path(table, league=league, season=season)
    if not path.exists() and league == PRIMARY_LEAGUE:
        # 시즌 토큰 없는 파일(예: players_sample) 도 시도
        alt = DATA_DIR / f"{table}.csv"
        path = alt if alt.exists() else path
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return None


def available_leagues() -> list[str]:
    """DB 에 실제로 데이터가 있는 리그 목록(없으면 활성 리그만)."""
    if not DB_PATH.exists():
        return [ACTIVE_LEAGUE]
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error:
        return [ACTIVE_LEAGUE]
    try:
        if not _table_exists(conn, "standings"):
            return [ACTIVE_LEAGUE]
        df = pd.read_sql('SELECT DISTINCT league FROM "standings"', conn)
        vals = [v for v in df["league"].tolist() if v and v != "_"]
        return vals or [ACTIVE_LEAGUE]
    except Exception:  # noqa: BLE001
        return [ACTIVE_LEAGUE]
    finally:
        conn.close()
