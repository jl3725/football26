"""서비스 메타데이터와 상태 확인 라우트."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

import api.bootstrap  # noqa: F401
import datastore as ds
from leagues import ACTIVE_LEAGUE, league_config
from season_context import current_window, season_label

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/context")
def context():
    return {
        "today": str(dt.date.today()),
        "data_season": season_label(),
        "window": current_window(),
    }


@router.get("/leagues")
def leagues():
    result = []
    for league in ds.available_leagues():
        try:
            config = league_config(league)
            result.append(
                {"key": league, "name": config.name, "country": config.country}
            )
        except KeyError:
            result.append({"key": league, "name": league, "country": ""})
    return result


@router.get("/health")
def health():
    return {
        "ok": True,
        "active_league": ACTIVE_LEAGUE,
        "leagues": ds.available_leagues(),
    }
