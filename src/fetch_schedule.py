"""
스케줄 수집기 — 리그 + 컵 + 유럽대회 픽스처/결과를 대회별로 통합.

ESPN scoreboard 로 대회별 경기를 긁어 우리 팀 관점 행(대회·상대·홈원정·스코어·상태)을 만든다.
치러진 경기는 event_id 로 라인업 연결. 리그별(EPL·LaLiga…) · 시즌별(25/26·26/27).

저장: data/schedule_full[_LaLiga]_{2025_2026|2026_2027}.csv
사용:
    python src/fetch_schedule.py                              # 전 리그 · 기본 시즌
    python src/fetch_schedule.py --league LaLiga
    python src/fetch_schedule.py --league LaLiga 2026_2027

기본 시즌 = 활성 데이터 시즌(FB_SEASON_START) + 달력상 현재 시즌(season_context) — 보통 1~2개.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from espn_common import (LEAGUE_CODE, EURO_COMPS, DOMESTIC_CUPS, scoreboard_events,
                         season_bounds, season_squad_of, squad_of)
from leagues import SEASON_START, data_path
from season_context import current_window

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def _season_token(start_year: int) -> str:
    return f"{start_year}_{start_year + 1}"


def default_seasons() -> list[str]:
    years = sorted({SEASON_START, current_window()["season_id"]})
    return [_season_token(y) for y in years]


def _comps(league: str):
    """(code, 라벨) 리스트 — 리그 + 유럽 + 국내컵."""
    return [LEAGUE_CODE[league]] + [(c, l) for c, l, _ in EURO_COMPS] \
        + [(c, l) for c, l, _ in DOMESTIC_CUPS.get(league, [])]


def collect_comp(code: str, label: str, start_year: int, league: str, ours) -> list[dict] | None:
    """대회 하나의 시즌 경기 → 우리 팀 관점 행. 조회 실패 시 None."""
    events = scoreboard_events(code, *season_bounds(start_year))
    if events is None:
        return None
    rows: list[dict] = []
    for e in events:
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
        kickoff = e.get("date") or ""          # UTC ISO(예 2026-10-18T14:00Z) — 화면은 한국 시간으로 바꿔 쓴다
        eid = str(e.get("id") or "")
        for side, opp in ((home, away), (away, home)):
            sq = ours(side.get("team", {}))
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
                "squad": sq, "comp": label, "comp_code": code, "date": date, "kickoff": kickoff,
                "home_away": "H" if side is home else "A",
                "opponent": squad_of(opp.get("team", {}), league) or (opp.get("team", {}) or {}).get("displayName", ""),
                "gf": gf, "ga": ga,
                "score": f"{gf}-{ga}" if (gf is not None and ga is not None) else "",
                "result": result,
                "status": "completed" if completed else "scheduled",
                "event_id": eid,
                # 우리 리그 밖 상대(컵 하부 리그·유럽대회 상대)는 로고 사전에 없다 → ESPN 로고를 함께 저장
                "opponent_logo": (opp.get("team", {}) or {}).get("logo")
                or next((l.get("href") for l in ((opp.get("team", {}) or {}).get("logos") or []) if l.get("href")), ""),
            })
    return rows


def run_season(season: str, league: str) -> int:
    start_year = int(season[:4])
    print(f"=== [{league}] 시즌 {season} ===")
    ours = season_squad_of(league, start_year)   # 강등팀이 다음 시즌 컵 경기로 섞이지 않게
    all_rows: list[dict] = []
    for code, label in _comps(league):
        rows = collect_comp(code, label, start_year, league, ours)
        if rows is None:
            # 부분 수집으로 기존 파일을 덮어쓰면 대회 하나가 통째로 사라진다 — 저장 중단.
            print(f"  {label:10} {code:20} 조회 실패 — 기존 파일 유지")
            return 1
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
    seasons = [a for a in args if len(a) == 9 and a[4] == "_"] or default_seasons()
    rc = 0
    for lg in leagues:
        for s in seasons:
            rc |= run_season(s, lg)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
