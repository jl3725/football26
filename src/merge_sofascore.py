"""SofaScore 세부 스탯을 기존 players_full 에 '추가 병합'(비파괴) — 수비지표 지수용.

fetch_understat 는 FBref 베이스에서 players_full 을 재구성하며 tm_photo/계약 등을 잃는다.
이 스크립트는 이미 만들어진 players_full 에 SofaScore 파생 컬럼(태클·인터셉트·볼리커버리·
경합승·클리어·블록 등)만 얹어, 사진/계약을 보존하면서 team_unit_metrics 압박·볼경합·
수비교란 지수가 계산되게 한다.

매칭은 2-패스: (1) 팀+전체이름(악센트 무시) 정확 매칭 → (2) 실패 시 팀+성(last name,
그 팀에서 유일할 때만) 폴백. 이름 변형(Dimitris↔Dimitrios, Jean Mattéo↔jean-matteo)을
회복해 커버리지를 끌어올린다.

사용:  FB_LEAGUE=Bundesliga python src/merge_sofascore.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import ACTIVE_LEAGUE, data_path  # noqa: E402

_SS_COLS = ["ss_rating", "pass_pct", "long_ball_pct", "cross_acc_pct", "dribble_success_pct",
            "tackles_won_pct", "aerial_won_pct", "ground_duels_won_pct", "total_duels_won_pct",
            "key_passes_per90", "big_chances_created_per90", "clearances_per90", "blocked_shots_per90",
            "outfielder_blocks_per90", "interceptions_per90_ss", "recoveries_per90", "aerial_won_per90",
            "tackles_won_per90_ss", "ground_duels_won_per90", "errors_per90", "possession_won_att_per90",
            "successful_dribbles_per90", "final_third_passes_per90", "gk_saves_per90", "gk_clean_sheets",
            "gk_high_claims_per90", "gk_runs_out_per90", "gk_punches_per90", "gk_crosses_not_claimed",
            "ss_appearances", "ss_minutes"]


# FBref(이 PC 주간 빌드)에서 오던 횟수 지표 — 같은 뜻의 Sofascore 원본 합계(매일)로 다시 계산한다.
# 2026-10-20 사용자: "세부 스탯도 매일". Sofascore 출전 분이 FBref 분 이상(= 더 최신)일 때만 바꾸고 fb_counts_src 에 표시.
# (xG 계열은 모델이 달라 Understat 을 매일 따로 받는다 — src/refresh_understat.py)
_FB_FROM_SS = {"sh_per90": "totalShots", "sot_per90": "shotsOnTarget", "crosses_per90": "totalCross",
               "fouls_per90": "fouls", "fouled_per90": "wasFouled", "tackles_won_per90": "tacklesWon",
               "interceptions_per90": "interceptions", "ast_per90": "assists"}


def fresh_fb_counts(r, s) -> dict | None:
    """선수 행 r(FBref 값) + Sofascore 원본 s → 새 FBref 횟수 per90(더 최신일 때만, 아니면 None).
    npg_per90 = (Sofascore 골 − 지난 FBref 기준 페널티 골) / 90분 — 페널티 골은 주간 값(골 − npg×분)으로 추정."""
    ss_min, fb_min = _num(s.get("minutesPlayed")), _num(r.get("minutes"))
    if ss_min <= 0 or ss_min < fb_min:
        return None
    n90 = ss_min / 90.0
    out = {c: round(_num(s.get(k)) / n90, 3) for c, k in _FB_FROM_SS.items() if s.get(k) is not None and s.get(k) == s.get(k)}
    pens = max(0.0, round(_num(r.get("goals")) - _num(r.get("npg_per90")) * fb_min / 90.0))
    if s.get("goals") is not None and s.get("goals") == s.get("goals"):
        out["npg_per90"] = round(max(0.0, _num(s.get("goals")) - pens) / n90, 3)
    return out


def _nf(team, player):
    return f"{unidecode(str(team)).lower().strip()}|{unidecode(str(player)).lower().strip()}"


def _lk(team, player):
    toks = unidecode(str(player)).lower().strip().split()
    return f"{unidecode(str(team)).lower().strip()}|{toks[-1] if toks else ''}"


def _vals(s):
    def g(name):
        return s.get(name)
    mn = _num(g("minutesPlayed"))
    n90 = mn / 90.0 if mn else np.nan

    def per90(name):
        v = _num(g(name))
        return round(v / n90, 3) if n90 and n90 > 0 else np.nan

    return {
        "ss_rating": g("rating"), "pass_pct": g("accuratePassesPercentage"),
        "long_ball_pct": g("accurateLongBallsPercentage"), "cross_acc_pct": g("accurateCrossesPercentage"),
        "dribble_success_pct": g("successfulDribblesPercentage"), "tackles_won_pct": g("tacklesWonPercentage"),
        "aerial_won_pct": g("aerialDuelsWonPercentage"), "ground_duels_won_pct": g("groundDuelsWonPercentage"),
        "total_duels_won_pct": g("totalDuelsWonPercentage"),
        "key_passes_per90": per90("keyPasses"), "big_chances_created_per90": per90("bigChancesCreated"),
        "clearances_per90": per90("clearances"), "blocked_shots_per90": per90("blockedShots"),
        "outfielder_blocks_per90": per90("outfielderBlocks"), "interceptions_per90_ss": per90("interceptions"),
        "recoveries_per90": per90("ballRecovery"), "aerial_won_per90": per90("aerialDuelsWon"),
        "tackles_won_per90_ss": per90("tacklesWon"), "ground_duels_won_per90": per90("groundDuelsWon"),
        "errors_per90": round((_num(g("errorLeadToGoal")) + _num(g("errorLeadToShot"))) / n90, 3) if n90 else np.nan,
        "possession_won_att_per90": per90("possessionWonAttThird"),
        "successful_dribbles_per90": per90("successfulDribbles"),
        "final_third_passes_per90": per90("accurateFinalThirdPasses"),
        "gk_saves_per90": per90("saves"), "gk_clean_sheets": g("cleanSheet"),
        "gk_high_claims_per90": per90("highClaims"), "gk_runs_out_per90": per90("runsOut"),
        "gk_punches_per90": per90("punches"), "gk_crosses_not_claimed": g("crossesNotClaimed"),
        "ss_appearances": g("appearances"), "ss_minutes": g("minutesPlayed"),
    }


def _num(v):
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pf_path = data_path("players_full")
    ss_path = data_path("players_sofascore_stats")
    if not pf_path.exists() or not ss_path.exists():
        print(f"[merge-ss] 파일 없음: {pf_path if not pf_path.exists() else ss_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(pf_path)
    ss = pd.read_csv(ss_path)

    full_map, last_map, last_dup = {}, {}, set()
    for _, s in ss.iterrows():
        vals = {**_vals(s), "_raw": s}
        full_map[_nf(s["squad"], s["player"])] = vals
        lk = _lk(s["squad"], s["player"])
        if lk in last_map:
            last_dup.add(lk)
        else:
            last_map[lk] = vals
    for k in last_dup:                       # 같은 팀 동성이인 → 폴백서 제외
        last_map.pop(k, None)

    rows, byfull, bylast, fresh = [], 0, 0, 0
    df["fb_counts_src"] = df.get("fb_counts_src", pd.Series("fbref", index=df.index)).fillna("fbref")
    for i, r in df.iterrows():
        fk = _nf(r["squad"], r["player"])
        v = full_map.get(fk)
        if v is not None:
            byfull += 1
        else:
            v = last_map.get(_lk(r["squad"], r["player"]))
            if v is not None:
                bylast += 1
        rows.append(v or {})
        fc = fresh_fb_counts(r, v["_raw"]) if v is not None else None
        if fc:
            for c, val in fc.items():
                if c in df.columns:
                    df.at[i, c] = val
            df.at[i, "fb_counts_src"] = "sofascore"
            fresh += 1
    add_df = pd.DataFrame(rows, index=df.index, columns=_SS_COLS)

    df = df.drop(columns=[c for c in _SS_COLS if c in df.columns])
    out = pd.concat([df, add_df], axis=1)
    rate = out["ss_rating"].notna().mean() * 100
    out.to_csv(pf_path, index=False, encoding="utf-8")
    print(f"[merge-ss] {ACTIVE_LEAGUE}: {pf_path.name} · 매칭 {rate:.0f}% "
          f"(정확 {byfull} + 성폴백 {bylast}) · FBref 횟수 지표 Sofascore 최신화 {fresh}명 · {len(out.columns)}컬럼")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
