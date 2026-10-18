"""
이름 정규화 — 원천 표기를 선수 레지스트리(src/player_registry.py)의 기준 표기(players_full)로 바꾼다.

datastore.read_table 이 ESPN 라인업·교체·선수 이벤트·위키 스쿼드·TM 부상을 읽을 때 자동으로 거친다 —
화면마다 따로 이름을 맞추던 코드(NameIndex·_espn_name·성+이니셜)가 처음부터 같은 이름을 본다.
레지스트리에 없는 이름은 그대로 둔다(틀리게 바꾸는 것보다 안전).

    cleanse(df, ["player"], "EPL")            # 같은 팀(squad) 안 별칭 → 기준 표기
    canon("Alisson Becker", "Liverpool", "EPL") == "Alisson"
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from player_registry import norm

# 테이블 → 정규화할 이름 컬럼
TABLE_COLS = {
    "espn_lineups": ["player"], "espn_lineups_cups": ["player"],
    "espn_subs": ["player_in", "player_out"], "espn_subs_cups": ["player_in", "player_out"],
    "match_events": ["player"], "wiki_squads": ["player"], "transfermarkt_injuries": ["player"],
    "fotmob_ratings": ["player"], "player_match_stats": ["player"],
}
_CACHE: dict = {}
_SPLIT = re.compile(r" because | due to ")


def alias_map(league: str, season: str | None = None) -> dict[tuple[str, str], str]:
    """{(squad, 정규화 별칭): 기준 표기}. 레지스트리가 없으면 빈 dict."""
    import datastore as ds  # noqa: PLC0415 — datastore 가 이 모듈을 부르므로 지연 import
    key = (league, season, ds._db_mtime())
    if key in _CACHE:
        return _CACHE[key]
    reg = ds.read_table("player_registry", league=league, season=season)
    out: dict[tuple[str, str], str] = {}
    if reg is not None and not reg.empty and {"squad", "alias", "canonical"} <= set(reg.columns):
        for sq, al, ca in zip(reg["squad"].astype(str), reg["alias"].astype(str), reg["canonical"].astype(str)):
            out.setdefault((sq, norm(al)), ca)
    if len(_CACHE) > 32:
        _CACHE.clear()
    _CACHE[key] = out
    return out


def canon(name, squad, league: str, season: str | None = None) -> str:
    s = str(name or "")
    base = _SPLIT.split(s)[0].strip()
    return alias_map(league, season).get((str(squad), norm(base)), s)


def with_squad(subs: pd.DataFrame, lineups: pd.DataFrame | None) -> pd.DataFrame:
    """교체 기록(event_id·home_away, 팀 없음)에 같은 경기 라인업의 팀을 붙인다."""
    if subs is None or subs.empty or "squad" in subs.columns or lineups is None or lineups.empty \
            or not {"event_id", "home_away", "squad"} <= set(lineups.columns):
        return subs
    side = {}
    for e, h, q in zip(lineups["event_id"].astype(str), lineups["home_away"].astype(str), lineups["squad"].astype(str)):
        side.setdefault((e.replace(".0", ""), h), q)
    out = subs.copy()
    out["squad"] = [side.get((str(e).replace(".0", ""), str(h))) for e, h in zip(out["event_id"], out["home_away"])]
    return out


def cleanse(df: pd.DataFrame, cols, league: str, season: str | None = None, squad_col: str = "squad") -> pd.DataFrame:
    """이름 컬럼을 기준 표기로(원래 값은 <컬럼>_src 로 보존). 바꿀 게 없으면 그대로."""
    if df is None or df.empty or squad_col not in df.columns:
        return df
    amap = alias_map(league, season)
    if not amap:
        return df
    out = df
    for c in cols:
        if c not in df.columns:
            continue
        vals = df[c].astype(str)
        new = [amap.get((sq, norm(_SPLIT.split(v)[0].strip())), v) if v and v != "nan" else v
               for sq, v in zip(df[squad_col].astype(str), vals)]
        if any(a != b for a, b in zip(new, vals)):
            if out is df:
                out = df.copy()
            out[c + "_src"] = df[c]
            out[c] = [n if o != "nan" else df[c].iloc[i] for i, (n, o) in enumerate(zip(new, vals))]
    return out


def read_lineup_csv(path, usecols) -> "pd.DataFrame":
    """라인업 CSV 를 읽어 이름을 기준 표기로(파일명에서 리그·시즌) — glob 으로 읽는 로더용."""
    import pandas as pd  # noqa: PLC0415
    from leagues import parse_data_filename  # noqa: PLC0415
    df = pd.read_csv(path, usecols=lambda c: c in set(usecols) | {"home_away"})
    meta = parse_data_filename(Path(path).name)
    if meta and meta[0] in TABLE_COLS:
        df = cleanse(df, TABLE_COLS[meta[0]], meta[1], meta[2])
    return df
