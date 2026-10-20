"""
리그 시즌 누적(골·도움·출전 분·경기 수)을 경기 직후 값으로 — FotMob 경기별 기록(data/fotmob_match_ratings_*)의 리그 경기 합.

2026-10-20 사용자: "홀란 8골인데 리그 기준 아직 6골". 화면의 골·도움은 FBref 시즌 표(이 PC 주간 빌드, 수요일)라
최대 7일 늦었다. FotMob 경기별 기록은 경기 종료 20분 뒤(match_watch → match_refresh) 들어오고 골·도움·출전 분이 있다.

규칙: 리그 대회 코드(eng.1 …) 경기만 합산(리그 스탯 = 리그만). 선수의 FotMob 리그 출전 분이 FBref 출전 분 이상일 때만
(= FotMob 쪽이 더 최신이거나 같을 때) goals·assists·minutes 를 바꾼다. FotMob 수집이 경기를 빠뜨려 분이 적으면 FBref 유지.
바뀐 행은 `_stats_src = "fotmob"`, `_stats_asof` = 마지막 리그 경기 날짜(화면 '기준일' 표시용).
"""
from __future__ import annotations

import pandas as pd

from espn_common import LEAGUE_CODE


def _fid(v) -> str | None:
    try:
        return str(int(float(v))) if v is not None and v == v and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def league_totals(mr: pd.DataFrame | None, league: str) -> tuple[dict, dict]:
    """({fotmob_id: 합계}, {'squad|player': 합계}) — 리그 경기만. 합계 = {minutes, goals, assists, apps, asof}."""
    if mr is None or mr.empty or league not in LEAGUE_CODE:
        return {}, {}
    d = mr[mr["comp_code"].astype(str) == LEAGUE_CODE[league][0]].copy()
    if d.empty:
        return {}, {}
    for c in ("minutes", "goals", "assists"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["fid"] = d["fotmob_id"].map(_fid)
    d = d.sort_values("date")
    by_id, by_name = {}, {}
    # FotMob id 단위로 묶는다 — 시즌 중 리그 안에서 팀을 옮긴 선수는 두 팀 경기를 합친다
    for fid, g in d[d["fid"].notna()].groupby("fid"):
        last = g.iloc[-1]
        t = {"minutes": int(g["minutes"].sum()), "goals": int(g["goals"].sum()), "assists": int(g["assists"].sum()),
             "apps": int((g["minutes"] > 0).sum()), "asof": str(last["date"])}
        by_id[fid] = t
        by_name[f"{last['squad']}|{last['player']}"] = t
    for (sq, pl), g in d[d["fid"].isna()].groupby(["squad", "player"]):
        by_name.setdefault(f"{sq}|{pl}", {"minutes": int(g["minutes"].sum()), "goals": int(g["goals"].sum()),
                                          "assists": int(g["assists"].sum()), "apps": int((g["minutes"] > 0).sum()),
                                          "asof": str(g["date"].max())})
    return by_id, by_name


def apply_live_totals(frame: pd.DataFrame, mr: pd.DataFrame | None, league: str) -> pd.DataFrame:
    """선수 표의 goals·assists·minutes 를 FotMob 리그 합으로(더 최신일 때만). `_stats_src`·`_stats_asof`·`_apps_live` 열."""
    out = frame.copy()
    out["_stats_src"], out["_stats_asof"], out["_apps_live"] = "fbref", None, None
    by_id, by_name = league_totals(mr, league)
    if not by_id and not by_name:
        return out
    for i, r in out.iterrows():
        fid = _fid(r.get("fm_id"))
        t = by_id.get(fid) if fid else None
        if t is None:
            t = by_name.get(f"{r.get('squad')}|{r.get('player')}")
        if t is None:
            continue
        mins = pd.to_numeric(r.get("minutes"), errors="coerce")
        if mins == mins and t["minutes"] < mins:
            continue                                   # FotMob 쪽이 경기를 빠뜨림 — FBref 유지
        out.at[i, "goals"], out.at[i, "assists"], out.at[i, "minutes"] = t["goals"], t["assists"], t["minutes"]
        out.at[i, "_stats_src"], out.at[i, "_stats_asof"], out.at[i, "_apps_live"] = "fotmob", t["asof"], t["apps"]
    return out
