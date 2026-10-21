"""리그 간 경기(유럽대회) 예측 백테스트 — 서로 다른 우리 리그 팀끼리의 UCL·UEL·UECL 경기를 '그 경기 전 데이터만으로'.

2026-10-21: 유럽 활약을 OVR 에 넣은 뒤(src/allcomp_stats.py) 리그 간 예측이 실제로 맞는지 잰다. 리그 백테스트(backtest_model.py)는
리그 경기만 봐서 predict_model 의 리그 간 계수(b_cross · w_cross_form · 기본 득점 MU_CROSS)는 '17경기로 방향만' 정한 값이었다.

표본: 25/26 + 26/27 schedule_full 에서 두 팀 모두 우리 8개 리그(서로 다른 리그)인 끝난 유럽 경기.
입력(경기 전): 팀 Elo = 그날 아침 스냅숏(src/team_elo.py) · 리그 안 공격·수비 = 그 날 전 리그 경기로 만든 상태(26/27 = xG, 25/26 = 득점)
  · 팀 OVR = 아래 두 가지
    prev  — 26/27 경기에 지난 시즌(25/26) 끝 OVR. 미래 정보 없음
    same  — 25/26 경기에 25/26 끝 OVR. 그 시즌 결과가 섞여 OVR 에 유리(참고 — 상한)
평가: 25/26 로 계수를 고르고(OVR 없이 / OVR same) 26/27 에서 확인(OVR prev). 로그 손실·브라이어·적중률.

사용: python scripts/backtest_cross.py [--grid]
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import league_level  # noqa: E402
import predict_model as pm  # noqa: E402
import ratings_v3 as rv3  # noqa: E402
import team_elo as te  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

SEASONS = ("2025_2026", "2026_2027")


def _team_ovr(season: str) -> dict:
    """{팀: 팀 OVR} — 그 시즌 players_full 로(backtest_model._ovr 와 같은 방식)."""
    out = {}
    for lg in LEAGUES:
        p = data_path("players_full", lg, season=season)
        if not p.exists():
            continue
        full = pd.read_csv(p)
        for t in full["squad"].dropna().unique():
            tr = rv3.team_ratings(full, str(t))
            if tr:
                out[str(t)] = tr["overall"]
    return out


def _team_ovr_frame(season: str, with_x: bool) -> dict:
    """{팀: 팀 OVR} — 화면과 같은 player_frame(두 출처 평점 등) 기준. with_x = 그 시즌 유럽·컵 평점(src/allcomp_stats)을 넣은 OVR.
    25/26 끝 값을 26/27 경기에 쓰면 누설 없음 — '유럽 평점을 넣은 OVR 이 리그 간 예측을 낫게 하나'를 비교한다."""
    sys.path.insert(0, str(ROOT))
    import allcomp_stats as acs  # noqa: PLC0415
    import datastore as ds  # noqa: PLC0415
    from api.services.player_data import player_frame  # noqa: PLC0415
    rd = lambda t, lg, s: ds.read_table(t, league=lg, season=s)   # noqa: E731
    xt = acs.x_tables(rd, season, ("bt", season)) if with_x else None
    out = {}
    for lg in LEAGUES:
        f = player_frame(lg, season)
        if f is None or f.empty:
            continue
        f = acs.attach_x(f, xt, None) if with_x else f.drop(columns=[c for c in f.columns if c.startswith("x_") or c.startswith("prev_x_")])
        for t in f["squad"].dropna().unique():
            tr = rv3.team_ratings(f, str(t))
            if tr:
                out[str(t)] = tr["overall"]
    return out


def _league_rows(season: str) -> dict:
    """{리그: 리그 경기 표(홈 기준 한 줄)} — 26/27 은 match_stats(xG), 25/26 은 schedule_full(득점만)."""
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
    """리그 간 경기 + 경기 전 입력(fh, fa = 리그 안 공격+상대 수비, elo_d, ovr_h/a)."""
    frames = []
    for se in SEASONS:
        fr = {lg: pd.read_csv(data_path("schedule_full", lg, season=se), dtype={"event_id": str})
              for lg in LEAGUES if data_path("schedule_full", lg, season=se).exists()}
        m = te.matches_from(fr)
        m["season"] = se
        frames.append(m)
    ms = pd.concat(frames, ignore_index=True).drop_duplicates("event_id").sort_values(["date", "event_id"])
    cross = ms[ms["lg_h"].notna() & ms["lg_a"].notna() & (ms["lg_h"] != ms["lg_a"])
               & ms["comp_code"].astype(str).str.startswith("uefa.")].copy()
    _, snaps = te.run(ms, {lg: te.league_base(league_level.level(lg)) for lg in LEAGUES}, set(cross["date"]))
    ovr = {se: _team_ovr(se) for se in SEASONS}
    rows = {se: _league_rows(se) for se in SEASONS}
    cache: dict = {}

    def state(se: str, lg: str, date: str, ovr_map: dict):
        k = (se, lg, date, id(ovr_map))
        if k not in cache:
            mt = rows[se].get(lg)
            before = mt[mt["date"] < date] if mt is not None else pd.DataFrame()
            cache[k] = pm.build_state(before, ovr_map, pm.PARAMS, asof=date) if len(before) else None
        return cache[k]
    out = []
    for r in cross.itertuples(index=False):
        se = r.season
        ovr_map = ovr["2025_2026"]                       # 26/27 = 지난 시즌 끝(누설 없음) · 25/26 = 같은 시즌 끝(누설)
        sh, sa = state(se, r.lg_h, r.date, ovr_map), state(se, r.lg_a, r.date, ovr_map)
        th = sh.teams.get(r.home) if sh else None
        ta = sa.teams.get(r.away) if sa else None
        snap = snaps.get(r.date, {})
        out.append({"season": se, "date": r.date, "comp": r.comp_code, "home": r.home, "away": r.away,
                    "lg_h": r.lg_h, "lg_a": r.lg_a, "hg": int(r.hg), "ag": int(r.ag),
                    "res": "H" if r.hg > r.ag else "A" if r.hg < r.ag else "D",
                    "fh": (th["att"] + ta["def"]) if th and ta else 0.0, "fa": (ta["att"] + th["def"]) if th and ta else 0.0,
                    "elo_d": (snap[r.home] - snap[r.away]) if r.home in snap and r.away in snap else 0.0,
                    "ovr_h": ovr_map.get(r.home), "ovr_a": ovr_map.get(r.away),
                    "ovr_cur_h": ovr["2026_2027"].get(r.home), "ovr_cur_a": ovr["2026_2027"].get(r.away)})
    df = pd.DataFrame(out)
    for tag, wx in (("lg", False), ("x", True)):            # 25/26 끝 OVR — 리그 평점만 vs 유럽·컵 평점 포함
        m = _team_ovr_frame("2025_2026", wx)
        df[f"ovr_{tag}_h"], df[f"ovr_{tag}_a"] = df["home"].map(m), df["away"].map(m)
    return df


def predict_row(x, p: dict, ovr_cols=("ovr_h", "ovr_a")) -> dict:
    """운영과 같은 식(predict_model.cross_lambdas → Elo → summarize(dk))."""
    oh, oa = x[ovr_cols[0]], x[ovr_cols[1]]
    d = ((oh - oa) / 10.0) if oh == oh and oa == oa and oh is not None and oa is not None else 0.0
    lh, la = pm.cross_lambdas(x["fh"], x["fa"], d, {**pm.PARAMS, "w_cross_form": p["f"], "b_cross": p["b_cross"]},
                              (p["mu_h"], p["mu_a"]))
    s = p["b_elo"] * x["elo_d"] / 400.0
    lh, la = min(max(lh * math.exp(s), 0.15), 4.5), min(max(la * math.exp(-s), 0.15), 4.5)
    return pm.summarize(lh, la, p.get("rho", pm.PARAMS["rho"]), p.get("dk", 1.0))


def metrics(df: pd.DataFrame, p: dict, ovr_cols=("ovr_h", "ovr_a")) -> dict:
    ll = br = hit = 0.0
    for _, x in df.iterrows():
        pr = predict_row(x, p, ovr_cols)
        q = {"H": pr["h"], "D": pr["d"], "A": pr["a"]}
        ll += -math.log(max(1e-6, q[x["res"]]))
        br += sum((q[k] - (1.0 if k == x["res"] else 0.0)) ** 2 for k in q)
        hit += 1.0 if max(q, key=q.get) == x["res"] else 0.0
    n = max(1, len(df))
    return {"n": len(df), "logloss": round(ll / n, 4), "brier": round(br / n, 4), "acc": round(hit / n, 3)}


def base_rate(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    f = train["res"].value_counts(normalize=True).to_dict()
    ll = sum(-math.log(max(1e-6, f.get(r, 1e-6))) for r in test["res"]) / max(1, len(test))
    br = sum(sum((f.get(k, 0) - (1.0 if k == r else 0.0)) ** 2 for k in "HDA") for r in test["res"]) / max(1, len(test))
    return {"n": len(test), "logloss": round(ll, 4), "brier": round(br, 4), "acc": round((test["res"] == max(f, key=f.get)).mean(), 3)}


CURRENT = {"mu_h": pm.MU_CROSS[0], "mu_a": pm.MU_CROSS[1], "f": pm.PARAMS["w_cross_form"],
           "b_cross": pm.PARAMS["b_cross"], "b_elo": pm.PARAMS["b_elo"], "rho": pm.PARAMS["cross_rho"], "dk": pm.PARAMS["cross_dk"]}
OLD = {"mu_h": 1.45, "mu_a": 1.15, "f": 0.25, "b_cross": 0.6, "b_elo": 0.45, "rho": -0.08, "dk": 1.0}   # 2026-10-21 전


def calibrate(df: pd.DataFrame, shrink: float = 60.0) -> dict:
    """지난 리그 간 경기로 기본 득점(평균)·무승부 배수(실제 무승부 ÷ 예측 무승부, 표본 수축) — data/model_cross.json."""
    n = len(df)
    mu_h, mu_a = float(df["hg"].mean()), float(df["ag"].mean())
    p = {**CURRENT, "mu_h": mu_h, "mu_a": mu_a, "dk": 1.0}
    pred_d = sum(predict_row(x, p)["d"] for _, x in df.iterrows()) / max(1, n)
    act_d = float((df["res"] == "D").mean())
    raw = act_d / pred_d if pred_d > 0 else 1.0
    dk = 1.0 + (raw - 1.0) * n / (n + shrink)
    return {"mu_h": round(mu_h, 3), "mu_a": round(mu_a, 3), "dk": round(min(1.2, max(0.5, dk)), 3), "n": n,
            "draw_actual": round(act_d, 3), "draw_pred_raw": round(pred_d, 3)}
GRID = {"mu_h": (1.6, 1.75, 1.9, 2.05, 2.2), "mu_a": (1.15, 1.3, 1.45, 1.6), "f": (0.0, 0.15, 0.3),
        "b_cross": (0.3, 0.45, 0.6, 0.75, 0.9), "b_elo": (0.0, 0.2, 0.3, 0.45, 0.6), "rho": (-0.08, 0.0)}


def grid(train: pd.DataFrame, fixed: dict | None = None, ovr_cols=("ovr_h", "ovr_a")) -> list[tuple[dict, dict]]:
    keys = list(GRID)
    out = []
    for vals in itertools.product(*(GRID[k] for k in keys)):
        p = dict(zip(keys, vals))
        if fixed and any(p[k] != v for k, v in fixed.items()):
            continue
        out.append((p, metrics(train, p, ovr_cols)))
    return sorted(out, key=lambda t: t[1]["logloss"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--write", action="store_true", help="보정값만 계산해 data/model_cross.json 에 쓴다(매일 daily_data)")
    a = ap.parse_args()
    df = samples()
    if a.write:
        import datetime as dt  # noqa: PLC0415
        import json  # noqa: PLC0415
        cal = calibrate(df)
        p_ = {**CURRENT, "mu_h": cal["mu_h"], "mu_a": cal["mu_a"], "dk": cal["dk"]}
        m_new, m_old = metrics(df, p_), metrics(df, OLD)
        cal.update(asof=dt.date.today().isoformat(), logloss=m_new["logloss"], logloss_old_params=m_old["logloss"],
                   acc=m_new["acc"], note="scripts/backtest_cross.py --write — 리그 간 유럽 경기 기본 득점·무승부 배수")
        out = ROOT / "data" / "model_cross.json"
        out.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"리그 간 보정 {cal} -> {out.name}")
        return 0
    tr, ts = df[df["season"] == "2025_2026"], df[df["season"] == "2026_2027"]
    print(f"리그 간 유럽 경기 — 25/26 {len(tr)} · 26/27 {len(ts)}")
    print(f"  실제 결과 25/26 H/D/A {tr['res'].value_counts(normalize=True).round(3).to_dict()} · 평균 득점 홈 {tr.hg.mean():.2f} 원정 {tr.ag.mean():.2f}")
    print("현재 계수:", CURRENT)
    for name, part in (("25/26(OVR same — 누설)", tr), ("26/27(OVR prev — 누설 없음)", ts)):
        print(f"  {name:28} 기준선 {base_rate(tr, part)} · 예전 {metrics(part, OLD)} · 현재 {metrics(part, CURRENT)}")
    print(f"  26/27 현재 OVR(26/27 시즌 — 일부 누설) {metrics(ts, CURRENT, ('ovr_cur_h', 'ovr_cur_a'))}")
    ts_lg, ts_x = ("ovr_lg_h", "ovr_lg_a"), ("ovr_x_h", "ovr_x_a")
    print(f"  26/27 · 25/26 끝 OVR(화면 기준) 리그 평점만 {metrics(ts, CURRENT, ts_lg)} · 유럽·컵 포함 {metrics(ts, CURRENT, ts_x)}")
    if a.grid:
        both = pd.concat([tr, ts])
        print("\n[B] 25/26 로 고름(OVR same — 누설, OVR 비중 상한) → 26/27(누설 없음)에서 확인")
        gb = grid(tr)
        for p, m in gb[:6]:
            print(f"    {p} train {m['logloss']} · 26/27 {metrics(ts, p)} · 26/27 유럽 포함 OVR {metrics(ts, p, ts_x)['logloss']}")
        best = gb[0][0]
        print("\n[E] 고른 계수 + OVR 종류(26/27, 누설 없음)")
        for name, cols in (("raw players_full", ("ovr_h", "ovr_a")), ("리그 평점만", ts_lg), ("유럽·컵 포함", ts_x)):
            print(f"    {name:16} 현재 계수 {metrics(ts, CURRENT, cols)} · 고른 계수 {metrics(ts, best, cols)}")
        print("\n[F] 예측 무승부 평균 vs 실제(두 시즌)")
        for name, p in (("현재", CURRENT), ("고른", best)):
            dd = sum(predict_row(x, p)["d"] for _, x in both.iterrows()) / len(both)
            print(f"    {name} 예측 무승부 {dd:.3f} · 실제 {(both['res'] == 'D').mean():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
