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


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLAYERS = DATA / "players_full_2025_2026.csv"
STANDINGS = DATA / "standings_2025_2026.csv"
STATBUNKER_TEAMS = DATA / "statbunker_team_stats_2025_2026.csv"
OUT = DATA / "team_unit_metrics_2025_2026.csv"


HIGH_GOOD = True
LOW_GOOD = False


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


def pct_map(values: dict[str, float | None], high_good: bool = True) -> dict[str, float | None]:
    valid = [(team, value) for team, value in values.items() if value is not None]
    valid.sort(key=lambda x: x[1], reverse=high_good)
    n = len(valid)
    if n <= 1:
        return {team: 1.0 if value is not None else None for team, value in values.items()}
    out = {team: None for team in values}
    for i, (team, _value) in enumerate(valid):
        out[team] = 1 - i / (n - 1)
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


def idx(value: float | None) -> int:
    if value is None:
        return 0
    return max(1, min(99, round(1 + value * 98)))


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
    ctx_path = DATA / "team_comp_context_2025_2026.csv"
    if ctx_path.exists():
        with ctx_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                comp_context[row["squad"]] = {
                    "european_games": int(float(row.get("euro_games", 0) or 0)),
                    "domestic_cup_games": int(float(row.get("domestic_cup_games", 0) or 0)),
                    "extra_games": int(float(row.get("extra_games", 0) or 0)),
                    "total_games_approx": int(float(row.get("total_games_approx", 0) or 0)),
                }

    teams = sorted({r["squad"] for r in players})
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
        raw[team] = {
            "points": as_float(s.get("points")),
            "gd": as_float(s.get("gd")),
            "gf": as_float(s.get("gf")),
            "ga": as_float(s.get("ga")),
            "non_penalty_set_piece_goals": as_float(sb.get("non_penalty_set_piece_goals")),
            "dead_ball_goals_including_pens": as_float(sb.get("dead_ball_goals_including_pens")),
            "corner_goals": as_float(sb.get("corner_goals")),
            "free_kick_family_goals": sum(v for v in [
                as_float(sb.get("free_kick_goals")) or 0,
                as_float(sb.get("direct_free_kick_goals")) or 0,
                as_float(sb.get("throw_in_goals")) or 0,
            ]),
            "penalties_for": as_float(sb.get("penalties_for")),
            "penalties_against": as_float(sb.get("penalties_against")),
            "yellow_cards_per_match": as_float(sb.get("yellow_cards_per_match")),
            "red_card_points": sum(v for v in [
                as_float(sb.get("red_cards")) or 0,
                as_float(sb.get("second_yellow_reds")) or 0,
            ]),
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
