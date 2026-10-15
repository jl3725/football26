"""
리그별 팀 라인 전력(_league_units)을 미리 계산해 data/team_units.json 에 쓴다 — 배포 빌드 단계용(render.yaml).

Render 무료(0.1 CPU · 512MB)에서는 서버가 깰 때마다 8개 리그 전 팀을 계산하느라 홈·Overview 첫 요청이
70초를 넘겼다(2026-10-15). 빌드 머신에서 한 번 계산해 두면 서버는 파일을 읽기만 한다.
스탬프(시즌 + DB 파일 시각)가 런타임 DB 와 다르면 API 가 무시하고 즉석 계산한다(안전).
커밋하지 않는다(.gitignore) — 로컬에서 돌리면 로컬 DB 기준으로만 유효.

사용: python scripts/build_db.py && python scripts/precompute_team_units.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    t0 = time.time()
    import api.main as M  # noqa: PLC0415
    leagues = {}
    for lg in M.ds.available_leagues():
        leagues[lg] = M._compute_league_units(lg)
    out = {"stamp": M._units_stamp(), "built": time.strftime("%Y-%m-%d %H:%M:%S"), "leagues": leagues}
    M._UNITS_FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n = sum(len(v) for v in leagues.values())
    print(f"[team_units] {len(leagues)}개 리그 {n}팀 -> {M._UNITS_FILE.name} ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
