"""선수 평점 일일 기록(변경분) — daily_data 워크플로가 매일 돌린다. 내용은 src/rating_history.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import rating_history  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(rating_history.main())
