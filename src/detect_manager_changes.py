"""감독 변화 감지 — 지난 시즌 대비 다음 시즌(추적 시즌) 감독 교체 탐지.

위키 시즌 문서의 감독표를 지난시즌(예 2025-26) vs 추적시즌(2026-27) 비교해
팀별 교체(예: Real Madrid: Arbeloa → Mourinho)를 감지, manager_changes[_league] 로 기록.
inbox(Signals) 탭이 이 테이블을 읽어 '감독 변화'로 표시한다.

EPL 은 기존 sync_manager_profiles 가 리치 스키마로 채우므로, 이 도구는 승격 리그 등
manager_changes 가 없는 리그(LaLiga…)용. 필요 시 --league EPL 로도 실행 가능.

사용:
    python src/detect_manager_changes.py --league LaLiga --write
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect_season_teams import _normalizer, _source_title  # noqa: E402
from leagues import PRIMARY_LEAGUE, data_path  # noqa: E402
from sync_manager_profiles import fetch_source_managers, tracking_season_title  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _prev_title(title: str) -> str:
    """'2026-27 La Liga' → '2025-26 La Liga'."""
    m = re.search(r"(\d{4})-(\d{2})", title)
    if not m:
        return title
    y1 = int(m.group(1))
    return title[:m.start()] + f"{y1 - 1}-{y1 % 100:02d}" + title[m.end():]


def _out_path(league: str) -> Path:
    if league == PRIMARY_LEAGUE:
        return ROOT / "data" / "manager_changes.csv"
    return data_path("manager_changes", league)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="LaLiga", help="EPL | LaLiga")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    league = args.league

    base = tracking_season_title()
    cur_title = _source_title(league, base)
    prev_title = _prev_title(cur_title)
    norm = _normalizer(league)
    print(f"[mgr-changes] {league}: {prev_title}  →  {cur_title}")

    try:
        cur = {norm(k): v for k, v in fetch_source_managers(cur_title).items()}
        prev = {norm(k): v for k, v in fetch_source_managers(prev_title).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"[mgr-changes] 위키 파싱 실패: {exc}", file=sys.stderr)
        return 1
    if len(cur) < 10 or len(prev) < 10:
        print(f"[mgr-changes] 팀 수 비정상(cur {len(cur)}, prev {len(prev)}) — 중단", file=sys.stderr)
        return 1

    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    rows = []
    for team in sorted(cur):
        c = str(cur[team] or "").strip()
        p = str(prev.get(team) or "").strip()
        _skip = {"TBA", "TBD", "N/A", "-"}
        if c.upper() in _skip or p.upper() in _skip:   # 미정은 교체로 안 봄
            continue
        if c and p and c != p:
            rows.append({
                "detected_at": now, "team": team,
                "previous_manager": p, "detected_manager": c,
                "change_type": "season", "accepted": 1,
                "source": f"Wikipedia {prev_title} → {cur_title}",
            })

    print(f"  감지 {len(rows)}건:")
    for r in rows:
        print(f"    {r['team']:18} {r['previous_manager']} → {r['detected_manager']}")

    fields = ["detected_at", "team", "previous_manager", "detected_manager",
              "change_type", "accepted", "source"]
    if args.write:
        out = _out_path(league)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"WROTE {out} ({len(rows)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
