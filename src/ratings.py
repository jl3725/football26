"""
팀 레이팅 순수 로직 — streamlit 비의존 단일 소스.

유저가 정밀 튜닝한 team_ratings 블렌드 공식을 UI(streamlit)에서 분리해, 이 모듈을
Streamlit·FastAPI 양쪽이 공유하게 한다. 여기 있는 저수준 헬퍼(_power_from_* 등)는
src/ui/metrics.py·overview.py 의 것과 동일한 구현(동작 보존). 이 모듈은 pandas/math
외 의존이 없다.

핵심: compute_team_ratings(team, full_df, standings, unit_metrics)
      → [(label, value, sub), ...] (종합/폼/공격/미드/수비)
"""
from __future__ import annotations

import math

import pandas as pd

# ── 선수 OVR (metrics.py 와 동일) ────────────────────────────────────
_OVR_LO_R, _OVR_LO_O = 6.3, 60
_OVR_HI_R, _OVR_HI_O = 7.7, 92
_OVR_SLOPE = (_OVR_HI_O - _OVR_LO_O) / (_OVR_HI_R - _OVR_LO_R)


def ovr_from_rating(ss) -> int | None:
    if ss is None or pd.isna(ss):
        return None
    ovr = _OVR_LO_O + _OVR_SLOPE * (float(ss) - _OVR_LO_R)
    return int(max(40, min(99, round(ovr))))


def ovr_from_value(v):
    if v is None or pd.isna(v) or float(v) <= 0:
        return None
    return 13.04 * math.log10(float(v)) - 16.24


def perf_ovr(ss_rating, goals=0, assists=0):
    base = ovr_from_rating(ss_rating)
    if base is None:
        return None
    g = float(goals) if (goals is not None and not pd.isna(goals)) else 0.0
    a = float(assists) if (assists is not None and not pd.isna(assists)) else 0.0
    return base + min(8.0, (g + a) * 0.4)


def player_ovr(value, ss_rating=None, minutes=0, goals=0, assists=0) -> int:
    vov = ovr_from_value(value)
    pov = perf_ovr(ss_rating, goals, assists)
    if vov is None and pov is None:
        return 60
    if vov is None:
        return int(max(48, min(95, round(pov))))
    if pov is None:
        return int(max(48, min(95, round(vov))))
    rel = min(1.0, (float(minutes) if (minutes and not pd.isna(minutes)) else 0) / 1200)
    w = 0.5 * rel
    return int(max(48, min(95, round((1 - w) * vov + w * pov))))


# ── 저수준 헬퍼 (metrics.py 와 동일) ─────────────────────────────────
def _rank_pct(values: pd.Series, team: str, high_is_good: bool = True) -> float | None:
    values = values.dropna()
    if values.empty or team not in values.index:
        return None
    return float(values.rank(ascending=high_is_good, pct=True)[team])


def _blend_scores(parts: list[tuple[int | float | None, float]]) -> int | None:
    valid = [(float(v), float(w)) for v, w in parts if v is not None and not pd.isna(v) and w > 0]
    if not valid:
        return None
    total = sum(w for _, w in valid)
    return int(max(1, min(99, round(sum(v * w for v, w in valid) / total))))


def _power_from_pct(pct: float | None, lo: int = 58, hi: int = 94) -> int | None:
    if pct is None or pd.isna(pct):
        return None
    pct = max(0.0, min(1.0, float(pct)))
    return int(round(lo + pct * (hi - lo)))


def _power_from_index(value: int | float | None, lo: int = 58, hi: int = 94) -> int | None:
    if value is None or pd.isna(value):
        return None
    pct = (max(1.0, min(99.0, float(value))) - 1.0) / 98.0
    return int(round(lo + pct * (hi - lo)))


# ── 팀 지표 헬퍼 (overview.py 와 동일) ───────────────────────────────
def _full_team_metric_pct(team: str, full_df: pd.DataFrame | None, col: str,
                          high_is_good: bool = True) -> float | None:
    if full_df is None or col not in full_df.columns or "squad" not in full_df.columns:
        return None
    vals = full_df.groupby("squad")[col].mean(numeric_only=True)
    return _rank_pct(vals, team, high_is_good=high_is_good)


