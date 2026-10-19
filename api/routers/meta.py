"""서비스 메타데이터와 상태 확인 라우트."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

import api.bootstrap  # noqa: F401
import datastore as ds
from leagues import ACTIVE_LEAGUE, league_config
import infra_health
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
        "infra": infra_health.status(),   # 차단 중인 선택 인프라(neo4j·qdrant)
    }


@router.get("/ops/status")
def ops_status():
    """DATA STATUS — 에이전트 레지스트리 × 실행 원장(data/ops/runs) × watchdog 결과.
    에이전트·feed 별 마지막 성공, 허용 지연 초과(지연), 최근 실패 단계. 화면: /status."""
    import ops_status as ops   # noqa: PLC0415 — 요청 때만(원장은 데이터 커밋마다 새 배포로 갱신)
    return ops.build_status()
