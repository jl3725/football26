"""예측 모델 백테스트 — 이번 시즌 리그 경기를 '그 경기 전 데이터만으로' 예측해 실제 결과와 비교(2026-10-15).

비교 대상
  base   : 리그 홈·무·원정 비율(모두에게 같은 확률) — 최소 기준
  v1     : 예전 자체 모델(match_center.win_prob: OVR 차이 + 경기당 골득실)
  v2     : src/predict_model.py (xG 공격·수비 강도 + OVR 사전값 + Dixon-Coles)
지표: 로그 손실(낮을수록 좋음) · 브라이어 점수(낮을수록) · 적중률(가장 높은 확률 = 실제 결과)
사용: python scripts/backtest_model.py [--grid] [--min-round 2]
  --grid : v2 파라미터 격자 탐색 후 최적값 출력(PARAMS 갱신용)

한계: 팀 OVR 은 '현재' 선수 평점이라 시즌 초 경기엔 미래 정보가 조금 섞인다(사전값 비중이 큰 초반에 유리).
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
import match_center as mc  # noqa: E402
import predict_model as pm  # noqa: E402
import ratings_v3 as rv3  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402


def _ovr(league: str, season: str | None = None) -> dict:
    p = data_path("players_full", league, season=season)
    if not p.exists():
        return {}
    full = pd.read_csv(p)
    out = {}
    for t in full["squad"].dropna().unique():
        tr = rv3.team_ratings(full, str(t))
        out[str(t)] = tr["overall"] if tr else 75
    return out


def _load(ovr_season: str | None = None) -> dict:
    """ovr_season='2025_2026' 이면 지난 시즌 팀 OVR(미래 정보 없음 — 공정 비교). 승격팀은 리그 평균."""
    data = {}
    for lg in LEAGUES:
        p = data_path("match_stats", lg)
        if p.exists():
            data[lg] = (pm.league_matches(pd.read_csv(p, dtype={"event_id": str})), _ovr(lg, ovr_season))
    return data


def _metrics(rows: list[tuple[dict, str]]) -> dict:
    ll = br = hit = 0.0
    for pr, res in rows:
        p = {"H": pr["h"], "D": pr["d"], "A": pr["a"]}
        ll += -math.log(max(1e-6, p[res]))
        br += sum((p[k] - (1.0 if k == res else 0.0)) ** 2 for k in p)
        hit += 1.0 if max(p, key=p.get) == res else 0.0
    n = max(1, len(rows))
    return {"n": len(rows), "logloss": round(ll / n, 4), "brier": round(br / n, 4), "acc": round(hit / n, 3)}


def run(data: dict, params: dict, min_round: int = 2, which=("base", "v1", "v2")) -> dict:
    res = {k: [] for k in which}
    for lg, (mt, ovr) in data.items():
        for i, r in mt.iterrows():
            before = mt[mt["date"] < r["date"]]
            games = pd.concat([before["home"], before["away"]]).value_counts()
            if min(games.get(r["home"], 0), games.get(r["away"], 0)) < min_round - 1:
                continue
            out = "H" if r["hg"] > r["ag"] else "A" if r["hg"] < r["ag"] else "D"
            if "base" in which:
                n = len(before)
                ph = ((before["hg"] > before["ag"]).sum() + 0.45 * 10) / (n + 10)
                pa = ((before["hg"] < before["ag"]).sum() + 0.30 * 10) / (n + 10)
                res["base"].append(({"h": ph, "d": 1 - ph - pa, "a": pa}, out))
            if "v1" in which:
                def gdpg(t):
                    rows = before[(before["home"] == t) | (before["away"] == t)]
                    if rows.empty:
                        return 0.0
                    gd = sum((x.hg - x.ag) if x.home == t else (x.ag - x.hg) for x in rows.itertuples())
                    return gd / len(rows)
                om = sum(ovr.values()) / len(ovr) if ovr else 75   # 승격팀 등 OVR 없으면 리그 평균(같은 경기로 비교)
                v1 = mc.win_prob(ovr.get(r["home"]) or om, ovr.get(r["away"]) or om, gdpg(r["home"]), gdpg(r["away"]))
                if v1:
                    res["v1"].append((v1, out))
            if "v2" in which:
                st = pm.build_state(before, ovr, params)
                v2 = pm.predict(st, r["home"], None, r["away"], params)
                if v2:
                    res["v2"].append((v2, out))
    return {k: _metrics(v) for k, v in res.items()}


def v3_inputs(data: dict) -> dict:
    """v3 입력 — 경기 날짜 아침의 팀 Elo(src/team_elo.py, 25/26 부터 전 대회 결과) · 선발 XI 전력 손실.

    결장 손실은 과거 부상자 명단이 없어서 '실제 선발 XI 평균 OVR 이 그 팀 베스트 11 평균보다 낮은 만큼'으로 대신 잰다
    (로테이션도 섞이고 선발은 경기 직전에야 알려져 계수가 실제보다 클 수 있다 → 운영에선 부상·출장정지 명단으로만 쓴다)."""
    import league_level  # noqa: PLC0415
    import team_elo as te  # noqa: PLC0415
    from leagues import SEASON_START  # noqa: PLC0415
    seasons = [f"{y}_{y + 1}" for y in (SEASON_START - 1, SEASON_START)]
    frames = []
    for se in seasons:
        fr = {}
        for lg in LEAGUES:
            fp = data_path("schedule_full", lg, season=se)
            if fp.exists():
                fr[lg] = pd.read_csv(fp, dtype={"event_id": str})
        frames.append(te.matches_from(fr))
    ms = pd.concat(frames, ignore_index=True).drop_duplicates("event_id").sort_values(["date", "event_id"])
    dates = {str(r["date"]) for mt, _ in data.values() for _, r in mt.iterrows()}
    _, snaps = te.run(ms, {lg: te.league_base(league_level.level(lg)) for lg in LEAGUES}, dates)
    # 선발 XI 손실
    sys.path.insert(0, str(ROOT))
    from api.services.player_data import player_frame  # noqa: PLC0415
    miss: dict = {}
    for lg in data:
        pf = player_frame(lg)
        lu_p = data_path("espn_lineups", lg)
        if pf is None or not lu_p.exists():
            continue
        import player_names as pn  # noqa: PLC0415
        lu = pn.read_lineup_csv(lu_p, ["squad", "event_id", "starter", "player"])
        lu = lu[pd.to_numeric(lu["starter"].astype(str).str.lower().map({"true": 1, "false": 0, "1": 1, "0": 0}), errors="coerce") == 1]
        ovr = {(str(s_), str(p_)): float(o) for s_, p_, o in zip(pf["squad"], pf["player"], pf["_ovr"]) if o == o}
        best = {}
        for t, g in pf.groupby("squad"):
            v = sorted(pd.to_numeric(g["_ovr"], errors="coerce").dropna(), reverse=True)[:11]
            best[str(t)] = sum(v) / len(v) if v else None
        for (eid, sq), g in lu.groupby(["event_id", "squad"]):
            vals = [ovr[(str(sq), str(p_))] for p_ in g["player"] if (str(sq), str(p_)) in ovr]
            if len(vals) >= 8 and best.get(str(sq)):
                miss[(str(eid).replace(".0", ""), str(sq))] = max(0.0, best[str(sq)] - sum(vals) / len(vals))
    return {"elo": snaps, "miss": miss}


def run_v3(data: dict, inp: dict, params: dict, grid_post: list[dict], min_round: int = 2) -> list[tuple[dict, dict]]:
    """tau 는 상태 계산에, b_elo·b_av 는 예측 뒤 보정에 들어간다 → 상태는 한 번만 계산하고 보정 조합만 바꿔 본다."""
    rows = []      # (경기 기본 λ, 입력, 결과)
    for lg, (mt, ovr) in data.items():
        for i, r in mt.iterrows():
            before = mt[mt["date"] < r["date"]]
            games = pd.concat([before["home"], before["away"]]).value_counts()
            if min(games.get(r["home"], 0), games.get(r["away"], 0)) < min_round - 1:
                continue
            st = pm.build_state(before, ovr, params, asof=str(r["date"]))
            base = pm.predict(st, r["home"], None, r["away"], {**params, "b_elo": 0, "b_av": 0})
            if not base:
                continue
            snap = inp["elo"].get(str(r["date"]), {})
            ed = (snap[r["home"]] - snap[r["away"]]) if r["home"] in snap and r["away"] in snap else None
            eid = str(r["event_id"])
            x = {"elo_d": ed, "miss_h": inp["miss"].get((eid, r["home"]), 0.0), "miss_a": inp["miss"].get((eid, r["away"]), 0.0)}
            out = "H" if r["hg"] > r["ag"] else "A" if r["hg"] < r["ag"] else "D"
            rows.append((base["xg_h"], base["xg_a"], x, out))
    res = []
    for g in grid_post:
        p = {**params, **g}
        preds = []
        for lh, la, x, out in rows:
            s_ = 0.0
            if p.get("b_elo") and x["elo_d"] is not None:
                s_ += p["b_elo"] * x["elo_d"] / 400.0
            if p.get("b_av"):
                s_ -= p["b_av"] * (x["miss_h"] - x["miss_a"]) / 10.0
            preds.append((pm.summarize(min(max(lh * math.exp(s_), 0.15), 4.5), min(max(la * math.exp(-s_), 0.15), 4.5), p["rho"]), out))
        res.append((g, _metrics(preds)))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--v3", action="store_true", help="v3 입력(Elo·선발 XI 손실·최근 가중) 격자 탐색")
    ap.add_argument("--min-round", type=int, default=2)
    ap.add_argument("--ovr", choices=["current", "prev"], default="prev",
                    help="prev = 지난 시즌 팀 OVR(누설 없음, 기본) · current = 현재 OVR(시즌 결과가 섞여 OVR 모델에 유리)")
    a = ap.parse_args()
    data = _load("2025_2026" if a.ovr == "prev" else None)
    print("OVR:", a.ovr)
    print(f"리그 {len(data)} · 경기 {sum(len(v[0]) for v in data.values())}")
    print("현재 PARAMS:", pm.PARAMS)
    for k, v in run(data, pm.PARAMS, a.min_round).items():
        print(f"  {k:5} {v}")
    if a.v3:
        inp = v3_inputs(data)
        print(f"v3 입력 — Elo 스냅숏 {len(inp['elo'])}일 · 선발 XI 손실 {len(inp['miss'])}팀-경기")
        post = [{"b_elo": be, "b_av": ba} for be in (0.0, 0.15, 0.3, 0.45, 0.6) for ba in (0.0, 0.3, 0.6, 1.0)]
        allr = []
        for tau in (0.0, 90.0, 60.0, 40.0):
            for b_ovr in (0.5, 0.35, 0.2):
                for g, mres in run_v3(data, inp, {**pm.PARAMS, "tau": tau, "b_ovr": b_ovr}, post, a.min_round):
                    allr.append(({"tau": tau, "b_ovr": b_ovr, **g}, mres))
        allr.sort(key=lambda x: x[1]["logloss"])
        print("로그손실 상위:")
        for tag, mres in allr[:8]:
            print("   ", tag, mres)
        print("결장 손실 없이(b_av=0) 상위:")
        for tag, mres in [x for x in allr if x[0]["b_av"] == 0][:4]:
            print("   ", tag, mres)
        return 0
    if a.grid:
        best = None
        grid = {"k": [3, 6, 10], "b_ovr": [0.12, 0.2, 0.3], "w_goal": [0.0, 0.25, 0.5], "rho": [-0.15, -0.08, 0.0]}
        for vals in itertools.product(*grid.values()):
            p = {**pm.PARAMS, **dict(zip(grid, vals))}
            m = run(data, p, a.min_round, which=("v2",))["v2"]
            if best is None or m["logloss"] < best[1]["logloss"]:
                best = (p, m)
                print("  ↑", {k: p[k] for k in grid}, m, flush=True)
        print("최적:", best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
