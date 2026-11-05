"""/api/health 가 HEAD 도 받는가 — UptimeRobot(HEAD 로 살핌)이 405 로 10/14 부터 다운으로 봤다(2026-11-05)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def test_health_accepts_head_and_get() -> None:
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routers import meta
    app = FastAPI()
    app.include_router(meta.router)
    c = TestClient(app)
    assert c.head("/api/health").status_code == 200
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json().get("ok") is True
