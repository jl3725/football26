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


def blend(frame: pd.DataFrame) -> pd.DataFrame:
    """ss_rating(·prev_ss_rating) = Sofascore 와 FotMob(척도 맞춤)의 평균, hist_* 빈칸은 FotMob 2시즌 전으로."""
    out = frame.copy()
    out["ss_rating_sofa"] = out.get("ss_rating")
    fm = fm_to_ss(_num(out.get("fm_rating")))
    out["ss_rating"] = _avg(out.get("ss_rating"), fm)
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
