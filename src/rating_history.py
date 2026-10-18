"""
선수 평점 추이 — OVR·폼·POT 를 날마다 기록해 '2주 전 대비 ▲▼'와 '지난 시즌 대비'를 만든다.

OVR 은 그 시점 데이터(시장가치·평점)로 매번 새로 계산되므로 과거 값이 남지 않는다. 그래서
daily_data 가 하루 한 번 record() 를 돌려 data/rating_history[_리그]_<시즌>.csv 에 남긴다.
값이 바뀐 선수만 한 줄씩 쓰는 변경분 저장이라(하루 수백 줄) 저장소가 크게 늘지 않는다.
'날짜 D 의 값' = 그 선수의 D 이전 마지막 기록.

모델(ratings_v3.MODEL_VERSION)이 바뀌면 그날 과거 기록을 '오늘 새 값 − 마지막 기록' 만큼 평행이동한다 —
공식 변경이 선수 추이(예: Modrić ▲8)로 보이지 않게. 하루치 실제 변화는 그 차이에 섞여 사라진다.

    python -m rating_history            # 전 리그 오늘자 기록(scripts/record_ratings.py 가 호출)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from leagues import LEAGUES, SEASON_START, data_path

COLS = ["date", "pid", "squad", "player", "norm_key", "ovr", "form", "pot", "model"]
TREND_DAYS = 14


def pid(row) -> str:
    """선수 식별자 — Transfermarkt id 우선, 없으면 이름. 'Rodri' 처럼 한 이름이 여러 리그에 있어서
    이름만으로는 맨시티 로드리와 모레이렌스 로드리가 섞인다."""
    t = row.get("tm_id")
    try:
        if t is not None and t == t and str(t).strip() not in ("", "nan"):
            return f"tm{int(float(t))}"
    except (TypeError, ValueError):
        pass
    return "nk:" + str(row.get("norm_key") or "").strip()


def _today() -> str:
    # 한국 날짜 기준(수집 일정·화면 표기와 맞춤)
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date().isoformat()


def history_path(league: str) -> Path:
    return data_path("rating_history", league)


def current_ratings(league: str) -> pd.DataFrame:
    """API 와 같은 입구·같은 함수로 지금 값을 계산."""
    import ratings_v3 as rv3
    from api.services.player_data import player_frame
    df = player_frame(league)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    rows = []
    for _, r in df.iterrows():
        pl = rv3.player_line(r)
        rows.append({"pid": pid(r), "squad": r.get("squad"), "player": r.get("player"), "norm_key": r.get("norm_key"),
                     "ovr": pl["ovr"], "form": pl["form"], "pot": pl["pot"], "model": rv3.MODEL_VERSION})
    return pd.DataFrame(rows)


def rebase(hist: pd.DataFrame, cur: pd.DataFrame, today: str) -> pd.DataFrame:
    """다른 모델 버전으로 남은 기록을 (오늘 값 − 그 선수 마지막 기록) 만큼 옮기고 현재 버전으로 표시."""
    if hist.empty or cur.empty or "model" not in cur.columns:
        return hist
    ver = str(cur["model"].iloc[0])
    hist = hist.copy()
    if "model" not in hist.columns:
        hist["model"] = ""
    old = hist["model"].fillna("").astype(str) != ver
    if not old.any():
        return hist
    last = state_at(hist, today).set_index("pid")
    c = cur.set_index("pid")
    common = c.index.intersection(last.index)
    d_ovr = (c.loc[common, "ovr"] - last.loc[common, "ovr"]).to_dict()
    d_pot = (c.loc[common, "pot"] - last.loc[common, "pot"]).to_dict()
    hist.loc[old, "ovr"] = hist.loc[old, "ovr"] + hist.loc[old, "pid"].map(d_ovr).fillna(0)
    hist.loc[old, "pot"] = hist.loc[old, "pot"] + hist.loc[old, "pid"].map(d_pot).fillna(0)
    hist["ovr"] = hist["ovr"].round().astype(int)
    hist["pot"] = hist["pot"].round().astype(int)
    hist.loc[old, "model"] = ver
    return hist


def load(league: str) -> pd.DataFrame:
    p = history_path(league)
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(p, dtype={"date": str})


def state_at(hist: pd.DataFrame, date: str) -> pd.DataFrame:
    """date(포함) 이전 각 선수의 마지막 기록."""
    h = hist[hist["date"] <= date]
    if h.empty:
        return h
    return h.sort_values("date").groupby("pid", as_index=False).last()


def record(league: str, today: str | None = None) -> int:
    """오늘 값 중 직전 기록과 달라진 선수만 덧붙인다. 같은 날 다시 돌리면 그날 줄을 갈아 끼운다."""
    today = today or _today()
    hist = load(league)
    hist = hist[hist["date"] != today]
    cur = current_ratings(league)
    if cur.empty:
        return 0
    if "model" not in cur.columns:
        cur["model"] = ""
    if "model" not in hist.columns:
        hist = hist.assign(model="")
    hist = rebase(hist, cur, today)
    prev = state_at(hist, today)
    cur["date"] = today
    if not prev.empty:
        m = cur.merge(prev[["pid", "squad", "ovr", "form", "pot"]], on="pid", how="left",
                      suffixes=("", "_p"))
        same = ((m["ovr"] == m["ovr_p"]) & (m["squad"] == m["squad_p"])
                & ((m["form"] == m["form_p"]) | (m["form"].isna() & m["form_p"].isna()))
                & ((m["pot"] == m["pot_p"])))
        cur = cur[~same.values]
    if cur.empty:
        hist.to_csv(history_path(league), index=False)
        return 0
    out = cur[COLS].copy() if hist.empty else pd.concat([hist, cur[COLS]], ignore_index=True)
    out["form"] = out["form"].astype("Int64")
    out.to_csv(history_path(league), index=False)
    return len(cur)


# ── 조회(API) ─────────────────────────────────────────────────────────
def trend_baseline(league: str, days: int = TREND_DAYS) -> dict[str, dict]:
    """pid → {ovr, form, date} — days 일 전 시점 값. 그보다 늦게 처음 기록된 선수는 없음."""
    hist = load(league)
    if hist.empty:
        return {}
    then = (dt.date.fromisoformat(_today()) - dt.timedelta(days=days)).isoformat()
    st = state_at(hist, then)
    return {str(r.pid): {"ovr": int(r.ovr), "form": (None if pd.isna(r.form) else int(r.form)), "date": r.date}
            for r in st.itertuples()}


def prev_season_ovr() -> dict[str, dict]:
    """선수 키 → {ovr, league, squad, minutes} — 지난 시즌 마지막 데이터에 지금 공식을 적용한 OVR.

    리그를 옮긴 선수도 찾도록 전 리그를 본다. 키는 pid(tm id)이고, tm id 가 없는 선수를 위해
    '이름|국적' 키도 함께 둔다(지난 시즌 전체에서 하나뿐일 때만 — 동명이인 오매칭 방지).
    """
    import ratings_v3 as rv3
    from api.services.player_data import player_frame
    season = f"{SEASON_START - 1}_{SEASON_START}"
    best: dict[str, tuple[float, dict]] = {}
    alt: dict[str, list] = {}
    for lg in LEAGUES:
        df = player_frame(lg, season)
        if df is None:
            continue
        for _, r in df.iterrows():
            mn = pd.to_numeric(r.get("minutes"), errors="coerce")
            mn = 0.0 if pd.isna(mn) else float(mn)
            pmn = pd.to_numeric(r.get("prev_minutes"), errors="coerce")
            rec = {"ovr": rv3.player_line(r)["ovr"], "league": lg, "squad": r.get("squad"), "minutes": int(mn),
                   "gated": rv3.youth_gated(r.get("age"), mn + (0.0 if pd.isna(pmn) else float(pmn)))}
            k = pid(r)
            if k not in best or best[k][0] < mn:
                best[k] = (mn, rec)
            alt.setdefault(name_key(r), []).append(rec)
    out = {k: v for k, (_, v) in best.items()}
    for k, recs in alt.items():
        if len(recs) == 1:
            out.setdefault(k, recs[0])
    return out


def name_key(row) -> str:
    return "nm:" + str(row.get("norm_key") or "").strip() + "|" + str(row.get("nationality") or "").strip().lower()


def lookup_prev(prev: dict, row) -> dict | None:
    """지난 시즌 기록 찾기 — tm id 우선, 없으면 이름+국적(유일할 때만)."""
    k = pid(row)
    if not k.startswith("nk:") and k in prev:
        return prev[k]
    return prev.get(name_key(row))


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    day = _today()
    for lg in LEAGUES:
        n = record(lg, day)
        print(f"[rating-history] {lg:17} {day} 변경 {n}명 → {history_path(lg).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
