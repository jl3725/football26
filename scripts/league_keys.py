"""
리그 키 목록(공백 구분) — 워크플로가 리그 목록을 직접 적지 않게(새 리그는 src/leagues.py 한 곳).

    python scripts/league_keys.py            # 전 리그
    python scripts/league_keys.py --full     # 풀 리그(FBref·Sofascore·ESPN 수집기)
    python scripts/league_keys.py --lite     # 라이트 리그(FotMob·TM 만 — src/lite_league.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from leagues import FULL_LEAGUES, LEAGUES, LITE_LEAGUES  # noqa: E402

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    keys = FULL_LEAGUES if arg == "--full" else LITE_LEAGUES if arg == "--lite" else list(LEAGUES)
    print(" ".join(keys))
