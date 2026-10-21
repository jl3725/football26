"""우리 승부 예측 모델 v2 — 팀 공격·수비 강도(xG 중심) × 전력(OVR) 사전값 → 포아송 + Dixon-Coles(2026-10-15).

예전 v1(match_center.win_prob)은 'OVR 차이 + 골득실'만 써서 화면에서 뺐다. v2 는 경기 내용(xG)으로 강도를 잡는다.

  1) 리그 경기마다 팀의 경기당 기회 창출·허용을 리그 평균 대비 비율로(5대 리그 = Understat xG, 그 외 = 슈팅×리그 득점 전환율)
     실제 득실도 w_goal 만큼 섞는다(결정력·운은 일부만 지속된다)
  2) 시즌 초엔 표본이 적으니 선수 평점 기반 팀 OVR 사전값 쪽으로 n/(n+k) 수축
  3) 기대 득점 λ = 리그 홈·원정 평균 × exp(공격 + 상대 수비) → 포아송 + Dixon-Coles(저득점 무승부 보정)
  4) 다른 리그끼리(유럽대회)는 OVR 차이(절대 척도)를 크게, 리그 안 지표는 덜 반영

파라미터는 scripts/backtest_model.py 로 이번 시즌 경기를 '그 경기 전 데이터만으로' 예측해 고른다(로그 손실 최소).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

# 2026-10-15 백테스트(scripts/backtest_model.py, 리그 435경기) — 지난 시즌 OVR 로그손실 0.968 · 현재 OVR 0.926
# (옛 v1 0.980 · 0.939, 기준선 1.110). 시즌 초라 실제 골이 xG 보다 잘 맞아 w_goal 0.75 — 표본이 쌓이면 다시 탐색
# v3(2026-10-19, --v3, 리그 488경기·지난 시즌 OVR): v2 0.970 / 적중 51.6% → 최근 40일 가중 + 자체 Elo(25/26~ 전 대회 결과)
# + OVR 사전값 0.35 = 0.958 / 53.9%, + 결장 손실 = 0.954. 결장 손실은 과거 부상 명단이 없어 '실제 선발 XI 손실'로 잰 대리값이라
# 최적(0.6)의 절반만 쓴다(운영 입력은 부상·출장정지 명단 — src/fetch_fotmob_injuries.py + TM).
# 리그 간(유럽대회) 계수 — 2026-10-21 scripts/backtest_cross.py(리그 간 215경기: 25/26 184 · 26/27 31) 로 다시 정함.
# 예전(b_cross 0.6 · w_cross_form 0.25 · 기본 득점 1.45/1.15 · rho −0.08)은 무승부를 23% 로 봤다(실제 14%).
# 같은 날 검수로 바로잡음: OVR 차는 '절대 전력'(베스트 XI 선수 OVR 만 — api._club_abs)으로 운영·백테스트 같은 척도.
# (화면 팀 OVR 은 리그 안 순위인 폼이 섞여 시즌 초엔 리그 간 격차가 시즌 말의 2배였다.) 그 척도에서 25/26 로 고른 계수:
# OVR 차 0.6 · Elo 0.2(리그 간 전용 — 리그 경기 b_elo 0.45 와 따로) · 리그 폼 0.15 · rho 0 · 기본 득점·무승부 배수 = 학습(model_cross.json)
# → 26/27(지난 시즌 OVR — 누설 없음, 31경기·무승부 2) 로그 손실 예전 계수 0.818 → 0.771 · 적중 64.5% → 67.7%,
#   두 시즌 215경기 0.880 → 0.842(model_cross.json). 표본이 작아 11월 재보정 때 다시 본다.
PARAMS = {"k": 10.0, "b_ovr": 0.35, "w_goal": 0.75, "rho": -0.08, "b_cross": 0.6, "w_cross_form": 0.15, "adjust": True,
          "cross_rho": 0.0, "cross_dk": 0.78, "cross_b_elo": 0.2,
          # v3(2026-10-19) — 백테스트로 정함(scripts/backtest_model.py --v3): Elo 차(400 = 로그 배수 1) · 결장 전력 손실(OVR 10 = 1) ·
          # 최근 경기 가중(tau 일 반감 아님, exp(−경과일/tau)). 0 이면 끔.
          "b_elo": 0.45, "b_av": 0.3, "tau": 40.0}
# 다른 리그끼리(유럽대회): 2026-10 리그 간 17경기로는 표본이 작아 방향만 반영(OVR 차이↑·리그 안 폼↓) — 예측 기록이 쌓이면 재조정
MU_FALLBACK = (1.45, 1.15)   # 리그 표본이 적을 때 홈·원정 기본 기대 득점
MU_CROSS = (1.72, 1.19)      # 리그 간 기본 득점(25/26 로 보정 — 예측 평균 득점 = 실제 1.81/1.31) — data/model_cross.json 이 있으면 그 학습값
_CROSS_CAL: dict = {}


def cross_calibration() -> dict:
    """리그 간 보정값 {mu_h, mu_a, dk, n, asof} — scripts/backtest_cross.py --write 가 매일 지난 리그 간 경기로 다시 잰다.
    파일이 없거나 표본이 적으면 기본값(MU_CROSS · PARAMS['cross_dk'])."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    p = Path(__file__).resolve().parent.parent / "data" / "model_cross.json"
    try:
        key = p.stat().st_mtime
    except OSError:
        return {}
    if _CROSS_CAL.get("key") != key:
        try:
            _CROSS_CAL.update(key=key, val=json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            _CROSS_CAL.update(key=key, val={})
    v = _CROSS_CAL.get("val") or {}
    return v if (v.get("n") or 0) >= 30 else {}


def cross_lambdas(fh: float, fa: float, d_ovr: float, p: dict = PARAMS, mu: tuple | None = None) -> tuple[float, float]:
    """리그 간 기대 득점(Elo·결장 보정 전) — 리그 안 공격·수비(fh = 홈 공격 + 원정 수비)는 덜, OVR 차(d_ovr = (홈 − 원정)/10)는 크게.
    운영(predict)과 백테스트(scripts/backtest_cross.py)가 같은 식을 쓴다."""
    m = mu or MU_CROSS
    f = p["w_cross_form"]
    return m[0] * math.exp(f * fh + p["b_cross"] * d_ovr), m[1] * math.exp(f * fa - p["b_cross"] * d_ovr)
MODEL_VERSION = "v3"          # 예측 기록(scripts/log_predictions.py model_ver) — 성적표가 버전별로 나눠 본다


@dataclass
class LeagueState:
    mu_h: float
    mu_a: float
    g_avg: float          # 팀-경기당 평균 득점
    x_avg: float          # 팀-경기당 평균 '기회'(xG 또는 환산 슈팅)
    teams: dict           # team -> {"n", "att", "def"} (로그 배수, 0 = 리그 평균)
    ovr_mean: float


def league_matches(ms: pd.DataFrame) -> pd.DataFrame:
    """match_stats(팀 기준 행) → 리그 경기 한 경기 한 줄(홈 기준)."""
    if ms is None or ms.empty:
        return pd.DataFrame(columns=["event_id", "date", "home", "away", "hg", "ag", "hxg", "axg", "hsh", "ash"])
    lg = ms[ms["comp_code"].astype(str).str.endswith(".1") & (ms["home_away"] == "H")].copy()
    col = lambda c: pd.to_numeric(lg[c], errors="coerce") if c in lg.columns else pd.Series([float("nan")] * len(lg), index=lg.index)  # noqa: E731
    out = pd.DataFrame({"event_id": lg["event_id"].astype(str), "date": lg["date"].astype(str).str[:10],
                        "home": lg["squad"], "away": lg["opponent"], "hg": col("gf"), "ag": col("ga"),
                        "hxg": col("xg"), "axg": col("xga"), "hsh": col("shots"), "ash": col("opp_shots")})
    return out.dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)


