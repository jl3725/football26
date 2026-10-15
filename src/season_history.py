"""
팀 시즌 이력 — 지난 여러 시즌의 득점·실점(리그 안 상대값)을 시즌이 쌓이는 대로 자동으로 반영한다.

원천(오래된 것 → 최근):
  data/standings_history.csv (ESPN 과거 최종 순위, src/fetch_standings_history.py)
  standings_{리그}_{시즌}.csv  (우리 수집 — 같은 시즌이면 이쪽이 우선)
시즌 목록은 하드코딩하지 않는다: 현재 시즌(SEASON_START) 이전 MAX_SEASONS 개를 찾아 있는 것만 쓴다.
시즌이 넘어가면 직전 시즌 파일이 자동으로 '과거'에 들어오고, 가장 오래된 시즌은 가중이 작아진다.

가중: 직전 시즌 1, 그 전 0.5, 0.25 … (DECAY). 팀이 그 시즌에 이 리그에 없었으면(승격 팀) 그 시즌은 건너뛴다.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from leagues import DATA_DIR, SEASON_START

MAX_SEASONS = 4      # 직전 시즌 포함 몇 시즌까지
DECAY = 0.5          # 한 시즌 멀어질 때마다 가중 ×0.5
MIN_TEAMS = 12       # 이보다 팀이 적은 표(플레이오프 그룹만 남은 벨기에 등)는 z 를 믿지 않는다
HISTORY = DATA_DIR / "standings_history.csv"

Reader = Callable[[str, str], "pd.DataFrame | None"]   # (league, season) → standings


def season_tag(start: int) -> str:
    return f"{start}_{start + 1}"


def short(season: str) -> str:
    """'2024_2025' → '24/25'."""
    a, _, b = season.partition("_")
    return f"{a[-2:]}/{b[-2:]}" if b else season


_HIST_CACHE: dict = {}


def _history(league: str) -> pd.DataFrame:
    """standings_history.csv 의 이 리그 행 — 파일 수정 시각이 같으면 다시 읽지 않는다(팀마다 부른다)."""
    if not HISTORY.exists():
        return pd.DataFrame()
    mt = HISTORY.stat().st_mtime
    if _HIST_CACHE.get("mtime") != mt:
        _HIST_CACHE.clear()
        _HIST_CACHE.update({"mtime": mt, "df": pd.read_csv(HISTORY)})
    h = _HIST_CACHE["df"]
    return h[h["league"] == league]


def past_tables(league: str, reader: Reader, current: int = SEASON_START,
                max_seasons: int = MAX_SEASONS) -> list[tuple[str, pd.DataFrame]]:
    """[(시즌, 순위표)] 최근 → 오래된 순. 우리 파일 우선, 없으면 ESPN 이력."""
    hist = _history(league)
    out = []
    for k in range(1, max_seasons + 1):
        s = season_tag(current - k)
        t = None
        try:
            t = reader(league, s)
        except Exception:  # noqa: BLE001 — 그 시즌 파일 없음
            t = None
        if (t is None or t.empty) and not hist.empty:
            t = hist[hist["season"] == s]
        if t is not None and not t.empty and len(t) >= MIN_TEAMS:
            out.append((s, t))
    return out


def table_stats(t: pd.DataFrame, team: str) -> dict | None:
    """순위표 한 장에서 팀의 경기당 득점·실점, 리그 안 z(실점은 적을수록 +), 순위."""
    pl = pd.to_numeric(t["played"], errors="coerce")
    t = t[pl > 0]
    if team not in set(t["squad"]):
        return None
    pl = pd.to_numeric(t["played"], errors="coerce")
    gf = pd.to_numeric(t["gf"], errors="coerce") / pl
    ga = pd.to_numeric(t["ga"], errors="coerce") / pl
    me = t["squad"] == team
    f, a = float(gf[me].iloc[0]), float(ga[me].iloc[0])
    sf, sa = float(gf.std()), float(ga.std())
    return {"played": int(pl[me].iloc[0]), "gf_pg": round(f, 2), "ga_pg": round(a, 2),
            "gf_z": (f - float(gf.mean())) / sf if sf > 0 else 0.0,
            "ga_z": -(a - float(ga.mean())) / sa if sa > 0 else 0.0,
            "gf_rank": int((gf > f).sum()) + 1, "ga_rank": int((ga < a).sum()) + 1, "n": int(len(t))}


def team_record(league: str, team: str, reader: Reader, current: int = SEASON_START) -> list[dict]:
    """팀의 과거 시즌 기록(최근 → 오래된 순) + 시즌 가중 w."""
    out = []
    for k, (s, t) in enumerate(past_tables(league, reader, current)):
        st = table_stats(t, team)
        if st:
            out.append({"season": s, "label": short(s), "w": DECAY ** k, **st})
    return out


def blended(records: list[dict], key: str) -> float | None:
    """시즌 가중 평균 z — 기록이 없으면 None."""
    ws = sum(r["w"] for r in records)
    return sum(r["w"] * r[key] for r in records) / ws if ws > 0 else None
