"""
DATA STATUS — 에이전트 레지스트리 × 실행 원장 → 에이전트·feed 별 상태(정상·실패 있음·지연·기록 없음).

  ok      마지막 성공이 허용 지연(max_age_h) 안이고, 단계×리그마다 가장 최근 실행이 성공
  warn    허용 지연 안이지만 어떤 단계×리그의 가장 최근 실행이 실패(다른 리그·단계는 갱신 중)
  late    마지막 성공이 허용 지연을 넘음(또는 성공 기록이 없음) — '이 데이터가 멈췄다'
  down    외부 원천 중단 — 어떤 단계의 가장 최근 실행이 75(사이트 차단·폐쇄·서버 오류)로 끝남. 우리 고장이 아니라
          고칠 수 없어 '지연'과 나눈다(2026-10-25 ClubElo Cloudflare 차단). 다른 단계 실패가 있으면 warn 이 먼저
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
RANK = {"late": 4, "warn": 3, "down": 2, "nodata": 1, "ok": 0}
SOURCE_DOWN = 75                                         # scripts/ci_try.sh 와 같은 약속(EX_TEMPFAIL)


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


def feed_status(feed: reg.Feed, entries: list[dict], now: dt.datetime, ledger_start: str | None = None) -> dict:
    mine = [e for e in entries if e.get("step") in feed.steps]
    latest: dict[tuple[str, str | None], dict] = {}
    for e in mine:                                       # entries 는 시간순 — 마지막 것이 최신
        latest[(e["step"], e.get("league"))] = e
    oks = [e["t"] for e in mine if e.get("ok")]
    last_ok = max(oks) if oks else None
    last_run = max((e["t"] for e in mine), default=None)
    failing = sorted(f"{s}{' ' + lg if lg else ''}" for (s, lg), e in latest.items()
                     if not e.get("ok") and e.get("code") != SOURCE_DOWN)
    down = sorted(f"{s}{' ' + lg if lg else ''}" for (s, lg), e in latest.items() if e.get("code") == SOURCE_DOWN)
    # 원천이 막힌 단계의 마지막 성공(그 데이터가 언제 멈췄나)
    down_ok = max((e["t"] for e in mine if e.get("ok") and f"{e['step']}{' ' + e['league'] if e.get('league') else ''}" in down),
                  default=None)
    age = _age_h(last_ok, now)
    if not mine:
        # 원장이 시작된 지 허용 시간(+하루)이 지났는데도 기록이 0이면 '첫 기록 대기'가 아니라 지연 — daily_data 가
        # 실패 중인데 그 피드들이 WAITING 17개로만 보였다(2026-10-20 점검).
        # 새 피드는 원장 시작이 아니라 추가한 날(feed.added)부터 센다 — 넣자마자 빨간불이 됐다(2026-10-23)
        start = max([x for x in (ledger_start, getattr(feed, "added", "") or None) if x], default=None)
        since = _age_h(start, now)
        state = "late" if since is not None and since > feed.max_age_h + 24 else "nodata"
    elif failing and (age is None or age > feed.max_age_h):
        state = "late"
    elif failing:
        state = "warn"
    elif down:
        state = "down"                                   # 막힌 원천뿐 — 다른 단계가 성공 중이어도, 전부 막혀 멈췄어도
    elif age is None or age > feed.max_age_h:
        state = "late"
    else:
        state = "ok"
    day_ago = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    recent = [e for e in mine if e.get("t", "") >= day_ago]
    return {"key": feed.key, "label": feed.label, "state": state, "cadence": feed.cadence,
            "max_age_h": feed.max_age_h, "runners": list(feed.runners), "outputs": list(feed.outputs),
            "last_ok": last_ok, "last_run": last_run, "age_h": age, "failing": failing[:12],
            "n_failing": len(failing), "down": down[:12], "down_age_h": _age_h(down_ok, now), "runs_24h": len(recent),
            "fails_24h": sum(1 for e in recent if not e.get("ok") and e.get("code") != SOURCE_DOWN)}


def build_status(now: dt.datetime | None = None, entries: list[dict] | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    entries = run_ledger.read_all() if entries is None else entries
    agents = []
    # 원장 시작 시각은 CI·로컬을 나눠 본다 — 로컬 주간 빌드는 10/14 부터, GH 워크플로는 10/20 부터 기록했다
    ci_start = next((e["t"] for e in entries if not str(e.get("runner", "")).startswith(("local-", "manual"))), None)
    local_start = next((e["t"] for e in entries if str(e.get("runner", "")).startswith("local-")), None)
    for a in reg.AGENTS:
        feeds = [feed_status(f, entries, now, local_start if all(r.startswith("local-") for r in f.runners) else ci_start)
                 for f in a.feeds]
        # 에이전트 상태 = 기록 있는 피드 중 가장 나쁜 것(대기 피드 하나 때문에 정상 에이전트가 WAITING 으로 보이지 않게)
        seen = [f["state"] for f in feeds if f["state"] != "nodata"]
        state = max(seen, key=lambda s: RANK[s]) if seen else "nodata"
        agents.append({"key": a.key, "en": a.en, "ko": a.ko, "does": a.does, "sources": list(a.sources),
                       "checks": list(a.checks), "extras": list(a.extras), "state": state, "feeds": feeds,
                       "n_ok": sum(1 for f in feeds if f["state"] == "ok"), "n_feeds": len(feeds)})
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
