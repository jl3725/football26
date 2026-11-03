"""
수집 결과의 '내용' 신선도 — 표가 담은 시즌 진행(팀당 경기 수)을 일정(schedule_full 의 끝난 리그 경기)과 대조한다.

2026-11-03 점검: 실행 원장은 'ok' 인데 내용이 낡은 수집이 여럿이었다 — FBref 주간 단계가 10/13 캐시만 다시 읽어 3주째
팀당 5~8경기(실제 8~11), StatBunker 1~4경기 늦음, Understat 'Paris Saint Germain,Rennes' 표기로 렌 선수 31명이 PSG 로 가
렌 팀 출전이 1.8경기분. 원장(종료 코드)만 보던 watchdog 은 못 잡았다 → 표마다 팀당 경기 수를 직접 세어 비교한다.

  stale   리그 가운데 값으로 LAG_GAMES 경기 이상 늦음(원천·캐시가 멈춤)
  team    리그는 맞는데 한 팀만 절반 이하(팀 이름 매칭 어긋남 — 다른 팀으로 들어감) 또는 표에 없음
"""
from __future__ import annotations

import pandas as pd

LAG_GAMES = 2.0
TEAM_MIN_GP = 4          # 팀 단위 검사는 4경기 이상 치른 뒤부터(시즌 초 잡음)
# (표, 경기 수 계산) — 'min:열' = 선수 출전 분 합 ÷ 990(11명 × 90분), 'col:열' = 팀 경기 수 열
SPECS = [
    ("players", "min:minutes", "FBref 선수 표(주간)"),
    ("understat_players", "min:minutes", "Understat xG"),
    ("players_sofascore_stats", "min:minutesPlayed", "Sofascore 시즌 통계"),
    ("statbunker_team_stats", "col:matches_statbunker", "StatBunker 팀 통계"),
    ("team_defense", "col:games_played", "팀 득실 강도"),
]


def league_games(league: str, read) -> pd.Series:
    """팀당 끝난 리그 경기 수(일정)."""
    from season_totals import league_code  # noqa: PLC0415
    sch = read("schedule_full", league)
    if sch is None or sch.empty or "comp_code" not in sch.columns:
        return pd.Series(dtype=float)
    code = league_code(league)
    done = sch[(sch["comp_code"].astype(str) == code) & (sch.get("status", "completed").astype(str) == "completed")]
    return done.groupby("squad").size().astype(float)


def table_games(df: pd.DataFrame, how: str) -> pd.Series | None:
    kind, col = how.split(":", 1)
    if df is None or df.empty or "squad" not in df.columns or col not in df.columns:
        return None
    v = pd.to_numeric(df[col], errors="coerce")
    if kind == "min":
        return (v.groupby(df["squad"]).sum() / 990.0).round(1)
    return v.groupby(df["squad"]).max()


def check_league(league: str, read) -> list[dict]:
    """[{table, label, kind('stale'|'team'), detail}] — read(표, 리그) → DataFrame | None."""
    gp = league_games(league, read)
    if gp.empty or gp.median() < 2:
        return []
    out = []
    from squads import canonical_squad  # noqa: PLC0415 — 앱이 읽을 때와 같은 표준 이름(자동 별칭 포함)으로 대조
    gp = gp.groupby([canonical_squad(t, league) for t in gp.index]).max()
    for table, how, label in SPECS:
        df = read(table, league)
        if df is not None and not df.empty and "squad" in df.columns:
            df = df.assign(squad=[canonical_squad(t, league) for t in df["squad"]])
        est = table_games(df, how)
        if est is None or est.empty:
            continue
        j = pd.concat([gp.rename("gp"), est.rename("est")], axis=1)
        j = j[j["gp"].notna()]
        lag = (j["gp"] - j["est"]).median()
        if lag >= LAG_GAMES:
            out.append({"table": table, "label": label, "kind": "stale",
                        "detail": f"팀당 {j['est'].median():.0f}경기분 · 일정 {j['gp'].median():.0f}경기(가운데 값 {lag:.0f}경기 늦음)"})
            continue
        bad = j[(j["gp"] >= TEAM_MIN_GP) & (j["est"].isna() | (j["est"] < 0.5 * j["gp"]))]
        if not bad.empty:
            names = ", ".join(f"{t}({0 if pd.isna(r.est) else r.est:g}/{r.gp:g})" for t, r in bad.head(4).iterrows())
            out.append({"table": table, "label": label, "kind": "team",
                        "detail": f"팀 {len(bad)}곳 경기분이 절반 이하·없음 — {names} (팀 이름 매칭 확인)"})
    return out


def check_all(read, leagues=None) -> list[str]:
    from leagues import LEAGUES  # noqa: PLC0415
    msgs = []
    for lg in leagues or LEAGUES:
        for x in check_league(lg, read):
            msgs.append(f"{lg} {x['label']}({x['table']}) {'늦음' if x['kind'] == 'stale' else '팀 누락'}: {x['detail']}")
    return msgs
