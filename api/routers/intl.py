"""국가대표 — A매치 기간·소집 명단(팀 화면 일정 탭 INTERNATIONAL BREAK 카드)."""
from __future__ import annotations

from fastapi import APIRouter

import api.bootstrap  # noqa: F401
from api.services import intl
from leagues import ACTIVE_LEAGUE

router = APIRouter(prefix="/api", tags=["intl"])


@router.get("/intl/windows")
def intl_windows():
    return {"windows": intl.windows()}


@router.get("/intl/team/{team}")
def intl_team(team: str, league: str = ACTIVE_LEAGUE):
    """다음(진행 중) A매치 기간 + 그 기간 소집 선수(명단 발표 전이면 지난 기간 명단, squad_state=previous)와 대표팀 경기."""
    return intl.team_payload(team, league)
