"""월드컵 API 라우트."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.services.world_cup import (
    WorldCupDataError,
    squad_payload,
    world_cup_payload,
)

router = APIRouter(prefix="/api/wc", tags=["world-cup"])


@router.get("")
def world_cup():
    try:
        return world_cup_payload()
    except WorldCupDataError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/squad/{nation}")
def world_cup_squad(nation: str):
    try:
        return squad_payload(nation)
    except WorldCupDataError as exc:
        raise HTTPException(404, str(exc)) from exc
