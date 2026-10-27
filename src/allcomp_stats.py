"""
전 대회(리그 + 유럽 + 국내 컵) 선수 기록 — FotMob 경기별 기록(src/fetch_fotmob_matches.py → fotmob_match_ratings_*).

2026-10-21 사용자: "리그 기준으로만 선수 스탯 계산하나요? 챔스·컵도 포함해야 데이터가 늘고 신빙성이 늘지 않을까요",
"PSG 가 지난 시즌 챔스 우승했는데 바르샤보다 많이 낮다". 리그 표(FBref·Sofascore)는 리그 경기만이라 유럽·컵 활약이
OVR 경기력·세부 지표에 들어가지 않았다(유럽은 선발 수 기반 BIG MATCH +0.7 상한뿐). 두 가지를 더한다.

1) 전 대회 평점(OVR 경기력 입력) — attach_x
   리그 밖 경기의 FotMob 평점을 같은 위치의 Sofascore 척도(rating_blend.fm_to_ss)로 바꿔, 경기마다 '상대 수준'과
   '가중'을 붙인다. ratings_v3._class_parts 가 리그 평점과 나란한 표본으로 섞는다(리그 보정과 같은 방식).
     상대 수준(EPL 평균 상대 = 100, 평점 보정 0.02/레벨): 그 경기 날 아침 상대 팀 Elo(src/team_elo.py — 일정 파일로
       직접 계산, 리그 평균 = 1500 + (레벨 − 80) × 10 이라 같은 눈금) → 80 + (Elo − 1500)/10, LVL_MIN~LVL_MAX 로 자름.
       리그 평점은 '그 리그 평균 상대'를 만난 값이고, 유럽·컵은 상대가 들쭉날쭉하다(맨시티 123 · 슬로반 79).
       Elo 를 못 찾으면 대회 기준 — UCL 100/90 · UEL 94/86 · UECL 90/82(우리 8개 리그 상대면 그 리그 수준과 하한 중 큰 값),
       국내 컵은 상대 리그 수준(하부 리그 팀이면 자기 리그 −12)
     가중(출전 분 ×): 유럽 1.0, 국내 컵 0.5(로테이션·하부 리그 상대)
   지난 시즌 유럽·컵(--season prev 수집)도 같은 방식으로 prev_x_* 에 — 지난 시즌 챔스 우승 활약이 들어간다.

2) 전 대회 세부 지표(선수 화면 템플릿 레이더, comps=all) — combine
   리그 값은 우리 표 그대로 두고, 리그 밖 경기의 FotMob 세부 기록을 per90·비율로 만들어 출전 분(×가중)으로 섞는다.
   제공처가 달라(리그 표 = FBref·Sofascore, 리그 밖 = FotMob) 같은 선수들의 '리그 경기' 값으로 지표마다 척도를 맞춘다
   (calibrate — 횟수는 비율, 성공률은 차이. 25/26·26/27 리그 경기 450′+ 선수 전원, 시즌마다 자동으로 다시 잰다).
"""
from __future__ import annotations

import pandas as pd

