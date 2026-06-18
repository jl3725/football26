"""
OVR · 백분위 · 능력치 계산 헬퍼.

여러 탭(Overview·Player·Pitch·Transfers)이 공유하는 순수 계산 함수 모음.
모두 인자만 받는 순수 함수라 전역 상태에 의존하지 않는다.
"""
from __future__ import annotations

import math

import pandas as pd

from similar_players import FEATURES
from .common import LABELS


def fm_rating(pct: float) -> int:
    """0~1 리그 백분위 → 1~99 능력치."""
    if pct is None or pd.isna(pct):
        return 1
    return max(1, min(99, round(1 + float(pct) * 98)))


def fm_color(r: int) -> str:
    """1~99 능력치 → 색상."""
    if r >= 85: return "#4d9aff"   # 파랑 — 압도적
    if r >= 70: return "#5cd66c"   # 초록 — 강점
    if r >= 50: return "#ffd048"   # 노랑 — 평균
    if r >= 35: return "#ff9c4a"   # 주황 — 평균 이하
    return "#ff6961"                # 빨강 — 약점


def _rank_pct(values: pd.Series, team: str, high_is_good: bool = True) -> float | None:
    values = values.dropna()
    if values.empty or team not in values.index:
        return None
    return float(values.rank(ascending=high_is_good, pct=True)[team])


def _blend_pcts(parts: list[tuple[float | None, float]]) -> float | None:
    valid = [(float(v), float(w)) for v, w in parts if v is not None and not pd.isna(v) and w > 0]
    if not valid:
        return None
    total = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total


def _blend_scores(parts: list[tuple[int | float | None, float]]) -> int | None:
    valid = [(float(v), float(w)) for v, w in parts if v is not None and not pd.isna(v) and w > 0]
    if not valid:
        return None
    total = sum(w for _, w in valid)
    return int(max(1, min(99, round(sum(v * w for v, w in valid) / total))))


def _pct_to_rating(pct: float | None) -> int | None:
    return fm_rating(pct) if pct is not None and not pd.isna(pct) else None


def _power_from_pct(pct: float | None, lo: int = 58, hi: int = 94) -> int | None:
    """Convert league percentile to a display power rating, not a raw 1-99 rank score."""
    if pct is None or pd.isna(pct):
        return None
    pct = max(0.0, min(1.0, float(pct)))
    return int(round(lo + pct * (hi - lo)))


def _power_from_index(value: int | float | None, lo: int = 58, hi: int = 94) -> int | None:
    """Convert stored 1-99 percentile-like indices into bounded team power ratings."""
    if value is None or pd.isna(value):
        return None
    pct = (max(1.0, min(99.0, float(value))) - 1.0) / 98.0
    return int(round(lo + pct * (hi - lo)))


# 선수 OVR — Sofascore 평점(객관적 절대 지표)을 고정 스케일로 1~99 변환.
# 백분위(상대 순위)와 달리, 동일 평점이면 팀·시즌 무관 동일 OVR → 객관적·비교가능.
# 앵커: ss 6.3 → OVR 60, ss 7.7 → OVR 92 (선형, 40~99 clamp).
#   ≈6.8(중앙값)→72 · 7.0→76 · 7.2→81 · 7.46(Rice)→87 · 7.61(리그1위)→90
_OVR_LO_R, _OVR_LO_O = 6.3, 60
_OVR_HI_R, _OVR_HI_O = 7.7, 92
_OVR_SLOPE = (_OVR_HI_O - _OVR_LO_O) / (_OVR_HI_R - _OVR_LO_R)


def ovr_from_rating(ss) -> int | None:
    """Sofascore 평점(≈6.3~7.7) → OVR 1~99. 결측이면 None."""
    if ss is None or pd.isna(ss):
        return None
    ovr = _OVR_LO_O + _OVR_SLOPE * (float(ss) - _OVR_LO_R)
    return int(max(40, min(99, round(ovr))))


def ovr_from_value(v):
    """시장가치(EUR) → OVR(로그 스케일, 미clamp float). 결측이면 None.
    앵커: €1M→62 · €10M→75 · €30M→81 · €75M→86 · €100M→88 · €200M→92."""
    if v is None or pd.isna(v) or float(v) <= 0:
        return None
    return 13.04 * math.log10(float(v)) - 16.24


def perf_ovr(ss_rating, goals=0, assists=0):
    """시즌 퍼포먼스 OVR — 평점 기반(60~92) + 골·도움 기여 보너스(최대 +8).
    기여 보너스는 가산만(수비수가 골 없다고 깎이지 않음). 평점 없으면 None."""
    base = ovr_from_rating(ss_rating)
    if base is None:
        return None
    g = float(goals) if (goals is not None and not pd.isna(goals)) else 0.0
    a = float(assists) if (assists is not None and not pd.isna(assists)) else 0.0
    return base + min(8.0, (g + a) * 0.4)


