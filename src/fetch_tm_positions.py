"""
Transfermarkt 선수 프로필 → 대표 포지션 + 그 밖의 포지션(커리어상 익숙한 자리) — 포지션별 OVR(src/position_ovr.py)의 하한.

라인업으로 보는 기간은 이번·지난 시즌뿐이라 그 전에 많이 뛴 자리(베르나르두 맨시티 시절 RW)는 칩이 낮거나 없고,
시즌이 바뀌면 지난 시즌 선발이 빠지며 익숙함이 내려간다(2026-11-02 사용자: 'OVR 도 좀 더 stable 해질까요').
TM 프로필의 'Main position' · 'Other position'(최대 2)을 받아 둔다 — 경기 수는 없어 익숙함 하한으로만 쓴다.

선수마다 프로필 한 장이라 요청이 많다. TM(WAF)은 짧은 시간에 많이 부르면 403 을 주고, 그 뒤엔 같은 실행의 다른 TM
수집도 막힌다 — 매일 수집(계약·이적…) 뒤에 붙였더니 리그마다 10명쯤에서 403, 다음 리그 계약 수집까지 실패했다
(2026-11-02). 그래서 따로 도는 단계(TM Data mode=positions)로, 천천히(PAUSE), 한 번에 MAX_PER_RUN 명까지,
막히면 한 번 쉬었다가 다시 막히면 그 실행을 멈춘다(exit 75 = 원천 중단, 받은 것은 저장).
포지션은 거의 안 바뀌므로 처음 보는 선수 먼저, 이미 받은 선수는 REFRESH_DAYS 지나면 다시.

Writes data/tm_positions[_리그].csv: squad, player, tm_player_id, main_position, other_positions('|' 구분), last_checked

Usage:
  python src/fetch_tm_positions.py                 # 전 리그(src/leagues.py), 한 번에 MAX_PER_RUN 명
  python src/fetch_tm_positions.py --league EPL --max 20
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import date, datetime

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm_http  # noqa: E402  — 클라우드(WAF 202)에서도 열리게
from leagues import LEAGUES, data_path  # noqa: E402

FIELDS = ["squad", "player", "tm_player_id", "main_position", "other_positions", "last_checked"]
REFRESH_DAYS = 60
MAX_PER_RUN = 900        # 전 리그 합(시간 예산 안에서 — 15초 간격이면 약 700명)
# 2026-11-03 점검: 3초 간격은 20명쯤에서 403, 300초 뒤 또 막혀 실행마다 20명(전체 3%). 부상 이력 수집(1.2초 간격 5천 장)은
# 안 막히는 걸 보면 프로필 페이지만 따로 세는 듯 — 천천히, 막히면 10·20·30분 쉬고 이어서, 시간 예산까지
PAUSE = 15.0             # 요청 간격(초)
BACKOFF = (600, 1200, 1800)   # 막힐 때마다 쉬는 시간(초) — 성공하면 처음부터
BUDGET_S = 3.5 * 3600    # 실행 시간 예산(초) — 워크플로 제한(300분) 안
EX_SOURCE_DOWN = 75
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


class Blocked(RuntimeError):
    pass


def parse_positions(page_html: str) -> tuple[str, list[str]]:
    """프로필 HTML → (대표 포지션, [그 밖의 포지션]). 상자가 없으면 ('', [])."""
    soup = BeautifulSoup(page_html, "lxml")
    main, others = "", []
    for dl in soup.select(".detail-position dl"):
        title = dl.select_one(".detail-position__title")
        vals = [dd.get_text(" ", strip=True) for dd in dl.select("dd.detail-position__position")]
        t = title.get_text(" ", strip=True).lower() if title else ""
        if t.startswith("main position") and vals:
            main = vals[0]
        elif t.startswith("other position"):
            others += [v for v in vals if v]
    return main, others


def fetch(tm_id: str) -> tuple[str, list[str]]:
    resp = tm_http.get(f"https://www.transfermarkt.com/-/profil/spieler/{tm_id}", headers=H, timeout=30)
    if resp.status_code in (202, 403, 429) or (resp.status_code == 200 and not resp.text.strip()):
        raise Blocked(f"HTTP {resp.status_code}")
    resp.raise_for_status()
    return parse_positions(resp.text)


def read_existing(out) -> dict[str, dict]:
    if not out.exists():
        return {}
    with out.open("r", newline="", encoding="utf-8") as f:
        return {r["tm_player_id"]: r for r in csv.DictReader(f) if r.get("tm_player_id")}


def write_rows(out, rows: dict[str, dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["squad"], r["player"])))


def _age_days(checked: str, today: date) -> int:
    try:
        return (today - date.fromisoformat(str(checked)[:10])).days
    except ValueError:
        return 10 ** 6


def todo(players: pd.DataFrame, have: dict[str, dict], today: date) -> list[tuple[int, str, str, str]]:
    """받을 선수 (오래된 정도, tm_id, squad, player) — 처음 보는 선수 먼저, 그다음 오래된 순."""
    ids = players["tm_id"] if "tm_id" in players.columns else pd.Series([None] * len(players))
    out, seen = [], set()
    for v, sq, pl in zip(ids, players["squad"].astype(str), players["player"].astype(str)):
        if pd.isna(v) or str(v).strip() in ("", "nan"):
            continue
        tid = str(int(float(v)))
        if tid in seen:
            continue
        seen.add(tid)
        age = _age_days(have[tid]["last_checked"], today) if tid in have else 10 ** 7
        if age >= REFRESH_DAYS:
            out.append((age, tid, sq, pl))
    out.sort(key=lambda x: -x[0])
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append", help="리그(여러 번 가능) — 없으면 전 리그")
    ap.add_argument("--max", type=int, default=MAX_PER_RUN, help="이번에 받을 최대 선수 수(전 리그 합)")
    args = ap.parse_args(argv)
    today = datetime.now().astimezone().date()
    leagues = args.league or list(LEAGUES)
    # 리그마다 할 일 — 처음 보는 선수가 많은 리그부터 고르게 돌도록 리그를 번갈아 뽑는다
    state, queues = {}, {}
    for lg in leagues:
        src = data_path("players_full", lg)
        if not src.exists():
            continue
        out = data_path("tm_positions", lg)
        have = read_existing(out)
        state[lg] = (out, have)
        queues[lg] = todo(pd.read_csv(src), have, today)
    plan: list[tuple[str, str, str, str]] = []
    while len(plan) < args.max and any(queues.values()):
        for lg in leagues:
            if queues.get(lg) and len(plan) < args.max:
                _age, tid, sq, pl = queues[lg].pop(0)
                plan.append((lg, tid, sq, pl))
    print(f"[tm_positions] 이번 {len(plan)}명 · 남은 {sum(len(q) for q in queues.values())}명 · 리그 {len(state)}")
    done, blocks, dirty = 0, 0, set()
    t0 = time.monotonic()
    i = 0
    while i < len(plan):
        if time.monotonic() - t0 > BUDGET_S:
            print(f"  · 시간 예산 끝 — 받은 {done}명 저장, 남은 {len(plan) - i}명은 다음 실행")
            break
        lg, tid, squad, player = plan[i]
        try:
            main_pos, others = fetch(tid)
        except Blocked as e:
            for g in dirty:
                write_rows(*state[g])
            dirty.clear()
            if blocks < len(BACKOFF) and time.monotonic() - t0 + BACKOFF[blocks] < BUDGET_S:
                print(f"  ! {player} ({tid}) {e} — {BACKOFF[blocks] // 60}분 쉬고 다시(받은 {done}명)")
                time.sleep(BACKOFF[blocks])
                blocks += 1
                continue                       # 같은 선수 다시
            print(f"  ! 계속 막힘({e}) — 이번 실행 멈춤, 받은 {done}명 저장")
            break
        except Exception as e:  # noqa: BLE001 — 한 선수 실패(404 등)는 건너뛴다
            print(f"    x {player} ({tid}): {type(e).__name__}: {e}")
            i += 1
            time.sleep(PAUSE)
            continue
        out, have = state[lg]
        have[tid] = {"squad": squad, "player": player, "tm_player_id": tid, "main_position": main_pos,
                     "other_positions": "|".join(others), "last_checked": today.isoformat()}
        dirty.add(lg)
        done += 1
        blocks = 0
        i += 1
        if done % 50 == 0:
            for g in dirty:
                write_rows(*state[g])
            dirty.clear()
            print(f"    · {done}명")
        time.sleep(PAUSE)
    for g in dirty:
        write_rows(*state[g])
    print(f"Done. 받음 {done} / {len(plan)}")
    return 0 if done or not plan else EX_SOURCE_DOWN        # 하나도 못 받았을 때만 원천 중단(받은 만큼은 진척)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
