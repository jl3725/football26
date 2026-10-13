"""API 모듈이 저장소의 ``src`` 도메인 모듈을 일관되게 찾도록 한다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

source_path = str(SRC)
if source_path not in sys.path:
    sys.path.insert(0, source_path)


def _load_dotenv() -> None:
    """저장소 루트 ``.env`` 의 값을 환경변수 기본값으로 올린다(이미 있는 값은 보존, 의존성 없음).

    운영(Render)은 대시보드 환경변수를 쓰므로 영향 없고, 로컬에서 Qdrant·Neo4j·OpenAI 키를
    매번 export 하지 않아도 API 가 선택 기능을 켠다. 모듈 import 시점(src 모듈이 env 를 읽기 전)에 실행.
    """
    import os

    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