def player_ovr(value, ss_rating=None, minutes=0, goals=0, assists=0) -> int:
    """OVR = 시장가치(품질) 50% + 시즌 퍼포먼스(평점+골·도움) 50% 블렌드.
    단, 출전 적은 선수는 폼 신뢰도가 낮아 퍼포먼스 비중을 출전시간에 비례 축소
    (min/1200, 1500분↑이면 완전 50/50). 한쪽 데이터만 있으면 그쪽만 사용."""
    vov = ovr_from_value(value)               # 가치 OVR (float) 또는 None
    pov = perf_ovr(ss_rating, goals, assists)  # 퍼포먼스 OVR (float) 또는 None
    if vov is None and pov is None:
        return 60
    if vov is None:
        return int(max(48, min(95, round(pov))))
    if pov is None:
        return int(max(48, min(95, round(vov))))
    rel = min(1.0, (float(minutes) if (minutes and not pd.isna(minutes)) else 0) / 1200)
    w = 0.5 * rel                              # 퍼포먼스 가중치(최대 0.5)
    return int(max(48, min(95, round((1 - w) * vov + w * pov))))


def _series_pct(series: pd.Series, value, high_is_good: bool = True) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if value is None or pd.isna(value) or s.empty:
        return None
    vals = list(s) + [float(value)]
    rank = pd.Series(vals).rank(ascending=not high_is_good, method="min").iloc[-1]
    n = len(vals)
    return 1 - (rank - 1) / (n - 1) if n > 1 else 1.0


def goalkeeper_ovr(row: pd.Series, gk_pool: pd.DataFrame) -> int:
    """GK 전용 OVR.

    공통 OVR은 시장가치와 평균평점 중심이라 클린시트/박스 장악 같은 GK 성과가 눌린다.
    여기서는 GK 풀 안에서 시즌 성과를 따로 환산하고, 클린시트 1위는 Golden Glove급
    시즌으로 소폭 보너스를 준다.
    """
    base = player_ovr(row.get("market_value_eur"), row.get("ss_rating"), row.get("minutes"), 0, 0)
    gk_pool = gk_pool[pd.to_numeric(gk_pool.get("minutes"), errors="coerce").fillna(0) >= 300]

    def pct(col: str, high: bool = True) -> float | None:
        if col not in gk_pool.columns:
            return None
        return _series_pct(gk_pool[col], row.get(col), high)

    parts = [
        (pct("gk_clean_sheets"), 0.33),
        (pct("gk_cs_pct"), 0.22),
        (pct("gk_save_pct"), 0.15),
        (pct("gk_high_claims_per90"), 0.10),
        (pct("gk_runs_out_per90"), 0.08),
        (pct("minutes"), 0.12),
    ]
    score = _blend_pcts(parts)
    if score is None:
        return base

    # GK raw percentile is very team-context sensitive: clean sheets and save volume
    # can punish good keepers on weaker teams. Convert it to a bounded power scale
    # before blending so established PL starters do not collapse into 50s.
    perf = _power_from_pct(score, 58, 92)
    minutes = float(row.get("minutes") or 0)
    weight = min(0.48, 0.22 + min(1.0, minutes / 2500) * 0.26)
    out = (1 - weight) * base + weight * perf

    clean_sheets = pd.to_numeric(gk_pool.get("gk_clean_sheets"), errors="coerce").dropna()
    if minutes >= 1800 and pd.notna(row.get("gk_clean_sheets")) and not clean_sheets.empty:
        if float(row.get("gk_clean_sheets")) >= float(clean_sheets.max()):
            out += 4
        elif float(row.get("gk_clean_sheets")) >= float(clean_sheets.quantile(0.85)):
            out += 2

    floor = 58 if minutes >= 900 else 50
    if minutes >= 1800:
        floor = max(floor, min(72, base - 4))

    return int(max(floor, min(95, round(out))))


