"""
Build derived team unit metrics from the current 2025/26 player dataset.

League-focused metrics (Attack/Mid/Def indices etc.) are computed relative to
other EPL teams.

Additionally (Option A), we attach multi-competition context from fl_matches:
- european_games, domestic_cup_games, extra_games, total_games_approx

This allows the UI to understand schedule load for European/cup teams (Arsenal,
Villa, etc.) without polluting the core league percentiles.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from leagues import data_path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLAYERS = data_path("players_full")
SCHEDULE_FULL = data_path("schedule_full")
STANDINGS = data_path("standings")
STATBUNKER_TEAMS = data_path("statbunker_team_stats")
OUT = data_path("team_unit_metrics")


HIGH_GOOD = True
LOW_GOOD = False



def comp_context_from_schedule() -> dict[str, dict]:
    """ESPN schedule_full(리그+유럽+국내컵)의 완료 경기로 팀별 대회 부담을 센다 — 전 리그 공용."""
    if not SCHEDULE_FULL.exists():
        return {}
    games: dict[str, dict] = defaultdict(lambda: {"league": 0, "euro": 0, "cup": 0})
    with SCHEDULE_FULL.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("status") != "completed":
                continue
            code = r.get("comp_code") or ""
            kind = "euro" if code.startswith("uefa.") else ("league" if code.endswith(".1") else "cup")
            games[r["squad"]][kind] += 1
    return {
        sq: {"european_games": g["euro"], "domestic_cup_games": g["cup"],
             "extra_games": g["euro"] + g["cup"], "total_games_approx": g["league"] + g["euro"] + g["cup"]}
        for sq, g in games.items()
    }

def as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    if math.isnan(v):
        return None
    return v


def player_ovr(row: dict) -> float | None:
    ss = as_float(row.get("ss_rating"))
    if ss is None:
        return None
    # Same broad scale as app.py: 6.3 -> 60, 7.7 -> 92, clamped.
    ovr = 60 + (ss - 6.3) * ((92 - 60) / (7.7 - 6.3))
    mv = as_float(row.get("market_value_eur"))
    minutes = as_float(row.get("minutes")) or 0
    if mv and mv >= 50_000_000:
        ovr += 3
    elif mv and mv >= 25_000_000:
        ovr += 1.5
    if minutes < 450:
        ovr -= 2
    return max(40, min(99, ovr))


def norm_role(row: dict) -> str:
    pos = (row.get("pos") or "").upper()
    fl = (row.get("fl_group") or "").upper()
    if "GK" in pos or fl == "GK":
        return "gk"
    if fl in {"CB", "FB", "RB", "LB"} or "DF" in pos:
        return "defense"
    if fl in {"DM", "CM", "AM"} or "MF" in pos:
        return "midfield"
    if fl in {"ST", "W", "RW", "LW"} or "FW" in pos:
        return "attack"
    return "other"


def weighted_mean(rows: list[dict], cols: list[str]) -> float | None:
    total = 0.0
    weight = 0.0
    for row in rows:
        minutes = as_float(row.get("minutes")) or 0
        if minutes <= 0:
            continue
        for col in cols:
            v = as_float(row.get(col))
            if v is None:
                continue
            total += v * minutes
            weight += minutes
    return total / weight if weight else None


def role_quality(rows: list[dict], role: str, top_n: int) -> float | None:
    pool = [r for r in rows if norm_role(r) == role and (as_float(r.get("minutes")) or 0) > 0]
    scored = []
    for row in pool:
        ovr = player_ovr(row)
        if ovr is not None:
            minutes = as_float(row.get("minutes")) or 1
            scored.append((ovr, min(2500, max(1, minutes)) ** 0.5))
    scored = sorted(scored, key=lambda x: x[0], reverse=True)[:top_n]
    if not scored:
        return None
    total_w = sum(w for _, w in scored)
    return sum(v * w for v, w in scored) / total_w


# 시즌 초 표본 수축 — 리그 경기 수 g 일 때 백분위를 0.5 쪽으로 g/(g+SHRINK_GAMES) 만큼만 반영.
# (7경기면 0.64 → 최대 82 안팎. 시즌이 쌓일수록 1 에 가까워진다)
SHRINK_GAMES = 4.0
_SHRINK_W = 1.0


def pct_map(values: dict[str, float | None], high_good: bool = True) -> dict[str, float | None]:
    """리그 안 상대 위치(0~1). 예전엔 순위(1위=1.0)라 근소한 차이도 99/1 로 벌어지고 동률이 정렬 순서
    (=알파벳)대로 다른 값을 받았다 — 26/27 세트피스·규율 원천이 비어 전원 0 이던 때 알파벳 첫 팀이 99.
    이제 평균·표준편차 기준 z → 정규 누적확률(크기 반영·동률 동일), 값이 모두 같으면 0.5, 표본 수축 적용."""
    import math
    valid = [v for v in values.values() if v is not None]
    if len(valid) < 3:
        return {team: None for team in values}
    mean = sum(valid) / len(valid)
    sd = (sum((v - mean) ** 2 for v in valid) / (len(valid) - 1)) ** 0.5
    out: dict[str, float | None] = {}
    for team, v in values.items():
        if v is None:
            out[team] = None
            continue
        z = 0.0 if sd == 0 else (v - mean) / sd
        if not high_good:
            z = -z
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        out[team] = 0.5 + (p - 0.5) * _SHRINK_W
    return out


def blend(row: dict[str, float | None], parts: list[tuple[str, float]]) -> float | None:
    total = 0.0
    weight = 0.0
    for col, w in parts:
        v = row.get(col)
        if v is None:
            continue
        total += v * w
        weight += w
    return total / weight if weight else None


def idx(value: float | None) -> int | None:
    """0~1 → 1~99. 원천이 없으면 None(CSV 빈칸) — 예전엔 0 을 써 '0점'처럼 보였다."""
    if value is None:
        return None
    return max(1, min(99, round(1 + value * 98)))


def per_game(v: float | None, games: float | None) -> float | None:
    """누적 기록 → 경기당(경기 수가 다른 팀끼리 비교되게)."""
    if v is None or not games:
        return None
    return v / games


def sum_or_none(*vals: float | None) -> float | None:
    """여러 원천 합계 — 전부 없으면 None(0 으로 만들지 않는다)."""
    got = [v for v in vals if v is not None]
    return sum(got) if got else None


def main() -> int:
    with PLAYERS.open("r", encoding="utf-8-sig", newline="") as f:
        players = list(csv.DictReader(f))
    with STANDINGS.open("r", encoding="utf-8-sig", newline="") as f:
        standings = {r["squad"]: r for r in csv.DictReader(f)}
    statbunker = {}
    if STATBUNKER_TEAMS.exists():
        with STATBUNKER_TEAMS.open("r", encoding="utf-8-sig", newline="") as f:
            statbunker = {r["squad"]: r for r in csv.DictReader(f)}

    # Multi-competition context (Option A)
    # League metrics stay pure. We add extra context for heavy-schedule teams
    # (Champions League, Europa, FA Cup, etc.) from fl_matches data.
    comp_context = {}
    ctx_path = data_path("team_comp_context")   # 레거시: EPL 25/26 football-lineups 기반
    if not ctx_path.exists():
        comp_context = comp_context_from_schedule()   # 그 외: ESPN 전 대회 일정(schedule_full)
    else:
        with ctx_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                comp_context[row["squad"]] = {
                    "european_games": int(float(row.get("euro_games", 0) or 0)),
                    "domestic_cup_games": int(float(row.get("domestic_cup_games", 0) or 0)),
                    "extra_games": int(float(row.get("extra_games", 0) or 0)),
                    "total_games_approx": int(float(row.get("total_games_approx", 0) or 0)),
                }

    teams = sorted({r["squad"] for r in players})
    global _SHRINK_W
    played = sorted(as_float(r.get("played")) or 0 for r in standings.values())
    g_med = played[len(played) // 2] if played else 0
    _SHRINK_W = g_med / (g_med + SHRINK_GAMES) if g_med else 1.0
    print(f"[unit-metrics] 리그 경기 수 중앙값 {g_med:.0f} → 표본 수축 계수 {_SHRINK_W:.2f}")
    by_team = defaultdict(list)
    for row in players:
        by_team[row["squad"]].append(row)

    raw: dict[str, dict[str, float | None]] = {}
    for team in teams:
        rows = by_team[team]
        mids = [r for r in rows if norm_role(r) == "midfield"]
        atts = [r for r in rows if norm_role(r) == "attack"]
        defs = [r for r in rows if norm_role(r) in {"defense", "gk"}]
        s = standings.get(team, {})
        sb = statbunker.get(team, {})
        g = as_float(s.get("played"))
        raw[team] = {
            # 누적 기록은 경기당으로(시즌 초 경기 수가 1~2경기씩 다르다)
            "points": per_game(as_float(s.get("points")), g),
            "gd": per_game(as_float(s.get("gd")), g),
            "gf": per_game(as_float(s.get("gf")), g),
            "ga": per_game(as_float(s.get("ga")), g),
            # StatBunker(세트피스·페널티·카드) — 원천이 없으면 None 그대로(예전엔 0 으로 채워 가짜 순위)
            "non_penalty_set_piece_goals": per_game(as_float(sb.get("non_penalty_set_piece_goals")), g),
            "dead_ball_goals_including_pens": per_game(as_float(sb.get("dead_ball_goals_including_pens")), g),
            "corner_goals": per_game(as_float(sb.get("corner_goals")), g),
            "free_kick_family_goals": per_game(sum_or_none(
                as_float(sb.get("free_kick_goals")), as_float(sb.get("direct_free_kick_goals")),
                as_float(sb.get("throw_in_goals"))), g),
            "penalties_for": per_game(as_float(sb.get("penalties_for")), g),
            "penalties_against": per_game(as_float(sb.get("penalties_against")), g),
            "yellow_cards_per_match": as_float(sb.get("yellow_cards_per_match")),
            "red_card_points": per_game(sum_or_none(
                as_float(sb.get("red_cards")), as_float(sb.get("second_yellow_reds"))), g),
            "attack_quality_raw": role_quality(rows, "attack", 6),
            "midfield_quality_raw": role_quality(rows, "midfield", 7),
            "defense_quality_raw": role_quality(rows, "defense", 7),
            "attack_creation_raw": weighted_mean(atts + mids, [
                "xa_p90", "kp_p90", "key_passes_per90",
                "big_chances_created_per90", "xg_chain_p90",
            ]),
            "attack_threat_raw": weighted_mean(atts, [
                "npxg_p90", "shots_p90", "xg_chain_p90", "successful_dribbles_per90",
            ]),
            "midfield_control_raw": weighted_mean(mids, [
                "pass_pct", "final_third_passes_per90", "xg_chain_p90", "long_ball_pct",
            ]),
            "midfield_creativity_raw": weighted_mean(mids, [
                "xa_p90", "kp_p90", "key_passes_per90",
                "big_chances_created_per90", "final_third_passes_per90",
            ]),
            "mid_recoveries_raw": weighted_mean(mids, ["recoveries_per90"]),
            "mid_att3rd_won_raw": weighted_mean(mids, ["possession_won_att_per90"]),
            "mid_ground_duels_raw": weighted_mean(mids, ["ground_duels_won_per90"]),
            "mid_tackles_raw": weighted_mean(mids, ["tackles_won_per90_ss"]),
            "mid_interceptions_raw": weighted_mean(mids, ["interceptions_per90_ss"]),
            "def_tackles_raw": weighted_mean(defs + mids, ["tackles_won_per90_ss"]),
            "def_interceptions_raw": weighted_mean(defs + mids, ["interceptions_per90_ss"]),
            "def_recoveries_raw": weighted_mean(defs + mids, ["recoveries_per90"]),
            "def_blocks_raw": weighted_mean(defs + mids, ["blocked_shots_per90", "outfielder_blocks_per90"]),
            "defense_box_aerial_raw": weighted_mean(defs, [
                "clearances_per90", "aerial_won_per90", "aerial_won_pct",
                "gk_saves_per90", "gk_high_claims_per90",
            ]),
        }

        # Attach competition context (non-league games)
        ctx = comp_context.get(team, {})
        raw[team]["european_games"] = ctx.get("european_games", 0)
        raw[team]["domestic_cup_games"] = ctx.get("domestic_cup_games", 0)
        raw[team]["extra_games"] = ctx.get("extra_games", 0)
        raw[team]["total_games_approx"] = ctx.get("total_games_approx", 0)

    directions = {
        "points": HIGH_GOOD, "gd": HIGH_GOOD, "gf": HIGH_GOOD, "ga": LOW_GOOD,
        "non_penalty_set_piece_goals": HIGH_GOOD, "dead_ball_goals_including_pens": HIGH_GOOD,
        "corner_goals": HIGH_GOOD, "free_kick_family_goals": HIGH_GOOD,
        "penalties_for": HIGH_GOOD, "penalties_against": LOW_GOOD,
        "yellow_cards_per_match": LOW_GOOD, "red_card_points": LOW_GOOD,
        "attack_quality_raw": HIGH_GOOD, "midfield_quality_raw": HIGH_GOOD,
        "defense_quality_raw": HIGH_GOOD, "attack_creation_raw": HIGH_GOOD,
        "attack_threat_raw": HIGH_GOOD, "midfield_control_raw": HIGH_GOOD,
        "midfield_creativity_raw": HIGH_GOOD, "mid_recoveries_raw": HIGH_GOOD,
        "mid_att3rd_won_raw": HIGH_GOOD, "mid_ground_duels_raw": HIGH_GOOD,
        "mid_tackles_raw": HIGH_GOOD, "mid_interceptions_raw": HIGH_GOOD,
        "def_tackles_raw": HIGH_GOOD, "def_interceptions_raw": HIGH_GOOD,
        "def_recoveries_raw": HIGH_GOOD, "def_blocks_raw": HIGH_GOOD,
        "defense_box_aerial_raw": HIGH_GOOD,
    }
    percentiles = {col: pct_map({t: raw[t].get(col) for t in teams}, good)
                   for col, good in directions.items()}

    rows = []
    for team in teams:
        r = {"squad": team}
        for col in directions:
            r[f"{col}_pct"] = percentiles[col][team]

        # Competition context (raw counts, not percentiled)
        ctx = comp_context.get(team, {})
        r["european_games"] = ctx.get("european_games", 0)
        r["domestic_cup_games"] = ctx.get("domestic_cup_games", 0)
        r["extra_games"] = ctx.get("extra_games", 0)
        r["total_games_approx"] = ctx.get("total_games_approx", 0)

        r["attack_output_index"] = idx(blend(r, [("gf_pct", 0.55), ("attack_threat_raw_pct", 0.45)]))
        r["attack_creation_index"] = idx(blend(r, [
            ("attack_creation_raw_pct", 0.65), ("midfield_creativity_raw_pct", 0.20),
            ("attack_quality_raw_pct", 0.15),
        ]))
        r["set_piece_attack_index"] = idx(blend(r, [
            ("non_penalty_set_piece_goals_pct", 0.50), ("corner_goals_pct", 0.30),
            ("free_kick_family_goals_pct", 0.15), ("dead_ball_goals_including_pens_pct", 0.05),
        ]))
        r["penalty_control_index"] = idx(blend(r, [
            ("penalties_for_pct", 0.55), ("penalties_against_pct", 0.45),
        ]))
        r["attack_index"] = idx(blend(r, [
            ("gf_pct", 0.35), ("attack_creation_raw_pct", 0.30),
            ("attack_threat_raw_pct", 0.15), ("attack_quality_raw_pct", 0.10),
            ("non_penalty_set_piece_goals_pct", 0.10),
        ]))

        r["midfield_control_index"] = idx(blend(r, [
            ("midfield_control_raw_pct", 0.55), ("midfield_quality_raw_pct", 0.25),
            ("midfield_ball_winning_raw_pct", 0.20),
        ]))
        r["midfield_creativity_index"] = idx(blend(r, [
            ("midfield_creativity_raw_pct", 0.65), ("attack_creation_raw_pct", 0.20),
            ("midfield_quality_raw_pct", 0.15),
        ]))
        r["midfield_ball_winning_index"] = idx(blend(r, [
            ("mid_att3rd_won_raw_pct", 0.35), ("mid_recoveries_raw_pct", 0.20),
            ("mid_tackles_raw_pct", 0.15), ("mid_interceptions_raw_pct", 0.15),
            ("mid_ground_duels_raw_pct", 0.15),
        ]))
        r["pressing_index"] = idx(blend(r, [
            ("mid_att3rd_won_raw_pct", 0.70), ("mid_recoveries_raw_pct", 0.20),
            ("mid_tackles_raw_pct", 0.10),
        ]))
        r["midfield_index"] = idx(blend(r, [
            ("midfield_quality_raw_pct", 0.35), ("midfield_control_raw_pct", 0.25),
            ("midfield_creativity_raw_pct", 0.20), ("mid_att3rd_won_raw_pct", 0.07),
            ("mid_recoveries_raw_pct", 0.04), ("mid_tackles_raw_pct", 0.03),
            ("mid_interceptions_raw_pct", 0.03), ("mid_ground_duels_raw_pct", 0.03),
        ]))

        r["defense_output_index"] = idx(blend(r, [("ga_pct", 0.70), ("defense_quality_raw_pct", 0.30)]))
        r["defense_disruption_index"] = idx(blend(r, [
            ("def_tackles_raw_pct", 0.25), ("def_interceptions_raw_pct", 0.25),
            ("def_recoveries_raw_pct", 0.20), ("def_blocks_raw_pct", 0.20),
            ("mid_att3rd_won_raw_pct", 0.10),
        ]))
        r["defense_box_aerial_index"] = idx(blend(r, [
            ("defense_box_aerial_raw_pct", 0.60), ("ga_pct", 0.25),
            ("defense_quality_raw_pct", 0.15),
        ]))
        r["discipline_index"] = idx(blend(r, [
            ("yellow_cards_per_match_pct", 0.40), ("red_card_points_pct", 0.30),
            ("penalties_against_pct", 0.30),
        ]))
        r["defense_index"] = idx(blend(r, [
            ("ga_pct", 0.45), ("defense_quality_raw_pct", 0.25),
            ("def_tackles_raw_pct", 0.04), ("def_interceptions_raw_pct", 0.04),
            ("def_recoveries_raw_pct", 0.03), ("def_blocks_raw_pct", 0.03),
            ("mid_att3rd_won_raw_pct", 0.01), ("defense_box_aerial_raw_pct", 0.10),
            ("yellow_cards_per_match_pct", 0.03), ("red_card_points_pct", 0.01),
            ("penalties_against_pct", 0.01),
        ]))
        rows.append(r)

    # Re-rank composite indices so overall/attack/midfield/defense share the same
    # league-relative scale as their sub-indices.
    for composite in ["attack_index", "midfield_index", "defense_index"]:
        pcts = pct_map({r["squad"]: r[composite] for r in rows}, HIGH_GOOD)
        for r in rows:
            r[f"{composite}_pct"] = pcts[r["squad"]]
    for r in rows:
        r["overall_raw_index"] = idx(blend(r, [
            ("points_pct", 0.35), ("gd_pct", 0.20), ("attack_index_pct", 0.15),
            ("midfield_index_pct", 0.15), ("defense_index_pct", 0.15),
        ]))
    pcts = pct_map({r["squad"]: r["overall_raw_index"] for r in rows}, HIGH_GOOD)
    for r in rows:
        r["overall_index_pct"] = pcts[r["squad"]]
        r["overall_index"] = idx(r["overall_index_pct"])

    columns = [
        "squad", "overall_index", "attack_index", "attack_output_index",
        "attack_creation_index", "midfield_index", "midfield_control_index",
        "set_piece_attack_index", "penalty_control_index",
        "midfield_creativity_index", "midfield_ball_winning_index",
        "pressing_index",
        "defense_index", "defense_output_index", "defense_disruption_index",
        "defense_box_aerial_index", "discipline_index",
        # Multi-competition context (Option A - league metrics stay clean)
        "european_games", "domestic_cup_games", "extra_games", "total_games_approx",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in sorted(rows, key=lambda x: x["squad"]):
            writer.writerow({col: row.get(col, "") for col in columns})
    print(f"[OK] wrote {OUT} ({len(rows)} teams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