LEAGUE_CODES = {"eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "por.1", "ned.1", "bel.1"}
try:                                       # 라이트 리그 리그 경기 코드(eng.2 …) — 컵으로 잘못 세지 않게
    from leagues import LEAGUES as _LG
    LEAGUE_CODES |= {c.espn for c in _LG.values() if c.espn}
except ImportError:
    pass
EURO = {"uefa.champions": (100.0, 90.0), "uefa.europa": (94.0, 86.0), "uefa.europa.conf": (90.0, 82.0)}
CUP_DROP = 12.0                 # 국내 컵 하부 리그 상대 — 자기 리그 수준에서 뺀다
LVL_MIN, LVL_MAX = 75.0, 115.0  # 상대 Elo 수준 범위 — 평점 보정 +0.5 ~ −0.3(한 경기 상대가 OVR 을 크게 흔들지 않게)
W_EURO, W_CUP = 1.0, 0.5
RATING_MIN_APP = 30             # 리그 밖 경기 평점 표본 — 이 분 미만 교체 출전은 평점에서 뺀다(rating_table)

# 우리 지표 열 ← FotMob 세부 기록: ('n', 분자) = per90, ('p', 성공, 시도) = %, ('p2', 승, 패) = 승/(승+패) %
MAP = {
    "npxg_p90": ("n", "npxg"), "shots_p90": ("n", "shots"), "sot_per90": ("n", "sot"), "xa_p90": ("n", "xa"),
    "key_passes_per90": ("n", "chances"), "big_chances_created_per90": ("n", "bigc"),
    "final_third_passes_per90": ("n", "f3"), "pass_pct": ("p", "pass_acc", "pass_tot"),
    "long_ball_pct": ("p", "long_acc", "long_tot"), "successful_dribbles_per90": ("n", "drib_won"),
    "dribble_success_pct": ("p", "drib_won", "drib_tot"), "crosses_per90": ("n", "cross_tot"),
    "cross_acc_pct": ("p", "cross_acc", "cross_tot"), "tackles_won_per90_ss": ("n", "tackles"),
    "interceptions_per90_ss": ("n", "ints"), "recoveries_per90": ("n", "recov"), "clearances_per90": ("n", "clear"),
    "blocked_shots_per90": ("n", "blocks"), "aerial_won_per90": ("n", "aer_won"),
    "aerial_won_pct": ("p", "aer_won", "aer_tot"), "ground_duels_won_per90": ("n", "grd_won"),
    "ground_duels_won_pct": ("p", "grd_won", "grd_tot"), "total_duels_won_pct": ("p2", "duel_won", "duel_lost"),
    "fouls_per90": ("n", "fouls"), "gk_saves_per90": ("n", "saves"), "gk_save_pct": ("p2", "saves", "conceded"),
    "gk_high_claims_per90": ("n", "high_claim"), "gk_runs_out_per90": ("n", "sweeper"), "gk_punches_per90": ("n", "punches"),
}
CAL_MIN = 450                   # 척도 맞추기 표본 — 리그 경기 450′+
CAL_N = 30


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def fid_of(v) -> str | None:
    try:
        return str(int(float(v))) if v is not None and v == v and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def kind(code) -> str:
    c = str(code or "")
    return "league" if c in LEAGUE_CODES else "euro" if c in EURO else "cup"


def match_level(code, own_level: float, opp_level: float | None) -> float:
    """리그 밖 경기 하나의 대회 수준(EPL=100)."""
    c = str(code or "")
    if c in EURO:
        top, floor = EURO[c]
        return min(top, max(floor, opp_level)) if opp_level is not None else floor
    return opp_level if opp_level is not None else own_level - CUP_DROP


def elo_level(elo: float) -> float:
    """팀 Elo → 같은 눈금의 수준(리그 평균 Elo = 1500 + (레벨 − 80) × 10 의 역)."""
    return min(LVL_MAX, max(LVL_MIN, 80.0 + (float(elo) - 1500.0) / 10.0))


def prep(mr: pd.DataFrame | None, levels: dict, team_league: dict, opp_elo=None) -> pd.DataFrame:
    """경기별 기록 → 리그 밖 행만 + _w(가중)·_lvl(상대 수준)·_fid. levels = {리그: 수준}, team_league = {팀: 리그},
    opp_elo(상대 이름, 날짜, 우리 팀) → 그날 아침 Elo | None."""
    if mr is None or mr.empty:
        return pd.DataFrame()
    d = mr[mr["comp_code"].map(kind) != "league"].copy()
    if d.empty:
        return d
    d["minutes"] = _num(d["minutes"]).fillna(0)
    d = d[d["minutes"] > 0]
    own = d["squad"].astype(str).map(team_league).map(levels)
    opp = d["opponent"].astype(str).map(team_league).map(levels)
    lv = []
    for c, o, p, nm, dt_, sq in zip(d["comp_code"], own, opp, d["opponent"].astype(str), d["date"].astype(str),
                                    d["squad"].astype(str)):
        e = opp_elo(nm, dt_, sq) if opp_elo else None
        lv.append(elo_level(e) if e is not None else match_level(c, float(o) if o == o else 100.0, float(p) if p == p else None))
    d["_lvl"] = lv
    d["_w"] = d["comp_code"].map(lambda c: W_EURO if kind(c) == "euro" else W_CUP)
    d["_fid"] = d["fotmob_id"].map(fid_of)
    return d


def rating_table(x: pd.DataFrame) -> tuple[dict, dict]:
    """({fotmob_id: 요약}, {'squad|player': 요약}) — 요약 = {fm_rating, minutes(가중), raw_minutes, level, comps}."""
    if x is None or x.empty:
        return {}, {}
    d = x[_num(x["rating"]).notna()].copy()
    d["rating"] = _num(d["rating"])
    # 평점은 RATING_MIN_APP 분 이상 뛴 경기만 — 짧은 교체 출전 평점은 체계적으로 낮고(같은 선수 클럽 리그 평점보다 30분 미만
    # −0.45 · 30~45분 −0.3) 정보가 거의 없다(상관 0.12, 2026-10-27 유럽 979경기·대표팀 1,054경기). 출전 분·대회 표시는 전부.
    d["_wm"] = d["minutes"] * d["_w"] * (d["minutes"] >= RATING_MIN_APP)

    def summ(g: pd.DataFrame) -> dict:
        wm = float(g["_wm"].sum())
        comps = g.groupby("comp_code")["minutes"].sum().astype(int).to_dict()
        return {"fm_rating": float((g["rating"] * g["_wm"]).sum() / wm) if wm else None, "minutes": wm,
                "raw_minutes": int(g["minutes"].sum()), "apps": int(len(g)),
                "level": float((g["_lvl"] * g["_wm"]).sum() / wm) if wm else None, "comps": comps}
    by_id = {f: summ(g) for f, g in d[d["_fid"].notna()].groupby("_fid")}
    by_name = {f"{sq}|{pl}": summ(g) for (sq, pl), g in d.groupby(["squad", "player"])}
    return by_id, by_name


def attach_x(frame: pd.DataFrame, cur: tuple[dict, dict], prev: tuple[dict, dict] | None = None,
             names: tuple[str, str] = ("x", "prev_x")) -> pd.DataFrame:
    """선수 표에 x_ss_rating · x_minutes(가중) · x_level · x_raw_minutes · x_comps(+ prev_x_*). fm_id 우선, 없으면 팀|이름.
    names=('nt', 'prev_nt') 면 대표팀 표본(nt_tables) — 같은 모양의 열을 다른 이름으로."""
    from rating_blend import fm_to_ss  # noqa: PLC0415
    out = frame.copy()
    for pre, (by_id, by_name) in ((names[0], cur), (names[1], prev or ({}, {}))):
        vals = []
        for _, r in out.iterrows():
            f = fid_of(r.get("fm_id"))
            t = by_id.get(f) if f else None
            if t is None and pre == names[0]:
                t = by_name.get(f"{r.get('squad')}|{r.get('player')}")
            vals.append(t)
        out[f"{pre}_ss_rating"] = [fm_to_ss(t["fm_rating"]) if t and t["fm_rating"] is not None else pd.NA for t in vals]
        out[f"{pre}_minutes"] = [t["minutes"] if t else pd.NA for t in vals]
        out[f"{pre}_level"] = [t["level"] if t else pd.NA for t in vals]
        out[f"{pre}_raw_minutes"] = [t["raw_minutes"] if t else pd.NA for t in vals]
        if pre == names[0]:
            out[f"{pre}_comps"] = [t["comps"] if t else None for t in vals]
    return out


# ── 대표팀 경기(src/fetch_fotmob_intl.py → fotmob_intl_ratings_{시즌}) ─────────────────────────
# 2026-10-27 사용자: '국대 활약도 넣자'(하베르츠 월드컵 3골). 유럽·컵과 같은 '리그 밖 표본'이지만 OVR 에만 넣는다 —
# 폼(이번 시즌 클럽)과 세부 지표(리그+유럽·컵)는 그대로. 열 이름 nt_* · prev_nt_*(attach_x names).
#   상대 수준 = NT_A + NT_B × (상대 FIFA 점수 − 1500) — nt_cal 이 데이터로 다시 맞춘다: 같은 선수의 같은 시즌 클럽 리그 평점
#   (FotMob)과 대표팀 평점의 차이가 상대 점수에 따라 어떻게 달라지는지(경기마다 '이 평점이 말하는 상대 수준'을 출전 분 가중
#   최소제곱). 표본이 모자라면(NT_CAL_MIN 줄 미만) 기본값. 랭킹에 없는 나라는 점수 NT_UNKNOWN_POINTS(약체)로.
#   가중: 공식 대회 0.5, 친선 0.25 — 같은 출전 시간대(300~600분)에서 표본 평점(수준 보정)과 같은 선수 클럽 리그 평점의 상관이
#   대표팀 0.26 · 유럽 0.38 · 국내 컵 0.39(2026-10-27, 각 285~296명). 동료·전술·준비 기간이 달라 클럽 실력을 덜 말해 준다.
#   1.0 으로 넣었을 땐 교체 3~4번(평점 6.7)뿐인 35세 그로스가 베테랑 보정에 증폭돼 78→77(golden 밖)
NT_A, NT_B = 94.2, 0.04          # 2026-10-27 nt_cal 결과(7,784줄) — 표본이 모자랄 때만 쓰는 기본값
NT_CAL_MIN, NT_UNKNOWN_POINTS = 300, 1150.0
W_NT, W_FRIENDLY = 0.5, 0.25


def nt_level(points, cal: tuple[float, float] = (NT_A, NT_B)) -> float:
    p = float(points) if points is not None and points == points else NT_UNKNOWN_POINTS
    return min(LVL_MAX, max(LVL_MIN, cal[0] + cal[1] * (p - 1500.0)))


def _nt_raw(read, season: str) -> pd.DataFrame:
    t = read("fotmob_intl_ratings", "EPL", season)
    if t is None or t.empty or "fotmob_id" not in t.columns:
        return pd.DataFrame()
    d = t[t["fotmob_id"].notna()].copy()
    d["minutes"] = _num(d["minutes"]).fillna(0)
    d["rating"] = _num(d["rating"])
    d = d[(d["minutes"] > 0) & d["rating"].notna()]
    d["_fid"] = d["fotmob_id"].map(fid_of)
    return d


def nt_cal(read, seasons: list[str]) -> tuple[float, float, int]:
    """(a, b, 줄 수) — 상대 수준 = a + b × (상대 점수 − 1500). 클럽 리그 평점(FotMob, 그 시즌 450분+)이 있는 선수 경기만.
    경기마다 L = 클럽 리그 수준 − (대표팀 평점 − 클럽 평점)(Sofascore 척도)/평점 보정(0.02) — 대표팀에서 평점이 클럽보다
    높으면 상대가 약했다는 뜻. 한 경기 평점은 흔들림이 커서(±0.7 → ±25 레벨) 많은 줄로 맞추고 L 은 40~160 으로 자른다."""
    import league_level  # noqa: PLC0415
    import rating_blend as rb  # noqa: PLC0415
    from league_level import RATING_PER_LEVEL  # noqa: PLC0415
    xs, ys, ws = [], [], []
    for se in seasons:
        d = _nt_raw(read, se)
        if d.empty or "opp_points" not in d.columns:
            continue
        base = rb._by_id(lambda lg, s: read("fotmob_ratings", lg, s), se)
        for f, r, m, p in zip(d["_fid"], d["rating"], d["minutes"], _num(d["opp_points"])):
            b = base.get(int(f)) if f else None
            if b is None or b[1] < 450 or p != p:
                continue
            diff = (rb.fm_to_ss(r) - rb.fm_to_ss(b[0]))
            L = league_level.level(b[2]) - diff / RATING_PER_LEVEL
            xs.append(float(p) - 1500.0)
            ys.append(min(160.0, max(40.0, L)))
            ws.append(min(float(m), 90.0))
    if len(xs) < NT_CAL_MIN:
        return NT_A, NT_B, len(xs)
    import numpy as np  # noqa: PLC0415
    x, y, w = np.array(xs), np.array(ys), np.array(ws)
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    b = float(np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2))
    return float(ym - b * xm), b, len(xs)


