"""
경기 종료 감시(match watch) — 경기가 끝나면 20분 뒤 match_refresh 를 바로 돌린다(설계도 2단계 '종료 이벤트').

배경: match_refresh 는 하루 1번(23:15 UTC) 예약 실행인데 GitHub 예약 실행이 실제로는 1~2시간 늦게, 짧은 주기는
3~8시간에 한 번만 돈다(2026-10-20 측정: 2시간 주기 뉴스가 3~8시간 간격, */10 핑이 3~7시간 간격). 그래서 토요일
낮 경기의 라인업·평점·결장·성적표가 다음 날 아침까지 비었다. 화면 스코어·잠정 순위는 /live-scores 로 이미 실시간.

동작(GH Actions 한 작업이 최대 ~5.5시간 돈다 — 공개 저장소라 분 단위 과금 없음):
  1. 우리 8개 리그 팀의 전 대회 일정(schedule_full)에서 지금 앞뒤 경기(event_id·대회 코드·킥오프)를 고른다.
  2. 5분마다 그 대회·날짜의 ESPN scoreboard 를 본다(요청 수 = 대회×날짜, 보통 5~15개).
  3. ESPN 에서 끝났는데 우리 데이터엔 아직 안 끝난 경기가 GRACE(20분 — FotMob 평점·ESPN 기록 확정) 지나면
     match_refresh 를 workflow_dispatch 로 실행. 재배포가 너무 잦지 않게 MIN_GAP(90분)에 한 번,
     단 남은 경기(진행 중·LOOKAHEAD 안 킥오프)가 없으면 마지막 물결이라 바로.
  4. 오늘 남은 경기가 없으면 끝. 시간 예산을 다 쓰면 남은 경기가 있을 때만 자기 자신을 다시 실행(이어 달리기).
  5. 감시하는 동안 5분마다 백엔드 /api/health 를 깨운다(BACKEND_URL) — keep_alive 예약 실행이 3~7시간 간격이라
     경기일 저녁에도 Render 무료 서버가 잠들어 첫 화면이 30초씩 걸렸다.

사용:
  python scripts/match_watch.py                 # GH Actions (GITHUB_TOKEN·GITHUB_REPOSITORY 필요)
  python scripts/match_watch.py --once --dry-run  # 지금 상태 한 번 보고 무엇을 할지만 출력
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from espn_common import BASE, get_json  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

POLL_S = 300
GRACE = dt.timedelta(minutes=20)
MIN_GAP = dt.timedelta(minutes=90)
LOOKAHEAD = dt.timedelta(hours=3)        # 이 안에 킥오프할 경기가 있으면 '아직 물결 중'
MATCH_LEN = dt.timedelta(hours=2, minutes=15)
FT_AFTER = dt.timedelta(hours=1, minutes=55)   # 킥오프 → 보통 종료(전후반 90 + 휴식 15 + 추가 시간)
REPO = os.getenv("GITHUB_REPOSITORY", "jl3725/football26")
BACKEND = os.getenv("BACKEND_URL", "").rstrip("/")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_fixtures(now: dt.datetime) -> pd.DataFrame:
    """우리 팀 경기(전 대회) 중 [지금-30시간, 오늘 끝+6시간] — event_id 단위 1행, done = 데이터에 이미 결과 있음."""
    frames = []
    for lg in LEAGUES:
        p = data_path("schedule_full", lg)
        if p.exists():
            frames.append(pd.read_csv(p, usecols=["comp_code", "kickoff", "status", "event_id"]))
    if not frames:
        return pd.DataFrame(columns=["event_id", "comp_code", "kickoff", "done"])
    d = pd.concat(frames).dropna(subset=["event_id", "kickoff"])
    d["event_id"] = d["event_id"].astype("int64").astype(str)
    d["kickoff"] = pd.to_datetime(d["kickoff"], utc=True, errors="coerce")
    end_of_day = pd.Timestamp(now.date(), tz="UTC") + pd.Timedelta(days=1, hours=6)
    d = d[(d["kickoff"] >= pd.Timestamp(now) - pd.Timedelta(hours=30)) & (d["kickoff"] <= end_of_day)]
    g = d.groupby("event_id").agg(comp_code=("comp_code", "first"), kickoff=("kickoff", "first"),
                                  done=("status", lambda s: (s == "completed").all()))
    return g.reset_index()


def espn_states(fx: pd.DataFrame) -> dict[str, str]:
    """event_id → ESPN 상태(pre·in·post·postponed). 대회×날짜(UTC) 마다 scoreboard 한 번."""
    out: dict[str, str] = {}
    for (code, day), _ in fx.groupby([fx["comp_code"], fx["kickoff"].dt.strftime("%Y%m%d")]):
        data = get_json(f"{BASE}/{code}/scoreboard?dates={day}", tries=2)
        for e in (data or {}).get("events", []):
            st = (e.get("status") or {}).get("type") or {}
            state = st.get("state") or "pre"
            if state == "post" and not st.get("completed", True):
                state = "postponed"                      # 연기·취소 — 결과 없음
            out[str(e.get("id"))] = state
    return out


class Watch:
    def __init__(self, now: dt.datetime):
        self.first_seen: dict[str, dt.datetime] = {}
        self.handled: set[str] = set()
        self.last_refresh: dt.datetime | None = None
        self.started = now

    def decide(self, fx: pd.DataFrame, states: dict[str, str], now: dt.datetime) -> dict:
        """이번 회차 판단 — {'refresh': [id…], 'live', 'soon', 'pending', 'later_today'}."""
        finished_new = [r.event_id for r in fx.itertuples()
                        if states.get(r.event_id) == "post" and not r.done and r.event_id not in self.handled]
        for i in finished_new:
            self.first_seen.setdefault(i, now)
        kick = dict(zip(fx["event_id"], fx["kickoff"]))
        # 끝난 걸 본 지 GRACE 지났거나, 감시 시작 전에 이미 끝난 경기(킥오프+1시간 55분+GRACE 지남)
        ready = [i for i in finished_new
                 if now - self.first_seen[i] >= GRACE or now >= kick[i] + FT_AFTER + GRACE]
        live = [r.event_id for r in fx.itertuples() if states.get(r.event_id) == "in"]
        soon = [r.event_id for r in fx.itertuples()
                if states.get(r.event_id, "pre") == "pre" and now - MATCH_LEN < r.kickoff <= now + LOOKAHEAD]
        later = [r.event_id for r in fx.itertuples()
                 if states.get(r.event_id, "pre") == "pre" and r.kickoff > now + LOOKAHEAD
                 and r.kickoff.date() <= (now + dt.timedelta(hours=6)).date()]
        wave_over = not live and not soon
        gap_ok = self.last_refresh is None or now - self.last_refresh >= MIN_GAP
        refresh = ready if ready and (gap_ok or wave_over) else []
        return {"refresh": refresh, "live": live, "soon": soon, "pending": [i for i in finished_new if i not in ready],
                "later_today": later}


def dispatch(workflow: str, dry: bool) -> bool:
    if dry:
        print(f"[watch] (dry-run) {workflow} 실행했을 것")
        return True
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=20)
    ok = r.status_code == 204
    print(f"[watch] {workflow} 실행 요청 → {r.status_code}{'' if ok else ' ' + r.text[:200]}")
    return ok


def ping_backend() -> None:
    if not BACKEND:
        return
    try:
        r = requests.get(f"{BACKEND}/api/health", timeout=60)
        print(f"[watch] 백엔드 깨우기 {r.status_code}")
    except requests.RequestException as e:
        print(f"[watch] 백엔드 깨우기 실패: {type(e).__name__}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=330)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    w = Watch(_now())
    deadline = w.started + dt.timedelta(minutes=a.max_minutes)
    while True:
        now = _now()
        fx = load_fixtures(now)
        if fx.empty:
            print("[watch] 오늘 앞뒤로 우리 팀 경기가 없음 — 종료")
            return 0
        states = espn_states(fx)
        d = w.decide(fx, states, now)
        print(f"[watch] {now:%H:%M}Z 경기 {len(fx)} · 진행 {len(d['live'])} · 곧 {len(d['soon'])} · "
              f"끝남(대기) {len(d['pending'])} · 갱신 대상 {len(d['refresh'])} · 오늘 늦게 {len(d['later_today'])}")
        if d["refresh"] and dispatch("match_refresh.yml", a.dry_run):
            w.handled.update(d["refresh"])
            w.last_refresh = now
        if a.once:
            return 0
        if not (d["live"] or d["soon"] or d["pending"] or d["later_today"]):
            print("[watch] 오늘 남은 경기 없음 — 종료")
            return 0
        if now + dt.timedelta(seconds=POLL_S) >= deadline:
            print("[watch] 시간 예산 끝 — 남은 경기가 있어 다음 감시를 이어서 실행")
            dispatch("match_watch.yml", a.dry_run)
            return 0
        ping_backend()
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
