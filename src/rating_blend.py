"""
두 출처 평균 평점 — Sofascore + FotMob(src/fetch_fotmob_ratings.py).

2026-10-19 사용자 제안: 'Sofascore 하나는 이상할 때가 있다, 여러 사이트 평균'. 평점은 OVR 경기력·폼·시즌 베스트 XI
의 원천이라 한 사이트의 버릇(수비수 액션 가중 등)이 그대로 들어갔다.

척도 맞추기: 25/26 전 리그 900분+ 1,941명에서 두 평점 상관 0.84, Sofascore 평균 6.848·표준편차 0.216,
FotMob 6.888·0.296 → FotMob 을 같은 위치(z)의 Sofascore 값으로 바꿔(fm_to_ss) 단순 평균. 한쪽만 있으면 그 값.

붙이는 열(player_frame 이 부른다):
  ss_rating_sofa · fm_rating(원래 값, 화면 표시용) · ss_rating = 두 출처 평균
  prev_* : 직전 시즌 FotMob(같은 FotMob 선수 id, 리그를 옮겼어도) — Sofascore 직전 평점과 평균, 없던 출전·리그도 채움
  hist_* : 2시즌 전 FotMob — attach_prev_season 의 hist_* 가 비었을 때(유효 출전 = 분 × 0.5)
"""
from __future__ import annotations

import pandas as pd

FM_MU, FM_SD, SS_MU, SS_SD = 6.888, 0.296, 6.848, 0.216
# 365Scores(세 번째 원천, src/fetch_365_ratings.py) — 척도는 리그·포지션 라인마다 이번 빌드에서 맞춘다(cal_365). 아래는 모자랄 때 기본값
# (26/27 EPL 450분+ 192명: 365 6.855±0.340 · Sofascore 6.957±0.297, 상관 365–FotMob 0.78 · 365–Sofascore 0.64 · Sofascore–FotMob 0.81).
# 골키퍼는 원천마다 크게 달라(E. 마르티네스 365 6.42 · Sofascore 7.63) 라인별로 맞춘다
S365_MU, S365_SD, S365_REF_MU, S365_REF_SD = 6.855, 0.340, 6.957, 0.297
CAL_MIN, CAL_N = 450.0, 25
# 라인별 척도 표본 — 골키퍼는 리그당 16~21명이라 25명 기준이면 늘 리그 전체 척도로 바뀌어, 365 골키퍼 평점(평균 6.7)이
# 필드 선수 척도로 옮겨져 골키퍼 평균이 0.15 내려갔다(2026-11-05). 12명+ 은 그 라인, 5~11명은 평균만 그 라인
CAL_N_LINE, CAL_N_MEAN = 12, 5
HIST_DECAY = 0.5


def fm_to_ss(x):
    """FotMob 평점 → 같은 위치의 Sofascore 척도."""
    return SS_MU + (x - FM_MU) * SS_SD / FM_SD


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _season_tag(season: str | None, back: int) -> str | None:
    from leagues import SEASON_START  # noqa: PLC0415
    start = int(season[:4]) if season else SEASON_START
    y = start - back
    return f"{y}_{y + 1}"


def _by_id(read, season: str) -> dict:
    """{fotmob_id: (평점, 분, 리그)} — 전 리그 그 시즌 FotMob 표(한 선수가 여러 리그면 분이 많은 쪽)."""
    from leagues import LEAGUES  # noqa: PLC0415
    out: dict = {}
    for lg in LEAGUES:
        t = read(lg, season)
        if t is None or t.empty or "fotmob_id" not in t.columns:
            continue
        for fid, r, mn in zip(t["fotmob_id"], _num(t["rating"]), _num(t["minutes"])):
            if pd.isna(fid) or pd.isna(r):
                continue
            k = int(fid)
            if k not in out or (mn or 0) > out[k][1]:
                out[k] = (float(r), float(mn or 0), lg)
    return out


