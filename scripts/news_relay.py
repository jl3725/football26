"""
뉴스 이어 달리기(news relay) — 뉴스 수집(daily_news)을 2시간 간격으로 실제로 돌린다(2026-11-12 사용자 '진행').

배경: daily_news 는 '2시간마다' 예약 실행인데 GitHub 예약 실행이 밀려 실제로는 하루 3~4번, 간격 5~11시간이었다
(11/09 10:35 → 18:34 → 11/10 05:37 KST). 뉴스 탭·AI 팀 뉴스 요약·이적설 기사가 반나절 늦고 watchdog agents 가 매일 빨간불.
match_watch·transfer_watch 와 같은 이어 달리기 — 직접 실행 요청(workflow_dispatch)은 예약 지연을 받지 않는다.

동작(GH Actions 한 작업 최대 ~5.5시간, 공개 저장소라 분 단위 과금 없음):
  1. POLL(10분)마다 daily_news 의 최근 실행을 본다.
  2. 대기·실행 중인 것이 없고 마지막 실행이 MIN_GAP(110분) 전보다 오래면 daily_news 를 실행 요청(번역 한도를 생각한
     원래 설계 그대로 2시간 간격 — 더 자주는 안 함).
  3. 시간 예산(330분)을 다 쓰면 자기 자신을 다시 실행하고 끝(다른 news_relay 가 이미 대기·실행 중이면 안 함).
  daily_news 의 2시간 예약과 news_relay 의 6시간 시동 예약은 사슬이 끊겼을 때 다시 잇는 안전장치로 남긴다.

사용:
  python scripts/news_relay.py                 # GH Actions (GITHUB_TOKEN·GITHUB_REPOSITORY)
  python scripts/news_relay.py --once --dry-run  # 지금 상태로 무엇을 할지만
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time

import requests

REPO = os.getenv("GITHUB_REPOSITORY", "jl3725/football26")
NEWS = "daily_news.yml"
SELF = "news_relay.yml"
MIN_GAP = 110          # 분 — 마지막 뉴스 실행이 이보다 오래되면 다시
POLL = 10              # 분
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}


def _api(path: str, params: dict | None = None) -> dict:
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    r = requests.get(f"https://api.github.com/repos/{REPO}/{path}", params=params or {}, timeout=30,
                     headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"} if tok else {})
    r.raise_for_status()
    return r.json()


def runs(workflow: str, n: int = 5) -> list[dict]:
    """최근 실행(새것 먼저) — [{id, status, created_at}]."""
    return [{"id": r["id"], "status": r["status"], "created_at": r["created_at"]}
            for r in _api(f"actions/workflows/{workflow}/runs", {"branch": "main", "per_page": n}).get("workflow_runs", [])]


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def news_due(rs: list[dict], now: dt.datetime, gap_min: int = MIN_GAP) -> tuple[bool, str]:
    """뉴스 수집을 지금 실행할까 — (해야 하나, 이유)."""
    if any(r["status"] in ACTIVE for r in rs):
        return False, "실행·대기 중"
    if not rs:
        return True, "기록 없음"
    age = (now - _ts(rs[0]["created_at"])).total_seconds() / 60
    return (age >= gap_min), f"마지막 실행 {age:.0f}분 전"


def other_relay_active(rs: list[dict], me: str | None) -> bool:
    return any(r["status"] in ACTIVE and str(r["id"]) != str(me or "") for r in rs)


def dispatch(workflow: str, dry: bool) -> bool:
    if dry:
        print(f"[news-relay] (dry-run) {workflow} 실행했을 것")
        return True
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=20)
    ok = r.status_code == 204
    print(f"[news-relay] {workflow} 실행 요청 → {r.status_code}{'' if ok else ' ' + r.text[:200]}", flush=True)
    return ok


def tick(dry: bool, now: dt.datetime | None = None, get_runs=runs, do=dispatch) -> bool:
    """한 번 보기 — 뉴스 수집을 실행 요청했으면 True."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        due, why = news_due(get_runs(NEWS), now)
    except requests.RequestException as e:
        print(f"[news-relay] 실행 기록 못 봄 {type(e).__name__} — 다음 차례에", flush=True)
        return False
    print(f"[news-relay] {now:%H:%M}Z daily_news {why} → {'실행' if due else '대기'}", flush=True)
    return bool(due and do(NEWS, dry))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=330)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    while True:
        tick(a.dry_run)
        if a.once:
            return 0
        if (time.monotonic() - t0) / 60 + POLL > a.max_minutes:
            break
        time.sleep(POLL * 60)
    try:
        busy = other_relay_active(runs(SELF), os.getenv("GITHUB_RUN_ID"))
    except requests.RequestException:
        busy = False
    if busy:
        print("[news-relay] 다른 news_relay 가 이미 대기·실행 중 — 이어 달리기 생략")
    else:
        dispatch(SELF, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
