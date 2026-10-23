"""
적정 이적료 — 시장가치 × 사는 리그·나이 배수(이적 기록에서 학습) + 비슷한 이적 5건(근거).

2026-10-23 사용자: "이 선수 €25~35M, 비슷한 사례: …"를 영입 후보 카드·스카우트 리포트에. 13개 리그 이적 기록으로 재 보니
(하나 빼고 맞히기) 비슷한 이적 5건의 이적료로 값을 내면 오차 중앙값 46%, OVR·나이 보정해도 41% — TM 시장가치 하나(33%)보다
못했다. 그래서 가운데 값 = 이적 직전 시장가치 × 배수(사는 리그 · 나이대, 30%), 비슷한 이적은 '근거'로만 보여 준다.
예전엔 네 곳(추천·작업대·정책·적합도)이 '시장가치 × 1.2' 고정값을 썼다 — 이제 전부 price().

- 사례 표(data/fee_comps.csv): 전 리그 transfers_* 의 유료 완전 이적(€0.5M 이상, 임대 제외), 양쪽 리그에 다 있으면 한 줄.
  당시 OVR = 이적 직전 시즌(여름 S → S-1/S, 겨울 S → S/S+1) 선수 표에 지금 공식(ratings_v3)을 적용, 그 시즌 표가 없으면 가장
  가까운 시즌(ovr_season 에 적음). 이적 직전 시장가치 = 그 시즌 표의 소속이 판 구단일 때만(이적 뒤 값은 이적료에 맞춰 바뀐다).
- 배수(data/fee_model.json): log(이적료 ÷ 시장가치)의 중앙값 + 사는 리그 효과 + 나이대 효과(표본이 적으면 0 쪽으로 줄임).
  범위 = 하나 빼고 맞힌 잔차의 가운데 50%(lo·hi) · 80%(lo80·hi80). 정확도(오차 중앙값·범위 적중률)도 같이 적는다.
- 계약 잔여: 선수 표의 계약 날짜가 이적 뒤 새 계약이라(중앙값 36개월) 과거 사례에 못 쓴다 — 화면에서 대상 선수 메모로만.
- 시장가치가 없으면 OVR·나이·리그·포지션 회귀(오차가 커서 범위가 넓고 basis='ovr').

사용: python src/fee_comps.py          # 사례 표·배수 다시 만들기(daily_data 'fee_comps' 단계)
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TABLE = DATA / "fee_comps.csv"
MODEL = DATA / "fee_model.json"
MIN_FEE = 500_000
SHRINK = 20            # 사는 리그·나이대 효과 — 표본 n 이면 n/(n+20) 만큼만 믿는다
AGE_BANDS = ((0, 21, "21세 이하"), (22, 26, "22~26세"), (27, 30, "27~30세"), (31, 99, "31세 이상"))

# TM 포지션 → 비교 묶음(포지션 그룹·라인). 라인이 다르면 사례로 쓰지 않는다
POS_GROUP = {"Goalkeeper": "GK", "Centre-Back": "CB", "Left-Back": "FB", "Right-Back": "FB", "Defensive Midfield": "DM",
             "Central Midfield": "CM", "Midfielder": "CM", "Attacking Midfield": "AM", "Left Winger": "W", "Right Winger": "W",
             "Left Midfield": "W", "Right Midfield": "W", "Centre-Forward": "CF", "Second Striker": "CF", "Forward": "CF"}
LINE = {"GK": 0, "CB": 1, "FB": 1, "DM": 2, "CM": 2, "AM": 3, "W": 3, "CF": 3}
# 사례 거리 — OVR 3점 ≈ 나이 2살 ≈ 리그 수준 4점 ≈ 1, 같은 라인 다른 포지션 +1.5
W_OVR, W_AGE, W_LV, W_POS = 1 / 3, 1 / 2, 1 / 4, 1.5


_BUCKET = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "FB": "FB", "DM": "DM", "CM": "CM",
           "AM": "AM", "LW": "W", "RW": "W", "LM": "W", "RM": "W", "W": "W", "ST": "CF", "CF": "CF", "SS": "CF"}


def pos_group(tm_pos) -> str:
    """TM 포지션('Left Winger') 또는 화면 버킷('LW'·'ST', api._pos_bucket) → 비교 묶음."""
    s = str(tm_pos or "").strip()
    return POS_GROUP.get(s) or _BUCKET.get(s.upper(), "CM")


def age_band(age) -> str:
    try:
        a = int(age)
    except (TypeError, ValueError):
        return AGE_BANDS[1][2]
    return next(lbl for lo, hi, lbl in AGE_BANDS if lo <= a <= hi)


def _level(lg) -> float | None:
    if not isinstance(lg, str) or not lg:
        return None
    try:
        import league_level as ll  # noqa: PLC0415
        return float(ll.level(lg))
    except Exception:  # noqa: BLE001
        return None


# ── 사례 표 ─────────────────────────────────────────────────────────────────
def _transfers(data_dir: Path) -> pd.DataFrame:
    from leagues import parse_data_filename  # noqa: PLC0415
    parts = []
    for f in glob.glob(str(data_dir / "transfers_*.csv")):
        try:
            _, lg, _ = parse_data_filename(Path(f).name)
            d = pd.read_csv(f)
        except Exception:  # noqa: BLE001 — 깨진 파일 하나가 전체를 막지 않게
            continue
        d["league"] = lg
        parts.append(d)
    if not parts:
        return pd.DataFrame()
    t = pd.concat(parts, ignore_index=True)
    loan = t["fee_text"].astype(str).str.contains("loan", case=False)
    t = t[(pd.to_numeric(t["fee_eur"], errors="coerce").fillna(0) >= MIN_FEE) & ~loan].copy()
    t["fee_eur"] = pd.to_numeric(t["fee_eur"], errors="coerce")
    inn = t["direction"].astype(str) == "in"
    t["seller"] = np.where(inn, t["club"], t["squad"])
    t["buyer"] = np.where(inn, t["squad"], t["club"])
    t["buyer_lg"] = np.where(inn, t["league"], None)
    t["seller_lg"] = np.where(~inn, t["league"], None)
    first = lambda s: next((x for x in s if isinstance(x, str) and x), None)   # noqa: E731
    g = t.groupby(["norm_key", "season_id", "window", "fee_eur"], as_index=False).agg(
        player=("player", "first"), pos=("pos", "first"), age=("age", "first"), nat=("nat", "first"),
        seller=("seller", "first"), buyer=("buyer", "first"), buyer_lg=("buyer_lg", first), seller_lg=("seller_lg", first),
        photo=("photo", "first"))
    return g


def _season_frames() -> dict[str, pd.DataFrame]:
    """시즌 → 전 리그 선수 표(norm_key·squad·league·ovr·market_value_eur·minutes)."""
    sys.path[:0] = [str(ROOT)] if str(ROOT) not in sys.path else []
    import api.bootstrap  # noqa: F401,PLC0415
    import ratings_v3 as rv3  # noqa: PLC0415
    from api.services.player_data import player_frame  # noqa: PLC0415
    from leagues import LEAGUES, SEASON_START  # noqa: PLC0415
    out: dict[str, pd.DataFrame] = {}
    for y in (SEASON_START - 1, SEASON_START):
        season = f"{y}_{y + 1}"
        parts = []
        for lg in LEAGUES:
            try:
                df = player_frame(lg, season)
            except Exception:  # noqa: BLE001
                df = None
            if df is None or df.empty:
                continue
            df = df.copy()
            df["league"] = lg
            df["ovr"] = [rv3.player_line(r)["ovr"] for _, r in df.iterrows()]
            parts.append(df[[c for c in ("norm_key", "squad", "league", "ovr", "market_value_eur", "minutes") if c in df.columns]])
        if parts:
            out[season] = pd.concat(parts, ignore_index=True)
    return out


def build_table(data_dir: Path | None = None, frames: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    g = _transfers(data_dir or DATA)
    if g.empty:
        return g
    frames = frames if frames is not None else _season_frames()
    avail = sorted(frames)
    rows = []
    for r in g.to_dict("records"):
        s = int(r["season_id"])
        want = f"{s - 1}_{s}" if str(r["window"]) == "summer" else f"{s}_{s + 1}"
        cands = [want] + sorted((x for x in avail if x != want), key=lambda x: abs(int(x[:4]) - int(want[:4])))
        hit, season = None, None
        for sea in cands:
            f = frames.get(sea)
            if f is None:
                continue
            m = f[f["norm_key"].astype(str) == str(r["norm_key"])]
            if len(m):
                same = m[m["squad"].astype(str) == str(r["seller"])]
                hit = (same if len(same) else m).sort_values("minutes", ascending=False).iloc[0]
                season = sea
                break
        pre = hit is not None and season == want and str(hit["squad"]) == str(r["seller"])
        mv = pd.to_numeric(hit["market_value_eur"], errors="coerce") if pre else np.nan
        seller_lg = r.get("seller_lg") or (str(hit["league"]) if hit is not None and str(hit["squad"]) == str(r["seller"]) else None)
        pg = pos_group(r.get("pos"))
        rows.append({**r, "pg": pg, "line": LINE[pg], "seller_lg": seller_lg,
                     "ovr": float(hit["ovr"]) if hit is not None else np.nan, "ovr_season": season or "",
                     "mv_eur": float(mv) if pd.notna(mv) and mv > 0 else np.nan})
    return pd.DataFrame(rows)


# ── 배수 학습 ──────────────────────────────────────────────────────────────────
def _shrunk(groups: pd.Series, vals: pd.Series) -> dict[str, float]:
    out = {}
    for k, v in vals.groupby(groups):
        out[str(k)] = float(v.median()) * len(v) / (len(v) + SHRINK)
    return out


def _fit_ratio(d: pd.DataFrame) -> dict:
    """log(이적료/시장가치) = base + 사는 리그 효과 + 나이대 효과(두 번 번갈아 맞춤)."""
    lr = np.log(d["fee_eur"] / d["mv_eur"])
    base = float(lr.median())
    buyer = d["buyer_lg"].fillna("other").astype(str)
    band = d["age"].map(age_band)
    lg_eff: dict[str, float] = {}
    age_eff: dict[str, float] = {}
    for _ in range(2):
        lg_eff = _shrunk(buyer, lr - base - band.map(age_eff).fillna(0.0))
        age_eff = _shrunk(band, lr - base - buyer.map(lg_eff).fillna(0.0))
    return {"base": base, "buyer": lg_eff, "age": age_eff}


def _ratio_pred(m: dict, buyer_lg, age) -> float:
    """학습 때와 같은 키 — 우리 13개 리그 밖 구단이 산 이적은 'other'."""
    key = str(buyer_lg) if isinstance(buyer_lg, str) and buyer_lg else "other"
    return m["base"] + m["buyer"].get(key, 0.0) + m["age"].get(age_band(age), 0.0)


def _ovr_design(d: pd.DataFrame, med_lv: float, groups: list[str]) -> np.ndarray:
    blv = d["buyer_lg"].map(_level).astype(float).fillna(med_lv)
    slv = d["seller_lg"].map(_level).astype(float).fillna(med_lv - 4)
    cols = [np.ones(len(d)), d["ovr"].astype(float), d["age"].astype(float), (d["age"].astype(float) - 25) ** 2, blv, slv]
    cols += [(d["pg"] == g).astype(float) for g in groups[1:]]
    return np.column_stack(cols)


def fit(table: pd.DataFrame) -> dict:
    """배수·범위·정확도. 하나 빼고 맞히기로 잰 잔차로 범위를 잡는다(제 자신을 넣고 재면 좁고 낙관적)."""
    t = table.dropna(subset=["fee_eur", "age"]).copy()
    t = t[t["fee_eur"] >= MIN_FEE]
    v = t.dropna(subset=["mv_eur"]).reset_index(drop=True)
    model: dict = {"built": dt.date.today().isoformat(), "n_transfers": int(len(t)), "n_mv": int(len(v))}
    if len(v) >= 40:
        m = _fit_ratio(v)
        y = np.log(v["fee_eur"] / v["mv_eur"]).to_numpy()
        res, base_err = [], []
        for i in range(len(v)):
            mi = _fit_ratio(v.drop(i))
            p = _ratio_pred(mi, v.at[i, "buyer_lg"], v.at[i, "age"])
            res.append(y[i] - p)
            base_err.append(abs(math.exp(y[i]) - 1))          # 시장가치 그대로
        res = np.array(res)
        q = np.quantile(res, [0.1, 0.25, 0.75, 0.9])
        err = np.abs(np.exp(res) - 1)
        model.update({**m, "q": {"q10": float(q[0]), "q25": float(q[1]), "q75": float(q[2]), "q90": float(q[3])},
                      "acc": {"med_err": round(float(np.median(err)), 3), "within30": round(float(np.mean(err <= 0.3)), 3),
                              "in50": round(float(np.mean((res >= q[1]) & (res <= q[2]))), 3),
                              "in80": round(float(np.mean((res >= q[0]) & (res <= q[3]))), 3),
                              "mv_only_err": round(float(np.median(base_err)), 3)},
                      "buyer_n": {str(k): int(n) for k, n in v["buyer_lg"].fillna("other").value_counts().items()},
                      "age_n": {str(k): int(n) for k, n in v["age"].map(age_band).value_counts().items()}})
    # 시장가치 없을 때 — OVR 회귀(LOO 잔차 = e/(1-h))
    o = t.dropna(subset=["ovr"]).reset_index(drop=True)
    if len(o) >= 60:
        lvs = [x for x in o["buyer_lg"].map(_level).tolist() if x is not None and x == x]
        med_lv = float(np.median(lvs)) if lvs else 90.0
        groups = sorted(o["pg"].unique())
        X = _ovr_design(o, med_lv, groups)
        y = np.log(o["fee_eur"].to_numpy())
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        h = np.einsum("ij,jk,ik->i", X, np.linalg.pinv(X.T @ X), X)
        loo = (y - X @ beta) / np.clip(1 - h, 1e-6, None)
        q = np.quantile(loo, [0.1, 0.25, 0.75, 0.9])
        err = np.abs(np.exp(loo) - 1)
        model["ovr_reg"] = {"beta": [float(b) for b in beta], "groups": groups, "med_lv": med_lv,
                            "q": {"q10": float(q[0]), "q25": float(q[1]), "q75": float(q[2]), "q90": float(q[3])},
                            "acc": {"med_err": round(float(np.median(err)), 3), "n": int(len(o))}}
    return model


# ── 읽기·계산(API) ───────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_cached(mtime_key: tuple) -> tuple[dict, pd.DataFrame]:
    try:
        m = json.loads(MODEL.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        m = {}
    try:
        t = pd.read_csv(TABLE)
    except (FileNotFoundError, ValueError):
        t = pd.DataFrame()
    return m, t


def load() -> tuple[dict, pd.DataFrame]:
    key = tuple(p.stat().st_mtime if p.exists() else 0 for p in (MODEL, TABLE))
    return _load_cached(key)


def _round_eur(x: float) -> int:
    """화면용 반올림 — €10M 넘으면 €1M 단위, 그 아래는 €0.1M."""
    step = 1_000_000 if x >= 10_000_000 else 100_000
    return int(round(x / step) * step)


def price(mv_eur, age, buyer_lg: str | None = None, *, ovr=None, pg: str | None = None, seller_lg: str | None = None,
          model: dict | None = None) -> dict | None:
    """적정 이적료 {lo, mid, hi, lo80, hi80, basis, factors}. 사는 리그를 모르면 리그 평균(basis 그대로, 'any' 표시)."""
    m = model if model is not None else load()[0]
    mv = pd.to_numeric(mv_eur, errors="coerce")
    if m.get("q") and pd.notna(mv) and mv > 0:
        lg_key = str(buyer_lg) if buyer_lg else None
        lg_eff = m["buyer"].get(lg_key, 0.0) if lg_key else 0.0
        a_eff = m["age"].get(age_band(age), 0.0)
        c = math.log(float(mv)) + m["base"] + lg_eff + a_eff
        q = m["q"]
        factors = [{"k": "buyer", "label": f"{buyer_lg} 구단" if buyer_lg else "사는 구단 미정(리그 평균)",
                    "x": round(math.exp(m["base"] + lg_eff), 2), "n": int((m.get("buyer_n") or {}).get(lg_key or "", 0))},
                   {"k": "age", "label": age_band(age), "x": round(math.exp(a_eff), 2),
                    "n": int((m.get("age_n") or {}).get(age_band(age), 0))}]
        return {"basis": "mv", "mv_eur": int(mv), "mid": _round_eur(math.exp(c)),
                "lo": _round_eur(math.exp(c + q["q25"])), "hi": _round_eur(math.exp(c + q["q75"])),
                "lo80": _round_eur(math.exp(c + q["q10"])), "hi80": _round_eur(math.exp(c + q["q90"])),
                "factors": factors, "acc": m.get("acc"), "buyer_known": bool(buyer_lg)}
    r = m.get("ovr_reg")
    if r and ovr is not None and age is not None and pd.notna(pd.to_numeric(ovr, errors="coerce")):
        row = pd.DataFrame([{"ovr": float(ovr), "age": float(age), "buyer_lg": buyer_lg, "seller_lg": seller_lg, "pg": pg or "CM"}])
        x = _ovr_design(row, r["med_lv"], r["groups"])[0]
        c = float(x @ np.array(r["beta"]))
        q = r["q"]
        return {"basis": "ovr", "mv_eur": None, "mid": _round_eur(math.exp(c)),
                "lo": _round_eur(math.exp(c + q["q25"])), "hi": _round_eur(math.exp(c + q["q75"])),
                "lo80": _round_eur(math.exp(c + q["q10"])), "hi80": _round_eur(math.exp(c + q["q90"])),
                "factors": [], "acc": r.get("acc"), "buyer_known": bool(buyer_lg)}
    return None


def comparables(norm_key: str, age, ovr, tm_pos, seller_lg: str | None, buyer_lg: str | None, k: int = 5,
                table: pd.DataFrame | None = None) -> list[dict]:
    """비슷한 이적 k건 — 같은 라인, 나이·당시 OVR·판 리그·산 리그가 가까운 순(같은 포지션이면 앞으로). 자기 자신 제외."""
    t = table if table is not None else load()[1]
    if t is None or t.empty or ovr is None or age is None:
        return []
    pg = pos_group(tm_pos)
    o = t[(t["line"] == LINE[pg]) & t["ovr"].notna() & (t["norm_key"].astype(str) != str(norm_key))].copy()
    if o.empty:
        return []
    lv_all = [x for x in o["buyer_lg"].map(_level).tolist() if x is not None and x == x]
    med = float(np.median(lv_all)) if lv_all else 90.0
    s_lv = _level(seller_lg) or med - 4
    b_lv = _level(buyer_lg) or med
    o_s = o["seller_lg"].map(_level).astype(float).fillna(med - 4)
    o_b = o["buyer_lg"].map(_level).astype(float).fillna(med)
    o["dist"] = (abs(o["ovr"] - float(ovr)) * W_OVR + abs(o["age"] - float(age)) * W_AGE + abs(o_s - s_lv) * W_LV
                 + abs(o_b - b_lv) * W_LV + (o["pg"] != pg) * W_POS)
    s = lambda x: x if isinstance(x, str) else ""   # noqa: E731 — CSV 빈 칸은 NaN(JSON 에 못 실음)
    out = []
    for r in o.nsmallest(k, "dist").to_dict("records"):
        mv = r.get("mv_eur")
        out.append({"player": s(r["player"]), "age": int(r["age"]), "ovr": int(round(r["ovr"])), "pos": s(r.get("pos")),
                    "from": s(r["seller"]), "to": s(r["buyer"]), "from_lg": s(r.get("seller_lg")), "to_lg": s(r.get("buyer_lg")),
                    "fee_eur": int(r["fee_eur"]), "ratio": round(float(r["fee_eur"]) / float(mv), 2) if mv == mv and mv else None,
                    "when": f"{str(int(r['season_id']))[2:]} {'여름' if r['window'] == 'summer' else '겨울'}",
                    "photo": r.get("photo") if isinstance(r.get("photo"), str) else "", "dist": round(float(r["dist"]), 2)})
    return out


def main() -> int:
    t = build_table()
    if t.empty:
        print("fee_comps: 이적 기록 없음 — 그대로 둠")
        return 1
    m = fit(t)
    t.sort_values(["season_id", "fee_eur"], ascending=[False, False]).to_csv(TABLE, index=False, encoding="utf-8", lineterminator="\n")
    MODEL.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    a = m.get("acc") or {}
    print(f"fee_comps: 사례 {len(t)}건(OVR {int(t['ovr'].notna().sum())} · 직전 시장가치 {m.get('n_mv')}) · "
          f"오차 중앙값 {a.get('med_err')} (시장가치만 {a.get('mv_only_err')}) · 범위 적중 {a.get('in50')} -> {TABLE.name}, {MODEL.name}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
