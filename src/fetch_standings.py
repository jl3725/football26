"""
FBref 일정 데이터에서 EPL 25/26 순위표 + 팀별 전적 목록을 계산해 저장.

출력:
  data/standings_2025_2026.csv  — rank, squad, played, won, drawn, lost, gf, ga, gd, points
  data/schedule_2025_2026.csv   — squad별 38경기 전적 (GW, date, home_away, opponent, score, result)

실행: python src/fetch_standings.py
"""
from __future__ import annotations

import pandas as pd
import soccerdata as sd

from leagues import SEASON_FBREF, data_path, league_config

OUT_STANDINGS = data_path("standings")
OUT_SCHEDULE = data_path("schedule")


def main() -> int:
    cfg = league_config()
    print(f"-> FBref 일정 로드 ({cfg.name}) ...", end=" ", flush=True)
    fb = sd.FBref(leagues=cfg.fbref_id, seasons=SEASON_FBREF)
    sched = fb.read_schedule().reset_index()
    sched.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c
                     for c in sched.columns]

    finished = sched[sched["score"].notna() & sched["score"].str.contains("–", na=False)].copy()
    finished[["hg", "ag"]] = finished["score"].str.split("–", expand=True).astype(int)
    print(f"{len(finished)} matches OK")

    # ── 순위표 집계 ──────────────────────────────────────────────────────────
    standing_rows = []
    for _, r in finished.iterrows():
        ht, at, hg, ag = r["home_team"], r["away_team"], r["hg"], r["ag"]
        if hg > ag:
            hw, hd, hl, aw, ad, al = 1, 0, 0, 0, 0, 1
        elif hg < ag:
            hw, hd, hl, aw, ad, al = 0, 0, 1, 1, 0, 0
        else:
            hw, hd, hl, aw, ad, al = 0, 1, 0, 0, 1, 0
        standing_rows.append({"squad": ht, "gf": hg, "ga": ag, "w": hw, "d": hd, "l": hl})
        standing_rows.append({"squad": at, "gf": ag, "ga": hg, "w": aw, "d": ad, "l": al})

    agg = (
        pd.DataFrame(standing_rows)
        .groupby("squad", as_index=False)
        .agg(played=("gf", "count"), won=("w", "sum"), drawn=("d", "sum"),
             lost=("l", "sum"), gf=("gf", "sum"), ga=("ga", "sum"))
    )
    agg["gd"]     = agg["gf"] - agg["ga"]
    agg["points"] = agg["won"] * 3 + agg["drawn"]
    agg = agg.sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)
    agg.insert(0, "rank", agg.index + 1)
    agg.to_csv(OUT_STANDINGS, index=False, encoding="utf-8")
    print(f"[OK] {OUT_STANDINGS.name} ({len(agg)} teams)")

    # ── 팀별 경기 목록 ────────────────────────────────────────────────────────
    schedule_rows = []
    date_col = "date" if "date" in finished.columns else None
    week_col = "week" if "week" in finished.columns else None

    for _, r in finished.iterrows():
        ht, at, hg, ag = r["home_team"], r["away_team"], int(r["hg"]), int(r["ag"])
        date = str(r[date_col])[:10] if date_col else ""
        week = int(r[week_col]) if week_col and pd.notna(r[week_col]) else 0

        if hg > ag:
            hr, ar = "W", "L"
        elif hg < ag:
            hr, ar = "L", "W"
        else:
            hr, ar = "D", "D"

        schedule_rows.append({
            "squad": ht, "gw": week, "date": date,
            "home_away": "H", "opponent": at,
            "gf": hg, "ga": ag, "score": f"{hg}:{ag}", "result": hr,
        })
        schedule_rows.append({
            "squad": at, "gw": week, "date": date,
            "home_away": "A", "opponent": ht,
            "gf": ag, "ga": hg, "score": f"{ag}:{hg}", "result": ar,
        })

    sdf = pd.DataFrame(schedule_rows).sort_values(["squad", "gw"]).reset_index(drop=True)
    sdf.to_csv(OUT_SCHEDULE, index=False, encoding="utf-8")
    print(f"[OK] {OUT_SCHEDULE.name} ({len(sdf)} rows)")

    print()
    print(agg[["rank", "squad", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points"]]
          .to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
