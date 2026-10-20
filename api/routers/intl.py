"""국가대표 — A매치 기간·소집 명단(팀 화면 일정 탭 INTERNATIONAL BREAK 카드)."""
from __future__ import annotations

from fastapi import APIRouter

import api.bootstrap  # noqa: F401
from api.services import intl
from api.services import intl_hub as intl_hub_svc
from leagues import ACTIVE_LEAGUE

router = APIRouter(prefix="/api", tags=["intl"])


@router.get("/intl/windows")
def intl_windows():
    return {"windows": intl.windows()}


@router.get("/intl/hub")
def intl_hub():
    """국가대표 탭 — 상태 불빛·지금(A매치 기간·진행 대회)·대륙별 대회(자동 발견, src/intl_comps.py)."""
    return intl_hub_svc.hub()


@router.get("/intl/matches")
def intl_matches(scope: str = "key", when: str = "upcoming", conf: str = "", kind: str = "", code: str = "", limit: int = 80):
    """A매치 목록 — scope=key(우리 리그 선수 소집국·FIFA 30위 안) | all, when=upcoming | recent, 대륙·종류·대회 필터."""
    return intl_hub_svc.match_list(scope=scope, when=when, conf=conf, kind=kind, code=code, limit=min(max(limit, 1), 300))


@router.get("/intl/comp/{code}")
def intl_comp(code: str, season: str = ""):
    """대회 한 회차 — 경기(단계별)·우승팀."""
    return intl_hub_svc.comp_detail(code, season)


@router.get("/intl/team/{team}")
def intl_team(team: str, league: str = ACTIVE_LEAGUE):
    """다음(진행 중) A매치 기간 + 그 기간 소집 선수(명단 발표 전이면 지난 기간 명단, squad_state=previous)와 대표팀 경기."""
    return intl.team_payload(team, league)
