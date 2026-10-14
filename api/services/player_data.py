"""선수 데이터 로딩과 API 표시용 공통 변환."""
from __future__ import annotations

import pandas as pd
from unidecode import unidecode

import api.bootstrap  # noqa: F401
import datastore as ds
from leagues import data_path

_EXTRA_PHOTO_CACHE: dict[str, dict[str, str]] = {}


def number(value, default=0.0):
    try:
        converted = float(value)
        return default if pd.isna(converted) else converted
    except (TypeError, ValueError):
        return default


def photo_url(row) -> str:
    photo = row.get("tm_photo")
    if photo is not None and not pd.isna(photo) and str(photo).startswith("http"):
        return str(photo)
    return ""


def extra_photo_map(league: str) -> dict[str, str]:
    """players_full에 없는 선수의 Transfermarkt 사진 폴백."""
    if league in _EXTRA_PHOTO_CACHE:
        return _EXTRA_PHOTO_CACHE[league]

    result: dict[str, str] = {}
    for table, photo_column in (
        ("transfers", "photo"),
        ("transfermarkt_contracts", "tm_photo"),
        ("transfermarkt_injuries", "tm_photo"),
    ):
        frame = ds.read_table(table, league=league)
        if (
            frame is None
            or photo_column not in frame.columns
            or "player" not in frame.columns
        ):
            continue
        for _, row in frame.iterrows():
            photo = str(row.get(photo_column) or "")
            if photo.startswith("http"):
                key = unidecode(str(row.get("player"))).lower().strip()
                result.setdefault(key, photo)

    _EXTRA_PHOTO_CACHE[league] = result
    return result


def resolve_photo(name, resolve, league: str) -> str:
    """이름 → players_full 사진, 없으면 Transfermarkt 폴백."""
    if not name:
        return ""
    row = resolve(name)
    photo = photo_url(row) if row is not None else ""
    key = unidecode(str(name)).lower().strip()
    return photo or extra_photo_map(league).get(key, "")


_FRAME_CACHE: dict = {}


def player_frame(league: str, season: str | None = None):
    """players_full과 대회별 선발 수를 합친 선수 데이터 단일 진입점.

    리그 레벨(_league_level)과 리그 내 순위 폼(_form)을 붙인다. 요청마다 수십 번 불리므로 DB 수정
    시각 기준으로 캐시하고, 호출부가 고쳐 써도 안전하게 사본을 준다. season(예: "2025_2026")을 주면
    그 시즌 표(지난 시즌 대비 성장 계산용).
    """
    key = (league, season, ds._db_mtime())
    hit = _FRAME_CACHE.get(key)
    if hit is not None:
        return hit.copy()
    frame = _build_frame(league, season)
    if frame is not None:
        if len(_FRAME_CACHE) > 16:
            _FRAME_CACHE.clear()
        _FRAME_CACHE[key] = frame
        return frame.copy()
    return None


def _build_frame(league: str, season: str | None = None):
    frame = ds.read_table("players_full", league=league, season=season)
    if frame is None:
        return None

    frame = frame.copy()
    # 평점 리그 보정용(ratings_v3) — 행마다 리그 레벨을 실어 어느 호출부에서든 같은 보정이 되게
    import league_level  # noqa: PLC0415
    frame["_league_level"] = league_level.level(league)
    if "norm_key" not in frame.columns:
        frame["norm_key"] = None
    missing = frame["norm_key"].isna() | frame["norm_key"].astype(str).str.strip().isin(
        ["", "nan", "None"]
    )
    if missing.any():
        frame.loc[missing, "norm_key"] = frame.loc[missing, "player"].map(
            lambda value: unidecode(str(value)).lower().strip()
        )

    try:
        usage = pd.read_csv(
            data_path("player_comp_usage", league, season),
            usecols=[
                "squad",
                "norm_key",
                "ucl_starts",
                "uel_starts",
                "conf_starts",
                "cup_starts",
            ],
        )
        frame = frame.merge(usage, on=["squad", "norm_key"], how="left")
    except (OSError, KeyError, ValueError):
        pass
    import ratings_v3 as rv3  # noqa: PLC0415
    return rv3.add_form_column(frame)
