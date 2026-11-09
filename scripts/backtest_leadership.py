"""리더십·결속력 백테스트 — 주장 결장·선발 연속성·핵심 선수 출전·베테랑이 'Elo + 선발 전력(OVR)' 위에 예측을 더 낫게 하나(2026-11-09).

사용자(11/04): '70 인데 주전으로 뛰고 있을 수도 있다 · 팀 결속력·리더십도 축구의 일부 · 베테랑도 중요'
→ 화면 영향력 지수(team_network.leadership)를 예측에 넣기 전에, 그런 신호가 결과를 실제로 더 설명하는지부터 본다.

방법
  기준 = 우리 Elo(그 경기 아침 값, src/team_elo) → 승·무·패(team_elo.wdl, 무승부 곡선 data/elo_draw.json)
  보정 = Elo 차 + β·(홈 − 원정 특징 차) — 특징은 모두 '그 경기 전' 정보로만
    xi_loss   선발 전력 손실: 그때까지 가장 많이 선발된 11명 평균 OVR − 이번 선발 11명 평균 OVR(OVR = 그 시즌 표 값)
    cont      선발 연속성: 직전 리그 경기와 같은 선발 수(0~11)
    core      핵심 출전: 그때까지 최다 선발 11명 중 이번 선발 수
    vets      베테랑: 선발 중 30세 이상 수
    cap_out   주장 결장: 위키 주장(완장 1번)이 그때까지 선발 60% 이상인데 이번에 선발이 아님(26/27 만 — 주장 표가 이번 시즌 것)
  학습 = 25/26 리그 경기(β 격자 탐색, 로그 손실 최소) → 검증 = 26/27 리그 경기(같은 β)
  판정 = 검증 로그 손실이 'Elo + xi_loss' 보다 0.002 이상 낮아야 '효과 있음'(경기 수천 개에서 잡음 수준이 ±0.001~0.002)

    python scripts/backtest_leadership.py            # 표 출력 + data/eval/leadership_backtest.json
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import league_level  # noqa: E402
import team_elo as te  # noqa: E402
from leagues import FULL_LEAGUES, SEASON_START, data_path  # noqa: E402
from team_network import NameIndex  # noqa: E402

OUT = ROOT / "data" / "eval" / "leadership_backtest.json"
PREV, CUR = f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"
MIN_PRIOR = 3          # 팀 리그 경기 3개 이후부터(핵심 11명·연속성이 의미 있게)
GAIN_MIN = 0.002


def _matches(season: str) -> pd.DataFrame:
    fr = {}
    for lg in FULL_LEAGUES:
        p = data_path("schedule_full", lg, season=season)
        if p.exists():
            fr[lg] = pd.read_csv(p, dtype={"event_id": str})
    return te.matches_from(fr)


def _elo_pre(seasons: list[str]) -> pd.DataFrame:
    """두 시즌을 이어 돌린 Elo — 경기마다 그 경기 아침 Elo 차(홈 어드밴티지 포함)."""
    ms = pd.concat([_matches(s) for s in seasons], ignore_index=True).sort_values(["date", "event_id"])
    _, snaps = te.run(ms, {lg: te.league_base(league_level.level(lg)) for lg in FULL_LEAGUES}, set(ms["date"]))
    ms["d"] = [te.elo_diff(snaps.get(r.date, {}), r.home, r.away) for r in ms.itertuples(index=False)]
    return ms


def _ovr_age(lg: str, season: str) -> tuple[dict, dict]:
    """(팀, 선수) → OVR · 나이 — player_frame(그 시즌 표)."""
    from api.services.player_data import player_frame  # noqa: PLC0415
    try:
        f = player_frame(lg, None if season == CUR else season)
    except Exception:  # noqa: BLE001
        return {}, {}
    keys = list(zip(f["squad"].astype(str), f["player"].astype(str)))
    ovr = {k: float(v) for k, v in zip(keys, pd.to_numeric(f["_ovr"], errors="coerce")) if v == v}
    age = {k: float(v) for k, v in zip(keys, pd.to_numeric(f["age"], errors="coerce")) if v == v}
    return ovr, age


def _captains(lg: str) -> dict:
    """팀 → 위키 주장(완장 1번) 이름 — 이번 시즌 표만 있다."""
    p = data_path("wiki_squads", lg)
    if not p.exists():
        return {}
    w = pd.read_csv(p)
    w = w[pd.to_numeric(w.get("role_rank"), errors="coerce") == 1]
    return {str(r.squad): str(r.player) for r in w.itertuples()}


def _team_features(lg: str, season: str) -> dict:
    """(event_id, 팀) → 특징 dict — 리그 경기 선발만, 날짜순으로 그 경기 전 정보만 쓴다."""
    p = data_path("espn_lineups", lg, season=season)
    if not p.exists():
        return {}
    lu = pd.read_csv(p, dtype={"event_id": str})
    lu = lu[lu["starter"].astype(str).str.lower().isin(["true", "1", "1.0"])]
    ovr, age = _ovr_age(lg, season)
    caps = _captains(lg) if season == CUR else {}
    out = {}
    for team, g in lu.groupby("squad"):
        team = str(team)
        idx = NameIndex(sorted({k[1] for k in ovr if k[0] == team}))
        name_of: dict[str, str | None] = {}

        def canon(n):
            if n not in name_of:
                name_of[n] = idx.find(n)
            return name_of[n]

        started: dict[str, int] = defaultdict(int)
        prev_xi: set[str] = set()
        n_prior = 0
        cap = caps.get(team)
        cap_idx = NameIndex([cap]) if cap else None
        is_cap: dict[str, bool] = {}
        for (eid, date), m in g.sort_values("date").groupby(["event_id", "date"], sort=False):
            xi = {str(x) for x in m["player"]}
            if len(xi) >= 10 and n_prior >= MIN_PRIOR:
                core = {p for p, _ in sorted(started.items(), key=lambda x: -x[1])[:11]}
                o_xi = [ovr.get((team, canon(p))) for p in xi]
                o_core = [ovr.get((team, canon(p))) for p in core]
                o_xi = [x for x in o_xi if x is not None]
                o_core = [x for x in o_core if x is not None]
                cap_out = None
                if cap:
                    for p in started:
                        if p not in is_cap:
                            is_cap[p] = bool(cap_idx.find(p))
                    cap_lu = next((p for p in started if is_cap[p]), None)
                    if cap_lu is not None and started[cap_lu] >= 0.6 * n_prior:
                        cap_out = 0.0 if cap_lu in xi else 1.0
                out[(str(eid), team)] = {
                    "xi_loss": (np.mean(o_core) - np.mean(o_xi)) if len(o_xi) >= 8 and len(o_core) >= 8 else 0.0,
                    "cont": float(len(xi & prev_xi)),
                    "core": float(len(xi & core)),
                    "vets": float(sum(1 for p in xi if (age.get((team, canon(p))) or 0) >= 30)),
                    "cap_out": cap_out,
                }
            for p in xi:
                started[p] += 1
            prev_xi = xi
            n_prior += 1
    return out


def _rows(season: str, elo: pd.DataFrame) -> pd.DataFrame:
    feats = {}
    for lg in FULL_LEAGUES:
        feats.update(_team_features(lg, season))
    lo, hi = (f"{season[:4]}-07-01", f"{season[5:]}-07-01")
    ms = elo[(elo["date"] >= lo) & (elo["date"] < hi) & elo["d"].notna()]
    rows = []
    for r in ms.itertuples(index=False):
        if not str(r.comp_code).endswith(".1") or r.lg_h != r.lg_a:   # 리그 경기만(컵·유럽 대회 빼고)
            continue
        fh, fa = feats.get((r.event_id, r.home)), feats.get((r.event_id, r.away))
        if not fh or not fa:
            continue
        res = "H" if r.hg > r.ag else "A" if r.hg < r.ag else "D"
        row = {"event_id": r.event_id, "date": r.date, "d": float(r.d), "res": res}
        for k in ("xi_loss", "cont", "core", "vets"):
            row[k] = fh[k] - fa[k]
        ch, ca = fh.get("cap_out"), fa.get("cap_out")
        row["cap_out"] = (ch or 0.0) - (ca or 0.0) if (ch is not None or ca is not None) else 0.0
        row["cap_known"] = int(ch is not None) + int(ca is not None)
        row["cap_any"] = int(bool(ch) or bool(ca))
        rows.append(row)
    return pd.DataFrame(rows)


def _ll(df: pd.DataFrame, betas: dict, dp: dict) -> float:
    d = df["d"].to_numpy(dtype=float).copy()
    for k, b in betas.items():
        d = d - b * df[k].to_numpy(dtype=float) if k == "xi_loss" or k == "cap_out" else d + b * df[k].to_numpy(dtype=float)
    tot = 0.0
    for di, res in zip(d, df["res"]):
        h, x, a = te.wdl(float(di), dp["draw_max"], dp["draw_width"])
        tot += -math.log(max(1e-6, {"H": h, "D": x, "A": a}[res]))
    return tot / max(1, len(df))


def _fit(df: pd.DataFrame, keys: list[str], fixed: dict, dp: dict, grid: list[float]) -> dict:
    """좌표 하강 — 키마다 격자에서 로그 손실 최소 β(다른 키는 고정)."""
    betas = {**fixed, **{k: 0.0 for k in keys}}
    for _ in range(2):
        for k in keys:
            best = min(grid, key=lambda b: _ll(df, {**betas, k: b}, dp))
            betas[k] = best
    return betas


def main() -> int:
    dp = te.draw_params()
    elo = _elo_pre([PREV, CUR])
    train, test = _rows(PREV, elo), _rows(CUR, elo)
    print(f"학습 {PREV} {len(train)}경기 · 검증 {CUR} {len(test)}경기 (주장 판단 가능 {int((test['cap_known'] > 0).sum())}경기, "
          f"주장 결장 포함 {int(test['cap_any'].sum())}경기)")
    g_ovr = [x * 4.0 for x in range(0, 16)]           # Elo 점 / OVR 1
    g_feat = [x * 2.0 for x in range(-8, 9)]          # Elo 점 / 선수 1명
    base = {"elo": {}}
    base["elo+xi_loss"] = _fit(train, ["xi_loss"], {}, dp, g_ovr)
    out = {"asof": pd.Timestamp.today().date().isoformat(), "train": PREV, "test": CUR, "n_train": len(train),
           "n_test": len(test), "gain_min": GAIN_MIN, "models": {}}
    ref = _ll(test, base["elo+xi_loss"], dp)
    for name, betas in base.items():
        out["models"][name] = {"betas": betas, "train_ll": round(_ll(train, betas, dp), 4), "test_ll": round(_ll(test, betas, dp), 4)}
    for k in ("cont", "core", "vets"):
        b = _fit(train, [k], base["elo+xi_loss"], dp, g_feat)
        out["models"][f"+{k}"] = {"betas": b, "train_ll": round(_ll(train, b, dp), 4), "test_ll": round(_ll(test, b, dp), 4)}
    # 주장 결장 — 학습 시즌 주장 표가 없어 검증 시즌 안에서 앞 절반 학습 · 뒤 절반 검증
    t = test.sort_values("date")
    half = len(t) // 2
    t1, t2 = t.iloc[:half], t.iloc[half:]
    b_cap = _fit(t1, ["cap_out"], base["elo+xi_loss"], dp, [x * 5.0 for x in range(-8, 13)])
    out["models"]["+cap_out(26/27 앞→뒤)"] = {"betas": b_cap, "train_ll": round(_ll(t1, b_cap, dp), 4),
                                            "test_ll": round(_ll(t2, b_cap, dp), 4),
                                            "ref_test_ll": round(_ll(t2, base["elo+xi_loss"], dp), 4),
                                            "n_cap_any": int(t2["cap_any"].sum())}
    # 주장 결장 경기의 실제 승점 − Elo 기대 승점(보정 없이)
    cap = test[test["cap_known"] > 0]
    res = []
    for r in cap.itertuples(index=False):
        h, x, a = te.wdl(r.d, dp["draw_max"], dp["draw_width"])
        pts_h = {"H": 3, "D": 1, "A": 0}[r.res]
        res.append({"cap_out": r.cap_out, "resid_h": pts_h - (3 * h + x)})
    rr = pd.DataFrame(res)
    if not rr.empty:
        out["cap_resid"] = {str(k): {"n": int(len(v)), "home_pts_minus_exp": round(float(v["resid_h"].mean()), 3)}
                            for k, v in rr.groupby("cap_out")}
    print(f"{'모델':28s} {'β':40s} {'학습 LL':>8s} {'검증 LL':>8s} {'개선':>7s}")
    for name, m in out["models"].items():
        r0 = m.get("ref_test_ll", ref)
        gain = (r0 - m["test_ll"]) if name != "elo" else 0.0
        m["gain_vs_xi"] = round(gain, 4)
        m["verdict"] = "효과 있음" if gain >= GAIN_MIN else "효과 없음"
        bt = ", ".join(f"{k}={v:g}" for k, v in m["betas"].items()) or "-"
        print(f"{name:28s} {bt:40s} {m['train_ll']:8.4f} {m['test_ll']:8.4f} {gain:+7.4f}")
    if "cap_resid" in out:
        print("주장 결장 여부별(홈 − 원정 결장 차) 홈 실제 승점 − Elo 기대:", out["cap_resid"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[OK] {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
