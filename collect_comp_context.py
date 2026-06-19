import pandas as pd
from pathlib import Path

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

# Per team counts
team_cats = fl.groupby(["squad", "comp_cat"]).size().unstack(fill_value=0)
for col in ["League", "Europe", "DomesticCup", "Other"]:
    if col not in team_cats.columns:
        team_cats[col] = 0
team_cats["total_fl"] = team_cats.sum(axis=1)
team_cats = team_cats.reset_index()

# League played from standings (more reliable for league)
stand_played = stand[["squad", "played"]].rename(columns={"played": "league_played_standings"})

team_cats = team_cats.merge(stand_played, on="squad", how="left")

# Also count league matches from schedule (gw based)
league_from_sched = sched.groupby("squad").size().reset_index(name="league_games_sched")
team_cats = team_cats.merge(league_from_sched, on="squad", how="left")

# Extra games proxy
team_cats["extra_games_fl"] = team_cats["total_fl"] - team_cats["League"]
team_cats["euro_games"] = team_cats["Europe"]
team_cats["domestic_cup_games"] = team_cats["DomesticCup"]

print("=== Sample (teams with most European games) ===")
cols = ["squad", "League", "euro_games", "domestic_cup_games", "total_fl", "league_played_standings", "extra_games_fl"]
print(team_cats.sort_values("euro_games", ascending=False).head(8)[cols].to_string())

print("\n=== Sample (Arsenal and other top teams) ===")
print(team_cats[team_cats["squad"].isin(["Arsenal", "Liverpool", "Manchester City", "Chelsea", "Aston Villa"])][cols].to_string())

Path("data").mkdir(exist_ok=True)
out = "data/team_comp_context_2025_2026.csv"
out_cols = ["squad", "League", "euro_games", "domestic_cup_games", "Other", "total_fl", "league_played_standings", "league_games_sched", "extra_games_fl"]
team_cats[out_cols].to_csv(out, index=False)
print(f"\n[OK] Saved {out}")
print("Columns:", out_cols)
EOF
python collect_comp_context.py 2>&1 | cat
rm collect_comp_context.py 2>nul || del collect_comp_context.py 2>nul || true