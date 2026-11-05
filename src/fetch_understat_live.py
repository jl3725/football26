"""
Understat 선수 시즌 xG(5대 리그) 매일 — data/understat_players[_리그]_<시즌>.csv (클라우드 match_refresh).

2026-10-20 사용자: "세부 스탯도 매일". 선수 표(players_full)의 xG 계열(xg·npxg·xa·kp·shots·xg_chain per90)은
이 PC 주간 빌드(fetch_understat — FBref 를 바탕으로 표를 통째로 다시 만든다)에서만 바뀌어 최대 7일 늦었다.
여기선 Understat 만 리그당 1요청으로 받아 별도 파일에 두고, 화면용 선수 표를 만들 때(api/services/player_data
→ src/season_totals.apply_understat_live) 더 최신이면 그 값으로 바꾼다 — 이 PC 가 커밋하는 players_full 과
같은 파일을 고치지 않아 push 충돌이 없다. Sofascore xG 로 바꾸지 않는 건 모델이 달라 OVR 기준이 흔들리기 때문.

    python src/fetch_understat_live.py            # 5대 리그
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import SEASON_FBREF, data_path, league_config, register_soccerdata_custom_leagues  # noqa: E402
from squads import canonical_squad  # noqa: E402

UNDERSTAT_LEAGUES = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1")
EX_SOURCE_DOWN = 75       # 원천 중단(scripts/ci_try.sh — 빨간불 대신 DATA 화면 '원천 중단', 기존 파일 유지)
# 사이트에 닿지 못한 오류 — 2026-11-02 부터 understat.com 이 클라우드·로컬 모두 연결 시간 초과(dial tcp … i/o timeout)라
# Match Refresh 가 연속 빨간불이었다(우리 고장이 아님)
_NET_ERR = ("dial tcp", "i/o timeout", "TLS Client Error", "timed out", "Connection", "connection", "Name or service",
            "getaddrinfo", "Max retries")
COLS = ["squad", "player", "minutes", "xg", "np_xg", "xa", "key_passes", "shots", "xg_chain", "goals", "assists"]


def fetch(league: str) -> pd.DataFrame | None:
    import soccerdata as sd  # noqa: PLC0415 — 수집 전용 의존(requirements-agents) — CI 테스트는 이 모듈을 불러오기만 한다
    us = sd.Understat(leagues=league_config(league).fbref_id, seasons=SEASON_FBREF, no_cache=True)
    d = us.read_player_season_stats().reset_index()
    if d.empty:
        return None
    d["squad"] = [canonical_squad(t, league) for t in d["team"]]
    return d[[c for c in COLS if c in d.columns]]


def site_state(timeout: float = 15.0) -> str:
    """막힌 이유를 사람 말로 — 점검 페이지('We will come back soon', 2026-11-02~)·차단·불통."""
    import requests  # noqa: PLC0415
    try:
        r = requests.get("https://understat.com/", timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return "understat.com 불통"
    body = r.text.lower()
    if "come back soon" in body or "maintenance" in body:
        return "understat.com 점검 중('We will come back soon')"
    return f"understat.com 차단(HTTP {r.status_code})"


def reachable(timeout: float = 15.0) -> bool:
    """understat.com 에 닿는가 — 연결만 본다(응답 코드는 상관없음)."""
    import requests  # noqa: PLC0415
    try:
        requests.get("https://understat.com/", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    register_soccerdata_custom_leagues()
    ok = 0
    for lg in UNDERSTAT_LEAGUES:
        failed = False
        for attempt in (1, 2):
            try:
                d = fetch(lg)
                break
            except OSError as e:
                # 첫 요청 때 TLS 라이브러리를 내려받는데, 그 다운로드가 가끔 실패해 5개 리그가 한꺼번에 실패했다
                # (2026-10-25 01시 'Failed to download the required TLS library') — 20초 뒤 한 번 더
                if attempt == 1 and "TLS library" in str(e):
                    print(f"[understat-live] {lg} TLS 라이브러리 내려받기 실패 — 20초 뒤 다시")
                    time.sleep(20)
                    continue
                print(f"[understat-live] {lg} 실패 {type(e).__name__}: {str(e)[:120]}")
                failed = True
                break
            except Exception as e:  # noqa: BLE001 — 한 리그 실패는 기존 파일 유지
                print(f"[understat-live] {lg} 실패 {type(e).__name__}: {str(e)[:120]}")
                # 연결 자체가 안 되거나, 닿긴 하는데 JSON 대신 차단 페이지(HTML)를 주는 경우(2026-11-03 밤부터 'Expecting value')
                # 둘 다 우리 고장이 아닌 원천 중단 — 빨간불 대신 75(FotMob 이 xG 를 대신 채운다, src/season_totals.apply_fotmob_xg)
                blocked = isinstance(e, ValueError) and "Expecting value" in str(e)
                if blocked or (any(k in str(e) for k in _NET_ERR) and not reachable()):
                    print(f"[understat-live] {site_state()} — 원천 중단(기존 파일 유지, 나머지 리그 건너뜀 · FotMob 이 xG 대신 채움)")
                    return EX_SOURCE_DOWN if ok == 0 else 1
                failed = True
                break
        if failed:
            continue
        if d is None or len(d) < 100:
            print(f"[understat-live] {lg} 선수 {0 if d is None else len(d)}명 — 너무 적어 기존 파일 유지")
            continue
        d.to_csv(data_path("understat_players", lg), index=False, encoding="utf-8")
        ok += 1
        print(f"[understat-live] {lg} 선수 {len(d)}명 · 출전 최대 {int(d['minutes'].max())}분")
    return 0 if ok == len(UNDERSTAT_LEAGUES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
