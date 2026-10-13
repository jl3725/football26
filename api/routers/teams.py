"""리그 팀 카탈로그 라우트."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

import api.bootstrap  # noqa: F401
import datastore as ds
import teammeta as tm
from leagues import ACTIVE_LEAGUE, ROOT, data_path
from season_context import current_window, season_label

router = APIRouter(prefix="/api", tags=["teams"])
SEASON_TEAMS_JSON = Path(ROOT) / "data" / "season_teams.json"


@router.get("/teams")
def teams(league: str = ACTIVE_LEAGUE):
    standings = ds.read_table("standings", league=league)
    if standings is None:
        raise HTTPException(404, "standings not found")
    standings = standings.sort_values("rank")
    return [
        {
            "name": row["squad"],
            "color": tm.team_color(row["squad"]),
            "logo": tm.team_logo(row["squad"]),
            "rank": int(row["rank"]),
            "points": int(row["points"]),
        }
        for _, row in standings.iterrows()
    ]


@router.get("/teams/next")
def teams_next(league: str = ACTIVE_LEAGUE):
    """다음 시즌 로스터: 감지 JSON → 일정 → 현재 순위 순으로 폴백.

    '다음 시즌' = 달력상 시즌(current_window). 시즌 중(phase=in_season)에는 데이터 시즌과 같다.
    """
    next_id = current_window()["season_id"]
    path = (
        SEASON_TEAMS_JSON
        if league == "EPL"
        else data_path("season_teams", league, ext="json")
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("teams"):
            return data
    except (OSError, json.JSONDecodeError):
        pass

    try:
        schedule = pd.read_csv(data_path("schedule_full", league, f"{next_id}_{next_id + 1}"))
        squads = sorted(set(schedule["squad"].astype(str)))
        if squads:
            items = [
                {
                    "name": squad,
                    "color": tm.team_color(squad),
                    "logo": tm.team_logo(squad),
                    "promoted": False,
                }
                for squad in squads
            ]
            return {
                "season_label": season_label(next_id),
                "source_title": f"schedule {next_id}-{(next_id + 1) % 100:02d}",
                "detected_at": "",
                "teams": items,
                "promoted": [],
                "relegated": [],
                "meta_missing": [],
            }
    except (OSError, KeyError, ValueError):
        pass

    standings = ds.read_table("standings", league=league)
    items = []
    if standings is not None and "squad" in standings.columns:
        for squad in sorted(standings["squad"].astype(str)):
            items.append(
                {
                    "name": squad,
                    "color": tm.team_color(squad),
                    "logo": tm.team_logo(squad),
                    "promoted": False,
                }
            )
    return {
        "season_label": "",
        "source_title": "",
        "detected_at": "",
        "teams": items,
        "promoted": [],
        "relegated": [],
        "meta_missing": [],
    }
