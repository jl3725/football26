"""
Build team defense/attack context from the active league standings file.

Output:
  data/team_defense_<league>_2025_2026.csv
"""
from __future__ import annotations

import pandas as pd

from leagues import data_path

STANDINGS = data_path("standings")
OUT = data_path("team_defense")


def main() -> int:
    if not STANDINGS.exists():
        print(f"standings not found: {STANDINGS}")
        return 1

    standings = pd.read_csv(STANDINGS)
    required = {"squad", "played", "gf", "ga"}
    missing = required - set(standings.columns)
    if missing:
        print(f"standings missing columns: {sorted(missing)}")
        return 1

    out = pd.DataFrame({
        "squad": standings["squad"].astype(str),
        "games_played": pd.to_numeric(standings["played"], errors="coerce"),
        "goals_for": pd.to_numeric(standings["gf"], errors="coerce"),
        "goals_against": pd.to_numeric(standings["ga"], errors="coerce"),
    })
    out = out.dropna(subset=["games_played", "goals_for", "goals_against"])
    out["goals_for_per_game"] = out["goals_for"] / out["games_played"]
    out["goals_against_per_game"] = out["goals_against"] / out["games_played"]

    ga = out["goals_against_per_game"]
    gf = out["goals_for_per_game"]
    out["defense_score"] = (ga.max() - ga) / (ga.max() - ga.min()) if ga.max() != ga.min() else 1.0
    out["attack_score"] = (gf - gf.min()) / (gf.max() - gf.min()) if gf.max() != gf.min() else 1.0
    out = out.sort_values("goals_against").reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n[OK] saved {OUT.name} ({len(out)} teams)")
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
