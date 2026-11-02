"""
Transfermarkt 선수 프로필 → 대표 포지션 + 그 밖의 포지션(커리어상 익숙한 자리) — 포지션별 OVR(src/position_ovr.py)의 하한.

라인업으로 보는 기간은 이번·지난 시즌뿐이라 그 전에 많이 뛴 자리(베르나르두 맨시티 시절 RW)는 칩이 낮거나 없고,
시즌이 바뀌면 지난 시즌 선발이 빠지며 익숙함이 내려간다(2026-11-02 사용자: 'OVR 도 좀 더 stable 해질까요').
TM 프로필의 'Main position' · 'Other position'(최대 2)을 받아 둔다 — 경기 수는 없어 익숙함 하한으로만 쓴다.

포지션은 거의 안 바뀌므로 처음 보는 선수 먼저, 이미 받은 선수는 REFRESH_DAYS 지나면 다시. 한 번에 리그당 MAX_PER_RUN 명
(TM Data 하루 2회 — 처음 채우기 2~3일, 그 뒤엔 새 선수만이라 몇 분).

Writes data/tm_positions[_리그].csv: squad, player, tm_player_id, main_position, other_positions('|' 구분), last_checked

Usage:
  FB_LEAGUE=EPL python src/fetch_tm_positions.py            # 리그 한 개(TM Data 워크플로가 리그마다 부름)
  FB_LEAGUE=EPL python src/fetch_tm_positions.py --max 0    # 제한 없이(처음 한 번에 채우기)
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
from leagues import data_path  # noqa: E402

PLAYERS = data_path("players_full")
OUT = data_path("tm_positions")
FIELDS = ["squad", "player", "tm_player_id", "main_position", "other_positions", "last_checked"]
REFRESH_DAYS = 60
MAX_PER_RUN = 150
MAX_STREAK = 15          # 연속 실패 — 전면 차단이면 일찍 멈추고 받은 것만 저장
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


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
    if resp.status_code != 200 or not resp.text.strip():
        raise RuntimeError(f"HTTP {resp.status_code} (WAF 챌린지 추정)")
    return parse_positions(resp.text)


def read_existing() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    with OUT.open("r", newline="", encoding="utf-8") as f:
        return {r["tm_player_id"]: r for r in csv.DictReader(f) if r.get("tm_player_id")}


def write_rows(rows: dict[str, dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["squad"], r["player"])))


def _age_days(checked: str, today: date) -> int:
    try:
        return (today - date.fromisoformat(str(checked)[:10])).days
    except ValueError:
        return 10 ** 6


def todo(players: pd.DataFrame, have: dict[str, dict], today: date) -> list[tuple[str, str, str]]:
    """받을 선수 (tm_id, squad, player) — 처음 보는 선수 먼저, 그다음 오래된 순."""
    out = []
    for tid, sq, pl in zip(players["__tmid"], players["squad"].astype(str), players["player"].astype(str)):
        if not tid:
            continue
        age = _age_days(have[tid]["last_checked"], today) if tid in have else 10 ** 7
        if age >= REFRESH_DAYS:
            out.append((age, tid, sq, pl))
    out.sort(key=lambda x: -x[0])
    seen, uniq = set(), []
    for _age, tid, sq, pl in out:
        if tid not in seen:
            seen.add(tid)
            uniq.append((tid, sq, pl))
    return uniq


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=MAX_PER_RUN, help="이번에 받을 최대 선수 수(0 = 제한 없음)")
    args = ap.parse_args(argv)
    if not PLAYERS.exists():
        print(f"선수 표 없음: {PLAYERS}")
        return 0
    df = pd.read_csv(PLAYERS)
    ids = df["tm_id"] if "tm_id" in df.columns else pd.Series([None] * len(df))
    df["__tmid"] = [str(int(float(v))) if pd.notna(v) and str(v).strip() not in ("", "nan") else "" for v in ids]
    have = read_existing()
    today = datetime.now().astimezone().date()
    queue = todo(df, have, today)
    if args.max:
        queue = queue[:args.max]
    print(f"[tm_positions] {OUT.name}: 받을 선수 {len(queue)}명(기존 {len(have)}명)")
    done = streak = 0
    for i, (tid, squad, player) in enumerate(queue, 1):
        try:
            main_pos, others = fetch(tid)
        except Exception as e:  # noqa: BLE001
            streak += 1
            print(f"    x {player} ({tid}): {e}")
            if streak >= MAX_STREAK:
                print(f"  ! 연속 {streak}회 실패 — 차단으로 보고 중단(받은 것만 저장)")
                break
            time.sleep(1.0)
            continue
        streak = 0
        have[tid] = {"squad": squad, "player": player, "tm_player_id": tid, "main_position": main_pos,
                     "other_positions": "|".join(others), "last_checked": today.isoformat()}
        done += 1
        if i % 50 == 0:
            write_rows(have)              # 중간 저장
        time.sleep(1.2)
    if done:
        write_rows(have)
    print(f"Done. 받음 {done} / {len(queue)} → {OUT}")
    return 1 if (streak >= MAX_STREAK and done == 0 and queue) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
