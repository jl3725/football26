"""
Collect multi-competition context from available data files.

This prepares data for Option A:
- Keep core league metrics pure.
- Add context columns: euro_games, domestic_cup_games, total_games, extra_games, etc.

Outputs: data/team_comp_context_2025_2026.csv
"""
import pandas as pd
from pathlib import Path

def main():
    fl = pd.read_csv("data/fl_matches_2025_2026.csv")
    sched = pd.read_csv("data/schedule_2025_2026.csv")
    stand = pd.read_csv("data/standings_2025_2026.csv")

    def comp_category(comp):
        if pd.isna(comp):
            return "League"
        c = str(comp).lower()
        if "epl" in c or "premier" in c:
            return "League"
        elif "champions" in c:
            return "Europe"
        elif "europa" in c or "conference" in c:
            return "Europe"
        elif "cup" in c or "trophy" in c:
            return "DomesticCup"
        elif "club world" in c:
            return "Europe"
        else:
            return "Other"

    fl["comp_cat"] = fl["comp"].apply(comp_category)

    # Per team counts from fl_matches (all documented matches)
    team_cats = (
        fl.groupby(["squad", "comp_cat"])
        .size()
        .unstack(fill_value=0)
    )
    for col in ["League", "Europe", "DomesticCup", "Other"]:
        if col not in team_cats.columns:
            team_cats[col] = 0
    team_cats["total_fl"] = team_cats.sum(axis=1)
    team_cats = team_cats.reset_index()

    # League played (most reliable source for league games)
    stand_played = stand[["squad", "played"]].rename(
        columns={"played": "league_played"}
    )
    team_cats = team_cats.merge(stand_played, on="squad", how="left")

    # League games from schedule (should be close to 38)
    league_sched = (
        sched.groupby("squad").size().reset_index(name="league_games_sched")
    )
    team_cats = team_cats.merge(league_sched, on="squad", how="left")

    # Derived
    team_cats["euro_games"] = team_cats["Europe"]
    team_cats["domestic_cup_games"] = team_cats["DomesticCup"]
    team_cats["other_games"] = team_cats["Other"]
    team_cats["extra_games"] = team_cats["total_fl"] - team_cats["League"]
    team_cats["total_games_approx"] = team_cats["league_played"].fillna(team_cats["League"]) + team_cats["extra_games"]

    # Clean output
    out_df = team_cats[
        [
            "squad",
            "league_played",
            "league_games_sched",
            "euro_games",
            "domestic_cup_games",
            "other_games",
            "extra_games",
            "total_fl",
            "total_games_approx",
        ]
    ].copy()

    Path("data").mkdir(exist_ok=True)
    out_path = Path("data/team_comp_context_2025_2026.csv")
    out_df.to_csv(out_path, index=False)

    print("[OK] Saved", out_path)
    print("\nSample (teams with European participation):")
    print(
        out_df.sort_values("euro_games", ascending=False)
        .head(8)
        .to_string(index=False)
    )
    print("\nArsenal row:")
    print(out_df[out_df.squad == "Arsenal"].to_string(index=False))

if __name__ == "__main__":
    main()
