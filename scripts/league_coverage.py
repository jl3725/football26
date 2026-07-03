"""
리그 커버리지(parity) 진단 — 리그 확장 시 '무엇이 빠졌나'를 한 번에.

각 리그 × 각 데이터 피처의 존재/행수를 매트릭스로 출력한다. 새 리그를 넣으면
이 표만 보면 되므로, 탭을 하나하나 눌러보며 확인할 필요가 없다.

사용:
    python scripts/league_coverage.py
    python scripts/league_coverage.py --json   # 기계 판독용
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import datastore as ds  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# (표시명, kind, 식별자) — kind: table(datastore) / json(league별) / json_team(공유 팀키)
FEATURES = [
    ("선수(players_full)",      "table", "players_full"),
    ("순위(standings)",          "table", "standings"),
    ("스케줄 통합(schedule_full)", "table", "schedule_full"),
    ("이적(transfers)",          "table", "transfers"),
    ("부상 현황(injuries)",       "table", "transfermarkt_injuries"),
    ("부상 변화(injury_changes)", "table", "transfermarkt_injury_changes"),
    ("부상 이력(tm_injury_history)", "table", "tm_injury_history"),
    ("계약(contracts)",          "table", "transfermarkt_contracts"),
    ("역할축(comp_usage)",        "table", "player_comp_usage"),
    ("라인업(espn_lineups)",      "table", "espn_lineups"),
    ("컵 라인업(cups)",           "table", "espn_lineups_cups"),
    ("팀 지표(unit_metrics)",     "table", "team_unit_metrics"),
    ("팀 스탯(statbunker)",       "table", "statbunker_team_stats"),
    ("수비(team_defense)",        "table", "team_defense"),
    ("뉴스(news_articles)",       "table", "news_articles"),
    ("이적 루머(transfer_buzz)",  "table", "transfer_buzz"),
    ("감독(manager_profiles)",    "json",  "manager_profiles"),
    ("팀 설명(team_profiles)",    "json_team", "team_profiles"),
]


def _rows(stem: str, league: str, teams: set) -> tuple[int | None, bool]:
    """(행수, 이 리그 데이터 맞나). 팀컬럼 있는데 리그 팀과 겹침 0 → 타리그 공유(예: EPL 뉴스)."""
    try:
        df = ds.read_table(stem, league=league)
    except Exception:  # noqa: BLE001
        return None, True
    if df is None:
        return None, True
    col = "squad" if "squad" in df.columns else ("team" if "team" in df.columns else None)
    if col and teams:
        overlap = len(set(df[col].astype(str)) & teams)
        return len(df), overlap > 0
    return len(df), True


def _json_rows(stem: str, league: str) -> int | None:
    p = (ROOT / "data" / f"{stem}_2025_2026.json") if league == "EPL" else data_path(stem, league, ext="json")
    try:
        return len(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def _team_json(stem: str, league: str, teams: set) -> int | None:
    """공유 JSON(team_profiles)에 이 리그 팀이 몇 개 들어있나."""
    try:
        d = json.loads((ROOT / "data" / f"{stem}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return sum(1 for t in teams if t in d)


def league_teams(league: str) -> set:
    df = ds.read_table("standings", league=league)
    if df is None:
        df = ds.read_table("players_full", league=league)
    return set(df["squad"].astype(str)) if df is not None and "squad" in df.columns else set()


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    leagues = list(LEAGUES)
    teams_by = {lg: league_teams(lg) for lg in leagues}
    matrix: dict = {}
    for label, kind, stem in FEATURES:
        row = {}
        for lg in leagues:
            if kind == "table":
                n, ok = _rows(stem, lg, teams_by[lg])
            elif kind == "json":
                n, ok = _json_rows(stem, lg), True
            else:
                n, ok = _team_json(stem, lg, teams_by[lg]), True
            row[lg] = {"n": n, "ok": ok}
        matrix[label] = row

    if "--json" in args:
        print(json.dumps(matrix, ensure_ascii=False, indent=2))
        return 0

    def cell(c) -> str:
        n, ok = c["n"], c["ok"]
        if not n:
            return "✗ 없음"
        if not ok:
            return f"⚠ 타리그({n})"      # 데이터는 있으나 이 리그 것이 아님(예: EPL 뉴스 공유)
        return f"✓ {n}"

    w = max(len(f[0]) for f in FEATURES) + 2
    cw = 15
    header = "피처".ljust(w) + "".join(lg.ljust(cw) for lg in leagues)
    print(header)
    print("─" * len(header))
    for label, _kind, _stem in FEATURES:
        print(label.ljust(w) + "".join(cell(matrix[label][lg]).ljust(cw) for lg in leagues))
    print("\n✓=정상  ⚠타리그=EPL 데이터 공유(실제 그 리그 아님)  ✗=없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