def attach_365(frame: pd.DataFrame, table: pd.DataFrame | None) -> pd.DataFrame:
    """365Scores 시즌 평점(s365_rating·s365_minutes) — (팀, 이름) 정확히, 안 되면 같은 팀 이름 규칙·하나뿐인 성(live_roster)."""
    out = frame.copy()
    out["s365_rating"], out["s365_minutes"] = pd.NA, pd.NA
    if table is None or table.empty or not {"squad", "player", "rating"} <= set(table.columns):
        return out
    import live_roster as lr  # noqa: PLC0415
    by_team: dict[str, dict[str, tuple]] = {}
    for s, p, r, mn in zip(table["squad"].astype(str), table["player"].astype(str), _num(table["rating"]), _num(table["minutes"])):
        by_team.setdefault(s, {})[p] = (r, mn)
    for sq, g in out.groupby(out["squad"].astype(str)):
        cand = by_team.get(sq) or {}
        if not cand:
            continue
        names = list(cand)
        for idx, p in zip(g.index, g["player"].astype(str)):
            hit = cand.get(p)
            if hit is None:
                k = lr.match_in_squad(p, names)
                hit = cand.get(k) if k else None
            if hit is not None:
                out.at[idx, "s365_rating"], out.at[idx, "s365_minutes"] = hit
    return out


def cal_365(frame: pd.DataFrame, ref_col: str = "ss_rating") -> dict[str, tuple[float, float, float, float]]:
    """{라인: (365 평균, 표준편차, 기준 평균, 표준편차)} — 이 리그에서 두 값이 다 있는 450분+ 선수로. 라인 표본이 CAL_N 미만이면
    리그 전체, 그것도 모자라면 기본값. 기준 = Sofascore 척도의 이번 시즌 평점(라이트 리그는 FotMob 을 같은 척도로 바꾼 값).
    라인 표본이 CAL_N_LINE 이상이면 그 라인 그대로, CAL_N_MEAN 이상이면 평균만 그 라인(흩어짐은 리그 전체)."""
    import ratings_v3 as rv3  # noqa: PLC0415
    a, b = _num(frame.get("s365_rating")), _num(frame.get(ref_col))
    m = _num(frame.get("s365_minutes")).fillna(0)
    ok = a.notna() & (a > 0) & b.notna() & (b > 0) & (m >= CAL_MIN)
    lines = pd.Series([rv3.line_of_row(r) for _, r in frame.iterrows()], index=frame.index)
    out = {}
    pooled = (float(a[ok].mean()), float(a[ok].std()), float(b[ok].mean()), float(b[ok].std())) if ok.sum() >= CAL_N else \
        (S365_MU, S365_SD, S365_REF_MU, S365_REF_SD)
    for ln in ("GK", "DEF", "MID", "ATT"):
        k = ok & (lines == ln)
        if k.sum() >= CAL_N_LINE:
            out[ln] = (float(a[k].mean()), float(a[k].std()), float(b[k].mean()), float(b[k].std()))
        elif k.sum() >= CAL_N_MEAN:
            out[ln] = (float(a[k].mean()), pooled[1], float(b[k].mean()), pooled[3])
        else:
            out[ln] = pooled
    out["_lines"] = lines  # type: ignore[assignment]
    return out


def s365_to_ss(frame: pd.DataFrame, cal: dict) -> pd.Series:
    """365 평점 → 같은 라인·같은 위치(z)의 Sofascore 척도."""
    lines = cal.get("_lines")
    x = _num(frame.get("s365_rating"))
    out = pd.Series(pd.NA, index=frame.index, dtype="object")
    for ln in ("GK", "DEF", "MID", "ATT"):
        mu, sd, rmu, rsd = cal[ln]
        k = (lines == ln) & x.notna() & (x > 0)
        if sd and sd == sd and sd > 0:
            out[k] = rmu + (x[k] - mu) * rsd / sd
    return _num(out)


