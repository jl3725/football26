"""
수집 소스 접근성 진단 — 이 머신(IP)에서 각 소스가 열리는지 한 번씩만 찔러 본다.

어떤 수집을 클라우드(GH 러너)로 옮길 수 있는지 판단용. 수동 실행 워크플로 probe_sources.yml 이
러너에서 돌리고, 로컬에서도 같은 스크립트로 비교할 수 있다. 데이터는 저장하지 않는다.

사용: python scripts/probe_sources.py
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"}


def transfermarkt() -> str:
    import requests
    r = requests.get("https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1", headers=UA, timeout=30)
    ok = r.status_code == 200 and "items" in r.text
    return f"HTTP {r.status_code}{' (WAF 챌린지)' if r.status_code == 202 else ''} · 표 {'있음' if ok else '없음'}"


def understat() -> str:
    import requests
    r = requests.get("https://understat.com/league/EPL", headers=UA, timeout=30)
    return f"HTTP {r.status_code} · 데이터 {'있음' if 'teamsData' in r.text or 'datesData' in r.text else '없음'}"


def sofascore_direct() -> str:
    import requests
    r = requests.get("https://www.sofascore.com/api/v1/unique-tournament/17/seasons", headers=UA, timeout=30)
    return f"HTTP {r.status_code}"


def sofascore_browser() -> str:
    import sofascore_client as sc
    try:
        st, data = sc.get_json("/unique-tournament/17/seasons")
        n = len((data or {}).get("seasons") or [])
        return f"HTTP {st} · 시즌 {n}개"
    finally:
        sc.close()


def fbref() -> str:
    import soccerdata as sd
    fb = sd.FBref(leagues="ENG-Premier League", seasons="2026-2027", no_cache=True)
    df = fb.read_schedule()
    return f"일정 {len(df)}행"


PROBES = [("transfermarkt", transfermarkt), ("understat", understat), ("sofascore(직접)", sofascore_direct),
          ("sofascore(브라우저)", sofascore_browser), ("fbref(soccerdata)", fbref)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for name, fn in PROBES:
        t = time.time()
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            res = f"실패 {type(e).__name__}: {str(e)[:160]}"
            traceback.print_exc(limit=1)
        print(f"[probe] {name:22} {time.time() - t:5.1f}s  {res}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