def build_state(mt: pd.DataFrame, ovr: dict, p: dict = PARAMS, asof: str | None = None) -> LeagueState:
    """경기 표(그 시점까지) + 팀 OVR → 팀별 공격·수비 로그 배수.
    p['tau'] > 0 이면 최근 경기에 무게(exp(−경과일/tau), asof 기준 — 없으면 마지막 경기일)."""
    n = len(mt)
    w_lg = n / (n + 20.0)
    mu_h = w_lg * (mt["hg"].mean() if n else 0) + (1 - w_lg) * MU_FALLBACK[0]
    mu_a = w_lg * (mt["ag"].mean() if n else 0) + (1 - w_lg) * MU_FALLBACK[1]
    g_avg = (mu_h + mu_a) / 2
    has_xg = n > 0 and mt["hxg"].notna().mean() > 0.5
    if has_xg:
        x_avg = pd.concat([mt["hxg"], mt["axg"]]).mean()
    else:
        sh = pd.concat([mt["hsh"], mt["ash"]]).dropna()
        conv = (g_avg / sh.mean()) if len(sh) and sh.mean() > 0 else 0.1
        x_avg = g_avg
    ovr_vals = [v for v in ovr.values() if v]
    ovr_mean = sum(ovr_vals) / len(ovr_vals) if ovr_vals else 75.0

    # 경기별 관측 '기회'(xG·환산 슈팅)와 실제 골을 섞은 값 — 홈·원정 각각
    last_date = str(mt["date"].max()) if n else ""
    obs = []
    for r in mt.itertuples(index=False):
        def chance(x, s, g):
            if has_xg and x == x:
                return x
            if not has_xg and s == s:
                return s * conv
            return g
        ch, ca = chance(r.hxg, r.hsh, r.hg), chance(r.axg, r.ash, r.ag)
        oh = (1 - p["w_goal"]) * ch / x_avg * g_avg + p["w_goal"] * r.hg   # 골 척도로 맞춘 관측 득점
        oa = (1 - p["w_goal"]) * ca / x_avg * g_avg + p["w_goal"] * r.ag
        obs.append((r.home, r.away, oh, oa, _recency(r.date, asof or last_date, p.get("tau") or 0.0)))
    teams_all = set(ovr) | {t for o in obs for t in o[:2]}
    prior = {}
    for t in teams_all:
        z = ((ovr.get(t) or ovr_mean) - ovr_mean) / 10.0
        prior[t] = (p["b_ovr"] * z, -p["b_ovr"] * z)
    n_of = {t: 0.0 for t in teams_all}             # 최근 가중 경기 수(수축 강도)
    cnt = {t: 0 for t in teams_all}                 # 실제 경기 수(화면 '표본 적음' 안내)
    for h, a, _oh, _oa, wt in obs:
        n_of[h] += wt
        n_of[a] += wt
        cnt[h] += 1
        cnt[a] += 1
    att = {t: prior[t][0] for t in teams_all}
    dfn = {t: prior[t][1] for t in teams_all}
    # 상대 강도 보정 — 공격 = 관측 득점 / (리그 평균 × 상대 수비 배수) 의 비율을 반복 추정(약팀 상대 xG 를 덜 쳐준다)
    for _ in range(8 if p.get("adjust", True) else 1):
        o_a = {t: 0.0 for t in teams_all}; e_a = {t: 0.0 for t in teams_all}
        o_d = {t: 0.0 for t in teams_all}; e_d = {t: 0.0 for t in teams_all}
        for h, a, oh, oa, wt in obs:
            adj = p.get("adjust", True)
            o_a[h] += wt * oh; e_a[h] += wt * mu_h * (math.exp(dfn[a]) if adj else 1.0)
            o_a[a] += wt * oa; e_a[a] += wt * mu_a * (math.exp(dfn[h]) if adj else 1.0)
            o_d[h] += wt * oa; e_d[h] += wt * mu_a * (math.exp(att[a]) if adj else 1.0)
            o_d[a] += wt * oh; e_d[a] += wt * mu_h * (math.exp(att[h]) if adj else 1.0)
        for t in teams_all:
            k = n_of[t]
            w = k / (k + p["k"])
            ra = math.log(max(0.15, o_a[t] / e_a[t])) if e_a[t] else 0.0
            rd = math.log(max(0.15, o_d[t] / e_d[t])) if e_d[t] else 0.0
            att[t] = w * ra + (1 - w) * prior[t][0]
            dfn[t] = w * rd + (1 - w) * prior[t][1]
    teams = {t: {"n": cnt[t], "n_eff": round(n_of[t], 1), "att": att[t], "def": dfn[t], "ovr": ovr.get(t) or ovr_mean}
             for t in teams_all}
    return LeagueState(mu_h, mu_a, g_avg, x_avg, teams, ovr_mean)


