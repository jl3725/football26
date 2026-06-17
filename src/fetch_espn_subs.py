"""
ESPN 경기 교체 이벤트 스크래퍼 (2025/26 EPL).

espn_lineups_2025_2026.csv 의 event_id 별로 ESPN 요약 API를 호출해
교체(IN/OUT + 분)를 data/espn_subs_2025_2026.csv 로 저장한다.
컬럼: event_id, home_away(home/away), minute, minute_sec, player_in, player_out

사용:
    python src/fetch_espn_subs.py            # 전 경기 (이미 받은 event는 건너뜀)
    python src/fetch_espn_subs.py --refresh  # 처음부터 다시
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
LINEUPS = DATA / "espn_lineups_2025_2026.csv"
OUT = DATA / "espn_subs_2025_2026.csv"
API = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
SLEEP = 0.4

_RE = re.compile(r"\.\s*(.+?)\s+replaces\s+(.+?)\.?\s*$")


def scrape_event(event_id) -> list[dict]:
    try:
        r = requests.get(API, headers=H, params={"event": event_id}, timeout=25)
    except requests.exceptions.RequestException:
        return []
    if r.status_code != 200:
        return []
    d = r.json()
    # team id → home/away
    ha: dict[str, str] = {}
    try:
        comps = d["header"]["competitions"][0]["competitors"]
        for c in comps:
            ha[str(c["team"]["id"])] = c.get("homeAway", "")
    except (KeyError, IndexError):
        pass
    out = []
    for ev in d.get("keyEvents", []):
        if (ev.get("type", {}) or {}).get("type") != "substitution":
            continue
        tid = str((ev.get("team", {}) or {}).get("id", ""))
        clock = (ev.get("clock", {}) or {})
        minute = clock.get("displayValue", "")
        minute_sec = clock.get("value", 0)
        m = _RE.search(ev.get("text", "") or "")
        p_in = m.group(1).strip() if m else ""
        p_out = m.group(2).strip() if m else ""
        if not (p_in or p_out):
            continue
        out.append({"event_id": event_id, "home_away": ha.get(tid, ""),
                    "minute": minute, "minute_sec": minute_sec,
                    "player_in": p_in, "player_out": p_out})
    return out


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    refresh = "--refresh" in args

    if not LINEUPS.exists():
        print(f"[오류] {LINEUPS.name} 없음")
        return 1
    events = sorted(pd.read_csv(LINEUPS)["event_id"].astype(str).unique())

    done: set[str] = set()
    all_rows: list[dict] = []
    if OUT.exists() and not refresh:
        prev = pd.read_csv(OUT)
        prev["event_id"] = prev["event_id"].astype(str)
        all_rows = prev.to_dict("records")
        done = set(prev["event_id"].unique())

    todo = [e for e in events if e not in done]
    print(f"이벤트 {len(events)}개 · 신규 {len(todo)}개 수집")
    for i, ev in enumerate(todo):
        rows = scrape_event(ev)
        all_rows += rows
        if (i + 1) % 25 == 0 or i + 1 == len(todo):
            pd.DataFrame(all_rows).to_csv(OUT, index=False, encoding="utf-8")
            print(f"  {i+1}/{len(todo)} · 누적 교체 {len(all_rows)}건 저장")
        time.sleep(SLEEP)

    pd.DataFrame(all_rows).to_csv(OUT, index=False, encoding="utf-8")
    print(f"[OK] 저장: {OUT.name} ({len(all_rows)}건 교체)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
