"""서버 스스로 깨어 있기(자체 핑)·재시작 횟수 — 2026-11-05 사용자 '오래 안 켜면 서버가 죽나요'."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]

import live_sync  # noqa: E402


class _Resp:
    def __init__(self, code):
        self.status_code = code


def test_self_ping_uses_render_url_and_counts(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("SELF_PING_URL", raising=False)
    assert live_sync.self_ping(lambda *a, **k: _Resp(200)) is False        # 주소 없음(로컬) — 아무것도 안 함
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://x.onrender.com/")
    seen = []
    before = live_sync.STATE["pings"]
    assert live_sync.self_ping(lambda url, **k: (seen.append(url), _Resp(200))[1]) is True
    assert seen == ["https://x.onrender.com/api/health"] and live_sync.STATE["pings"] == before + 1
    bad = live_sync.STATE["ping_fail"]
    assert live_sync.self_ping(lambda url, **k: _Resp(503)) is False and live_sync.STATE["ping_fail"] == bad + 1


def test_backend_restart_warning(tmp_path, monkeypatch) -> None:
    import watchdog as wd
    monkeypatch.setattr(wd, "ROOT", tmp_path)
    (tmp_path / "data" / "ops").mkdir(parents=True)
    now = wd.NOW
    ups = [(now - wd.dt.timedelta(hours=h)).isoformat(timespec="seconds") for h in (20, 9, 1)]
    assert wd._backend_restarts({"up_since": ups[0]}) == []
    assert wd._backend_restarts({"up_since": ups[1]}) == []
    msgs = wd._backend_restarts({"up_since": ups[2], "live_sync": {"pings": 12}})
    assert msgs and "3회/24h" in msgs[0] and "자체 핑 12회" in msgs[0]
    hist = json.loads((tmp_path / "data" / "ops" / "backend_uptime.json").read_text(encoding="utf-8"))
    assert hist == ups                                                      # 같은 up_since 는 한 번만
    assert wd._backend_restarts({"up_since": ups[2]})[0].startswith("운영 서버 재시작 3회")