def season_achievement_bonus(row: pd.Series, player_pool: pd.DataFrame) -> float:
    """포지션별 시즌 업적 보너스.

    특정 선수 수동 보정이 아니라 리그 내 순위/상위 백분위에 따라 작은 보너스를 준다.
    OVR 본체는 여전히 시장가치+평점 기반이고, 이 함수는 득점왕/도움왕/수비 리더처럼
    시즌 서사가 분명한 선수들이 과소평가되지 않게 보정하는 레이어다.
    """
    minutes = float(row.get("minutes") or 0)
    if minutes < 900:
        return 0.0

    pool = player_pool[pd.to_numeric(player_pool.get("minutes"), errors="coerce").fillna(0) >= 900].copy()
    pos = str(row.get("pos", "")).upper()
    fl = str(row.get("fl_group", "")).upper()
    is_def = "DF" in pos or fl in {"CB", "FB", "RB", "LB"}
    is_mid = "MF" in pos or fl in {"DM", "CM", "AM"}
    is_att = "FW" in pos or fl in {"ST", "W", "RW", "LW"}

    def rank_bonus(col: str, top1: float, top5: float, top10: float = 0.0) -> float:
        if col not in pool.columns or pd.isna(row.get(col)):
            return 0.0
        s = pool[["player", col]].copy()
        s[col] = pd.to_numeric(s[col], errors="coerce")
        s = s.dropna().drop_duplicates("player").set_index("player")[col]
        player = row.get("player")
        if s.empty:
            return 0.0
        rank = int(s.rank(ascending=False, method="min").get(player, 9999))
        if rank == 1:
            return top1
        if rank <= 5:
            return top5
        if rank <= 10:
            return top10
        return 0.0

    def pct_bonus(col: str, p95: float, p85: float = 0.0) -> float:
        if col not in pool.columns:
            return 0.0
        pct = _series_pct(pool[col], row.get(col), True)
        if pct is None:
            return 0.0
        if pct >= 0.95:
            return p95
        if pct >= 0.85:
            return p85
        return 0.0

    bonus = 0.0
    goals = float(row.get("goals") or 0)
    assists = float(row.get("assists") or 0)
    row_ga = goals + assists
    pool_ga = pd.to_numeric(pool.get("goals"), errors="coerce").fillna(0) + pd.to_numeric(
        pool.get("assists"), errors="coerce"
    ).fillna(0)
    pool_ga.index = pool["player"]
    if not pool_ga.empty:
        ga_rank = int(pool_ga.rank(ascending=False, method="min").get(row.get("player"), 9999))
        if ga_rank == 1:
            bonus += 2.0
        elif ga_rank <= 5:
            bonus += 1.2
        elif ga_rank <= 10:
            bonus += 0.6

    squad = row.get("squad")
    player = row.get("player")
    if squad is not None and "squad" in pool.columns:
        squad_pool = pool[pool["squad"] == squad].copy()
        if len(squad_pool) >= 8:
            squad_players = squad_pool["player"].astype(str)
            squad_mins = pd.to_numeric(squad_pool.get("minutes"), errors="coerce").fillna(0)
            squad_mins.index = squad_players
            squad_ratings = pd.to_numeric(squad_pool.get("ss_rating"), errors="coerce")
            squad_ratings.index = squad_players
            minute_rank = int(squad_mins.rank(ascending=False, method="min").get(str(player), 9999))
            rating_pct = _series_pct(squad_ratings, row.get("ss_rating"), True)
            if minutes >= 2700 and minute_rank <= 2:
                bonus += 0.8
            elif minutes >= 2200 and minute_rank <= 4:
                bonus += 0.4
            if rating_pct is not None and rating_pct >= 0.85 and minutes >= 1800:
                bonus += 0.8
            elif rating_pct is not None and rating_pct >= 0.70 and minutes >= 1800:
                bonus += 0.4

            if player is not None:
                squad_ga = (
                    pd.to_numeric(squad_pool.get("goals"), errors="coerce").fillna(0)
                    + pd.to_numeric(squad_pool.get("assists"), errors="coerce").fillna(0)
                )
                squad_ga.index = squad_players
                ga_team_rank = int(squad_ga.rank(ascending=False, method="min").get(str(player), 9999))
                if row_ga >= 12 and ga_team_rank == 1:
                    bonus += 1.6
                elif row_ga >= 12 and ga_team_rank <= 2:
                    bonus += 1.3
                elif row_ga >= 8 and ga_team_rank <= 2:
                    bonus += 0.8

    if is_att:
        bonus += rank_bonus("goals", 3.0, 2.0, 1.0)
        bonus += rank_bonus("assists", 1.4, 0.9, 0.4)
        bonus += pct_bonus("npxg_p90", 1.0, 0.5)
    elif is_mid:
        bonus += rank_bonus("assists", 3.0, 2.0, 1.0)
        bonus += pct_bonus("key_passes_per90", 1.4, 0.7)
        bonus += pct_bonus("big_chances_created_per90", 1.4, 0.7)
        bonus += pct_bonus("final_third_passes_per90", 0.8, 0.4)
        bonus += pct_bonus("tackles_won_per90", 0.6, 0.3)
        bonus += pct_bonus("interceptions_per90", 0.6, 0.3)
    elif is_def:
        bonus += pct_bonus("interceptions_per90", 1.2, 0.6)
        bonus += pct_bonus("tackles_won_per90", 1.0, 0.5)
        bonus += pct_bonus("aerial_won_pct", 0.9, 0.4)
        bonus += pct_bonus("clearances_per90", 0.8, 0.4)
        bonus += rank_bonus("gk_clean_sheets", 1.4, 0.8, 0.4)
    else:
        bonus += rank_bonus("goals", 1.5, 0.8, 0.4)
        bonus += rank_bonus("assists", 1.5, 0.8, 0.4)

    return min(4.0, bonus)


def top_strengths(prow: pd.Series, n: int = 3) -> list[tuple[str, int]]:
    # LABELS에 있고 prow에도 존재하는 피처만 사용 — 새 피처 추가 시 KeyError 방지
    avail = [f for f in FEATURES if f in LABELS and f in prow.index and pd.notna(prow.get(f))]
    s = prow[avail].sort_values(ascending=False)
    return [(LABELS[f], round(prow[f] * 100)) for f in s.index[:n]]
