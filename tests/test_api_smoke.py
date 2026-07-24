from __future__ import annotations

import asyncio

import httpx
import pytest

from api.main import app, scout
from leagues import LEAGUES


def get(path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


def test_health_and_context() -> None:
    health = get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    context = get("/api/context")
    assert context.status_code == 200
    assert context.json()["window"]["state"] in {"summer", "winter", "closed"}


def test_league_catalog_matches_configured_data() -> None:
    response = get("/api/leagues")
    assert response.status_code == 200
    returned = {item["key"] for item in response.json()}
    assert set(LEAGUES).issubset(returned)


@pytest.mark.parametrize("league", list(LEAGUES))
def test_team_and_overview_smoke_for_every_league(league: str) -> None:
    teams_response = get("/api/teams", params={"league": league})
    assert teams_response.status_code == 200
    teams = teams_response.json()
    assert teams

    team = teams[0]["name"]
    overview = get(f"/api/overview/{team}", params={"league": league})
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["team"] == team
    assert payload["league"] == league
    assert {"overall", "attack", "midfield", "defense"}.issubset(payload["ovr"])

    next_teams = get("/api/teams/next", params={"league": league})
    assert next_teams.status_code == 200
    assert "teams" in next_teams.json()


def test_precomputed_home_hub_is_valid_json() -> None:
    response = get("/api/home/all")
    assert response.status_code == 200
    payload = response.json()
    assert payload["leagues"]
    assert "top_deals" in payload


def test_world_cup_routes() -> None:
    response = get("/api/wc")
    assert response.status_code == 200
    payload = response.json()
    assert {
        "matches",
        "groups",
        "scorers",
        "club_callups",
        "fifa_ranking",
    }.issubset(payload)
    assert payload["matches"]
    assert payload["nations"]

    nation = payload["nations"][0]["nation"]
    squad = get(f"/api/wc/squad/{nation}")
    assert squad.status_code == 200
    assert squad.json()["nation"] == nation
    assert squad.json()["players"]


def test_openapi_contains_split_router_paths() -> None:
    paths = app.openapi()["paths"]
    for path in (
        "/api/health",
        "/api/teams",
        "/api/teams/next",
        "/api/wc",
        "/api/wc/squad/{nation}",
    ):
        assert path in paths


def test_scout_requires_explicit_public_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SCOUT_TOKEN", raising=False)
    monkeypatch.delenv("SCOUT_ALLOW_PUBLIC", raising=False)

    response = scout({"q": "test"})
    assert response["available"] is False
    assert response["auth_required"] is True
