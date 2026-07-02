"""절대·퍼포먼스 우선 평가 모델 v2.

기존 ratings.py 는 시장가치(잠재력·화제성 반영)에 앵커돼 15세 유망주가 30세 주전보다
높게 나오는 문제가 있었다(예: Dowman 81 > Trossard 79). v2 는 이를 바로잡는다.

핵심
----
- **현재 OVR (절대)**: 퍼포먼스(ss_rating)+아웃풋을 앵커로, **출전 적으면 나이 베이스라인으로
  회귀**(몸값이 아니라), 시장가치는 **약한·나이보정 prior**. 30+ 완만한 하락.
- **POT(잠재력)**: 어린 선수의 성장 여지를 별도 축으로(시장가치 천장 + 나이 여지).
- **팀 OVR (절대)**: 스쿼드 현재 OVR 의 **출전가중 평균**. 리그 순위/폼과 분리.

기존 ratings.py 는 폴백으로 보존, 이 모듈은 병행 후 교체.
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


# ss_rating → 퍼포먼스 OVR (현재 실력 앵커). 6.3→62, 7.7→92
_LO_R, _LO_O = 6.3, 62.0
_HI_R, _HI_O = 7.7, 92.0
_SLOPE = (_HI_O - _LO_O) / (_HI_R - _LO_R)


def perf_from_rating(ss) -> float | None:
    if ss is None or (isinstance(ss, float) and math.isnan(ss)):
        return None
    try:
        return _LO_O + _SLOPE * (float(ss) - _LO_R)
    except (TypeError, ValueError):
        return None


def value_ovr(v) -> float | None:
    val = _num(v)
    if val <= 0:
        return None
    return 13.04 * math.log10(val) - 16.24


def age_curve(age) -> float:
    """현재 실력 나이 modifier. 피크 21~29=0, 그 전 완만한 미성숙, 30+ 완만한 하락."""
    a = _num(age)
    if a <= 0:
        return 0.0
    if a < 21:
        return -0.4 * (21 - a)          # 어릴수록 아직 피크 전(완만)
    if a <= 29:
        return 0.0
    return -min(7.0, (a - 29) * 0.8)     # 30+ 하락


def _value_weight(age) -> float:
    """시장가치 prior 가중. 어릴수록 value=잠재력이라 현재 실력엔 덜 반영."""
    a = _num(age)
    if a <= 20:
        return 0.06
    if a <= 23:
        return 0.12
    if a <= 31:
        return 0.20
    return 0.14


def _baseline(age) -> float:
    """표본 부족 시 회귀할 보수적 베이스라인(몸값 아님)."""
    a = _num(age)
    if 0 < a < 18:
        return 60.0
    if a < 21:
        return 61.0
    if a >= 32:
        return 63.0
    return 64.0


def output_bonus(pos_group: str, minutes, goals, assists) -> float:
    """90분당 공격 기여 보너스. 공격 라인 크게, 수비/GK 작게."""
    mn = _num(minutes)
    if mn < 270:
        return 0.0
    per90 = (_num(goals) + _num(assists)) / (mn / 90.0)
    g = (pos_group or "").upper()
    if g in ("ST", "W", "RW", "LW", "AM", "FW"):
        return min(7.0, per90 * 7.0)
    if g in ("CM", "DM", "MF"):
        return min(4.0, per90 * 5.0)
    return min(2.5, per90 * 4.0)


def current_ovr(*, ss_rating, minutes, age, value, goals=0, assists=0, pos_group="") -> int:
    """현재 실력 OVR (절대). 퍼포먼스 앵커 + 표본회귀 + 약한 가치 prior + 나이곡선."""
    perf = perf_from_rating(ss_rating)
    vov = value_ovr(value)
    mn = _num(minutes)
    base = _baseline(age)

    if perf is None:
        # 경기 데이터 없음 → 가치+베이스라인 보수 추정
        v = vov if vov is not None else base
        return int(_clamp(round(0.5 * base + 0.5 * v + age_curve(age)), 45, 95))

    perf += output_bonus(pos_group, minutes, goals, assists)
    rel = _clamp(mn / 1000.0, 0.0, 1.0)
    perf_reg = rel * perf + (1 - rel) * base       # 적은 출전 → 몸값 아닌 베이스라인으로

    if vov is None:
        cur = perf_reg
    else:
        vw = _value_weight(age)
        cur = (1 - vw) * perf_reg + vw * vov

    cur += age_curve(age)
    return int(_clamp(round(cur), 45, 99))


def potential(*, current: int, age, value) -> int:
    """잠재력. 23세 이하 + 시장가치 천장 + 나이 여지. 그 외엔 현재와 동일."""
    a = _num(age)
    vov = value_ovr(value)
    if a <= 0 or a > 23 or vov is None:
        return current
    youth = max(0.0, 23 - a) * 0.8
    pot = max(current, 0.45 * current + 0.55 * vov + youth)
    return int(_clamp(round(pot), current, 99))


def player_line(row) -> dict:
    """players_full 행 → {ovr, pot}."""
    pos = str(row.get("fl_group") or row.get("pos") or "")
    cur = current_ovr(
        ss_rating=row.get("ss_rating"), minutes=row.get("minutes"), age=row.get("age"),
        value=row.get("market_value_eur"), goals=row.get("goals"), assists=row.get("assists"),
        pos_group=pos,
    )
    pot = potential(current=cur, age=row.get("age"), value=row.get("market_value_eur"))
    return {"ovr": cur, "pot": pot}


# ── 팀 (절대 출전가중 평균) ─────────────────────────────────────────
_ATT = {"ST", "W", "RW", "LW", "AM", "FW"}
_MID = {"DM", "CM", "AM", "MF"}
_DEF = {"CB", "FB", "RB", "LB", "GK", "DF"}


def _active_squad(full_df, squad):
    sq = full_df[full_df["squad"] == squad].copy()
    if "left_for" in sq.columns:
        sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]
    return sq


def _wavg(pairs: list[tuple[float, float]]) -> float | None:
    """[(value, weight)] 가중평균."""
    pairs = [(v, w) for v, w in pairs if w > 0]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def team_ratings(full_df, squad) -> dict | None:
    """팀 절대 OVR — 스쿼드 현재 OVR 출전가중 평균 + 라인별. 폼/순위와 분리.

    반환: {overall, attack, midfield, defense, top_xi, squad_size}
    가중 = sqrt(minutes) (주전 비중↑, 벤치 과대반영 방지). 상위 기여 위주.
    """
    if full_df is None or "squad" not in full_df.columns:
        return None
    sq = _active_squad(full_df, squad)
    if sq.empty:
        return None

    rows = []
    for _, r in sq.iterrows():
        pl = player_line(r)
        mn = _num(r.get("minutes"))
        pos = str(r.get("fl_group") or r.get("pos") or "").upper()
        rows.append({"ovr": pl["ovr"], "pot": pl["pot"], "min": mn, "pos": pos})

    def unit(codes):
        return _wavg([(x["ovr"], max(1.0, x["min"]) ** 0.5) for x in rows if x["pos"] in codes])

    # 종합 = 실제로 뛰는 스쿼드(출전가중). 상위 16명 위주로 벤치 잡음 완화.
    core = sorted(rows, key=lambda x: -x["min"])[:16]
    overall = _wavg([(x["ovr"], max(1.0, x["min"]) ** 0.5) for x in core])
    att, mid, dfn = unit(_ATT), unit(_MID), unit(_DEF)
    top_xi = _wavg([(x["ovr"], 1.0) for x in sorted(rows, key=lambda x: -x["ovr"])[:11]])

    def _i(v, fb=70):
        return int(round(v)) if v is not None else fb
    return {
        "overall": _i(overall), "attack": _i(att, _i(overall)),
        "midfield": _i(mid, _i(overall)), "defense": _i(dfn, _i(overall)),
        "top_xi": _i(top_xi, _i(overall)), "squad_size": len(rows),
    }
