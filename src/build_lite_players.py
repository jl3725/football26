"""
라이트 리그 선수 표 — FotMob(시즌 통계·1군 명단) + Transfermarkt(시장가치·계약·사진·국적) → players_full_{리그}_{시즌}.csv

2026-10-22 1단계 리그 확장(챔피언십·쉬페르리그·오스트리아·덴마크·스위스). 기존 8개 리그는 로컬 주간 빌드
(FBref·Understat·Sofascore)로 선수 표를 만들지만 새 리그는 클라우드 수집만으로 같은 열을 만든다 — 화면·OVR(ratings_v3)·
스카우트 코드는 그대로 두고 원천만 바꾼다.
- 행: FotMob 1군 명단(lite_league 가 쓴 fotmob_squads) ∪ 시즌 통계에 나온 선수(시즌 중 떠난 선수·유스 데뷔 포함).
- 시즌 통계: FotMob 리그 → 시즌별 통계 링크(40여 개 파일). 파일마다 합계·90분당이 섞여 있어 STATS 가 열 이름과 단위를 정한다
  (2026-10-22 챔피언십 확인: goals·mins_played·expected_goals 는 합계, total_scoring_att·interception 은 90분당).
  90분당 파일은 출전 하한이 있어 적게 뛴 선수는 빈칸 — 합계 파일이 있으면 합계 ÷ 분으로 직접 낸다.
- 평점: FotMob 평점을 Sofascore 척도로(rating_blend.fm_to_ss) ss_rating 에 — player_frame 의 두 출처 평균이 같은 값을 다시 낸다.
- 포지션: 명단의 그룹(GK·DF·MF·FW)과 세부 포지션. 명단에 없는 선수는 FotMob 포지션 번호 → 그룹 대응을 명단 선수들에게서
  배워(같은 리그, 다수결) 쓴다.
- TM: transfermarkt_contracts(팀 스쿼드 페이지 — 시장가치·포지션·국적·사진·계약·tm_id)를 (팀, 이름)으로 붙인다.
- 팀 득실 강도: fetch_team_defense 와 같은 식(순위표, 경기당 득실의 리그 안 최소~최대 비율).
- 직전 시즌 기록(prev_*·hist_*): attach_prev_season 그대로(전 리그 지난 시즌 표 — tm_id → 이름+팀 → 이름).

    python src/build_lite_players.py [--league Championship] [--season prev]
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, LITE_LEAGUES, SEASON_START, data_path  # noqa: E402

# FotMob 통계 파일 → (우리 열, 단위) — 't' 합계(StatValue), 'p90' 90분당(StatValue), 'sub' SubStatValue(성공률 %)
STATS = {
    "rating.json": [("_rating", "t")],
    "mins_played.json": [("minutes", "t"), ("_matches", "sub")],
    "goals.json": [("goals", "t")],
    "goal_assist.json": [("assists", "t")],
    "expected_goals.json": [("_xg", "t")],
    "expected_assists.json": [("_xa", "t")],
    "total_att_assist.json": [("_chances", "t")],
    "big_chance_created.json": [("_bigc", "t")],
    "total_scoring_att.json": [("sh_per90", "p90")],
    "ontarget_scoring_att.json": [("sot_per90", "p90")],
    "accurate_pass.json": [("_acc_pass_p90", "p90"), ("pass_pct", "sub")],
    "accurate_long_balls.json": [("_acc_long_p90", "p90"), ("long_ball_pct", "sub")],
    "won_contest.json": [("successful_dribbles_per90", "p90"), ("dribble_success_pct", "sub")],
    "total_tackle.json": [("tackles_won_per90", "p90")],
    "interception.json": [("interceptions_per90", "p90")],
    "effective_clearance.json": [("clearances_per90", "p90")],
    "outfielder_block.json": [("outfielder_blocks_per90", "p90")],
    "ball_recovery.json": [("recoveries_per90", "p90")],
    "fouls.json": [("fouls_per90", "p90")],
    "clean_sheet.json": [("gk_clean_sheets", "t")],
    "_save_percentage.json": [("gk_save_pct", "t")],
    "saves.json": [("gk_saves_per90", "p90")],
    "total_high_claim.json": [("gk_high_claims_per90", "p90")],
    "total_keeper_sweeper.json": [("gk_runs_out_per90", "p90")],
}
TM_COLS = {"market_value_eur": "market_value_eur", "nationality": "nationality", "tm_position": "tm_position",
           "tm_photo": "tm_photo", "tm_id": "tm_id", "contract_until": "tm_contract_until",
           "detected_at": "tm_contract_checked_at", "joined_date": "tm_joined_date", "contract_signal": "tm_contract_signal"}
GROUP = {"keepers": "GK", "defenders": "DF", "midfielders": "MF", "attackers": "FW"}


def stat_base(league: str, season: str) -> str | None:
    """그 시즌 FotMob 통계 파일 경로의 앞부분(…/season/<id>/)."""
    from fetch_fotmob_ratings import FOTMOB_ID, season_links  # noqa: PLC0415
    url = season_links(FOTMOB_ID[league]).get(season)
    return url.rsplit("/", 1)[0] + "/" if url else None


def season_stats(league: str, season: str, get) -> pd.DataFrame:
    """(fotmob_id, 팀) 한 행 — STATS 의 열. 팀 이름은 FotMob 표기."""
    base = stat_base(league, season)
    if not base:
        return pd.DataFrame()
    # 리그마다 있는 파일이 조금 다르다(덴마크·스위스는 GK 공중볼·스위퍼 파일 없음 — 403) — 리그 응답의 목록에 있는 것만
    from fetch_fotmob_ratings import FOTMOB_ID  # noqa: PLC0415
    d = get(f"https://www.fotmob.com/api/data/leagues?id={FOTMOB_ID[league]}") or {}
    avail = {str(x.get("fetchAllUrl") or "").rsplit("/", 1)[-1] for x in ((d.get("stats") or {}).get("players") or [])}
    rows: dict[tuple[str, str], dict] = {}
    for fname, cols in STATS.items():
        if avail and fname not in avail:
            continue
        j = get(base + fname) or {}
        for x in ((j.get("TopLists") or [{}])[0].get("StatList") or []):
            pid = str(x.get("ParticiantId") or x.get("ParticipantId") or "")
            if not pid:
                continue
            key = (pid, str(x.get("TeamName") or ""))
            r = rows.setdefault(key, {"fotmob_id": pid, "team_fm": key[1], "team_id": str(x.get("TeamId") or ""),
                                      "player": x.get("ParticipantName"),
                                      "_pos_ids": ",".join(str(p) for p in (x.get("Positions") or [])),
                                      "_min_any": x.get("MinutesPlayed"), "_games_any": x.get("MatchesPlayed")})
            for col, kind in cols:
                r[col] = x.get("SubStatValue") if kind == "sub" else x.get("StatValue")
        time.sleep(0.3)
    return pd.DataFrame(list(rows.values()))


def _per90(total, minutes):
    t, m = pd.to_numeric(total, errors="coerce"), pd.to_numeric(minutes, errors="coerce")
    return (t * 90 / m).where(m > 0)


def _pos_learner(squads: pd.DataFrame, stats: pd.DataFrame) -> dict[str, str]:
    """FotMob 포지션 번호(첫 값) → GK/DF/MF/FW — 명단에도 통계에도 있는 선수들에게서 다수결로."""
    if squads is None or squads.empty or stats.empty:
        return {}
    grp = dict(zip(squads["fotmob_id"].astype(str), squads["pos"].astype(str)))
    votes: dict[str, Counter] = {}
    for fid, ids in zip(stats["fotmob_id"].astype(str), stats["_pos_ids"].astype(str)):
        first = ids.split(",")[0]
        if fid in grp and first:
            votes.setdefault(first, Counter())[grp[fid]] += 1
    return {k: c.most_common(1)[0][0] for k, c in votes.items()}


def _team_scores(standings: pd.DataFrame) -> pd.DataFrame:
    st = standings.copy()
    gp = pd.to_numeric(st["played"], errors="coerce").replace(0, np.nan)
    st["team_goals_for"] = pd.to_numeric(st["gf"], errors="coerce")
    st["team_goals_against"] = pd.to_numeric(st["ga"], errors="coerce")
    st["team_gf_per_game"] = st["team_goals_for"] / gp
    st["team_ga_per_game"] = st["team_goals_against"] / gp
    ga, gf = st["team_ga_per_game"], st["team_gf_per_game"]
    st["team_defense_score"] = (ga.max() - ga) / (ga.max() - ga.min()) if ga.max() != ga.min() else 1.0
    st["team_attack_score"] = (gf - gf.min()) / (gf.max() - gf.min()) if gf.max() != gf.min() else 1.0
    return st[["squad", "team_goals_for", "team_goals_against", "team_gf_per_game", "team_ga_per_game",
               "team_defense_score", "team_attack_score"]]


def fill_ages(league: str, df: pd.DataFrame, get, cap: int = 80) -> pd.DataFrame:
    """명단에 없는 출전 선수(시즌 중 떠난 선수·유스 데뷔)의 나이 — FotMob 선수 데이터의 생년월일(받은 선수는 다시 안 받음,
    fotmob_squads.player_info 와 같은 표 fotmob_player_info)."""
    import datetime as dt  # noqa: PLC0415

    import fotmob_squads as fsq  # noqa: PLC0415
    path = data_path("fotmob_player_info", league)
    have = pd.read_csv(path, dtype={"fotmob_id": str}) if path.exists() else pd.DataFrame(columns=fsq.INFO_COLS)
    known = {str(r["fotmob_id"]): r for r in have.to_dict("records")}
    new = []
    for i in df.index[pd.to_numeric(df["age"], errors="coerce").isna() & df["fotmob_id"].notna()]:
        fid = str(df.at[i, "fotmob_id"])
        r = known.get(fid)
        if r is None and len(new) < cap:
            d = get(f"https://www.fotmob.com/api/data/playerData?id={fid}") or {}
            r = {"squad": df.at[i, "squad"], "player": df.at[i, "player"], "fotmob_id": fid,
                 "birth_date": str(((d.get("birthDate") or {}).get("utcTime")) or "")[:10],
                 "primary_team": (d.get("primaryTeam") or {}).get("teamName") or "", "fetched": dt.date.today().isoformat()}
            new.append(r)
            known[fid] = r
            time.sleep(0.3)
        if r is not None:
            a = fsq.age_of({"birth_date": r.get("birth_date") or ""})
            if a:
                df.at[i, "age"] = a
    if new:
        pd.concat([have, pd.DataFrame(new, columns=fsq.INFO_COLS)], ignore_index=True).to_csv(
            path, index=False, encoding="utf-8", lineterminator="\n")
    return df


def build(league: str, season: str, get) -> pd.DataFrame:
    import fotmob_squads as fsq  # noqa: PLC0415
    import player_registry as preg  # noqa: PLC0415
    from rating_blend import fm_to_ss  # noqa: PLC0415
    from squads import to_ours  # noqa: PLC0415
    cur = season == f"{SEASON_START}_{SEASON_START + 1}"
    try:
        standings = pd.read_csv(data_path("standings", league, season))
    except FileNotFoundError:
        standings = pd.DataFrame(columns=["squad", "played", "gf", "ga"])
    ours = list(standings["squad"].astype(str))
    stats = season_stats(league, season, get)
    if stats.empty:
        raise RuntimeError(f"{league} {season}: FotMob 시즌 통계 없음")
    # 팀은 FotMob 팀 id 로(통계 파일의 팀 이름은 리그 표와 다를 때가 있다 — 'Amedspor'↔'Amed Sportif', 'RZ Pellets WAC'↔'Wolfsberger AC')
    import lite_league  # noqa: PLC0415
    by_tid = {str(t.get("fotmob_id")): sq for sq, t in (lite_league.team_map(league).get("teams") or {}).items()}
    stats["squad"] = [by_tid.get(i) or (to_ours(t, league, ours) if ours else None) or t
                      for i, t in zip(stats["team_id"].astype(str), stats["team_fm"])]
    squads = pd.read_csv(data_path("fotmob_squads", league), dtype={"fotmob_id": str}) if cur else pd.DataFrame()
    if cur and not squads.empty:
        # 명단에만 있는 선수(이번 시즌 0분 — 백업 GK·부상·유스)를 행으로
        have = set(zip(stats["fotmob_id"].astype(str), stats["squad"].astype(str)))
        extra = [{"fotmob_id": str(r["fotmob_id"]), "team_fm": r["squad"], "squad": r["squad"], "player": r["player"],
                  "_pos_ids": "", "minutes": 0}
                 for r in squads.to_dict("records") if (str(r["fotmob_id"]), str(r["squad"])) not in have]
        stats = pd.concat([stats, pd.DataFrame(extra)], ignore_index=True)
    df = stats.copy()
    # 출전 분: mins_played 하한 아래 선수는 다른 파일의 MinutesPlayed 로
    df["minutes"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(pd.to_numeric(df["_min_any"], errors="coerce")).fillna(0)
    for c in ("goals", "assists"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0)
    df["npg_per90"] = _per90(df["goals"], df["minutes"])
    df["ast_per90"] = _per90(df["assists"], df["minutes"])
    df["xg_p90"] = _per90(df.get("_xg"), df["minutes"])
    df["npxg_p90"] = df["xg_p90"]
    df["xa_p90"] = _per90(df.get("_xa"), df["minutes"])
    df["kp_p90"] = _per90(df.get("_chances"), df["minutes"])
    df["key_passes_per90"] = df["kp_p90"]
    df["big_chances_created_per90"] = _per90(df.get("_bigc"), df["minutes"])
    df["shots_p90"] = df.get("sh_per90")
    df["interceptions_per90_ss"] = df.get("interceptions_per90")
    df["tackles_won_per90_ss"] = df.get("tackles_won_per90")
    df["blocked_shots_per90"] = df.get("outfielder_blocks_per90")
    rating = pd.to_numeric(df.get("_rating"), errors="coerce")
    df["ss_rating"] = fm_to_ss(rating).round(3)
    df["ss_minutes"] = df["minutes"].where(rating.notna())
    df["ss_appearances"] = pd.to_numeric(df.get("_matches"), errors="coerce").fillna(pd.to_numeric(df["_games_any"], errors="coerce"))
    games = df["ss_appearances"].replace(0, np.nan)
    df["gk_cs_pct"] = (pd.to_numeric(df.get("gk_clean_sheets"), errors="coerce") / games * 100).round(1)
    df["fb_counts_src"] = "fotmob"

    # 포지션·나이 — 명단 우선, 없으면 포지션 번호(배운 대응)·생년월일
    learned = _pos_learner(squads, stats)
    by_id = {str(r["fotmob_id"]): r for r in squads.to_dict("records")} if not squads.empty else {}
    pos, tmpos, age = [], [], []
    for fid, ids in zip(df["fotmob_id"].astype(str), df["_pos_ids"].fillna("").astype(str)):
        r = by_id.get(fid)
        if r:
            pos.append(r.get("pos"))
            tmpos.append(r.get("tm_position"))
            age.append(fsq.age_of(r))
        else:
            g = learned.get(ids.split(",")[0]) if ids else None
            pos.append(g or "MF")
            tmpos.append(fsq.GROUP_TM.get({v: k for k, v in GROUP.items()}.get(g or "MF"), ""))
            age.append(None)
    df["pos"], df["_fm_tm_position"], df["age"] = pos, tmpos, age

    # TM — 같은 팀 안에서 이름 대조(player_registry 규칙)
    for c in TM_COLS.values():
        df[c] = None
    if cur:
        try:
            tm = pd.read_csv(data_path("transfermarkt_contracts", league), dtype={"tm_id": str})
        except FileNotFoundError:
            tm = pd.DataFrame()
        if not tm.empty:
            by_team = {sq: {str(p): r for p, r in zip(g["player"], g.to_dict("records"))} for sq, g in tm.groupby("squad")}
            for i, (sq, name) in enumerate(zip(df["squad"].astype(str), df["player"].astype(str))):
                cands = by_team.get(sq) or {}
                hit = name if name in cands else preg.best_match(name, {n: n for n in cands})[0]
                r = cands.get(hit) if hit else None
                if r is None:
                    continue
                idx = df.index[i]
                for src, dst in TM_COLS.items():
                    v = r.get(src)
                    if v is not None and not (isinstance(v, float) and np.isnan(v)) and str(v) != "":
                        df.at[idx, dst] = v
                if pd.isna(df.at[idx, "age"]) and pd.notna(r.get("age")):
                    df.at[idx, "age"] = r.get("age")
    df["tm_position"] = df["tm_position"].where(df["tm_position"].notna() & (df["tm_position"].astype(str) != ""),
                                                df["_fm_tm_position"])
    if cur:
        df = fill_ages(league, df, get)
    df["norm_key"] = df["player"].map(preg.norm)
    df = df.merge(_team_scores(standings), on="squad", how="left") if not standings.empty else df
    keep = [c for c in df.columns if not c.startswith("_") and c not in ("team_fm", "team_id")]
    out = df[keep].copy()
    out = out.sort_values(["squad", "minutes"], ascending=[True, False]).drop_duplicates(["squad", "fotmob_id"])
    # 직전 시즌 기록(이번 시즌 표에만) — 전 리그 지난 시즌 표에서
    if cur:
        import attach_prev_season as aps  # noqa: PLC0415
        out, _ = aps.attach(out, aps.load_prev(SEASON_START))
        out = aps.attach_hist(out, SEASON_START)
    return out


def write_strength() -> dict:
    """2부 리그 레벨 — 전 리그 이번 시즌 선수 표의 클럽 평균 스쿼드 시장가치로 맞춘 직선(league_level.fit_second_tier)."""
    import datetime as dt  # noqa: PLC0415
    import json  # noqa: PLC0415

    import league_level as ll  # noqa: PLC0415
    club_mv = {}
    for lg in LEAGUES:
        p = data_path("players_full", lg)
        if not p.exists():
            continue
        df = pd.read_csv(p, usecols=lambda c: c in ("squad", "market_value_eur"))
        if "market_value_eur" not in df.columns:
            continue
        club = pd.to_numeric(df["market_value_eur"], errors="coerce").groupby(df["squad"]).sum()
        club = club[club > 0]
        if len(club) >= 8:
            club_mv[lg] = float(club.mean())
    ll._CACHE = None
    known = {lg: v for lg, v in ll.levels().items() if lg in ll.LEAGUE_COUNTRY and LEAGUES.get(lg) and LEAGUES[lg].division == 1}
    levels, fit = ll.fit_second_tier(club_mv, known)
    out = {"at": dt.date.today().isoformat(), "fit": fit, "levels": levels,
           "club_mv_mean_m": {k: round(v / 1e6, 1) for k, v in club_mv.items()}}
    if levels:
        ll.STRENGTH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[league_strength] 2부 리그 레벨 {levels} (직선 n={fit.get('n')} · 기울기 {fit.get('slope')})")
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from fetch_fotmob_ratings import _get  # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--season", choices=["cur", "prev"], default="cur")
    a = ap.parse_args(argv)
    y = SEASON_START - (1 if a.season == "prev" else 0)
    season = f"{y}_{y + 1}"
    bad = 0
    for lg in [a.league] if a.league else LITE_LEAGUES:
        if not LEAGUES[lg].lite:
            print(f"[{lg}] 라이트 리그가 아님 — 건너뜀")
            continue
        path = data_path("players_full", lg, season)
        if a.season == "prev" and path.exists():
            continue                                   # 끝난 시즌은 한 번만
        try:
            out = build(lg, season, _get)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패가 다른 리그를 멈추지 않게(파일은 그대로)
            print(f"[{lg}] 실패 {type(e).__name__}: {e}")
            bad += 1
            continue
        out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        mv = out["market_value_eur"].notna().mean() if "market_value_eur" in out else 0
        print(f"[{lg} {season}] {len(out)}명 · {out['squad'].nunique()}팀 · 출전 {int((out['minutes'] > 0).sum())}명 · "
              f"평점 {int(out['ss_rating'].notna().sum())}명 · 시장가치 {mv:.0%} -> {path.name}")
    if a.season == "cur":
        try:
            write_strength()
        except Exception as e:  # noqa: BLE001
            print(f"[league_strength] 건너뜀 {type(e).__name__}: {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
