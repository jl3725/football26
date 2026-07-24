"""API 모듈이 저장소의 ``src`` 도메인 모듈을 일관되게 찾도록 한다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

source_path = str(SRC)
if source_path not in sys.path:
    sys.path.insert(0, source_path)
