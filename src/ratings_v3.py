"""평가 모델 v3 — 절대(커리어 클래스) · 폼(이번 시즌) · POT · 신뢰도 분리.

도메인 전문가(아스날 팬) 캘리브레이션 반영:
- v2 는 이번 시즌 ss_rating(=폼)에 앵커해 엘리트·GK·CB 를 저평가했다(Raya 76, Saka 86…).
- v3 는 **절대 OVR = 커리어 클래스**(시장가치 강 prior + 포지션 공정 보정 + 검증/베테랑 보정,
  어린 미검증은 게이팅) 로 두어 Raya 90·Rice 95·Saka 92 급을 재현하고,
  **폼 = 이번 시즌 평점(포지션 스케일)+아웃풋** 을 별도 축으로 둔다.
- POT = 유망주 성장여지. 신뢰도 = 표본/검증(PL 다시즌) 여부.

ground-truth(사용자 아스날 절대/폼)로 계수를 맞춘 뒤 전 리그로 일반화.
"""
from __future__ import annotations

import math

import pandas as pd


def _num(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return d if math.isnan(f) else f
    except (TypeError, ValueError):
        return d


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def line_of(pos) -> str:
    p = str(pos or "").upper()
    if p in ("GK",) or "KEEPER" in p:
        return "GK"
    if p in ("CB", "FB", "RB", "LB", "DF") or "BACK" in p or "DEFEN" in p:
        return "DEF"
    if p in ("ST", "W", "RW", "LW", "FW") or "WING" in p or "FORWARD" in p or "STRIKER" in p:
        return "ATT"
    return "MID"


def value_ovr(v) -> float | None:
    val = _num(v)
    if val <= 0:
        return None
    return 13.04 * math.log10(val) - 16.24


# ── 절대 OVR (커리어 클래스) ──────────────────────────────────────
_POS_ADJ = {"GK": 8.0, "DEF": 2.0, "MID": 2.0, "ATT": 1.0}   # 시장이 GK/수비를 저평가 → 보정
_SS_MID = {"GK": 6.85, "DEF": 6.95, "MID": 7.05, "ATT": 6.95}  # 포지션별 '평범한 주전' 평점


def absolute_ovr(*, value, ss_rating, minutes, age, pos_group) -> int:
    ln = line_of(pos_group)
    mn, a = _num(minutes), _num(age)
    vov = value_ovr(value)
    ss = _num(ss_rating)
    base = vov if vov is not None else 60.0
    perf_adj = _clamp((ss - _SS_MID[ln]) * 8.0, -3.5, 3.5) if ss > 0 else 0.0
    vet_adj = 3.0 if (a >= 30 and mn >= 1500) else 0.0     # 검증된 베테랑은 시장가 저평가 보정
    raw = base + _POS_ADJ[ln] + perf_adj + vet_adj
    # 어린 미검증만 게이팅(누적 커리어 부족) — 기성 선수는 저출전이어도 클래스 유지(부상 등)
    if 0 < a <= 21:
        proven = _clamp(mn / 900.0, 0.1, 1.0) * _clamp((a - 13) / 8.0, 0.2, 1.0)
        raw = proven * raw + (1 - proven) * 60.0
    return int(_clamp(round(raw), 45, 99))


# ── 폼 (이번 시즌) ────────────────────────────────────────────────
_F_LO_SS = {"GK": 6.50, "DEF": 6.60, "MID": 6.70, "ATT": 6.55}
_F_HI_SS = {"GK": 7.00, "DEF": 7.30, "MID": 7.50, "ATT": 7.45}
_F_LO = {"GK": 72.0, "DEF": 70.0, "MID": 70.0, "ATT": 68.0}
_F_HI = 95.0


def _output_bonus(ln: str, minutes, goals, assists) -> float:
    mn = _num(minutes)
    if mn < 270:
        return 0.0
    per90 = (_num(goals) + _num(assists)) / (mn / 90.0)
    if ln == "ATT":
        return min(6.0, per90 * 6.0)
    if ln == "MID":
        return min(4.0, per90 * 5.0)
    return min(2.0, per90 * 4.0)


def form_rating(*, ss_rating, minutes, goals=0, assists=0, pos_group="") -> int | None:
    ss, mn = _num(ss_rating), _num(minutes)
    if ss <= 0 or mn < 200:
        return None   # 표본 부족 → 폼 미산정
    ln = line_of(pos_group)
    t = _clamp((ss - _F_LO_SS[ln]) / (_F_HI_SS[ln] - _F_LO_SS[ln]), 0.0, 1.2)
    f = _F_LO[ln] + t * (_F_HI - _F_LO[ln]) + _output_bonus(ln, minutes, goals, assists) * 0.5
    return int(_clamp(round(f), 40, 99))


# ── 잠재력 ────────────────────────────────────────────────────────
def potential(*, absolute: int, age, value) -> int:
    a = _num(age)
    vov = value_ovr(value)
    if a <= 0 or a > 23 or vov is None:
        return absolute
    youth = max(0.0, 23 - a) * 1.0
    pot = max(absolute, 0.4 * absolute + 0.6 * (vov + 3) + youth)
    return int(_clamp(round(pot), absolute, 99))


# ── 신뢰도 (검증 vs 투영) ─────────────────────────────────────────
def confidence(*, minutes, ss_rating) -> str:
    mn = _num(minutes)
    if _num(ss_rating) <= 0:
        return "low"
    if mn >= 1500:
        return "high"
    if mn >= 700:
        return "med"
    return "low"


def player_line(row) -> dict:
    pos = str(row.get("fl_group") or row.get("pos") or "")
    ab = absolute_ovr(value=row.get("market_value_eur"), ss_rating=row.get("ss_rating"),
                      minutes=row.get("minutes"), age=row.get("age"), pos_group=pos)
    fm = form_rating(ss_rating=row.get("ss_rating"), minutes=row.get("minutes"),
                     goals=row.get("goals"), assists=row.get("assists"), pos_group=pos)
    return {"ovr": ab, "form": fm, "pot": potential(absolute=ab, age=row.get("age"), value=row.get("market_value_eur")),
            "confidence": confidence(minutes=row.get("minutes"), ss_rating=row.get("ss_rating"))}


# ── 팀 (베스트 XI 가중, 절대·폼 블렌드) ───────────────────────────
_ATT = {"ATT"}
_MID = {"MID"}
_DEF = {"DEF", "GK"}


def team_ratings(full_df, squad) -> dict | None:
    if full_df is None or "squad" not in full_df.columns:
        return None
    sq = full_df[full_df["squad"] == squad].copy()
    if "left_for" in sq.columns:
        sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]
    if sq.empty:
        return None
    rows = []
    for _, r in sq.iterrows():
        pl = player_line(r)
        # 팀 강함 = 클래스(절대) 와 이번폼 블렌드. 폼 없으면 절대만.
        strength = pl["ovr"] if pl["form"] is None else round(0.55 * pl["ovr"] + 0.45 * pl["form"])
        rows.append({"ovr": pl["ovr"], "strength": strength, "min": _num(r.get("minutes")),
                     "line": line_of(r.get("fl_group") or r.get("pos"))})

    def _avg_best(items, n):
        top = sorted(items, key=lambda x: -x["strength"])[:n]
        return round(sum(x["strength"] for x in top) / len(top)) if top else None

    def _unit(codes, n):
        return _avg_best([x for x in rows if x["line"] in codes], n)

    overall = _avg_best(rows, 11)   # 베스트 XI
    att, mid, dfn = _unit(_ATT, 3), _unit(_MID, 4), _unit(_DEF, 4)

    def _i(v, fb=75):
        return int(v) if v is not None else fb
    return {"overall": _i(overall), "attack": _i(att, _i(overall)),
            "midfield": _i(mid, _i(overall)), "defense": _i(dfn, _i(overall)),
            "squad_size": len(rows)}
