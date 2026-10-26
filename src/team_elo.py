"""
팀 Elo — 리그·국내컵·유럽대회 결과로 직접 계산(예측 모델 v3 입력, 2026-10-19).

ClubElo 는 과거 날짜 API 가 응답하지 않아 백테스트를 못 한다 → 우리 일정 파일(schedule_full, 25/26 부터)로 같은 방식의
Elo 를 직접 돌린다. 여러 시즌 결과가 쌓인 '팀 실적' 축이라 선수 평점 기반 팀 OVR 과 서로 보완된다.
- 시작(첫 시즌 7/1): 리그 기본값 1500 + (리그 레벨 − 80) × 10(EPL 1700 · 벨기에 1585). 처음 보는 팀은 그 리그 기본값 − 80
  (승격팀), 우리 리그 밖 유럽대회 상대는 1500.
- 갱신: eloratings.net 방식 — K 20(유럽대회 25) × 골차 배수(1 · 1.5 · (11+N)/8), 홈 어드밴티지 HFA.
- 결과 행: 일정 파일의 팀 기준 두 줄(우리 리그끼리)을 event_id 로 한 경기로 합친다.
"""
from __future__ import annotations

import pandas as pd

K_LEAGUE, K_EURO, HFA = 20.0, 25.0, 65.0
START_BASE = 1500.0


def league_base(level: float) -> float:
    return START_BASE + (float(level) - 80.0) * 10.0


