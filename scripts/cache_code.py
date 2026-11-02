"""
데이터 배포본 캐시를 만들 코드 고르기 — 운영 서버가 지금 돌리는 코드(Publish Data 워크플로가 부른다).

배포본(scripts/publish_data.py)은 main 최신 코드로 캐시(선수 표·OVR·세부 지표 표)를 만들어 code_sig 를 붙이고, 운영 서버
(src/live_sync.py)는 자기 코드와 지문이 같은 캐시만 받는다. 코드는 하루 한 번 배포(Deploy Backend)라 코드를 푸시한 날엔
배포 전까지 몇 시간 동안 지문이 달라 서버가 캐시를 못 받고 데이터가 바뀔 때마다 0.1 CPU 로 직접 다시 만들었다 —
그동안 운영이 느렸다(2026-11-03 사용자 '운영이 자꾸 느리고 안 뜬다').
그래서 운영 서버 코드(/api/health commit)가 main 과 다르면 그 커밋의 코드(src·api·scripts)만 따로 꺼내(데이터는 main 것을
그대로 연결) 캐시를 만들게 한다. 결과는 $GITHUB_ENV 로:
  CACHE_CODE_DIR  운영 코드를 꺼낸 폴더(data → 지금 작업 폴더의 data 연결) — 없으면 main 코드 그대로
  CACHE_CODE_SIG  그 코드의 지문(배포본 manifest code_sig)
운영 커밋을 못 읽거나 코드가 같으면 아무것도 쓰지 않는다(예전처럼 main 코드). 배포 직전(Deploy Backend)은 main 코드로
만들어야 하므로 워크플로 입력 cache_code=head 면 이 단계를 건너뛴다.

    python scripts/cache_code.py [--dir /tmp/srvcode]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from code_sig import code_sig  # noqa: E402

CODE_PATHS = ("src", "api", "scripts", "requirements.txt")


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _env(**kv: str) -> None:
    path = os.getenv("GITHUB_ENV")
    for k, v in kv.items():
        print(f"[cache-code] {k}={v}")
        if path:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{k}={v}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/srvcode")
    a = ap.parse_args(argv)
    import deploy_backend as dbk  # noqa: PLC0415 — 운영 커밋 읽기·GitHub API 를 같이 쓴다
    short = dbk.prod_commit()
    if not short:
        print("[cache-code] 운영 커밋을 못 읽음 — main 코드로")
        return 0
    head = _git("rev-parse", "HEAD")
    if head.startswith(short):
        print(f"[cache-code] 운영 = main({short}) — main 코드로")
        return 0
    try:
        full = dbk._gh(f"commits/{short}")["sha"]
        _git("fetch", "--no-tags", "--depth=1", "origin", full)
        out = Path(a.dir)
        _git("worktree", "add", "--no-checkout", "--detach", str(out), full)
        _git("checkout", full, "--", *[p for p in CODE_PATHS], cwd=out)   # 데이터(수백 MB)는 꺼내지 않는다
    except Exception as e:  # noqa: BLE001 — 못 꺼내면 예전처럼 main 코드
        print(f"[cache-code] 운영 코드 꺼내기 실패 {type(e).__name__}: {e} — main 코드로")
        return 0
    sig_prod, sig_head = code_sig(out), code_sig(ROOT)
    if sig_prod == sig_head:
        print(f"[cache-code] 운영({short}) 코드 지문 = main — main 코드로")
        _git("worktree", "remove", "--force", str(out))
        return 0
    (out / "data").symlink_to(ROOT / "data", target_is_directory=True)
    print(f"[cache-code] 운영 {short} ≠ main {head[:12]} — 캐시는 운영 코드로")
    _env(CACHE_CODE_DIR=str(out), CACHE_CODE_SIG=sig_prod)
    return 0


if __name__ == "__main__":
    sys.exit(main())
