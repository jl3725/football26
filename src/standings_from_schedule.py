"""
ESPN 전 대회 일정(schedule_full)의 리그 경기 결과로 순위표·팀별 전적을 만든다.

fetch_standings(FBref, soccerdata)와 같은 산출물(standings·schedule)을 만들지만 브라우저가
필요 없어 GH Actions(daily_data)에서 매일 돌릴 수 있다 — 시즌 중 순위 자동 갱신용.
정렬 기준도 fetch_standings 와 같다(승점 → 득실차 → 다득점).
ESPN 리그 코드에는 시즌 뒤 플레이오프(에레디비시 유럽 PO·벨기에 PO 등)가 섞여 있어 팀당 정규 라운드 수
(games_per_team)까지만 센다. 중단·연기 경기(ESPN 미완료)는 제외 — FBref 는 중단 경기를 0:0 으로 집계함.

사용: FB_LEAGUE=LaLiga python src/standings_from_schedule.py
"""
from __future__ import annotations

import sys

import pandas as pd

from espn_common import LEAGUE_CODE
from leagues import ACTIVE_LEAGUE, data_path, league_config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def build(sched_full: pd.DataFrame, league_code: str,
          games_per_team: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """schedule_full(우리 팀 관점 행) → (standings, schedule)."""
    lg = sched_full[(sched_full["comp_code"] == league_code) & (sched_full["status"] == "completed")].copy()
    lg["gf"] = pd.to_numeric(lg["gf"], errors="coerce")
    lg["ga"] = pd.to_numeric(lg["ga"], errors="coerce")
    lg = lg.dropna(subset=["gf", "ga"]).drop_duplicates(["squad", "event_id"])
    lg["gf"], lg["ga"] = lg["gf"].astype(int), lg["ga"].astype(int)
    if games_per_team:   # 정규 라운드만(날짜순 앞 N경기) — 시즌 뒤 플레이오프 제외
        lg = lg.sort_values(["squad", "date", "event_id"]).groupby("squad").head(games_per_team)
    lg["w"] = (lg["gf"] > lg["ga"]).astype(int)
    lg["d"] = (lg["gf"] == lg["ga"]).astype(int)
    lg["l"] = (lg["gf"] < lg["ga"]).astype(int)

    st = (lg.groupby("squad", as_index=False)
            .agg(played=("gf", "count"), won=("w", "sum"), drawn=("d", "sum"), lost=("l", "sum"),
                 gf=("gf", "sum"), ga=("ga", "sum")))
    st["gd"] = st["gf"] - st["ga"]
    st["points"] = st["won"] * 3 + st["drawn"]
    st = st.sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)
    st.insert(0, "rank", st.index + 1)

    lg = lg.sort_values(["squad", "date", "event_id"])
    lg["gw"] = lg.groupby("squad").cumcount() + 1
    sched = pd.DataFrame({
        "squad": lg["squad"], "gw": lg["gw"], "date": lg["date"], "home_away": lg["home_away"],
        "opponent": lg["opponent"], "gf": lg["gf"], "ga": lg["ga"],
        "score": lg["gf"].astype(str) + ":" + lg["ga"].astype(str),
        "result": lg["result"],
    }).reset_index(drop=True)
    return st, sched


def main() -> int:
    src = data_path("schedule_full")
    if not src.exists():
        print(f"[standings] {src.name} 없음")
        return 1
    st, sched = build(pd.read_csv(src), LEAGUE_CODE[ACTIVE_LEAGUE][0], league_config().games_per_team)
    if st.empty:
        print(f"[standings] {ACTIVE_LEAGUE}: 완료된 리그 경기 없음 — 기존 파일 유지")
        return 1
    st.to_csv(data_path("standings"), index=False, encoding="utf-8")
    sched.to_csv(data_path("schedule"), index=False, encoding="utf-8")
    print(f"[standings] {ACTIVE_LEAGUE}: {len(st)}팀 · 최다 {int(st['played'].max())}경기 · "
          f"선두 {st.iloc[0]['squad']} {int(st.iloc[0]['points'])}점 -> {data_path('standings').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
