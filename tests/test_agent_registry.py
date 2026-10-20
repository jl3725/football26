"""에이전트 레지스트리·실행 원장·DATA STATUS — 워크플로에 단계를 더하면 레지스트리에도 적어야 한다."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import agent_registry as reg  # noqa: E402
import ops_status  # noqa: E402
import run_ledger  # noqa: E402


def _workflow_steps() -> set[str]:
    steps: set[str] = set()
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        for label in re.findall(r'ci_try\.sh "([^"]+)"', text):
            first = label.split()[0]
            if not first.startswith("$"):
                steps.add(first)
        # tm_data: STEPS="transfers:src/... injuries:src/..." 를 "$NAME $LG" 로 돌린다
        for block in re.findall(r'STEPS="([^"]+)"', text):
            steps.update(s.split(":")[0] for s in block.split())
    return steps


def test_every_collection_step_is_registered() -> None:
    import build_season

    known = set(reg.step_index())
    wf = _workflow_steps()
    assert {"schedule", "transfers", "injury_history", "fotmob_injuries"} <= wf   # 파싱이 제대로 되는지
    missing = sorted((wf | set(build_season.STEP_NAMES) | {"news", "fanvote"}) - known)
    assert not missing, f"agent_registry 에 없는 수집 단계: {missing}"


def test_registry_keys_unique() -> None:
    agents = [a.key for a in reg.AGENTS]
    feeds = [(a.key, f.key) for a in reg.AGENTS for f in a.feeds]
    assert len(agents) == len(set(agents)) and len(feeds) == len(set(feeds))
    steps = [s for a in reg.AGENTS for f in a.feeds for s in f.steps]
    assert len(steps) == len(set(steps)), "한 단계는 한 feed 에만"


def test_ledger_record_trims_old_and_reads_back(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_ledger, "LEDGER_DIR", tmp_path)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=run_ledger.KEEP_DAYS + 2)
    run_ledger.record("daily_data", "schedule EPL", 0, 3.2, when=old)
    run_ledger.record("daily_data", "schedule LaLiga", 1, 5)
    run_ledger.record("daily_data", "fotmob_injuries", None, 9, note="timeout")
    rows = run_ledger.read_all(tmp_path)
    assert [(r["step"], r["league"], r["ok"]) for r in rows] == [("schedule", "LaLiga", False), ("fotmob_injuries", None, False)]
    assert rows[1]["code"] is None and rows[1]["note"] == "timeout"
    assert json.loads((tmp_path / "daily_data.jsonl").read_text(encoding="utf-8").splitlines()[0])["league"] == "LaLiga"


def test_runner_name_from_workflow_ref(monkeypatch) -> None:
    monkeypatch.delenv("LEDGER_RUNNER", raising=False)
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "jl3725/football26/.github/workflows/match_refresh.yml@refs/heads/main")
    assert run_ledger.runner_name() == "match_refresh"
    monkeypatch.setenv("LEDGER_RUNNER", "local-sofascore-daily")
    assert run_ledger.runner_name() == "local-sofascore-daily"


def _e(hours_ago: float, step: str, league: str | None, ok: bool, now: dt.datetime) -> dict:
    return {"t": (now - dt.timedelta(hours=hours_ago)).isoformat(timespec="seconds"), "step": step,
            "league": league, "ok": ok, "runner": "x"}


def test_feed_states() -> None:
    now = dt.datetime(2026, 10, 20, 12, tzinfo=dt.timezone.utc)
    feed = reg.Feed("schedule", "일정", ("schedule",), ("match_refresh",), "매일", 30)
    assert ops_status.feed_status(feed, [], now)["state"] == "nodata"
    # 원장이 시작된 지 오래(허용 시간 + 하루 초과)인데 기록이 0이면 지연(2026-10-20 — daily_data 실패가 WAITING 으로 숨었다)
    old_start = (now - dt.timedelta(hours=feed.max_age_h + 48)).isoformat()
    assert ops_status.feed_status(feed, [], now, old_start)["state"] == "late"
    new_start = (now - dt.timedelta(hours=2)).isoformat()
    assert ops_status.feed_status(feed, [], now, new_start)["state"] == "nodata"
    ok = [_e(5, "schedule", "EPL", True, now), _e(5, "schedule", "LaLiga", True, now)]
    assert ops_status.feed_status(feed, ok, now)["state"] == "ok"
    # LaLiga 만 이번에 실패 — 다른 리그는 갱신 중이라 '실패 있음'
    warn = ok + [_e(1, "schedule", "LaLiga", False, now)]
    st = ops_status.feed_status(feed, warn, now)
    assert st["state"] == "warn" and st["failing"] == ["schedule LaLiga"] and st["fails_24h"] == 1
    # 같은 리그가 다시 성공하면 정상으로 돌아온다
    assert ops_status.feed_status(feed, warn + [_e(0.5, "schedule", "LaLiga", True, now)], now)["state"] == "ok"
    # 마지막 성공이 허용 지연(30h) 넘음
    assert ops_status.feed_status(feed, [_e(40, "schedule", "EPL", True, now)], now)["state"] == "late"
    assert ops_status.feed_status(feed, [_e(2, "schedule", "EPL", False, now)], now)["state"] == "late"


def test_build_status_shape_and_late_text() -> None:
    now = dt.datetime(2026, 10, 20, 12, tzinfo=dt.timezone.utc)
    entries = [_e(50, "news", None, True, now), _e(1, "schedule", "EPL", True, now), _e(1, "mystery", None, True, now)]
    s = ops_status.build_status(now=now, entries=entries)
    by = {a["key"]: a for a in s["agents"]}
    assert by["news"]["state"] == "late" and by["match"]["feeds"][0]["state"] == "ok"
    assert s["unregistered_steps"] == ["mystery"]
    assert any("NEWS · 뉴스 수집·번역" in x for x in ops_status.late_feeds(s))
