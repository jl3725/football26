"""SofaScore 세부 스탯을 기존 players_full 에 '추가 병합'(비파괴) — 수비지표 지수용.

fetch_understat 는 FBref 베이스에서 players_full 을 재구성하며 tm_photo/계약 등을 잃는다.
이 스크립트는 이미 만들어진 players_full 에 SofaScore 파생 컬럼(태클·인터셉트·볼리커버리·
경합승·클리어·블록 등)만 얹어, 사진/계약을 보존하면서 team_unit_metrics 압박·볼경합·
수비교란 지수가 계산되게 한다.

사용:  FB_LEAGUE=Bundesliga python src/merge_sofascore.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import ACTIVE_LEAGUE, data_path  # noqa: E402
from fetch_understat import merge_key, sofascore_identity_for_merge  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pf_path = data_path("players_full")
    ss_path = data_path("players_sofascore_stats")
    if not pf_path.exists():
        print(f"[merge-ss] players_full 없음: {pf_path}", file=sys.stderr)
        return 1
    if not ss_path.exists():
        print(f"[merge-ss] sofascore 없음: {ss_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(pf_path)
    ss = pd.read_csv(ss_path)

    def c(name):
        return ss[name] if name in ss.columns else pd.Series([np.nan] * len(ss))

    m = c("minutesPlayed").replace(0, np.nan)
    n90 = m / 90.0
    ss_add = pd.DataFrame({
        "_key": [merge_key(*sofascore_identity_for_merge(t, p)) for t, p in zip(ss["squad"], ss["player"])],
        "ss_rating": c("rating"), "pass_pct": c("accuratePassesPercentage"),
        "long_ball_pct": c("accurateLongBallsPercentage"), "cross_acc_pct": c("accurateCrossesPercentage"),
        "dribble_success_pct": c("successfulDribblesPercentage"), "tackles_won_pct": c("tacklesWonPercentage"),
        "aerial_won_pct": c("aerialDuelsWonPercentage"), "ground_duels_won_pct": c("groundDuelsWonPercentage"),
        "total_duels_won_pct": c("totalDuelsWonPercentage"),
        "key_passes_per90": c("keyPasses") / n90, "big_chances_created_per90": c("bigChancesCreated") / n90,
        "clearances_per90": c("clearances") / n90, "blocked_shots_per90": c("blockedShots") / n90,
        "outfielder_blocks_per90": c("outfielderBlocks") / n90, "interceptions_per90_ss": c("interceptions") / n90,
        "recoveries_per90": c("ballRecovery") / n90, "aerial_won_per90": c("aerialDuelsWon") / n90,
        "tackles_won_per90_ss": c("tacklesWon") / n90, "ground_duels_won_per90": c("groundDuelsWon") / n90,
        "errors_per90": (c("errorLeadToGoal").fillna(0) + c("errorLeadToShot").fillna(0)) / n90,
        "possession_won_att_per90": c("possessionWonAttThird") / n90,
        "successful_dribbles_per90": c("successfulDribbles") / n90,
        "final_third_passes_per90": c("accurateFinalThirdPasses") / n90,
        "gk_saves_per90": c("saves") / n90, "gk_clean_sheets": c("cleanSheet"),
        "gk_high_claims_per90": c("highClaims") / n90, "gk_runs_out_per90": c("runsOut") / n90,
        "gk_punches_per90": c("punches") / n90, "gk_crosses_not_claimed": c("crossesNotClaimed"),
        "ss_appearances": c("appearances"), "ss_minutes": c("minutesPlayed"),
    })

    df["_key"] = [merge_key(t, p) for t, p in zip(df["squad"], df["player"])]
    dup = [x for x in ss_add.columns if x != "_key" and x in df.columns]
    if dup:
        df = df.drop(columns=dup)      # 기존 값 덮어써서 최신 SofaScore 반영
    out = df.merge(ss_add, on="_key", how="left").drop(columns=["_key"])
    rate = out["ss_rating"].notna().mean() * 100
    out.to_csv(pf_path, index=False, encoding="utf-8")
    print(f"[merge-ss] {ACTIVE_LEAGUE}: {pf_path.name} · SofaScore 매칭 {rate:.0f}% · {len(out.columns)}컬럼")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