def nt_rows(read, season: str, cal: tuple[float, float]) -> pd.DataFrame:
    """대표팀 경기 → rating_table 이 읽는 모양(_w·_lvl·_fid·squad·comp_code)."""
    d = _nt_raw(read, season)
    if d.empty:
        return d
    pts = _num(d["opp_points"]) if "opp_points" in d.columns else pd.Series(float("nan"), index=d.index)
    d["_lvl"] = [nt_level(p, cal) for p in pts]
    d["_w"] = [W_FRIENDLY if int(f or 0) else W_NT for f in _num(d.get("friendly", 0)).fillna(0)]
    d["squad"] = d["club"].astype(str) if "club" in d.columns else ""
    d["comp_code"] = "intl." + d["comp_id"].astype(str)
    return d


def nt_tables(read, season: str, version=None) -> tuple[dict, dict]:
    """대표팀 표본 요약(rating_table) — 상대 수준 보정은 이번·지난 시즌을 함께 맞춘 값."""
    key = ("nt", season, version)
    if version is not None and key in _CACHE:
        return _CACHE[key]
    from leagues import SEASON_START  # noqa: PLC0415
    ckey = ("ntcal", "", version)
    cal = _CACHE.get(ckey) if version is not None else None
    if cal is None:
        cal = nt_cal(read, [f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"])
        if version is not None:
            _put(ckey, cal)
    out = rating_table(nt_rows(read, season, cal[:2]))
    if version is not None:
        _put(key, out)
    return out


# ── 세부 지표 ───────────────────────────────────────────────────────────────
def per90(rows: pd.DataFrame, weight: str | None = None) -> pd.DataFrame:
    """경기별 행 → 선수별(_key) 우리 지표 열. weight 열이 있으면 분·횟수에 곱한다(대회 가중)."""
    if rows is None or rows.empty:
        return pd.DataFrame()
    d = rows.copy()
    w = d[weight] if weight else 1.0
    cols = {c for spec in MAP.values() for c in spec[1:]}
    for c in cols:
        d[c] = _num(d.get(c, pd.Series(0, index=d.index))).fillna(0) * w
    d["_m"] = _num(d["minutes"]).fillna(0) * w
    g = d.groupby("_key")[[*cols, "_m"]].sum()
    out = pd.DataFrame(index=g.index)
    m = g["_m"].where(g["_m"] > 0)
    for col, spec in MAP.items():
        if spec[0] == "n":
            out[col] = g[spec[1]] / m * 90
        elif spec[0] == "p":
            out[col] = (g[spec[1]] / g[spec[2]].where(g[spec[2]] > 0)) * 100
        else:
            tot = g[spec[1]] + g[spec[2]]
            out[col] = (g[spec[1]] / tot.where(tot > 0)) * 100
    out["_m"] = g["_m"]
    return out


def calibrate(ours: pd.DataFrame, fm_league: pd.DataFrame) -> dict:
    """{열: ('ratio', k) | ('diff', d)} — 같은 선수들의 리그 경기 값으로 FotMob → 우리 표 척도.
    ours: _key·minutes·지표 열, fm_league: per90(리그 경기) 결과."""
    j = ours.set_index("_key").join(fm_league, how="inner", rsuffix="_fm")
    j = j[(_num(j["minutes"]) >= CAL_MIN) & (_num(j["_m"]) >= CAL_MIN)]
    cal = {}
    for col, spec in MAP.items():
        if col not in j.columns or f"{col}_fm" not in j.columns:
            continue
        a, b = _num(j[col]), _num(j[f"{col}_fm"])
        ok = a.notna() & b.notna()
        if ok.sum() < CAL_N:
            continue
        w = _num(j["minutes"])[ok]
        if spec[0] == "n":
            den = float((b[ok] * w).sum())
            if den > 0:
                k = float((a[ok] * w).sum()) / den
                cal[col] = ("ratio", round(min(2.5, max(0.4, k)), 3))
        else:
            dd = float(((a[ok] - b[ok]) * w).sum() / w.sum())
            cal[col] = ("diff", round(min(20.0, max(-20.0, dd)), 2))
    return cal


def apply_cal(x: pd.DataFrame, cal: dict) -> pd.DataFrame:
    out = x.copy()
    for col, (how, k) in cal.items():
        if col in out.columns:
            out[col] = out[col] * k if how == "ratio" else (out[col] + k).clip(0, 100)
    return out


def combine(frame: pd.DataFrame, x90: pd.DataFrame, cal: dict) -> pd.DataFrame:
    """선수 표(리그) + 리그 밖 per90(가중 분 _m) → 같은 인덱스의 전 대회 표.
    지표 = (리그 값 × 리그 분 + 척도 맞춘 리그 밖 값 × 가중 분) / (리그 분 + 가중 분). minutes = 리그 분 + 가중 분."""
    out = frame.copy()
    out["_league_minutes"] = _num(out["minutes"]).fillna(0)
    out["_x_minutes"] = 0.0
    if x90 is None or x90.empty:
        return out
    xc = apply_cal(x90, cal)
    keys = out["_key"]
    xm = _num(keys.map(xc["_m"])).fillna(0)
    lm = out["_league_minutes"]
    if "npxg_p90" in out.columns:
        out["_npxg_lg"] = _num(out["npxg_p90"])   # 결정력(비PK골 − npxG)은 리그 범위로 — 유럽 비PK골은 알 수 없다(PK 골 미구분)
    for col in MAP:
        if col not in out.columns or col not in cal:
            continue                                     # 척도를 못 맞춘 지표는 리그 값 그대로
        lv, xv = _num(out[col]), _num(keys.map(xc[col]))
        both = lv.notna() & xv.notna() & (xm > 0)
        only_x = lv.isna() & xv.notna() & (xm > 0)
        res = lv.copy()
        res[both] = (lv[both] * lm[both] + xv[both] * xm[both]) / (lm[both] + xm[both])
        res[only_x] = xv[only_x]
        out[col] = res
    out["_x_minutes"] = xm
    out["minutes"] = lm + xm
    return out


# ── 불러오기(시즌 전체 8개 리그) ────────────────────────────────────────────────
_CACHE: dict = {}


def _put(key: tuple, val):
    """캐시에 넣으며 같은 (종류, 시즌)의 옛 판(이전 DB 시각)을 지운다 — 오래 도는 서버에서 DB 가 갱신될 때마다 쌓이지 않게."""
    for k in [k for k in _CACHE if k[:2] == key[:2] and k != key]:
        _CACHE.pop(k, None)
    _CACHE[key] = val
    return val


def season_rows(read, season: str, version=None) -> pd.DataFrame:
    """read(table, league, season) → 8개 리그 경기별 기록을 합친 리그 밖 행(prep). version 이 같으면 캐시."""
    key = ("rows", season, version)
    if version is not None and key in _CACHE:
        return _CACHE[key]
    import league_level  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    frames, team_league = [], {}
    for lg in LEAGUES:
        st = read("standings", lg, season)
        if st is not None and not st.empty and "squad" in st.columns:
            team_league.update({str(s): lg for s in st["squad"]})
        t = read("fotmob_match_ratings", lg, season)
        if t is not None and not t.empty:
            frames.append(t)
    mr = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    try:
        x = mr[mr["comp_code"].map(kind) != "league"] if not mr.empty else mr
        opp = opp_elo_fn(read, set(x["date"].astype(str)) if not x.empty else set())
    except Exception as e:  # noqa: BLE001 — 일정 파일이 없으면 대회 기준 수준
        print(f"[allcomp] Elo 건너뜀 {type(e).__name__}: {e}")
        opp = None
    out = prep(mr, league_level.levels(), team_league, opp)
    if version is not None:
        _put(key, out)
    return out


def opp_elo_fn(read, dates: set[str]):
    """(상대 이름, 날짜, 우리 팀) → 그날 아침 Elo. 일정 파일(schedule_full, 지난 시즌부터 8개 리그 + 컵·유럽)로 src/team_elo 를 돌린다.
    상대는 먼저 일정에서 (우리 팀, 날짜 ±1일)로 정확히 찾고 — FotMob·ESPN 표기 차이로 이름 유사 매칭이 'Atlético'(포르투갈 3부)를
    아틀레티코 마드리드로, 'Rangers' 를 QPR 로 잇던 것(2026-10-21 검수) — 없을 때만 team_names.best.
    그날 아침 스냅숏에 아직 없는 팀(첫 경기 전)은 시작값(우리 리그 = 리그 기본값, 밖 = 1500) — 최종 Elo(그 경기·뒤 경기 결과 포함)는 미래 정보."""
    import league_level  # noqa: PLC0415
    import team_elo as te  # noqa: PLC0415
    import team_names as tnm  # noqa: PLC0415
    from leagues import LEAGUES, SEASON_START  # noqa: PLC0415
    frames = []
    for se in (f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"):
        fr = {lg: read("schedule_full", lg, se) for lg in LEAGUES}
        frames.append(te.matches_from({k: v for k, v in fr.items() if v is not None and not v.empty}))
    ms = pd.concat(frames, ignore_index=True).drop_duplicates("event_id").sort_values(["date", "event_id"])
    if ms.empty:
        return None
    bases = {lg: te.league_base(league_level.level(lg)) for lg in LEAGUES}
    final, snaps = te.run(ms, bases, snap_dates=dates)
    names = list(final)
    team_lg: dict = {}
    by_day: dict = {}
    for r in ms.itertuples(index=False):
        for me, opp, lg in ((r.home, r.away, r.lg_h), (r.away, r.home, r.lg_a)):
            by_day[(str(me), str(r.date)[:10])] = str(opp)
            if lg:
                team_lg[str(me)] = lg
    alias: dict = {}

    def resolve(name: str, date: str, squad: str | None):
        if squad:
            d0 = pd.Timestamp(date[:10])
            for k in (0, -1, 1):
                hit = by_day.get((squad, (d0 + pd.Timedelta(days=k)).date().isoformat()))
                if hit:
                    return hit
        if name not in alias:
            alias[name] = name if name in final else tnm.best(name, names)
        return alias[name]

    def f(name: str, date: str, squad: str | None = None):
        k = resolve(name, date, squad)
        if not k:
            return None
        snap = snaps.get(date) or {}
        if k in snap:
            return snap[k]
        return bases.get(team_lg.get(k), te.START_BASE)    # 첫 경기 전 — 시작값(미래 값 쓰지 않음)
    return f


def x_tables(read, season: str, version=None) -> tuple[dict, dict]:
    key = ("tbl", season, version)
    if version is not None and key in _CACHE:
        return _CACHE[key]
    out = rating_table(season_rows(read, season, version))
    if version is not None:
        _put(key, out)
    return out


def league_rows(read, season: str, version=None) -> pd.DataFrame:
    """8개 리그 경기별 기록 중 리그 경기만(척도 맞추기용) — _key 포함."""
    key = ("league", season, version)
    if version is not None and key in _CACHE:
        return _CACHE[key]
    from leagues import LEAGUES  # noqa: PLC0415
    frames = [t for t in (read("fotmob_match_ratings", lg, season) for lg in LEAGUES) if t is not None and not t.empty]
    mr = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not mr.empty:
        mr = mr[(mr["comp_code"].map(kind) == "league") & (_num(mr["minutes"]).fillna(0) > 0)].copy()
        mr["_key"] = row_keys(mr)
    if version is not None:
        _put(key, mr)
    return mr


def row_keys(rows: pd.DataFrame) -> list[str]:
    """경기별 행 → 선수 키(FotMob id, 없으면 '팀|이름')."""
    return [fid_of(f) or f"{s}|{p}" for f, s, p in zip(rows["fotmob_id"], rows["squad"], rows["player"])]


def frame_keys(frame: pd.DataFrame, rows: pd.DataFrame | None = None) -> list[str]:
    """선수 표 → 같은 키(fm_id — rating_blend.attach 가 붙임). fm_id 가 없는 선수(시즌 평점 표에 없는 765명)는 경기별 행의
    '팀|이름' → FotMob id 로 이어 준다 — 경기별 행은 언제나 id 키라 이름 키로는 못 만났다(Dowman 의 리그컵 기록이 빠짐, 2026-10-21 검수)."""
    ids = frame["fm_id"] if "fm_id" in frame.columns else [None] * len(frame)
    nm: dict = {}
    if rows is not None and not rows.empty and "fotmob_id" in rows.columns:
        for f_, s_, p_ in zip(rows["fotmob_id"], rows["squad"], rows["player"]):
            fid = fid_of(f_)
            if fid:
                nm.setdefault(f"{s_}|{p_}", fid)
    out = []
    for f, s, p in zip(ids, frame["squad"], frame["player"]):
        k = f"{s}|{p}"
        out.append(fid_of(f) or nm.get(k) or k)
    return out