def _weighted_team_metric_pct(team: str, full_df: pd.DataFrame | None, col: str,
                              high_is_good: bool = True,
                              min_minutes: int = 300) -> float | None:
    if (
        full_df is None
        or col not in full_df.columns
        or "squad" not in full_df.columns
        or "minutes" not in full_df.columns
    ):
        return None
    df = full_df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df = df[df[col].notna() & (df["minutes"] >= min_minutes)]
    if df.empty:
        return _full_team_metric_pct(team, full_df, col, high_is_good=high_is_good)
    scores = {}
    for squad, rows in df.groupby("squad"):
        weights = rows["minutes"].clip(lower=1, upper=3000) ** 0.5
        scores[squad] = float((rows[col] * weights).sum() / weights.sum())
    return _rank_pct(pd.Series(scores), team, high_is_good=high_is_good)


def _role_quality_pct(team: str, full_df: pd.DataFrame | None, role: str) -> float | None:
    if full_df is None or "squad" not in full_df.columns:
        return None
    required = {"minutes", "ss_rating", "market_value_eur", "goals", "assists"}
    if not required.issubset(full_df.columns):
        return None

    pool = full_df[full_df["minutes"].fillna(0) > 0].copy()
    if pool.empty:
        return None
    pos = pool.get("pos", pd.Series("", index=pool.index)).fillna("").str.upper()
    fl = pool.get("fl_group", pd.Series("", index=pool.index)).fillna("").str.upper()

    if role == "attack":
        pool = pool[fl.isin(["ST", "W", "RW", "LW", "AM"]) | pos.str.contains("FW", na=False)]
        top_n = 6
    elif role == "midfield":
        pool = pool[fl.isin(["DM", "CM", "AM"]) | pos.str.contains("MF", na=False)]
        top_n = 7
    elif role == "defense":
        pool = pool[fl.isin(["CB", "FB", "RB", "LB", "GK"]) |
                    pos.str.contains("DF|GK", regex=True, na=False)]
        top_n = 7
    else:
        top_n = 15

    if pool.empty:
        return None
    pool["_ovr"] = pool.apply(
        lambda r: player_ovr(r.get("market_value_eur"), r.get("ss_rating"),
                             r.get("minutes"), r.get("goals"), r.get("assists")),
        axis=1,
    )

    scores = {}
    for squad, rows in pool.groupby("squad"):
        eligible = rows[rows["minutes"].fillna(0) >= 300]
        if eligible.empty:
            eligible = rows
        top = eligible.sort_values("_ovr", ascending=False).head(top_n).copy()
        weights = top["minutes"].fillna(0).clip(lower=1, upper=2500) ** 0.5
        scores[squad] = float((top["_ovr"] * weights).sum() / weights.sum())
    return _rank_pct(pd.Series(scores), team, high_is_good=True)


