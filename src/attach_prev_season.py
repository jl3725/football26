"""
활성 시즌 players_full 에 직전 시즌 기록(prev_*)을 붙인다 — 시즌 초반 OVR 안정화용.

시즌 초(예: 10월, 최대 ~600분)에는 이번 시즌 출전시간·평점만으로 판단하면
  - 21세 이하 '검증도'(출전시간 게이팅)가 바닥이라 주전 유망주가 크게 저평가되고
  - 30세+ 베테랑 보정(1500분 조건)이 전원 탈락한다.
ratings_v3 가 prev_minutes·prev_ss_rating 이 있으면 이를 합산·가중해 판단하도록 하고,
여기서는 그 컬럼만 채운다(없으면 기존 동작 그대로 — 25/26 데이터와 호환).

매칭: 직전 시즌 8개 리그 전체 players_full 에서 tm_id → (norm_key, 같은 squad) → norm_key(유일할 때만)
순으로 찾는다. 리그를 옮긴 선수(EPL→LaLiga 등)도 잡힌다. 리그가 다르면 출전시간을 리그 강도로
환산하지 않고 그대로 쓴다(검증 '양'의 근거로만 쓰므로).

사용: FB_LEAGUE=EPL FB_SEASON_START=2026 python src/attach_prev_season.py
"""
from __future__ import annotations

import sys

import pandas as pd
from unidecode import unidecode

from leagues import ACTIVE_LEAGUE, LEAGUES, SEASON_START, data_path

# 골키퍼 선방률·클린시트·시장가치도 — GK OVR 이 이번 시즌 몇 경기만 보던 것, 시장가치 누락 선수 기준점(2026-10-15)
PREV_COLS = ["prev_minutes", "prev_ss_rating", "prev_squad", "prev_league",
             "prev_gk_save_pct", "prev_gk_cs_pct", "prev_market_value_eur"]


def _norm(s) -> str:
    return unidecode(str(s or "")).lower().strip()


def _tmid(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ""


def load_prev(season_start: int) -> pd.DataFrame:
    """직전 시즌 전 리그 players_full (필요 컬럼만)."""
    frames = []
    for lg in LEAGUES:
        path = data_path("players_full", lg, f"{season_start - 1}_{season_start}")
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=lambda c: c in {"player", "squad", "minutes", "ss_rating", "tm_id", "norm_key",
                                                       "gk_save_pct", "gk_cs_pct", "market_value_eur"})
        for c in ("gk_save_pct", "gk_cs_pct", "market_value_eur"):
            if c not in df.columns:
                df[c] = pd.NA
        df["league"] = lg
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    prev = pd.concat(frames, ignore_index=True)
    prev["nk"] = [(_norm(k) if isinstance(k, str) and k else _norm(p))
                  for k, p in zip(prev.get("norm_key", prev["player"]), prev["player"])]
    prev["tid"] = prev["tm_id"].map(_tmid) if "tm_id" in prev.columns else ""
    prev["minutes"] = pd.to_numeric(prev["minutes"], errors="coerce").fillna(0)
    # 한 선수가 여러 행(시즌 중 이적)이면 출전이 가장 많은 행을 대표로
    return prev.sort_values("minutes", ascending=False)


def attach(cur: pd.DataFrame, prev: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = cur.drop(columns=[c for c in PREV_COLS if c in cur.columns]).copy()
    if prev.empty:
        for c in PREV_COLS:
            out[c] = pd.NA
        return out, {"tm_id": 0, "name+squad": 0, "name": 0, "none": len(out)}

    by_tid = {t: r for t, r in prev[prev["tid"] != ""].groupby("tid").head(1).set_index("tid").iterrows()}
    by_nk_sq = {(r.nk, r.squad): r for r in prev.groupby(["nk", "squad"]).head(1).itertuples()}
    nk_counts = prev.groupby("nk")["tid"].nunique()
    by_nk = {r.nk: r for r in prev.groupby("nk").head(1).itertuples()
             if nk_counts.get(r.nk, 0) <= 1}

    stats = {"tm_id": 0, "name+squad": 0, "name": 0, "none": 0}
    vals = []
    for _, r in out.iterrows():
        nk = _norm(r.get("norm_key") or r.get("player"))
        hit, how = None, "none"
        tid = _tmid(r.get("tm_id"))
        if tid and tid in by_tid:
            hit, how = by_tid[tid], "tm_id"
        elif (nk, r.get("squad")) in by_nk_sq:
            hit, how = by_nk_sq[(nk, r.get("squad"))], "name+squad"
        elif nk in by_nk:
            hit, how = by_nk[nk], "name"
        stats[how] += 1
        if hit is None:
            vals.append((pd.NA,) * len(PREV_COLS))
        else:
            g = (lambda k: hit[k]) if isinstance(hit, pd.Series) else (lambda k: getattr(hit, k))
            vals.append((int(g("minutes")), g("ss_rating"), g("squad"), g("league"),
                         g("gk_save_pct"), g("gk_cs_pct"), g("market_value_eur")))
    for c, col in zip(PREV_COLS, zip(*vals) if vals else [[]] * len(PREV_COLS)):
        out[c] = list(col)
    return out, stats


def main() -> int:
    path = data_path("players_full")
    if not path.exists():
        print(f"[prev] {path.name} 없음")
        return 1
    cur = pd.read_csv(path)
    prev = load_prev(SEASON_START)
    out, stats = attach(cur, prev)
    out.to_csv(path, index=False, encoding="utf-8")
    hit = len(out) - stats["none"]
    print(f"[prev] {ACTIVE_LEAGUE} {SEASON_START}: {hit}/{len(out)} 매칭 "
          f"(tm_id {stats['tm_id']} · 이름+팀 {stats['name+squad']} · 이름 {stats['name']}) -> {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
