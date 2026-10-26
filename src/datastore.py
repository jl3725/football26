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
import threading
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from leagues import (
    DATA_DIR, SEASON, ACTIVE_LEAGUE, PRIMARY_LEAGUE, data_path,
)

DB_PATH = DATA_DIR / "football.db"
# 뉴스 표는 따로 둔 파일 — 실행 중인 서버가 뉴스만 갈아 끼우고(src/live_sync.py), 뉴스 캐시만 무효화되게(src/news_view.py).
# 파일이 없으면(옛 빌드) football.db 에서 읽는다
NEWS_VIEW_PATH = DATA_DIR / "news_view.db"
NEWS_TABLES = frozenset({"news_articles", "news_players", "news_meta"})


def db_path(table: str) -> Path:
    """표가 들어 있는 DB 파일."""
    return NEWS_VIEW_PATH if table in NEWS_TABLES and NEWS_VIEW_PATH.exists() else DB_PATH


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def news_mtime() -> float:
    """뉴스 표 파일 시각 — 뉴스 캐시 열쇠(api _memo(news=True))."""
    return _mtime(db_path("news_articles"))


def forget(tables) -> int:
    """이 표들의 읽기 캐시를 버린다 — 실행 중 뉴스를 갈아 끼운 뒤 옛 사본(수십 MB)이 LRU 로 밀려날 때까지 남지 않게."""
    tables = set(tables)
    with _CACHE_LOCK:
        keys = [k for k in _CACHE if k[0] in tables]
        for k in keys:
            _CACHE.pop(k, None)
    return len(keys)

# DB 읽기 캐시 — API 요청 하나가 같은 테이블을 수십 번 읽었다(추천 1회에 read_table 40회, 무료 인스턴스
# 에서 수 초). 키에 DB 수정 시각을 넣어 배포·재빌드 시 자동 무효화. 호출부가 고쳐 써도 안전하게 사본을 준다.
_CACHE: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_CACHE_MAX = 48
_CACHE_LOCK = threading.Lock()


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

    key = (table, league, season, _mtime(db_path(table)))
    if _unscoped(table):
        # 리그·시즌 열이 없는 표(뉴스 기사 등)는 리그마다 같은 표 전체가 읽혔다 — 사본을 리그마다 캐시하면
        # 뉴스 3만 건(43MB) × 8개 리그로 무료 인스턴스(512MB)를 거의 채운다(2026-10-21). 한 벌만 둔다.
        key = (table, "*", "*", key[3])
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
    if hit is not None:
        return hit.copy()
    df = _read_from_db(table, league, season)
    if df is not None:
        df = _cleanse_names(table, df, league, season)
        with _CACHE_LOCK:
            _CACHE[key] = df
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
        return df.copy()
    return _cleanse_names(table, _read_from_csv(table, league, season), league, season)   # CSV 폴백은 캐시 안 함


_SCOPE: dict = {}


def _unscoped(table: str) -> bool:
    """리그·시즌 열도, 리그별로 달라지는 정규화 대상(squad·선수 이름)도 없는 표인가 — DB 파일 시각마다 한 번 확인."""
    path = db_path(table)
    mt = _mtime(path)
    hit = _SCOPE.get(table)
    if hit and hit[0] == mt:
        return hit[1]
    out = False
    if path.exists():
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            finally:
                conn.close()
            try:
                import player_names as pn  # noqa: PLC0415
                named = table in pn.TABLE_COLS
            except ImportError:
                named = False
            out = bool(cols) and not ({"league", "season", "squad"} & cols) and not named
        except sqlite3.Error:
            out = False
    _SCOPE[table] = (mt, out)
    return out


def _canon_squads(df: pd.DataFrame, league: str) -> pd.DataFrame:
    """squad 열을 표준 클럽 표기로(src/squads.canonical_squad — 수동·IDENTITY 자동 별칭). 출처마다 'Sparta Rotterdam'·
    'Sparta R.' 처럼 달라 FotMob 평점·결장이 그 클럽 선수에 안 붙던 것(2026-10-20)."""
    if "squad" not in df.columns or df.empty:
        return df
    try:
        import squads  # noqa: PLC0415
    except ImportError:
        return df
    uniq = df["squad"].dropna().astype(str).unique()
    m = {s: squads.canonical_squad(s, league) for s in uniq}
    if all(k == v for k, v in m.items()):
        return df
    out = df.copy()
    out["squad"] = out["squad"].map(lambda s: m.get(str(s), s) if s == s else s)
    return out


def _cleanse_names(table: str, df: pd.DataFrame | None, league: str, season: str) -> pd.DataFrame | None:
    """선수 이름 원천(ESPN·위키·TM 부상)은 레지스트리 기준 표기로 — src/player_names.py. 클럽 표기도 표준으로."""
    if df is None:
        return df
    df = _canon_squads(df, league)
    try:
        import player_names as pn  # noqa: PLC0415
    except ImportError:
        return df
    cols = pn.TABLE_COLS.get(table)
    if not cols:
        return df
    try:
        if table.startswith("espn_subs") and "squad" not in df.columns:
            lu = read_table(table.replace("espn_subs", "espn_lineups"), league=league, season=season)
            out = pn.cleanse(pn.with_squad(df, lu), cols, league, season)
            return out.drop(columns=["squad"]) if "squad" in out.columns else out
        return pn.cleanse(df, cols, league, season)
    except Exception:  # noqa: BLE001 — 정규화 실패가 화면을 깨지 않게
        return df


def _read_from_db(table: str, league: str, season: str) -> pd.DataFrame | None:
    path = db_path(table)
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        if not _table_exists(conn, table):
            return None
        # league/season 필터는 SQL 에서 — 전 리그·전 시즌을 읽고 pandas 로 거르면 시즌이 쌓일수록
        # 요청당 메모리가 배로 늘어 무료 인스턴스(512MB)에서 위험하다.
        decl = {r[1]: str(r[2]).upper() for r in conn.execute(f'PRAGMA table_info("{table}")')}
        cols = set(decl)
        where, params = [], []
        if "league" in cols:
            where.append("league = ?")
            params.append(league)
        if "season" in cols:
            where.append("season = ?")
            params.append(season)
        sql = f'SELECT * FROM "{table}"' + (f" WHERE {' AND '.join(where)}" if where else "")
        df = pd.read_sql(sql, conn, params=params)
        if df.empty:
            return None
        # 이 리그·시즌에서 전부 비어 있는 컬럼은 None(object) 으로 읽힌다. 전체 테이블을 읽던 이전
        # 동작에선 다른 리그의 숫자 값 때문에 float NaN 이었으므로, 그런 컬럼만 float 으로 맞춘다.
        for c in df.columns:
            if df[c].dtype == object and df[c].isna().all() and decl.get(c) in ("REAL", "INTEGER"):
                if conn.execute(f'SELECT 1 FROM "{table}" WHERE "{c}" IS NOT NULL LIMIT 1').fetchone():
                    df[c] = df[c].astype("float64")
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()

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
