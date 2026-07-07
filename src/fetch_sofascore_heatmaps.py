"""
Sofascore 시즌 히트맵 수집 — 선수별 시즌 누적 활동 구역.

`/player/{id}/unique-tournament/{ut}/season/{sid}/heatmap/overall` → points[{x,y}] (0-100).
포인트를 GW×GH 그리드로 다운샘플·정규화(0-100)해 저장(원본 수백 포인트 → 96칸).
players_sofascore_stats 와 동일한 norm_key(unidecode(name).lower()) 로 조인.

리그: FB_LEAGUE 환경변수(기본 EPL). 사용: FB_LEAGUE=Eredivisie python src/fetch_sofascore_heatmaps.py
출력: data/player_heatmaps_<league>.csv (norm_key,name,team,n_points,gw,gh,grid)
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from unidecode import unidecode  # noqa: E402
from fetch_sofascore_stats import (get, find_season_id, fetch_teams,  # noqa: E402
                                    fetch_team_players, UT_ID)
from leagues import data_path, ACTIVE_LEAGUE  # noqa: E402

GW, GH = 12, 8   # 길이(x) × 폭(y) 그리드


def _grid(points: list[dict]) -> list[int] | None:
    """points[{x,y}] (0-100) → GH×GW 정규화 그리드(0-100), row-major(row=y폭, col=x길이)."""
    if not points:
        return None
    cells = [0] * (GW * GH)
    for p in points:
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            continue
        col = min(GW - 1, max(0, int(x / 100.0 * GW)))
        row = min(GH - 1, max(0, int(y / 100.0 * GH)))
        cells[row * GW + col] += 1
    mx = max(cells) or 1
    return [round(c / mx * 100) for c in cells]


def fetch_heatmap(player_id: int, season_id: int) -> list[dict] | None:
    d = get(f"/player/{player_id}/unique-tournament/{UT_ID}/season/{season_id}/heatmap/overall")
    return (d or {}).get("points") if isinstance(d, dict) else None


def main() -> int:
    league = ACTIVE_LEAGUE
    sid = find_season_id()
    if not sid:
        print(f"[heatmap] {league}: 25/26 시즌 id 못 찾음", file=sys.stderr)
        return 1
    teams = fetch_teams(sid)
    if not teams:
        print(f"[heatmap] {league}: 팀 목록 실패", file=sys.stderr)
        return 1
    print(f"[heatmap] {league} season {sid} · {len(teams)}팀 수집…")

    rows, seen = [], set()
    for t in teams:
        pls = fetch_team_players(t["id"])
        n_team = 0
        for p in pls:
            pid, name = p.get("id"), str(p.get("name") or "")
            if not pid or not name:
                continue
            key = unidecode(name).lower().strip()
            if key in seen:
                continue
            pts = fetch_heatmap(pid, sid)
            g = _grid(pts or [])
            if not g:
                continue
            seen.add(key)
            rows.append({"norm_key": key, "name": name, "team": t["name"],
                         "n_points": len(pts), "gw": GW, "gh": GH,
                         "grid": " ".join(str(v) for v in g)})
            n_team += 1
            time.sleep(0.25)
        print(f"  {t['name'][:22]:22} {n_team}명")

    if not rows:
        print(f"[heatmap] {league}: 수집 0 — 중단(기존 파일 유지)", file=sys.stderr)
        return 1
    out = data_path("player_heatmaps", league)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["norm_key", "name", "team", "n_points", "gw", "gh", "grid"])
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] {out.name} · {len(rows)}명 히트맵")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
