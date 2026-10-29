"""
백엔드 배포(Render) — 하루 한 번(경기 없는 때) + 수동. render.yaml autoDeploy 는 끔(2026-10-29).

왜 자동 배포를 껐나
  · Render 무료 빌드는 월 500분 — 빌드 7분 × 코드 커밋마다 자동 배포로 10/26 에 다 써 그달 남은 배포가 전부 즉시 실패했다
  · 배포마다 서버가 다시 떠 캐시가 비고, 그 사이 웹이 '서버 응답 없음'(70초 제한)을 보였다
  데이터는 배포와 무관 — data-live 배포본을 운영 서버가 3분마다 받는다(src/live_sync.py). 이 배포는 코드 변경만 옮긴다.

순서
  1. 운영 /api/health 의 commit 이 main 의 최신 백엔드 커밋(BACKEND_PATHS)을 담고 있으면 끝 — 빌드 분을 안 쓴다
  2. 예약 실행이면 우리 팀 경기가 진행 중일 때 끝날 때까지 기다린다(최대 WAIT_LIVE). 수동(--now)은 바로
  3. data-live 캐시가 지금 코드로 만든 것이 아니면 Publish Data 를 요청하고 기다린다(최대 WAIT_PUBLISH) — 빌드가 배포본을
     받아 쓰므로(scripts/fetch_live_data.py) 같은 코드의 캐시여야 빌드에서 다시 계산하지 않는다(못 기다리면 빌드가 계산)
  4. Render Deploy Hook(비밀 RENDER_DEPLOY_HOOK) 호출 → /api/health 가 새 코드를 담을 때까지 확인(최대 WAIT_DEPLOY)

    python scripts/deploy_backend.py [--now] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = os.getenv("GITHUB_REPOSITORY", "jl3725/football26")
BACKEND = os.getenv("BACKEND_URL", "").rstrip("/")
# 서버가 읽는 코드 — 이 중 하나라도 바뀐 커밋만 배포한다(scripts/watchdog.py check_backend 도 이 목록)
BACKEND_PATHS = ("api", "src", "requirements.txt", "render.yaml", "scripts/build_db.py",
                 "scripts/precompute_team_units.py", "scripts/fetch_live_data.py")
WAIT_LIVE, WAIT_PUBLISH, WAIT_DEPLOY = 150 * 60, 30 * 60, 25 * 60


def _gh(path: str, method: str = "GET", **kw):
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}
    r = requests.request(method, f"https://api.github.com/repos/{REPO}/{path}", headers=h, timeout=30, **kw)
    r.raise_for_status()
    return r.json() if r.content else None


def prod_commit() -> str:
    """운영 서버 코드 커밋 — 잠들어 있으면 깨우느라 한 번 더. 못 읽으면 ''."""
    if not BACKEND:
        return ""
    for _ in range(2):
        try:
            return str(requests.get(f"{BACKEND}/api/health", timeout=90).json().get("commit") or "")
        except (requests.RequestException, ValueError):
            time.sleep(20)
    return ""


def latest_backend() -> dict | None:
    """main 에서 BACKEND_PATHS 를 마지막으로 바꾼 커밋."""
    latest = None
    for path in BACKEND_PATHS:
        c = _gh("commits", params={"sha": "main", "path": path, "per_page": 1})
        if c and (latest is None or c[0]["commit"]["committer"]["date"] > latest["commit"]["committer"]["date"]):
            latest = c[0]
    return latest


def has_code(prod: str, latest: dict | None) -> bool:
    """운영 커밋이 최신 백엔드 커밋을 담고 있나(같거나 그 뒤)."""
    if latest is None:
        return True
    if not prod:
        return False
    if latest["sha"].startswith(prod) or prod.startswith(latest["sha"]):
        return True
    return _gh(f"compare/{latest['sha']}...{prod}").get("status") in ("identical", "ahead")


def live_now() -> list[str]:
    """지금 진행 중인 우리 팀 경기(ESPN in) — 경기 감시와 같은 판단(scripts/match_watch.py)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import match_watch as mw  # noqa: PLC0415
        fx = mw.load_fixtures(mw._now())
        states = mw.espn_states(fx) if not fx.empty else {}
    except Exception as e:  # noqa: BLE001 — 일정·ESPN 을 못 보면 기다리지 않는다
        print(f"[deploy] 경기 확인 실패 {type(e).__name__} — 기다리지 않음")
        return []
    return [i for i in fx["event_id"] if states.get(i) == "in"]


