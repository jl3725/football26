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
    # 유료(OpenAI) 경로는 SCOUT_ALLOW_PAID 로 켰을 때만 — 그때는 토큰(또는 공개 허용) 없이는 막는다
    import scout_agent
    monkeypatch.setattr(scout_agent, "_load_dotenv", lambda: None)   # 로컬 .env 의 키가 섞이지 않게
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SCOUT_ALLOW_PAID", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SCOUT_TOKEN", raising=False)
    monkeypatch.delenv("SCOUT_ALLOW_PUBLIC", raising=False)

    response = scout({"q": "test"})
    assert response["available"] is False
    assert response["auth_required"] is True

    # 유료 키만 있고 허용하지 않았으면 무료 규칙 엔진 — 토큰 없이 누구나, 유료 호출 없음(2026-10-20)
    monkeypatch.delenv("SCOUT_ALLOW_PAID", raising=False)
    response = scout({"q": "test"})
    assert response["available"] is True and response.get("engine") == "rules"
    assert not response.get("auth_required")


def test_ops_intl_digest_endpoints() -> None:
    """설계도 1~3단계 새 엔드포인트 — DATA STATUS · A매치 · 주간 요약 · 선수 뉴스가 깨지지 않고 모양이 맞는지."""
    ops = get("/api/ops/status").json()
    assert {"counts", "agents", "recent_failures"} <= set(ops) and len(ops["agents"]) >= 10
    intl = get("/api/intl/team/Arsenal", params={"league": "EPL"}).json()
    assert {"window", "state", "squad_state", "players", "summary"} <= set(intl)
    dg = get("/api/digest", params={"league": "EPL"}).json()
    assert {"risers", "fallers", "injuries", "news", "rumors", "summary"} <= set(dg)
    assert "ai" in get("/api/news/Arsenal", params={"league": "EPL"}).json()
    assert all(m["delta"] > 0 for m in dg["risers"]) and all(m["delta"] < 0 for m in dg["fallers"])
    nw = get("/api/news-player/Bukayo Saka", params={"club": "Arsenal", "league": "EPL"}).json()
    assert isinstance(nw["articles"], list)


def test_scout_realtime_tools_without_llm() -> None:
    """Ask Scout 실시간 도구 — LLM(유료 키) 없이 실행기만: 결과는 API 함수 값 그대로."""
    import scout_agent as sa

    names = {t["function"]["name"] for t in sa.TOOLS}
    assert {"team_now", "player_news", "league_week"} <= names
    intent, r = sa._execute("team_now", {"team": "Arsenal"}, "EPL")
    assert intent == "team_now" and r["team"] == "Arsenal" and "next" in r and "injuries" in r
    intent, r = sa._execute("league_week", {"league": "Nowhere"}, "EPL")   # 모르는 리그면 현재 리그
    assert intent == "week" and r["league"] == "EPL"
    assert set(sa._slim("week", r)) >= {"risers", "injuries", "rumors"}
