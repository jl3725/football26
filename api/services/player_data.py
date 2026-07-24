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


def player_frame(league: str):
    """players_full과 대회별 선발 수를 합친 선수 데이터 단일 진입점."""
    frame = ds.read_table("players_full", league=league)
    if frame is None:
        return None

    frame = frame.copy()
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
            data_path("player_comp_usage", league),
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
    return frame