def manifest() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    import live_sync  # noqa: PLC0415
    ref = live_sync.head() or live_sync.DATA_BRANCH
    r = requests.get(live_sync._raw("manifest.json", ref), timeout=30)
    return r.json() if r.status_code == 200 else {}


def ensure_publish(dry: bool) -> bool:
    """data-live 캐시가 지금 코드로 만든 것인지 — 아니면 Publish Data 요청 후 기다린다. 맞췄으면 True."""
    sys.path.insert(0, str(ROOT / "src"))
    from code_sig import code_sig  # noqa: PLC0415
    sig = code_sig(ROOT)
    if manifest().get("code_sig") == sig:
        print("[deploy] 배포본 캐시 = 지금 코드")
        return True
    t0 = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print("[deploy] 배포본 캐시가 옛 코드 — Publish Data 요청")
    if dry:
        return False
    _gh("actions/workflows/publish_data.yml/dispatches", method="POST", json={"ref": "main"})
    end = time.monotonic() + WAIT_PUBLISH
    while time.monotonic() < end:
        time.sleep(60)
        m = manifest()
        if m.get("code_sig") == sig or str(m.get("built_at") or "") >= t0:   # 그새 main 이 더 나갔으면 그 코드로 만든 것도 됨
            print(f"[deploy] 배포본 갱신 {str(m.get('main_sha'))[:12]}")
            return True
    print("::notice title=배포본 대기 끝::Publish Data 가 늦음 — 빌드가 캐시를 직접 만든다(빌드 몇 분 더)")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="경기 중이어도 바로(수동 실행)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prod, latest = prod_commit(), latest_backend()
    if has_code(prod, latest):
        print(f"[deploy] 운영 {prod[:7]} 이 최신 코드 — 배포 안 함")
        return 0
    print(f"[deploy] 운영 {prod[:7] or '?'} · 최신 코드 {latest['sha'][:7]}({latest['commit']['committer']['date'][:16]}) — 배포 필요")

    if not a.now:
        end = time.monotonic() + WAIT_LIVE
        while (live := live_now()) and time.monotonic() < end:
            print(f"[deploy] 경기 진행 중 {len(live)}개 — 끝날 때까지 대기")
            time.sleep(300)
        if live:
            print("::notice title=배포 미룸::경기가 계속 진행 중 — 다음 예약 실행에서")
            return 0

    ensure_publish(a.dry_run)
    hook = os.getenv("RENDER_DEPLOY_HOOK", "")
    if not hook:
        print("::error title=배포 훅 없음::GitHub 비밀 RENDER_DEPLOY_HOOK 이 없다 — Render 대시보드 Settings → Deploy Hook 주소를 넣을 것")
        return 1
    if a.dry_run:
        print("[deploy] (dry-run) Deploy Hook 호출했을 것")
        return 0
    r = requests.post(hook, timeout=30)
    if r.status_code >= 300:
        print(f"::error title=배포 요청 실패::Deploy Hook {r.status_code}")
        return 1
    print(f"[deploy] 배포 요청 {r.status_code} — 새 코드가 뜰 때까지 확인")
    end = time.monotonic() + WAIT_DEPLOY
    while time.monotonic() < end:
        time.sleep(90)
        now = prod_commit()
        if now and now != prod and has_code(now, latest):
            print(f"[deploy] 운영 {now[:7]} — 배포 끝")
            return 0
    print("::error title=배포 확인 실패::25분 안에 새 코드가 안 떴다 — Render Events(빌드 분 한도·시작 실패) 확인")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