def attach(frame: pd.DataFrame, league: str, season: str | None, read) -> pd.DataFrame:
    """read(league, season) → FotMob 표(이름은 레지스트리로 정규화된 것). frame 사본을 돌려준다."""
    out = frame.copy()
    cur = read(league, season or _season_tag(None, 0))
    fid = pd.Series([None] * len(out), index=out.index, dtype="object")
    out["fm_rating"] = pd.NA
    out["fm_minutes"] = pd.NA
    if cur is not None and not cur.empty:
        key = {(str(s), str(p)): (i, r, mn) for s, p, i, r, mn in
               zip(cur["squad"], cur["player"], cur["fotmob_id"], _num(cur["rating"]), _num(cur["minutes"]))}
        for idx, s, p in zip(out.index, out["squad"].astype(str), out["player"].astype(str)):
            hit = key.get((s, p))
            if hit:
                fid[idx] = int(hit[0]) if pd.notna(hit[0]) else None
                out.at[idx, "fm_rating"] = hit[1]
                out.at[idx, "fm_minutes"] = hit[2]
        # 이름이 원천마다 다른 선수 — src/live_roster 가 같은 팀·같은 성으로 맞춘 FotMob 번호(_fm_hint)로
        # ('Bachir Belloumi' ↔ 'Mohamed Belloumi', 2026-11-03)
        if "_fm_hint" in out.columns:
            by_id = {int(i): (r, mn) for i, r, mn in zip(cur["fotmob_id"], _num(cur["rating"]), _num(cur["minutes"]))
                     if pd.notna(i)}
            for idx in out.index[fid.isna() & out["_fm_hint"].notna()]:
                try:
                    k = int(float(out.at[idx, "_fm_hint"]))
                except (TypeError, ValueError):
                    continue
                fid[idx] = k
                if k in by_id:
                    out.at[idx, "fm_rating"], out.at[idx, "fm_minutes"] = by_id[k]
    # 이번 시즌 FotMob 에 없는 선수(출전 적음·부상)는 직전 시즌 표에서 (직전 팀, 이름)으로 id 를 찾는다
    prev_tag = _season_tag(season, 1)
    if "prev_squad" in out.columns:
        need = fid.isna()
        if need.any():
            prev_key = {}
            from leagues import LEAGUES  # noqa: PLC0415
            for lg in LEAGUES:
                t = read(lg, prev_tag)
                if t is not None and not t.empty:
                    prev_key.update({(str(s), str(p)): i for s, p, i in zip(t["squad"], t["player"], t["fotmob_id"])})
            for idx in out.index[need]:
                i = prev_key.get((str(out.at[idx, "prev_squad"]), str(out.at[idx, "player"])))
                if i is not None and pd.notna(i):
                    fid[idx] = int(i)
    out["fm_id"] = fid
    for tag, pre in ((prev_tag, "prev_fm"), (_season_tag(season, 2), "hist_fm")):
        table = _by_id(read, tag)
        vals = [table.get(i) if i is not None else None for i in fid]
        out[f"{pre}_rating"] = [v[0] if v else pd.NA for v in vals]
        out[f"{pre}_minutes"] = [v[1] if v else pd.NA for v in vals]
        out[f"{pre}_league"] = [v[2] if v else pd.NA for v in vals]
    return out


def _avg(a: pd.Series, b: pd.Series) -> pd.Series:
    a, b = _num(a), _num(b)
    a = a.where(a > 0)
    b = b.where(b > 0)
    return pd.concat([a, b], axis=1).mean(axis=1, skipna=True)


