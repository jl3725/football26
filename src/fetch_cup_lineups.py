"""
컵·유럽 라인업/교체 수집기 — Phase B (리그별).

espn_lineups(리그 전용)와 동일 스키마로 챔스·UEL·컨퍼런스 + 국내컵(EPL: FA·EFL / LaLiga:
코파델레이)의 라인업/교체를 긁어, 스케줄 탭에서 컵 경기도 포메이션·교체를 보이게 한다.

저장:
    data/espn_lineups_cups[_LaLiga]_2025_2026.csv
    data/espn_subs_cups[_LaLiga]_2025_2026.csv
사용:
    python src/fetch_cup_lineups.py                  # EPL
    python src/fetch_cup_lineups.py --league LaLiga
"""
from __future__ import annotations

import re
import sys
import time

import pandas as pd
import requests

from espn_common import EURO_COMPS, DOMESTIC_CUPS, squad_of
from leagues import data_path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

SEASON_RANGE = "20250701-20260630"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_SUB_RE = re.compile(r"\.\s*(.+?)\s+replaces\s+(.+?)\.?\s*$")


def team_name(team: dict | None, league: str) -> str:
    return squad_of(team, league) or (team or {}).get("displayName") or ""


def _get(url: str, tries: int = 3) -> dict | None:
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.ok:
                return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"    [재시도 {i+1}] {e}")
        time.sleep(0.6)
    return None


def season_events(code: str, league: str) -> list[str]:
    data = _get(f"{BASE}/{code}/scoreboard?dates={SEASON_RANGE}&limit=500")
    out = []
    for e in (data or {}).get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed"):
            continue
        if any(squad_of(c.get("team", {}), league) for c in comp.get("competitors", [])):
            out.append(e.get("id"))
    return [x for x in out if x]


def parse_summary(code: str, eid: str, league: str) -> tuple[list[dict], list[dict]]:
    s = _get(f"{BASE}/{code}/summary?event={eid}")
    if not s:
        return [], []
    rosters = s.get("rosters", [])
    by_ha = {t.get("homeAway"): t.get("team", {}) for t in rosters}
    lineup_rows = []
    try:
        date = (s.get("header", {}).get("competitions", [{}])[0].get("date") or "")[:10]
    except Exception:  # noqa: BLE001
        date = ""
    for t in rosters:
        squad = squad_of(t.get("team", {}), league)
        if not squad:
            continue
        ha = t.get("homeAway")
        opp = team_name(by_ha.get("away" if ha == "home" else "home"), league)
        formation = t.get("formation", "")
        for p in t.get("roster", []):
            pos = p.get("position", {}) or {}
            ath = p.get("athlete", {}) or {}
            lineup_rows.append({
                "squad": squad, "date": date, "opponent": opp, "home_away": ha,
                "formation": formation, "starter": 1 if p.get("starter") else 0,
                "jersey": p.get("jersey", ""), "player": ath.get("displayName", ""),
                "espn_pos": pos.get("abbreviation", ""),
                "formation_place": p.get("formationPlace", ""), "event_id": eid,
            })
    ha_by_tid, our_tid = {}, set()
    try:
        for c in s["header"]["competitions"][0]["competitors"]:
            tid = str(c["team"]["id"])
            ha_by_tid[tid] = c.get("homeAway", "")
            if squad_of(c.get("team", {}), league):
                our_tid.add(tid)
    except (KeyError, IndexError):
        pass
    sub_rows = []
    for ev in s.get("keyEvents", []):
        if (ev.get("type", {}) or {}).get("type") != "substitution":
            continue
        tid = str((ev.get("team", {}) or {}).get("id", ""))
        if tid not in our_tid:
            continue
        clk = ev.get("clock", {}) or {}
        m = _SUB_RE.search(ev.get("text", "") or "")
        if not m:
            continue
        sub_rows.append({"event_id": eid, "home_away": ha_by_tid.get(tid, ""),
                         "minute": clk.get("displayValue", ""), "minute_sec": clk.get("value", 0),
                         "player_in": m.group(1).strip(), "player_out": m.group(2).strip()})
    return lineup_rows, sub_rows


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    league = "EPL"
    if "--league" in args:
        league = args[args.index("--league") + 1]

    comps = [c for c, _, _ in EURO_COMPS] + [c for c, _, _ in DOMESTIC_CUPS.get(league, [])]
    all_lineups, all_subs = [], []
    for code in comps:
        eids = season_events(code, league)
        print(f"  [{code}] 완료경기 {len(eids)}개 — 라인업/교체 수집…")
        for i, eid in enumerate(eids):
            lu, sb = parse_summary(code, eid, league)
            all_lineups += lu
            all_subs += sb
            time.sleep(0.12)
            if (i + 1) % 30 == 0:
                print(f"    {i+1}/{len(eids)} · 라인업 {len(all_lineups)} · 교체 {len(all_subs)}")

    if not all_lineups:
        print("수집 없음.")
        return 1
    ldf = pd.DataFrame(all_lineups).drop_duplicates(subset=["event_id", "squad", "player"])
    sdf = pd.DataFrame(all_subs).drop_duplicates()
    print(f"\n[{league}] 경기 {ldf['event_id'].nunique()} · 라인업 {len(ldf)}(선발 {int(ldf['starter'].sum())}) · 교체 {len(sdf)} · 팀 {ldf['squad'].nunique()}")
    if dry:
        print("[DRY] 저장 안 함.")
    else:
        lout, sout = data_path("espn_lineups_cups", league), data_path("espn_subs_cups", league)
        ldf.to_csv(lout, index=False, encoding="utf-8")
        sdf.to_csv(sout, index=False, encoding="utf-8")
        print(f"[OK] {lout.name} + {sout.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
