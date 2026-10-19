"""
최근 폼(최근 3·5경기) — FotMob 경기별 평점(src/fetch_fotmob_matches.py → data/fotmob_match_ratings_*).

2026-10-19 사용자: "노팅엄전 사카가 엄청 못했는데 '폼 절정'. 최근 3경기는 그저 그랬다 — 시즌 전체 폼과
최근 3·5경기 폼을 나누자". 시즌 폼(_form)은 시즌 평균 평점의 리그·포지션 안 순위라 한두 경기 부진이 안 보인다.

- 경기: 전 대회(리그·유럽·컵), 최근 60일 안 출전 중 평점 있는 경기만, 최근 RECENT_N(5)경기.
- 평점: 출전 시간 가중 평균(90분 = 1, 최소 0.25 — 짧은 교체 평점이 평균을 끌어올리지 않게)을
  FotMob 척도에서 Sofascore 척도로 옮겨(rating_blend.fm_to_ss) 시즌 폼과 같은 포지션 평균·편차로 본다.
- 점수: 포지션 평균 쪽으로 1경기어치만 당기고(한 경기 반짝·부진이 전부가 되지 않게), 같은 리그·포지션 안
  순위를 시즌 폼과 같은 45~99 척도로(72 = 중간, 90+ 상위 10%). 2경기 미만이면 점수 없음.
"""
from __future__ import annotations

import datetime

import pandas as pd

from rating_blend import fm_to_ss
from ratings_v3 import _F_MEAN, _F_SD, _form_scale, line_of_row

RECENT_N = 5
MIN_APPS = 2
WINDOW_DAYS = 60
PRIOR_W = 1.0


def _today() -> str:
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date().isoformat()


def recent_rows(mr: pd.DataFrame | None, today: str | None = None) -> pd.DataFrame:
    """평점 있는 최근 60일 출전 — 날짜 내림차순."""
    if mr is None or mr.empty:
        return pd.DataFrame()
    lo = (datetime.date.fromisoformat(today or _today()) - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    d = mr.copy()
    d["rating"] = pd.to_numeric(d["rating"], errors="coerce")
    d = d[d["rating"].notna() & (d["date"].astype(str) >= lo)]
    d["fotmob_id"] = d["fotmob_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    return d.sort_values(["date", "match_id"], ascending=False)


def _key_of(fm_id, squad, player) -> tuple[str, str]:
    try:
        if fm_id is not None and fm_id == fm_id and int(fm_id) > 0:
            return ("id", str(int(fm_id)))
    except (TypeError, ValueError):
        pass
    return ("nm", f"{squad}|{player}")


def by_player(rr: pd.DataFrame) -> dict[tuple[str, str], pd.DataFrame]:
    """{('id', fotmob_id) | ('nm', 'squad|player'): 최근 경기 행(최신 → 과거, 최대 5)}."""
    out: dict = {}
    if rr is None or rr.empty:
        return out
    for fid, g in rr.groupby("fotmob_id", sort=False):
        top = g.head(RECENT_N)
        out[("id", str(fid))] = top
        r0 = top.iloc[0]
        out.setdefault(("nm", f"{r0['squad']}|{r0['player']}"), top)
    return out


def _wavg(r: pd.Series, w: pd.Series) -> float:
    return float((r * w).sum() / w.sum())


def summary(g: pd.DataFrame | None) -> dict | None:
    """최근 경기 → {n, avg5, avg3(FotMob 척도, 출전 시간 가중), ss5(Sofascore 척도), w5(가중 경기 수)}.

    25분 교체 1골 1도움 7.94 같은 짧은 출전 평점이 풀타임 경기와 같은 무게면 평균을 끌어올린다(사카 릴전) —
    출전 90분 = 1, 짧을수록 덜(최소 0.25)."""
    if g is None or g.empty:
        return None
    d = g.assign(rating=pd.to_numeric(g["rating"], errors="coerce")).dropna(subset=["rating"])
    if d.empty:
        return None
    w = (pd.to_numeric(d["minutes"], errors="coerce").fillna(90) / 90.0).clip(0.25, 1.0)
    r = d["rating"]
    a5, a3 = _wavg(r.head(5), w.head(5)), _wavg(r.head(3), w.head(3))
    return {"n": int(len(r)), "avg5": round(a5, 2), "avg3": round(a3, 2), "ss5": float(fm_to_ss(a5)), "w5": float(w.head(5).sum())}


def add_recent_form(frame: pd.DataFrame, mr: pd.DataFrame | None, today: str | None = None) -> pd.DataFrame:
    """선수 표에 `_recent`(45~99) · `_recent_avg5`·`_recent_avg3`(FotMob 평균) · `_recent_n` 열."""
    out = frame.copy()
    for c in ("_recent", "_recent_avg5", "_recent_avg3", "_recent_n"):
        out[c] = None
    bp = by_player(recent_rows(mr, today))
    if not bp or out.empty:
        return out
    lines = out.apply(line_of_row, axis=1)
    z, sums = [], []
    for (_, r), ln in zip(out.iterrows(), lines):
        s = summary(lookup(bp, r.get("fm_id"), r.get("squad"), r.get("player")))
        sums.append(s)
        if not s or s["n"] < MIN_APPS:
            z.append(float("nan"))
            continue
        shrunk = (s["ss5"] * s["w5"] + _F_MEAN[ln] * PRIOR_W) / (s["w5"] + PRIOR_W)
        z.append((shrunk - _F_MEAN[ln]) / _F_SD[ln])
    zs = pd.Series(z, index=out.index, dtype="float64")
    pct = zs.groupby(lines).rank(pct=True, method="average")
    n = zs.groupby(lines).transform("count")
    p = (pct * n - 0.5) / n
    out["_recent"] = [(_form_scale(v) if v == v else None) for v in p]
    out["_recent_avg5"] = [s["avg5"] if s else None for s in sums]
    out["_recent_avg3"] = [s["avg3"] if s else None for s in sums]
    out["_recent_n"] = [s["n"] if s else None for s in sums]
    return out


def lookup(bp: dict, fm_id, squad, player) -> pd.DataFrame | None:
    """by_player 색인에서 한 선수 — FotMob id 우선, 없으면 (팀, 이름)."""
    k = _key_of(fm_id, squad, player)
    g = bp.get(k) if k[0] == "id" else None
    return g if g is not None else bp.get(("nm", f"{squad}|{player}"))


def match_list(g: pd.DataFrame | None) -> list[dict]:
    """최근 5경기 — 화면 막대용(최신 → 과거)."""
    if g is None or g.empty:
        return []
    num = lambda v: int(pd.to_numeric(v, errors="coerce") or 0)  # noqa: E731
    return [{"date": str(x["date"]), "comp_code": str(x["comp_code"]), "opponent": str(x["opponent"]),
             "home_away": str(x["home_away"]), "minutes": num(x["minutes"]), "rating": round(float(x["rating"]), 2),
             "goals": num(x["goals"]), "assists": num(x["assists"])}
            for _, x in g.iterrows()]
