"""리그 간 경기(유럽대회) 예측 백테스트·보정 — 서로 다른 우리 리그 팀끼리의 UCL·UEL·UECL 경기를 '그 경기 전 데이터만으로'.

2026-10-21: 유럽 활약을 OVR 에 넣은 뒤(src/allcomp_stats.py) 리그 간 예측이 맞는지 잰다. 리그 백테스트(backtest_model.py)는
리그 경기만 봐서 predict_model 의 리그 간 계수는 '17경기로 방향만' 정한 값이었다.
같은 날 검수: OVR 차의 척도가 운영과 달랐다(운영 = 화면 팀 OVR — 폼·팀 실적 보정이 섞여 시즌 초엔 리그 간 격차가 시즌 말의 2배).
→ 운영·백테스트 모두 '절대 전력'(베스트 XI 선수 OVR 만, rv3.team_ratings form_w=0 — api._club_abs)으로 OVR 차를 잰다.

표본: 지난 시즌 + 이번 시즌(leagues.SEASON_START 기준 자동) schedule_full 에서 두 팀 모두 우리 8개 리그(서로 다른 리그)인 끝난 유럽 경기.
입력(경기 전): 팀 Elo = 그날 아침 스냅숏(src/team_elo.py) · 리그 안 공격·수비 = 그 날 전 리그 경기로 만든 상태(xG 있으면 xG,
  없으면 득점) — 사전값은 그 리그 팀끼리의 절대 전력(운영처럼 리그 안 상대) · OVR 차 = 직전 시즌 끝 절대 전력(없으면 같은 시즌 — 누설, 표시)
평가: 지난 시즌으로 계수를 고르고(--grid) 이번 시즌에서 확인. 보정(--write): 기본 득점·무승부 배수를 지난 경기에 맞춘다.

사용: python scripts/backtest_cross.py [--grid] [--write]
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import league_level  # noqa: E402
import predict_model as pm  # noqa: E402
import ratings_v3 as rv3  # noqa: E402
import team_elo as te  # noqa: E402
from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402

SEASONS = (f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}")
CUR = SEASONS[1]


def _prev_season(se: str) -> str:
    y = int(se[:4]) - 1
    return f"{y}_{y + 1}"


def _team_abs(season: str) -> dict:
    """{리그: {팀: 절대 전력}} — 그 시즌 선수 표(player_frame, 화면과 같은 평점·리그 보정)의 베스트 XI OVR(폼·팀 실적 제외)."""
    out: dict = {}
    if not any(data_path("players_full", lg, season=season).exists() for lg in LEAGUES):
        return out
    from api.services.player_data import player_frame  # noqa: PLC0415
    for lg in LEAGUES:
        if not data_path("players_full", lg, season=season).exists():
            continue
        f = player_frame(lg, None if season == CUR else season)
        if f is None or f.empty:
            continue
        m = {}
        for t in f["squad"].dropna().unique():
            tr = rv3.team_ratings(f, str(t), perf=None, form_w=0.0)
            if tr:
                m[str(t)] = tr["overall"]
        out[lg] = m
    return out


def _league_rows(season: str) -> dict:
    """{리그: 리그 경기 표(홈 기준 한 줄)} — match_stats(xG) 가 있으면 그것, 없으면 schedule_full(득점만)."""
    out = {}
    for lg in LEAGUES:
        ms = data_path("match_stats", lg, season=season)
        if ms.exists():
            out[lg] = pm.league_matches(pd.read_csv(ms, dtype={"event_id": str}))
            continue
        sp = data_path("schedule_full", lg, season=season)
        if not sp.exists():
            continue
        s = pd.read_csv(sp, dtype={"event_id": str})
        s = s[(s["status"].astype(str) == "completed") & s["comp_code"].astype(str).str.endswith(".1") & (s["home_away"] == "H")]
        out[lg] = pd.DataFrame({"event_id": s["event_id"].astype(str), "date": s["date"].astype(str).str[:10],
                                "home": s["squad"], "away": s["opponent"],
                                "hg": pd.to_numeric(s["gf"], errors="coerce"), "ag": pd.to_numeric(s["ga"], errors="coerce"),
                                "hxg": float("nan"), "axg": float("nan"), "hsh": float("nan"), "ash": float("nan")}
                               ).dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)
    return out


def samples() -> pd.DataFrame:
    """리그 간 경기 + 경기 전 입력(fh, fa = 리그 안 공격+상대 수비, elo_d, abs_h/a = 절대 전력, ovr_leak = 같은 시즌 값을 썼나)."""
    frames = []
    for se in SEASONS:
        fr = {lg: pd.read_csv(data_path("schedule_full", lg, season=se), dtype={"event_id": str})
              for lg in LEAGUES if data_path("schedule_full", lg, season=se).exists()}
        if not fr:
            continue
        m = te.matches_from(fr)
        m["season"] = se
        frames.append(m)
    ms = pd.concat(frames, ignore_index=True).drop_duplicates("event_id").sort_values(["date", "event_id"])
    cross = ms[ms["lg_h"].notna() & ms["lg_a"].notna() & (ms["lg_h"] != ms["lg_a"])
               & ms["comp_code"].astype(str).str.startswith("uefa.")].copy()
    _, snaps = te.run(ms, {lg: te.league_base(league_level.level(lg)) for lg in LEAGUES}, set(cross["date"]))
    abs_by: dict = {}

    def abs_for(se: str) -> tuple[dict, bool]:
        """경기 시즌의 직전 시즌 절대 전력(누설 없음), 없으면 같은 시즌(누설)."""
        for s_, leak in ((_prev_season(se), False), (se, True)):
            if s_ not in abs_by:
                abs_by[s_] = _team_abs(s_)
            if abs_by[s_]:
                return abs_by[s_], leak
        return {}, True
    rows = {se: _league_rows(se) for se in SEASONS}
    cache: dict = {}

    def state(se: str, lg: str, date: str, amap: dict):
        k = (se, lg, date)
        if k not in cache:
            mt = rows[se].get(lg)
            before = mt[mt["date"] < date] if mt is not None else pd.DataFrame()
            cache[k] = pm.build_state(before, amap.get(lg, {}), pm.PARAMS, asof=date) if len(before) else None   # 리그 안 사전값(운영처럼)
        return cache[k]
    out = []
    for r in cross.itertuples(index=False):
        se = r.season
        amap, leak = abs_for(se)
        sh, sa = state(se, r.lg_h, r.date, amap), state(se, r.lg_a, r.date, amap)
        th = sh.teams.get(r.home) if sh else None
        ta = sa.teams.get(r.away) if sa else None
        snap = snaps.get(r.date, {})
        out.append({"season": se, "date": r.date, "comp": r.comp_code, "home": r.home, "away": r.away,
                    "lg_h": r.lg_h, "lg_a": r.lg_a, "hg": int(r.hg), "ag": int(r.ag),
                    "res": "H" if r.hg > r.ag else "A" if r.hg < r.ag else "D",
                    "fh": (th["att"] + ta["def"]) if th and ta else 0.0, "fa": (ta["att"] + th["def"]) if th and ta else 0.0,
                    "elo_d": (snap[r.home] - snap[r.away]) if r.home in snap and r.away in snap else 0.0,
                    "abs_h": amap.get(r.lg_h, {}).get(r.home), "abs_a": amap.get(r.lg_a, {}).get(r.away), "ovr_leak": leak})
    return pd.DataFrame(out)


def lambdas(x, p: dict) -> tuple[float, float]:
    """운영과 같은 식(predict_model.cross_lambdas → Elo) — 결장 보정은 과거 명단이 없어 뺀다."""
    oh, oa = x["abs_h"], x["abs_a"]
    d = ((oh - oa) / 10.0) if oh is not None and oa is not None and oh == oh and oa == oa else 0.0
    lh, la = pm.cross_lambdas(x["fh"], x["fa"], d, {**pm.PARAMS, "w_cross_form": p["f"], "b_cross": p["b_cross"]},
                              (p["mu_h"], p["mu_a"]))
    s = p["b_elo"] * x["elo_d"] / 400.0
    return min(max(lh * math.exp(s), 0.15), 4.5), min(max(la * math.exp(-s), 0.15), 4.5)


def predict_row(x, p: dict) -> dict:
    lh, la = lambdas(x, p)
    return pm.summarize(lh, la, p.get("rho", pm.PARAMS["cross_rho"]), p.get("dk", 1.0))


def metrics(df: pd.DataFrame, p: dict) -> dict:
    ll = br = hit = 0.0
    for _, x in df.iterrows():
        pr = predict_row(x, p)
        q = {"H": pr["h"], "D": pr["d"], "A": pr["a"]}
        ll += -math.log(max(1e-6, q[x["res"]]))
        br += sum((q[k] - (1.0 if k == x["res"] else 0.0)) ** 2 for k in q)
        hit += 1.0 if max(q, key=q.get) == x["res"] else 0.0
    n = max(1, len(df))
    return {"n": len(df), "logloss": round(ll / n, 4), "brier": round(br / n, 4), "acc": round(hit / n, 3)}


def base_rate(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    f = train["res"].value_counts(normalize=True).to_dict()
    ll = sum(-math.log(max(1e-6, f.get(r, 1e-6))) for r in test["res"]) / max(1, len(test))
    return {"n": len(test), "logloss": round(ll, 4), "acc": round((test["res"] == max(f, key=f.get)).mean(), 3)}


CURRENT = {"mu_h": pm.MU_CROSS[0], "mu_a": pm.MU_CROSS[1], "f": pm.PARAMS["w_cross_form"],
           "b_cross": pm.PARAMS["b_cross"], "b_elo": pm.PARAMS.get("cross_b_elo", pm.PARAMS["b_elo"]),
           "rho": pm.PARAMS["cross_rho"], "dk": pm.PARAMS["cross_dk"]}
OLD = {"mu_h": 1.45, "mu_a": 1.15, "f": 0.25, "b_cross": 0.6, "b_elo": 0.45, "rho": -0.08, "dk": 1.0}   # 2026-10-21 전


def calibrate(df: pd.DataFrame, p: dict | None = None, shrink: float = 60.0) -> dict:
    """기본 득점(예측 평균 득점 = 실제 평균이 되게 반복) · 무승부 배수(예측 무승부 = 실제가 되는 값을 이분 탐색 → 표본 수축)."""
    p = {**(p or CURRENT)}
    n = len(df)
    act_h, act_a, act_d = float(df["hg"].mean()), float(df["ag"].mean()), float((df["res"] == "D").mean())
    mu_h, mu_a = act_h, act_a
    for _ in range(4):
        q = {**p, "mu_h": mu_h, "mu_a": mu_a}
        lam = [lambdas(x, q) for _, x in df.iterrows()]
        mu_h *= act_h / (sum(a for a, _ in lam) / n)
        mu_a *= act_a / (sum(b for _, b in lam) / n)
    q = {**p, "mu_h": mu_h, "mu_a": mu_a}
    lam = [lambdas(x, q) for _, x in df.iterrows()]

    def mean_draw(dk: float) -> float:
        return sum(pm.summarize(a, b, q["rho"], dk)["d"] for a, b in lam) / n
    lo, hi = 0.3, 1.5
    for _ in range(25):
        mid = (lo + hi) / 2
        if mean_draw(mid) > act_d:
            hi = mid
        else:
            lo = mid
    raw = (lo + hi) / 2
    dk = 1.0 + (raw - 1.0) * n / (n + shrink)
    return {"mu_h": round(mu_h, 3), "mu_a": round(mu_a, 3), "dk": round(min(1.2, max(0.4, dk)), 3), "dk_raw": round(raw, 3), "n": n,
            "draw_actual": round(act_d, 3), "draw_pred_dk1": round(mean_draw(1.0), 3), "goals_actual": [round(act_h, 2), round(act_a, 2)]}


GRID = {"mu_h": (1.75, 1.9, 2.05), "mu_a": (1.3, 1.45), "f": (0.0, 0.15, 0.3),
        "b_cross": (0.2, 0.3, 0.45, 0.6, 0.75), "b_elo": (0.2, 0.3, 0.45, 0.6), "rho": (0.0,), "dk": (0.65, 0.75, 0.85, 1.0)}


def grid(train: pd.DataFrame) -> list[tuple[dict, dict]]:
    keys = list(GRID)
    out = [(p, metrics(train, p)) for p in (dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys)))]
    return sorted(out, key=lambda t: t[1]["logloss"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--write", action="store_true", help="보정값만 계산해 data/model_cross.json 에 쓴다(매일 daily_data)")
    a = ap.parse_args()
    df = samples()
    if df.empty:
        print("리그 간 경기 없음")
        return 0
    if a.write:
        import datetime as dt  # noqa: PLC0415
        import json  # noqa: PLC0415
        cal = calibrate(df)
        p_ = {**CURRENT, "mu_h": cal["mu_h"], "mu_a": cal["mu_a"], "dk": cal["dk"]}
        cal.update(asof=dt.date.today().isoformat(), seasons=list(SEASONS), max_match_date=str(df["date"].max()),
                   logloss=metrics(df, p_)["logloss"], logloss_old_params=metrics(df, OLD)["logloss"],
                   ovr_scale="절대 전력(베스트 XI 선수 OVR, 폼·팀 실적 제외) — api._club_abs",
                   note="scripts/backtest_cross.py --write — 리그 간 유럽 경기 기본 득점·무승부 배수")
        out = ROOT / "data" / "model_cross.json"
        out.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"리그 간 보정 {cal} -> {out.name}")
        return 0
    tr, ts = df[df["season"] == SEASONS[0]], df[df["season"] == SEASONS[1]]
    print(f"리그 간 유럽 경기 — {SEASONS[0]} {len(tr)}(OVR 누설 {bool(tr['ovr_leak'].any())}) · {SEASONS[1]} {len(ts)}(누설 {bool(ts['ovr_leak'].any())})")
    print(f"  절대 전력 차/10 표준편차 {((df['abs_h'] - df['abs_a']) / 10).std():.3f}")
    for name, part in ((SEASONS[0], tr), (SEASONS[1], ts)):
        print(f"  {name} 기준선 {base_rate(tr, part)} · 예전 {metrics(part, OLD)} · 현재 {metrics(part, CURRENT)}")
    if a.grid:
        g = grid(tr)
        print(f"\n[{SEASONS[0]} 로 고름 → {SEASONS[1]} 확인]")
        for p, m in g[:8]:
            print(f"    {p} train {m['logloss']} · test {metrics(ts, p)} · 합 {metrics(df, p)['logloss']}")
        best = g[0][0]
        cal_tr = calibrate(tr, best)
        p2 = {**best, "mu_h": cal_tr["mu_h"], "mu_a": cal_tr["mu_a"], "dk": cal_tr["dk"]}
        print(f"\n[고른 계수 + {SEASONS[0]} 로 보정한 기본 득점·무승부] {cal_tr}\n    test {metrics(ts, p2)} · 합 {metrics(df, p2)}")
        for name, p in (("예전", OLD), ("현재", CURRENT), ("고른+보정", p2)):
            dd = sum(predict_row(x, p)["d"] for _, x in df.iterrows()) / len(df)
            print(f"    {name} 예측 무승부 {dd:.3f} · 실제 {(df['res'] == 'D').mean():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