def coverage_avg(a: pd.Series, a_min: pd.Series, b: pd.Series, b_min: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(평균, a 의 몫) — 각 출처가 반영한 이번 시즌 출전 시간만큼. 둘 다 최신이면(분이 같으면) 단순 평균과 같다.
    2026-10-27: Sofascore 는 이 PC 에서만 받는다(클라우드 IP 차단) — PC 가 꺼진 날엔 며칠 전 값이 오늘 FotMob 과 반반
    섞였다. 이제 Sofascore 가 360분, FotMob 이 720분을 반영했으면 Sofascore 몫은 1/3. 출전 시간이 없는 쪽은 최신으로 본다."""
    a, b = _num(a).where(_num(a) > 0), _num(b).where(_num(b) > 0)
    am, bm = _num(a_min), _num(b_min)
    top = pd.concat([am, bm], axis=1).max(axis=1)
    wa = (am / top).where(am.notna() & (top > 0), 1.0).clip(0, 1).where(a.notna(), 0.0)
    wb = (bm / top).where(bm.notna() & (top > 0), 1.0).clip(0, 1).where(b.notna(), 0.0)
    w = wa + wb
    avg = ((a.fillna(0) * wa + b.fillna(0) * wb) / w).where(w > 0)
    return avg, (wa / w).where(w > 0)


def coverage_avg_n(vals: list[pd.Series], mins: list[pd.Series]) -> tuple[pd.Series, list[pd.Series]]:
    """원천 N개 — 각자 반영한 이번 시즌 출전 시간만큼(가장 많은 쪽 = 1) 가중 평균. (평균, [원천별 몫])."""
    vs = [_num(v).where(_num(v) > 0) for v in vals]
    ms = [_num(m) for m in mins]
    top = pd.concat(ms, axis=1).max(axis=1)
    ws = [(m / top).where(m.notna() & (top > 0), 1.0).clip(0, 1).where(v.notna(), 0.0) for v, m in zip(vs, ms)]
    w = sum(ws)
    avg = (sum(v.fillna(0) * wi for v, wi in zip(vs, ws)) / w).where(w > 0)
    return avg, [(wi / w).where(w > 0) for wi in ws]


def blend(frame: pd.DataFrame, lite: bool = False) -> pd.DataFrame:
    """ss_rating(·prev_ss_rating) = Sofascore · FotMob · 365Scores(척도 맞춤)의 평균, hist_* 빈칸은 FotMob 2시즌 전으로.
    이번 시즌은 출처별 반영 출전 시간 가중(coverage_avg_n) — ss_share_sofa·ss_share_365 에 몫.
    lite=True(라이트 리그) — ss_rating 이 이미 FotMob 을 바꾼 값이라 Sofascore 로 세지 않는다(FotMob 두 번 방지).
    2026-11-05 사용자: '평점 원천 3곳 평균이면 신빙성이 오르지 않나' → 365Scores 추가."""
    out = frame.copy()
    out["ss_rating_sofa"] = out.get("ss_rating")
    fm = fm_to_ss(_num(out.get("fm_rating")))
    col = lambda c: out[c] if c in out.columns else pd.Series(pd.NA, index=out.index, dtype="object")   # noqa: E731
    sofa = pd.Series(pd.NA, index=out.index, dtype="object") if lite else col("ss_rating")
    vals, mins = [sofa, pd.Series(fm, index=out.index)], [col("ss_minutes"), col("fm_minutes")]
    if "s365_rating" in out.columns and _num(out["s365_rating"]).notna().any():
        ref = pd.Series(fm, index=out.index) if lite else _num(col("ss_rating")).where(_num(col("ss_rating")) > 0, pd.Series(fm, index=out.index))
        cal = cal_365(out.assign(_ref=ref), ref_col="_ref")
        out["s365_ss"] = s365_to_ss(out, cal)
        vals.append(out["s365_ss"])
        mins.append(col("s365_minutes"))
    avg, shares = coverage_avg_n(vals, mins)
    if lite and _num(avg).isna().all():
        avg = col("ss_rating")
    out["ss_rating"] = avg.where(avg.notna(), _num(col("ss_rating")) if not lite else avg)
    out["ss_share_sofa"] = shares[0]
    out["ss_share_365"] = shares[2] if len(shares) > 2 else pd.Series(0.0, index=out.index)
    if "prev_fm_rating" in out.columns:
        pfm = fm_to_ss(_num(out["prev_fm_rating"]))
        if "prev_ss_rating" not in out.columns:
            out["prev_ss_rating"] = pd.NA
        out["prev_ss_rating_sofa"] = out["prev_ss_rating"]
        out["prev_ss_rating"] = _avg(out["prev_ss_rating"], pfm)
        # 직전 시즌 기록이 없던 선수(우리 데이터 밖 리그·이름 매칭 실패)는 FotMob 출전·리그로 채운다
        for col, src in (("prev_minutes", "prev_fm_minutes"), ("prev_league", "prev_fm_league")):
            if col not in out.columns:
                out[col] = pd.NA
            out[col] = out[col].astype("object")
            empty = out[col].isna() | (out[col].astype(str).isin(["", "nan", "None"]))
            out.loc[empty, col] = out.loc[empty, src]
        out["prev_minutes"] = _num(out["prev_minutes"])
    if "hist_fm_rating" in out.columns:
        for col in ("hist_ss_rating", "hist_minutes", "hist_league"):
            if col not in out.columns:
                out[col] = pd.NA
            out[col] = out[col].astype("object")
        empty = _num(out["hist_ss_rating"]).isna() & _num(out["hist_fm_rating"]).notna()
        out.loc[empty, "hist_ss_rating"] = fm_to_ss(_num(out.loc[empty, "hist_fm_rating"]))
        out.loc[empty, "hist_minutes"] = _num(out.loc[empty, "hist_fm_minutes"]) * HIST_DECAY
        out.loc[empty, "hist_league"] = out.loc[empty, "hist_fm_league"]
        out["hist_ss_rating"] = _num(out["hist_ss_rating"])
        out["hist_minutes"] = _num(out["hist_minutes"])
    return out
