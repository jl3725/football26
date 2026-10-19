"""
DATA STATUS — 에이전트 레지스트리 × 실행 원장 → 에이전트·feed 별 상태(정상·실패 있음·지연·기록 없음).

  ok      마지막 성공이 허용 지연(max_age_h) 안이고, 단계×리그마다 가장 최근 실행이 성공
  warn    허용 지연 안이지만 어떤 단계×리그의 가장 최근 실행이 실패(다른 리그·단계는 갱신 중)
  late    마지막 성공이 허용 지연을 넘음(또는 성공 기록이 없음) — '이 데이터가 멈췄다'
  nodata  원장에 아직 기록이 없음(원장 도입 직후·새 단계)

/api/ops/status 와 watchdog 'agents' 점검이 같은 계산을 쓴다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import agent_registry as reg
import run_ledger

ROOT = Path(__file__).resolve().parent.parent
WATCHDOG_JSON = ROOT / "data" / "ops" / "watchdog.json"
RANK = {"late": 3, "warn": 2, "nodata": 1, "ok": 0}


def _age_h(iso: str | None, now: dt.datetime) -> float | None:
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return round((now - t).total_seconds() / 3600, 1)


def feed_status(feed: reg.Feed, entries: list[dict], now: dt.datetime) -> dict:
    mine = [e for e in entries if e.get("step") in feed.steps]
    latest: dict[tuple[str, str | None], dict] = {}
    for e in mine:                                       # entries 는 시간순 — 마지막 것이 최신
        latest[(e["step"], e.get("league"))] = e
    oks = [e["t"] for e in mine if e.get("ok")]
    last_ok = max(oks) if oks else None
    last_run = max((e["t"] for e in mine), default=None)
    failing = sorted(f"{s}{' ' + lg if lg else ''}" for (s, lg), e in latest.items() if not e.get("ok"))
    age = _age_h(last_ok, now)
    if not mine:
        state = "nodata"
    elif age is None or age > feed.max_age_h:
        state = "late"
    elif failing:
        state = "warn"
    else:
        state = "ok"
    day_ago = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    recent = [e for e in mine if e.get("t", "") >= day_ago]
    return {"key": feed.key, "label": feed.label, "state": state, "cadence": feed.cadence,
            "max_age_h": feed.max_age_h, "runners": list(feed.runners), "outputs": list(feed.outputs),
            "last_ok": last_ok, "last_run": last_run, "age_h": age, "failing": failing[:12],
            "n_failing": len(failing), "runs_24h": len(recent),
            "fails_24h": sum(1 for e in recent if not e.get("ok"))}


def build_status(now: dt.datetime | None = None, entries: list[dict] | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    entries = run_ledger.read_all() if entries is None else entries
    agents = []
    for a in reg.AGENTS:
        feeds = [feed_status(f, entries, now) for f in a.feeds]
        state = max((f["state"] for f in feeds), key=lambda s: RANK[s]) if feeds else "nodata"
        agents.append({"key": a.key, "en": a.en, "ko": a.ko, "does": a.does, "sources": list(a.sources),
                       "checks": list(a.checks), "extras": list(a.extras), "state": state, "feeds": feeds})
    known = reg.step_index()
    fails = [e for e in reversed(entries) if not e.get("ok")][:20]
    unknown = sorted({e.get("step", "") for e in entries} - set(known) - {""})
    wd = None
    if WATCHDOG_JSON.exists():
        try:
            wd = json.loads(WATCHDOG_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            wd = None
    counts = {s: sum(1 for a in agents for f in a["feeds"] if f["state"] == s) for s in RANK}
    return {"generated": now.isoformat(timespec="seconds"), "counts": counts,
            "first_entry": entries[0]["t"] if entries else None, "agents": agents,
            "recent_failures": [{**e, "agent": known[e["step"]][0].en if e.get("step") in known else None}
                                for e in fails],
            "unregistered_steps": unknown, "watchdog": wd}


def late_feeds(status: dict) -> list[str]:
    """watchdog 용 — 지연된 feed 를 사람 말로."""
    out = []
    for a in status["agents"]:
        for f in a["feeds"]:
            if f["state"] == "late":
                when = f"마지막 성공 {f['age_h']:.0f}시간 전" if f["age_h"] is not None else "성공 기록 없음"
                out.append(f"{a['en']} · {f['label']} — {when}(허용 {f['max_age_h']:.0f}시간, {', '.join(f['runners'])})")
    return out
