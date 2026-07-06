"""전 리그 통합 대시보드(/api/home/all) 페이로드를 배포 시 미리 계산해
data/home_all.json 에 저장한다. Render startCommand 에서 build_db 직후 실행 →
런타임 첫 요청이 무거운 집계를 워커에서 돌리지 않고(헬스체크 재시작 루프 방지)
이 파일을 그대로 서빙한다.

사용: python scripts/precompute_hub.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    import main as api  # api/main.py (FastAPI 앱 + 계산 로직)
    body = api._compute_hub_body()
    api._HUB_FILE.write_bytes(body)
    print(f"[precompute-hub] wrote {api._HUB_FILE} ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
