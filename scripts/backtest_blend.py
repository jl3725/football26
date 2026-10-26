"""예측 모델 v3 ↔ Elo 기준 — 같은 경기, 경기 전 데이터만으로 비교하고 섞는 비율·온도 보정을 정한다(2026-10-26).

PREDICTION LEAGUE 141경기에서 Elo 기준(우리 Elo 만, src/team_elo.wdl)이 모델 v3 보다 브라이어가 좋았다(0.58 vs 0.609) —
모델이 확률을 너무 뾰족하게 내는지(과신) 큰 표본으로 확인한다.
  리그 안  이번 시즌 match_stats 전 경기(지난 시즌 팀 OVR · 그 경기 아침 Elo · 선발 XI 손실 = scripts/backtest_model.v3_inputs)
  리그 간  두 시즌 유럽대회(scripts/backtest_cross.samples · 운영과 같은 식)
비교: v3 · elo · 섞기 w·v3 + (1−w)·elo · 온도 보정 p^(1/T) — 날짜 앞쪽 절반으로 정하고 뒤쪽 절반에서 잰다(과적합 방지).

2026-10-26 결과 — 보정 불필요, 운영 모델 그대로:
  리그 안 945경기(뒤쪽 473): v3 로그손실 0.9808 · elo 0.9838 · 섞기 최적 w=1.0(이득 없음) · 온도 T=1.1 −0.0014(무시할 수준)
  리그 간 226경기(뒤쪽 113): v3 0.8584 · elo 0.939 · 섞기·온도 이득 없음
  성적표 141경기에서 Elo 가 앞선 것(브라이어 0.58 vs 0.609)은 11일 표본의 흔들림으로 본다. 표본이 쌓이면 다시 재 볼 것.

    python scripts/backtest_blend.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]

import predict_model as pm  # noqa: E402
import team_elo as te  # noqa: E402

WS = [i / 10 for i in range(11)]
TS = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.6]


def _norm(p: dict) -> dict:
    s = p["h"] + p["d"] + p["a"]
    return {k: p[k] / s for k in ("h", "d", "a")}


def blend(m: dict, e: dict, w: float) -> dict:
    return {k: w * m[k] + (1 - w) * e[k] for k in ("h", "d", "a")}


def temper(m: dict, t: float) -> dict:
    return _norm({k: max(1e-9, m[k]) ** (1.0 / t) for k in ("h", "d", "a")})


def metrics(rows: list[tuple[dict, str]]) -> dict:
    ll = br = hit = 0.0
    for p, res in rows:
        q = {"H": p["h"], "D": p["d"], "A": p["a"]}
        ll -= math.log(max(1e-6, q[res]))
        br += sum((q[k] - (k == res)) ** 2 for k in q)
        hit += max(q, key=q.get) == res
    n = max(1, len(rows))
    return {"n": len(rows), "logloss": round(ll / n, 4), "brier": round(br / n, 4), "acc": round(hit / n, 3)}


def league_rows() -> list[dict]:
    import backtest_model as bm  # noqa: PLC0415
    data = bm._load("2025_2026")
    inp = bm.v3_inputs(data)
    dp = te.draw_params()
    p = pm.PARAMS
    out = []
    for lg, (mt, ovr) in data.items():
        for _, r in mt.iterrows():
            before = mt[mt["date"] < r["date"]]
            games = __import__("pandas").concat([before["home"], before["away"]]).value_counts()
            if min(games.get(r["home"], 0), games.get(r["away"], 0)) < 1:
                continue
            snap = inp["elo"].get(str(r["date"]), {})
            if r["home"] not in snap or r["away"] not in snap:
                continue
            st = pm.build_state(before, ovr, p, asof=str(r["date"]))
            eid = str(r["event_id"])
            x = {"elo_d": snap[r["home"]] - snap[r["away"]], "miss_h": inp["miss"].get((eid, r["home"]), 0.0),
                 "miss_a": inp["miss"].get((eid, r["away"]), 0.0)}
            v3 = pm.predict(st, r["home"], None, r["away"], p, x)
            if not v3:
                continue
            eh, ed, ea = te.wdl(x["elo_d"] + te.HFA, **dp)
            out.append({"seg": "league", "date": str(r["date"]), "res": "H" if r["hg"] > r["ag"] else "A" if r["hg"] < r["ag"] else "D",
                        "m": {"h": v3["h"], "d": v3["d"], "a": v3["a"]}, "e": {"h": eh, "d": ed, "a": ea}})
    return out


def cross_rows() -> list[dict]:
    import backtest_cross as bc  # noqa: PLC0415
    df = bc.samples()
    dp = te.draw_params()
    out = []
    for _, x in df.iterrows():
        if not x["elo_d"]:
            continue
        pr = bc.predict_row(x, bc.CURRENT)
        eh, ed, ea = te.wdl(float(x["elo_d"]) + te.HFA, **dp)
        out.append({"seg": "cross", "date": str(x["date"]), "res": x["res"], "m": {"h": pr["h"], "d": pr["d"], "a": pr["a"]},
                    "e": {"h": eh, "d": ed, "a": ea}})
    return out


def best_w(rows: list[dict]) -> float:
    return min(WS, key=lambda w: metrics([(blend(r["m"], r["e"], w), r["res"]) for r in rows])["logloss"])


def best_t(rows: list[dict]) -> float:
    return min(TS, key=lambda t: metrics([(temper(r["m"], t), r["res"]) for r in rows])["logloss"])


def report(seg: str, rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: r["date"])
    half = len(rows) // 2
    train, test = rows[:half], rows[half:]
    w, t = best_w(train), best_t(train)
    res = {"n": len(rows), "train_until": train[-1]["date"] if train else "", "w_train": w, "t_train": t,
           "test": {"v3": metrics([(r["m"], r["res"]) for r in test]), "elo": metrics([(r["e"], r["res"]) for r in test]),
                    f"blend w={w}": metrics([(blend(r["m"], r["e"], w), r["res"]) for r in test]),
                    f"temper T={t}": metrics([(temper(r["m"], t), r["res"]) for r in test])},
           "w_all": best_w(rows), "t_all": best_t(rows)}
    print(f"\n[{seg}] 경기 {len(rows)} · 앞쪽 {len(train)}경기(~{res['train_until']})로 정함 → w={w} · T={t}")
    for k, v in res["test"].items():
        print(f"   뒤쪽 {len(test)}경기  {k:14} 로그손실 {v['logloss']}  브라이어 {v['brier']}  적중 {v['acc']}")
    print(f"   전체로 정하면 w={res['w_all']} · T={res['t_all']}")
    return res


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lg, cr = league_rows(), cross_rows()
    report("리그 안", lg)
    report("리그 간(유럽대회)", cr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