def matches_from(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{리그: schedule_full} → 끝난 경기 한 경기 한 줄 [event_id, date, home, away, hg, ag, comp_code, lg_h, lg_a]."""
    rows: dict[str, dict] = {}
    for lg, sch in frames.items():
        if sch is None or sch.empty:
            continue
        s = sch[sch["status"].astype(str) == "completed"]
        for r in s.itertuples(index=False):
            eid = str(r.event_id).replace(".0", "")
            gf, ga = pd.to_numeric(r.gf, errors="coerce"), pd.to_numeric(r.ga, errors="coerce")
            if not eid or gf != gf or ga != ga:
                continue
            home = r.home_away == "H"
            x = rows.setdefault(eid, {"event_id": eid, "date": str(r.date)[:10], "comp_code": str(r.comp_code),
                                      "home": None, "away": None, "hg": None, "ag": None, "lg_h": None, "lg_a": None})
            me, opp = str(r.squad), str(r.opponent)
            if home:
                x.update(home=me, lg_h=lg, hg=int(gf), ag=int(ga))
                x["away"] = x["away"] or opp
            else:
                x.update(away=me, lg_a=lg, hg=int(ga), ag=int(gf))
                x["home"] = x["home"] or opp
    df = pd.DataFrame(rows.values())
    if df.empty:
        return df
    return df.dropna(subset=["home", "away", "hg", "ag"]).sort_values(["date", "event_id"]).reset_index(drop=True)


def _gmult(d: int) -> float:
    d = abs(d)
    return 1.0 if d <= 1 else 1.5 if d == 2 else (11.0 + d) / 8.0


def expected(r_h: float, r_a: float, neutral: bool = False) -> float:
    return 1.0 / (1.0 + 10 ** (-(r_h + (0 if neutral else HFA) - r_a) / 400.0))


def run(ms: pd.DataFrame, bases: dict[str, float], snap_dates: set[str] | None = None) -> tuple[dict, dict]:
    """경기 표를 날짜순으로 돌려 최종 Elo 와 (요청한 날짜 아침 기준) 스냅숏 {날짜: {팀: Elo}}.
    bases: {리그: 기본값}. 팀 리그는 경기 행의 lg_h/lg_a 로 안다."""
    elo: dict[str, float] = {}
    seen_lg: dict[str, str] = {}
    snaps: dict[str, dict] = {}
    want = sorted(snap_dates or [])
    wi = 0
    first_season_end = None
    for r in ms.itertuples(index=False):
        while wi < len(want) and want[wi] <= r.date:
            snaps[want[wi]] = dict(elo)
            wi += 1
        if first_season_end is None:
            first_season_end = f"{int(r.date[:4]) + (1 if r.date[5:7] >= '07' else 0)}-07-01"
        for team, lg in ((r.home, r.lg_h), (r.away, r.lg_a)):
            if team not in elo:
                base = bases.get(lg, START_BASE) if lg else START_BASE
                # 첫 시즌 뒤에 처음 보는 우리 리그 팀 = 승격팀 → 기본값보다 낮게
                elo[team] = base - (80.0 if lg and r.date >= first_season_end else 0.0)
            if lg:
                seen_lg[team] = lg
        h, a = elo[r.home], elo[r.away]
        we = expected(h, a)
        w = 1.0 if r.hg > r.ag else 0.5 if r.hg == r.ag else 0.0
        k = (K_EURO if str(r.comp_code).startswith("uefa.") else K_LEAGUE) * _gmult(int(r.hg) - int(r.ag))
        elo[r.home] = h + k * (w - we)
        elo[r.away] = a - k * (w - we)
    while wi < len(want):
        snaps[want[wi]] = dict(elo)
        wi += 1
    return elo, snaps


def elo_diff(elo: dict, home: str, away: str) -> float | None:
    """홈 어드밴티지 포함 Elo 차(홈 − 원정). 한쪽이라도 없으면 None."""
    if home not in elo or away not in elo:
        return None
    return elo[home] + HFA - elo[away]


def win_prob(d: float) -> float:
    return 1.0 / (1.0 + 10 ** (-d / 400.0))


# ── Elo 만으로 승·무·패 — 홈 PREDICTION LEAGUE 의 'ELO' 기준 예측(2026-10-26) ─────────────────────────────────
# ClubElo 가 10/25 부터 Cloudflare 봇 확인·API 502 로 막혀 같은 방식의 단순 기준을 우리 Elo 로 낸다. 이길 기대치
# E = 승 + 무/2 는 Elo 식 그대로 지키고, 무승부는 두 팀 차이가 작을수록 크게(종 모양 곡선 draw_max·exp(−(d/width)²)).
# 곡선 두 값은 **지난 시즌 경기로만** 맞춘다(그 경기 아침 Elo) — 이번 시즌 경기를 소급 예측해도 미래 정보가 안 섞인다.
DRAW_JSON = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "elo_draw.json"
DEFAULT_DRAW = {"draw_max": 0.29, "draw_width": 420.0}


def wdl(d: float, draw_max: float, draw_width: float) -> tuple[float, float, float]:
    """홈 어드밴티지를 넣은 Elo 차 → (홈 승, 무, 원정 승)."""
    import math  # noqa: PLC0415
    e = win_prob(d)
    pdraw = min(draw_max * math.exp(-(d / draw_width) ** 2), 1.96 * min(e, 1.0 - e))
    return e - pdraw / 2.0, pdraw, 1.0 - e - pdraw / 2.0


def fit_draw(samples: list[tuple[float, str]]) -> dict:
    """[(Elo 차, 'H'|'D'|'A')] → 로그 손실이 가장 낮은 무승부 곡선(격자)."""
    import math  # noqa: PLC0415
    best = None
    for dm in [x / 100 for x in range(18, 37)]:
        for w in range(150, 801, 25):
            ll = 0.0
            for d, res in samples:
                ph, pd_, pa = wdl(d, dm, float(w))
                ll -= math.log(max(1e-6, {"H": ph, "D": pd_, "A": pa}[res]))
            if best is None or ll < best[0]:
                best = (ll, dm, float(w))
    n = len(samples)
    return {"draw_max": best[1], "draw_width": best[2], "n": n, "logloss": round(best[0] / max(1, n), 4),
            "draw_actual": round(sum(r == "D" for _, r in samples) / max(1, n), 3)}


def draw_params() -> dict:
    import json  # noqa: PLC0415
    try:
        d = json.loads(DRAW_JSON.read_text(encoding="utf-8"))
        return {"draw_max": float(d["draw_max"]), "draw_width": float(d["draw_width"])}
    except (OSError, ValueError, KeyError):
        return dict(DEFAULT_DRAW)


def to_log_lambda(d: float) -> float:
    """Elo 차 → 기대 득점 로그 배수 단위(400 Elo = 1)."""
    return d / 400.0 if d == d else 0.0



def fit_from_files(season_start: int | None = None) -> dict:
    """지난 시즌 일정 파일로 Elo 를 돌려(시즌 첫 3개월은 Elo 가 자리 잡는 기간이라 뺌) 무승부 곡선을 맞춘다."""
    import datetime as dt  # noqa: PLC0415
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import league_level  # noqa: PLC0415
    from leagues import LEAGUES, SEASON_START, data_path  # noqa: PLC0415
    s0 = season_start or SEASON_START
    prev = f"{s0 - 1}_{s0}"
    fr = {}
    for lg in LEAGUES:
        p = data_path("schedule_full", lg, season=prev)
        if p.exists():
            fr[lg] = pd.read_csv(p, dtype={"event_id": str})
    ms = matches_from(fr).sort_values(["date", "event_id"])
    lo, hi = f"{s0 - 1}-10-01", f"{s0}-07-01"
    fit_rows = ms[(ms["date"] >= lo) & (ms["date"] < hi)]
    _, snaps = run(ms, {lg: league_base(league_level.level(lg)) for lg in LEAGUES}, set(fit_rows["date"]))
    samples = []
    for r in fit_rows.itertuples(index=False):
        snap = snaps.get(r.date, {})
        if r.home in snap and r.away in snap:
            samples.append((snap[r.home] + HFA - snap[r.away], "H" if r.hg > r.ag else "A" if r.hg < r.ag else "D"))
    out = fit_draw(samples)
    out.update({"fit_on": f"{lo}~{hi}", "asof": dt.date.today().isoformat(),
                "note": "Elo 만으로 승·무·패(team_elo.wdl) — 무승부 곡선은 지난 시즌 경기로만 맞춤(이번 시즌 소급 예측에 미래 정보 없음)"})
    return out


if __name__ == "__main__":
    import json as _json
    import sys as _sys
    res = fit_from_files()
    if "--write" in _sys.argv:
        DRAW_JSON.write_text(_json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"elo_draw: draw_max {res['draw_max']} · width {res['draw_width']} · 경기 {res['n']} · 로그손실 {res['logloss']} "
          f"· 실제 무승부 {res['draw_actual']} ({res['fit_on']})")
