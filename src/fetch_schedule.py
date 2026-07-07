"""
스케줄 수집기 — 리그 + 컵 + 유럽대회 픽스처/결과를 대회별로 통합.

ESPN scoreboard 로 대회별 경기를 긁어 우리 팀 관점 행(대회·상대·홈원정·스코어·상태)을 만든다.
치러진 경기는 event_id 로 라인업 연결. 리그별(EPL·LaLiga…) · 시즌별(25/26·26/27).

저장: data/schedule_full[_LaLiga]_{2025_2026|2026_2027}.csv
사용:
    python src/fetch_schedule.py                              # EPL 두 시즌
    python src/fetch_schedule.py --league LaLiga
    python src/fetch_schedule.py --league LaLiga 2026_2027
"""
from __future__ import annotations

import sys
import time

import pandas as pd
import requests

from espn_common import LEAGUE_CODE, EURO_COMPS, DOMESTIC_CUPS, squad_of
from leagues import data_path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
SEASONS = {"2025_2026": "20250701-20260630", "2026_2027": "20260701-20270630"}


def _comps(league: str):
    """(code, 라벨) 리스트 — 리그 + 유럽 + 국내컵."""
    return [LEAGUE_CODE[league]] + [(c, l) for c, l, _ in EURO_COMPS] \
        + [(c, l) for c, l, _ in DOMESTIC_CUPS.get(league, [])]


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


def collect_comp(code: str, label: str, date_range: str, league: str) -> list[dict]:
    data = _get(f"{BASE}/{code}/scoreboard?dates={date_range}&limit=500")
    rows: list[dict] = []
    for e in (data or {}).get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        by_ha = {c.get("homeAway"): c for c in cs}
        home, away = by_ha.get("home"), by_ha.get("away")
        if not home or not away:
            continue
        status = comp.get("status", {}).get("type", {})
        completed = bool(status.get("completed"))
        date = (e.get("date") or "")[:10]
        eid = str(e.get("id") or "")
        for side, opp in ((home, away), (away, home)):
            sq = squad_of(side.get("team", {}), league)
            if not sq:
                continue
            gf, ga = side.get("score"), opp.get("score")
            try:
                gf = int(gf) if gf not in (None, "") else None
                ga = int(ga) if ga not in (None, "") else None
            except (TypeError, ValueError):
                gf = ga = None
            result = ""
            if completed and gf is not None and ga is not None:
                result = "W" if gf > ga else ("L" if gf < ga else "D")
            rows.append({
                "squad": sq, "comp": label, "comp_code": code, "date": date,
                "home_away": "H" if side is home else "A",
                "opponent": squad_of(opp.get("team", {}), league) or (opp.get("team", {}) or {}).get("displayName", ""),
                "gf": gf, "ga": ga,
                "score": f"{gf}-{ga}" if (gf is not None and ga is not None) else "",
                "result": result,
                "status": "completed" if completed else "scheduled",
                "event_id": eid,
            })
    return rows


def run_season(season: str, league: str) -> int:
    date_range = SEASONS[season]
    print(f"=== [{league}] 시즌 {season} ===")
    all_rows: list[dict] = []
    for code, label in _comps(league):
        rows = collect_comp(code, label, date_range, league)
        print(f"  {label:10} {code:20} 경기행 {len(rows)}")
        all_rows += rows
        time.sleep(0.2)
    if not all_rows:
        print("  수집 없음.")
        return 1
    df = pd.DataFrame(all_rows).drop_duplicates(subset=["squad", "event_id"]).sort_values(["squad", "date"])
    out = data_path("schedule_full", league, season)
    df.to_csv(out, index=False, encoding="utf-8")
    done = int((df["status"] == "completed").sum())
    print(f"  [OK] {out.name} · {len(df)}행 (완료 {done}/예정 {len(df)-done}) · 팀 {df['squad'].nunique()} · 대회 {df['comp'].nunique()}")
    return 0


LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague"]  # --league 미지정 시 전 리그 자동 갱신(agent용)


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    leagues = LEAGUES
    if "--league" in args:
        i = args.index("--league")
        leagues = [args[i + 1]]
        del args[i:i + 2]
    seasons = [a for a in args if a in SEASONS] or list(SEASONS)
    rc = 0
    for lg in leagues:
        for s in seasons:
            rc |= run_season(s, lg)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