def _recency(date, asof: str, tau: float) -> float:
    if not tau or not asof:
        return 1.0
    try:
        d = (pd.Timestamp(asof[:10]) - pd.Timestamp(str(date)[:10])).days
    except (ValueError, TypeError):
        return 1.0
    return math.exp(-max(0, d) / tau)


def _pois(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(lh: float, la: float, rho: float, n: int = 10) -> list[list[float]]:
    """Dixon-Coles — 0-0·1-0·0-1·1-1 확률을 rho 로 보정(실제 축구는 저득점 무승부가 포아송보다 잦다)."""
    m = [[_pois(lh, i) * _pois(la, j) for j in range(n)] for i in range(n)]
    m[0][0] *= 1 - lh * la * rho
    m[0][1] *= 1 + lh * rho
    m[1][0] *= 1 + la * rho
    m[1][1] *= 1 - rho
    t = sum(map(sum, m))
    return [[v / t for v in row] for row in m]


def summarize(lh: float, la: float, rho: float, dk: float = 1.0) -> dict:
    """dk = 무승부 배수(리그 간 경기 — 포아송이 무승부를 실제보다 많이 본다). 대각선(무승부 스코어)에 곱하고 다시 정규화."""
    m = score_matrix(lh, la, rho)
    if dk != 1.0:
        for i in range(len(m)):
            m[i][i] *= dk
        t = sum(map(sum, m))
        m = [[v / t for v in row] for row in m]
        # 표시 기대 득점도 보정한 행렬의 평균으로(무승부를 줄이면 득점 기대가 조금 오른다)
        lh = sum(i * v for i, row in enumerate(m) for v in row)
        la = sum(j * v for row in m for j, v in enumerate(row))
    n = len(m)
    ph = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    pd_ = sum(m[i][i] for i in range(n))
    pa = 1 - ph - pd_
    i, j = max(((i, j) for i in range(n) for j in range(n)), key=lambda t: m[t[0]][t[1]])
    btts = 1 - sum(m[0]) - sum(m[i][0] for i in range(n)) + m[0][0]
    o25 = 1 - sum(m[i][j] for i in range(n) for j in range(n) if i + j <= 2)
    return {"h": round(ph, 3), "d": round(pd_, 3), "a": round(pa, 3), "xg_h": round(lh, 2), "xg_a": round(la, 2),
            "score": f"{i}-{j}", "btts": round(btts, 3), "o25": round(o25, 3)}


def predict(st_h: LeagueState, home: str, st_a: LeagueState | None, away: str, p: dict = PARAMS,
            extra: dict | None = None) -> dict | None:
    """같은 리그면 st_a=None. 다른 리그(유럽대회)면 각자 리그 상태로.
    extra(v3): elo_d = 홈 Elo − 원정 Elo(홈 어드밴티지 제외 — 리그 홈·원정 평균이 이미 담는다),
    miss_h·miss_a = 결장(부상·출장정지)으로 빠진 베스트 XI 전력(OVR 점수, 0 이상)."""
    th = st_h.teams.get(home)
    ta = (st_a or st_h).teams.get(away)
    if not th or not ta:
        return None
    cross = not (st_a is None or st_a is st_h)
    if not cross:
        lh = st_h.mu_h * math.exp(th["att"] + ta["def"])
        la = st_h.mu_a * math.exp(ta["att"] + th["def"])
        rho, dk = p["rho"], 1.0
    else:
        # 다른 리그 — 리그 안 상대 지표는 덜, OVR(리그 보정된 절대 척도) 차이는 크게. 기본 득점·무승부 배수는 학습값
        cal = cross_calibration()
        mu = (cal["mu_h"], cal["mu_a"]) if cal.get("mu_h") else MU_CROSS
        # OVR 차 — extra['ovr_d'](절대 전력, 폼 제외 — api._club_abs)가 있으면 그것, 없으면 리그 상태의 팀 OVR
        d_ovr = (extra or {}).get("ovr_d")
        if d_ovr is None:
            d_ovr = (th["ovr"] - ta["ovr"]) / 10.0
        lh, la = cross_lambdas(th["att"] + ta["def"], ta["att"] + th["def"], d_ovr, p, mu)
        rho, dk = p.get("cross_rho", p["rho"]), float(cal.get("dk") or p.get("cross_dk", 1.0))
    x = extra or {}
    s = 0.0
    b_elo = p.get("cross_b_elo", p.get("b_elo")) if cross else p.get("b_elo")   # 리그 간은 따로 정한 Elo 가중
    if b_elo and x.get("elo_d") is not None:
        s += b_elo * x["elo_d"] / 400.0
    if p.get("b_av"):
        s -= p["b_av"] * ((x.get("miss_h") or 0.0) - (x.get("miss_a") or 0.0)) / 10.0
    lh, la = lh * math.exp(s), la * math.exp(-s)
    lh, la = min(max(lh, 0.15), 4.5), min(max(la, 0.15), 4.5)
    out = summarize(lh, la, rho, dk)
    out["n_h"], out["n_a"] = th["n"], ta["n"]
    if x:
        out["inputs"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in x.items() if v is not None}
    return out
