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
from pathlib import Path

import pandas as pd
import soccerdata as sd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import SEASON_FBREF, data_path, league_config, register_soccerdata_custom_leagues  # noqa: E402
from squads import canonical_squad  # noqa: E402

UNDERSTAT_LEAGUES = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1")
COLS = ["squad", "player", "minutes", "xg", "np_xg", "xa", "key_passes", "shots", "xg_chain", "goals", "assists"]


def fetch(league: str) -> pd.DataFrame | None:
    us = sd.Understat(leagues=league_config(league).fbref_id, seasons=SEASON_FBREF, no_cache=True)
    d = us.read_player_season_stats().reset_index()
    if d.empty:
        return None
    d["squad"] = [canonical_squad(t, league) for t in d["team"]]
    return d[[c for c in COLS if c in d.columns]]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    register_soccerdata_custom_leagues()
    ok = 0
    for lg in UNDERSTAT_LEAGUES:
        try:
            d = fetch(lg)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패는 기존 파일 유지
            print(f"[understat-live] {lg} 실패 {type(e).__name__}: {str(e)[:120]}")
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