# ── 팀 레이팅 (overview.team_ratings 의 unit_metrics 분기 verbatim) ──
def compute_team_ratings(team: str, full_df, standings, unit_metrics) -> list[tuple] | None:
    """
    [(label, value, sub), ...] = 종합/폼/공격/미드/수비. unit_metrics 에 team 이
    없으면 None (호출측 폴백). unit_metrics 는 squad 인덱스 기대.
    """
    if unit_metrics is None or team not in getattr(unit_metrics, "index", []):
        return None
    row = unit_metrics.loc[team]

    def iv(col: str) -> int:
        v = row.get(col)
        return int(v) if pd.notna(v) else 1

    rank = None
    form_idx = None
    gf = ga = gd = points = played = None
    gf_rank_idx = ga_rank_idx = None
    if standings is not None and (standings["squad"] == team).any():
        srow = standings[standings["squad"] == team].iloc[0]
        rank = int(srow["rank"])
        gf = float(srow.get("gf", 0))
        ga = float(srow.get("ga", 0))
        gd = float(srow.get("gd", 0))
        points = float(srow.get("points", 0))
        played = float(srow.get("played", 38) or 38)
        st = standings.set_index("squad")
        gf_rank_idx = _power_from_pct(_rank_pct(st["gf"], team, high_is_good=True), 60, 95)
        ga_rank_idx = _power_from_pct(_rank_pct(st["ga"], team, high_is_good=False), 62, 95)
        ppg_power = max(52, min(95, 56 + ((points / max(played, 1)) / 3.0) * 40))
        gd_power = max(52, min(95, 72 + (gd / max(played, 1)) * 11))
        form_idx = _blend_scores([(ppg_power, 0.62), (gd_power, 0.38)])

    squad_idx = _power_from_pct(_role_quality_pct(team, full_df, "overall"), 62, 95)
    attack_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "attack"), 60, 95)
    midfield_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "midfield"), 60, 95)
    defense_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "defense"), 60, 95)
    attack_output = max(48, min(93, 48 + ((gf or 0) / max(played or 38, 1)) * 16)) if gf is not None else _power_from_index(iv("attack_output_index"), 52, 92)
    defense_output = max(50, min(95, 93 - ((ga or 0) / max(played or 38, 1)) * 17)) if ga is not None else _power_from_index(iv("defense_output_index"), 54, 95)
    attack_result = _blend_scores([
        (attack_output, 0.52),
        (gf_rank_idx, 0.48),
    ]) or attack_output
    shot_power = _blend_scores([
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "npxg_p90"), 58, 95), 0.60),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "sot_per90"), 58, 95), 0.40),
    ])
    progression_power = _blend_scores([
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "final_third_passes_per90"), 58, 95), 0.45),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "key_passes_per90"), 58, 95), 0.30),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "xg_chain_p90"), 58, 95), 0.25),
    ])
    midfield_recovery_power = _blend_scores([
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "recoveries_per90"), 58, 95), 0.42),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "possession_won_att_per90"), 58, 95), 0.26),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "tackles_won_per90_ss"), 58, 95), 0.18),
        (_power_from_pct(_weighted_team_metric_pct(team, full_df, "interceptions_per90_ss"), 58, 95), 0.14),
    ])
    pass_stability_power = _power_from_pct(_weighted_team_metric_pct(team, full_df, "pass_pct"), 58, 95)
    defense_result = _blend_scores([
        (defense_output, 0.55),
        (ga_rank_idx, 0.45),
    ]) or defense_output
    set_piece_power = _power_from_index(iv("set_piece_attack_index"), 58, 95)
    pressure_power = _power_from_index(iv("pressing_index"), 58, 95)

    attack = _blend_scores([
        (attack_result, 0.42),
        (shot_power, 0.28),
        (attack_quality_idx, 0.16),
        (set_piece_power, 0.08),
        (pressure_power, 0.06),
    ]) or iv("attack_index")
    midfield = _blend_scores([
        (midfield_quality_idx, 0.24),
        (_blend_scores([
            (_power_from_index(iv("midfield_creativity_index"), 58, 95), 0.34),
            (progression_power, 0.42),
            (_power_from_index(iv("attack_creation_index"), 58, 95), 0.24),
        ]), 0.31),
        (_blend_scores([(_power_from_index(iv("midfield_control_index"), 58, 95), 0.48), (pass_stability_power, 0.52)]), 0.19),
        (_blend_scores([(pressure_power, 0.44), (midfield_recovery_power, 0.56)]), 0.18),
        (form_idx, 0.08),
    ]) or iv("midfield_index")
    defense = _blend_scores([
        (defense_quality_idx, 0.24),
        (defense_result, 0.46),
        (_power_from_index(iv("defense_box_aerial_index"), 58, 95), 0.12),
        (_power_from_index(iv("defense_disruption_index"), 58, 95), 0.10),
        (_power_from_index(iv("discipline_index"), 58, 95), 0.08),
    ]) or iv("defense_index")
    if ga_rank_idx is not None:
        elite_defense_lift = max(0, (ga_rank_idx - 88) / 6) * min(3.0, max(0, (defense_quality_idx - 76) / 6))
        defense = min(95, defense + elite_defense_lift)
    attack = int(max(1, min(99, attack - 3)))
    midfield = int(max(1, min(99, midfield + 1)))
    unit_idx = _blend_scores([(attack, 0.33), (midfield, 0.34), (defense, 0.33)])
    overall = _blend_scores([
        (squad_idx, 0.44),
        (unit_idx, 0.34),
        (form_idx, 0.22),
    ]) or iv("overall_index")

    return [
        ("종합 지수", overall, f"Squad OVR · Form {int(round(form_idx or overall))}"),
        ("시즌 폼", form_idx or overall, f"리그 {rank}위 · 승점 {int(points or 0)}" if rank else "시즌 결과"),
        ("공격 지수", attack,
         f"득점 {int(gf) if gf is not None else '-'} / 창출 {iv('attack_creation_index')} / 세트피스 {iv('set_piece_attack_index')}"),
        ("미드필드 지수", midfield,
         f"장악 {iv('midfield_control_index')} / 창의성 {iv('midfield_creativity_index')} / 압박 {iv('pressing_index')}"),
        ("수비 지수", defense,
         f"실점 {int(ga) if ga is not None else '-'} / 저지 {iv('defense_disruption_index')} / 징계관리 {iv('discipline_index')}"),
    ]
