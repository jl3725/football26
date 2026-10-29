"""
Render 빌드용 — 서버 DB·캐시를 빌드에서 새로 만들지 않고 data-live 배포본(Publish Data 가 클라우드에서 만든 것)을 받는다.

2026-10-29: 빌드 한 번에 7분(pip + build_db + precompute_team_units)인데 코드 커밋마다 자동 배포라 Render 무료 빌드 분
(월 500분)을 10/26 에 다 썼다 → 그달 남은 배포가 전부 즉시 실패. 받기만 하면 1~2분(src/live_sync.sync_data 와 같은 길).
배포본 캐시가 다른 코드로 만든 것이면(코드 지문 다름 — 배포 직전 Publish Data 가 아직 안 돈 경우) 캐시만 여기서 다시 만든다.
받기에 실패하면 1 로 끝나고 render.yaml 이 예전처럼 build_db 로 만든다.

    python scripts/fetch_live_data.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import live_sync  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.monotonic()
    try:
        n = live_sync.sync_data(notify=False)
    except Exception as e:  # noqa: BLE001 — 무엇이든 실패면 build_db 로
        print(f"[fetch-live] 배포본 받기 실패 {type(e).__name__}: {e} — build_db 로 대신", flush=True)
        return 1
    if not live_sync.STATE["data_sha"] or not (ROOT / "data" / "football.db").exists():
        print("[fetch-live] 배포본 없음 — build_db 로 대신", flush=True)
        return 1
    print(f"[fetch-live] 배포본 {live_sync.STATE['data_sha'][:12]} — 파일 {n}개 ({time.monotonic() - t0:.0f}초)", flush=True)
    if not live_sync.STATE["data_caches"]:
        print("[fetch-live] 배포본 캐시는 다른 코드로 만든 것 — 캐시만 여기서 다시", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "precompute_team_units.py")], cwd=ROOT)
        if r.returncode:
            print("[fetch-live] team_units 건너뜀(API 가 즉석 계산으로 대체)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
