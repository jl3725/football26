"""
리그 시즌 누적(골·도움·출전 분·경기 수)을 경기 직후 값으로 — FotMob 경기별 기록(data/fotmob_match_ratings_*)의 리그 경기 합.
xG 계열 per90 은 Understat 매일 수집(data/understat_players_*)으로 — apply_understat_live.

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


def league_code(league: str) -> str:
    """FotMob 경기별 기록의 리그 대회 코드(eng.1 …) — 라이트 리그(eng.2 …)는 leagues.py espn."""
    from leagues import LEAGUES  # noqa: PLC0415
    return LEAGUE_CODE[league][0] if league in LEAGUE_CODE else getattr(LEAGUES.get(league), "espn", "")


def league_totals(mr: pd.DataFrame | None, league: str) -> tuple[dict, dict]:
    """({fotmob_id: 합계}, {'squad|player': 합계}) — 리그 경기만. 합계 = {minutes, goals, assists, apps, asof}."""
    code = league_code(league)
    if mr is None or mr.empty or not code:
        return {}, {}
    d = mr[mr["comp_code"].astype(str) == code].copy()
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


# 같은 경기를 두 원천이 몇 분 다르게 센다(추가 시간 — 26/27 1,408명이 FotMob 1~15분 적음). 이 안이고 골·도움도 덜하지 않으면
# FotMob 이 경기를 빠뜨린 게 아니라 같은 경기 — 헤더도 SEASON LOG(FotMob 경기별)와 같은 값으로(Thijs Jansen 990′ ≠ 982′, 2026-11-06)
MINUTE_SLACK = 15


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
            g, a = pd.to_numeric(r.get("goals"), errors="coerce"), pd.to_numeric(r.get("assists"), errors="coerce")
            if mins - t["minutes"] > MINUTE_SLACK or (g == g and t["goals"] < g) or (a == a and t["assists"] < a):
                continue                               # FotMob 쪽이 경기를 빠뜨림(분이 한참 적거나 골·도움이 덜함) — FBref 유지
        out.at[i, "goals"], out.at[i, "assists"], out.at[i, "minutes"] = t["goals"], t["assists"], t["minutes"]
        out.at[i, "_stats_src"], out.at[i, "_stats_asof"], out.at[i, "_apps_live"] = "fotmob", t["asof"], t["apps"]
    return out


# ── xG 계열(Understat 매일 — src/fetch_understat_live.py) ─────────────────────
_US_P90 = {"xg_p90": "xg", "npxg_p90": "np_xg", "xa_p90": "xa", "kp_p90": "key_passes", "shots_p90": "shots",
           "xg_chain_p90": "xg_chain"}


def _norm(s) -> str:
    from unidecode import unidecode
    return " ".join(unidecode(str(s or "")).lower().replace("-", " ").split())


def apply_understat_live(frame: pd.DataFrame, us: pd.DataFrame | None) -> pd.DataFrame:
    """xG 계열 per90 을 Understat 최신 합계로 — Understat 출전 분이 선수 표(FBref) 분 이상일 때만. `_xg_src` 열.
    매칭: (팀, 이름) 정확 → 같은 팀에서 성이 하나뿐일 때 (팀, 성)."""
    out = frame.copy()
    out["_xg_src"] = "weekly"
    if us is None or us.empty:
        return out
    full, last, dup = {}, {}, set()
    for r in us.to_dict("records"):
        full[(_norm(r["squad"]), _norm(r["player"]))] = r
        lk = (_norm(r["squad"]), (_norm(r["player"]).split() or [""])[-1])
        if lk in last:
            dup.add(lk)
        last[lk] = r
    for k in dup:
        last.pop(k, None)
    for i, r in out.iterrows():
        sq, pl = _norm(r.get("squad")), _norm(r.get("player"))
        u = full.get((sq, pl)) or last.get((sq, (pl.split() or [""])[-1]))
        if u is None:
            continue
        um, fm = pd.to_numeric(u.get("minutes"), errors="coerce"), pd.to_numeric(r.get("minutes"), errors="coerce")
        if not (um == um and um > 0) or (fm == fm and um < fm):
            continue
        n90 = um / 90.0
        for col, src in _US_P90.items():
            v = pd.to_numeric(u.get(src), errors="coerce")
            if v == v:
                out.at[i, col] = round(float(v) / n90, 3)
        out.at[i, "_xg_src"] = "understat_live"
    return out


# ── xG 계열 대체 원천(FotMob · Opta xG — 13개 리그 경기마다, 클라우드 매일) ──────────────
# 2026-11-03 사용자: Understat(빅5만, 11/02 부터 접속 불가) 대체 사이트? → FotMob 경기별 선수 기록(xg·npxg·xa·키패스·슈팅,
# 선수-경기 4.3만 건 xG 100%)을 자동 대체로. Understat 가 살아 있으면 그대로 우선(understat_live), 그렇지 않을 때
# 값이 비었거나 FotMob 이 한 경기 이상 더 최신이면 FotMob 합으로. 척도는 같은 선수들의 기존 값과 비율로 맞춘다.
_FM_XG = {"xg_p90": "xg", "npxg_p90": "npxg", "xa_p90": "xa", "kp_p90": "chances", "shots_p90": "shots"}
FM_XG_MIN_GAP = 90.0        # 주간 값보다 이만큼(한 경기) 더 최신일 때만 바꾼다(값이 비어 있으면 바로)
FM_XG_CAL_MIN, FM_XG_CAL_N = 450, 30


def fotmob_xg_totals(mr: pd.DataFrame | None, league: str) -> pd.DataFrame:
    """리그 경기(세부 기록 있는 행) 선수별 합 — index = 키(FotMob id 또는 '팀|이름'), 열 = xg·npxg·xa·chances·shots·minutes."""
    import allcomp_stats as acs  # noqa: PLC0415
    code = league_code(league)
    if mr is None or mr.empty or not code or "comp_code" not in mr.columns:
        return pd.DataFrame()
    d = mr[(mr["comp_code"].astype(str) == code) & (pd.to_numeric(mr.get("det"), errors="coerce").fillna(0) > 0)].copy()
    if d.empty:
        return pd.DataFrame()
    d["_key"] = acs.row_keys(d)
    cols = [*_FM_XG.values(), "minutes"]
    for c in cols:
        d[c] = pd.to_numeric(d.get(c), errors="coerce").fillna(0)
    return d.groupby("_key")[cols].sum()


def _xg_ratio(frame: pd.DataFrame, tot: pd.DataFrame, keys: pd.Series) -> tuple[dict[str, float], set[str]]:
    """({열: 우리 값 / FotMob per90 비율(출전 가중)}, {기준이 없는 열}) — 450′+ 선수 30명 이상일 때 0.4~2.5, 모자라면 1.
    기준이 없는 열 = 450′+ 선수 절반 이상이 0·빈값(포르투갈·에레디비시·벨기에는 Understat 가 없어 xg_p90 이 전부 0 이었다 —
    0 에 맞추면 비율이 0.4 로 눌린다) → 비율 1, 그 리그는 FotMob 으로 바로 채운다."""
    mins = pd.to_numeric(frame["minutes"], errors="coerce")
    fm = keys.map(tot["minutes"]) if "minutes" in tot.columns else pd.Series(float("nan"), index=frame.index)
    ok = (mins >= FM_XG_CAL_MIN) & (fm >= FM_XG_CAL_MIN)
    out, none = {}, set()
    for col, src in _FM_XG.items():
        if col not in frame.columns:
            continue
        a = pd.to_numeric(frame[col], errors="coerce")
        b = keys.map(tot[src]) / fm * 90
        if ok.sum() >= 10 and float((a[ok].fillna(0) == 0).mean()) >= 0.5:
            out[col] = 1.0
            none.add(col)
            continue
        m = ok & a.notna() & (a > 0) & b.notna() & (b > 0)
        if m.sum() < FM_XG_CAL_N:
            out[col] = 1.0
            continue
        w = mins[m]
        out[col] = round(min(2.5, max(0.4, float((a[m] * w).sum() / (b[m] * w).sum()))), 3)
    return out, none


def apply_fotmob_xg(frame: pd.DataFrame, mr: pd.DataFrame | None, league: str) -> pd.DataFrame:
    """Understat 최신값(understat_live)이 아닌 선수의 xG 계열 per90 을 FotMob 리그 경기 합으로 — 값이 비었거나
    FotMob 출전 분이 주간 표보다 FM_XG_MIN_GAP 이상 많을 때. `_xg_src = 'fotmob'`, `_xg_ratio` 열(보정 비율, 점검용)."""
    import allcomp_stats as acs  # noqa: PLC0415
    out = frame.copy()
    if "_xg_src" not in out.columns:
        out["_xg_src"] = "weekly"
    tot = fotmob_xg_totals(mr, league)
    if tot.empty:
        return out
    lg_rows = mr[mr["comp_code"].astype(str) == league_code(league)] if "comp_code" in mr.columns else mr
    keys = pd.Series(acs.frame_keys(out, lg_rows), index=out.index)
    ratio, no_base = _xg_ratio(out, tot, keys)
    fm_min = pd.to_numeric(keys.map(tot["minutes"]), errors="coerce")
    fb_min = pd.to_numeric(out["minutes"], errors="coerce").fillna(0)
    n = 0
    for i in out.index:
        lm = fm_min.get(i)
        if lm is None or lm != lm or lm <= 0 or str(out.at[i, "_xg_src"]) == "understat_live":
            continue
        vals = {c: pd.to_numeric(out.at[i, c], errors="coerce") for c in _FM_XG if c in out.columns}
        empty = any(v != v for v in vals.values()) or bool(no_base)       # 기준 자체가 없는 리그는 바로
        if not empty and lm - float(fb_min.get(i, 0)) < FM_XG_MIN_GAP:
            continue
        t = tot.loc[keys.at[i]]
        for col, src in _FM_XG.items():
            if col in out.columns:
                out.at[i, col] = round(float(t[src]) / lm * 90 * ratio.get(col, 1.0), 3)
        out.at[i, "_xg_src"] = "fotmob"
        n += 1
    out["_xg_ratio"] = str({k: v for k, v in ratio.items()} | ({"no_base": sorted(no_base)} if no_base else {})) if n else ""
    return out


def apply_gk_live(frame: pd.DataFrame, ss: pd.DataFrame | None) -> pd.DataFrame:
    """GK 클린시트% 를 Sofascore 시즌 기록(cleanSheet ÷ appearances, 매일)으로 — FBref(주간)는 한 라운드 늦어
    Raya 가 50%(3/6)로 나왔다(실제 4/7, 2026-10-20 점검). Sofascore 는 매일 갱신이라 GK 행은 이 값으로 덮는다."""
    if ss is None or ss.empty or not {"cleanSheet", "appearances", "player", "squad"} <= set(ss.columns):
        return frame
    out = frame.copy()
    if "gk_cs_pct" not in out.columns:
        return out
    key = lambda sq, pl: f"{sq}|{pl}"  # noqa: E731
    live = {}
    for sq, pl, cs, ap in zip(ss["squad"].astype(str), ss["player"].astype(str),
                              pd.to_numeric(ss["cleanSheet"], errors="coerce"), pd.to_numeric(ss["appearances"], errors="coerce")):
        if ap == ap and ap and cs == cs:
            live[key(sq, pl)] = (float(cs), float(ap))
    for i, r in out.iterrows():
        hit = live.get(key(r.get("squad"), r.get("player")))
        if not hit or r.get("gk_cs_pct") is None:
            continue
        cs, ap = hit
        old = r.get("gk_cs_pct")
        if old == old:                               # GK 행(FBref 값이 있는 선수)만 — 필드 선수 cleanSheet 는 의미 없음
            out.at[i, "gk_cs_pct"] = round(cs / ap * 100, 1)
    return out
