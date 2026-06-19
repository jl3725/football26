"""
Build season-specific squad snapshots from player and transfer data.

Usage:
    python src/sync_roster_seasons.py
    python src/sync_roster_seasons.py --write

The output lets the app/agents compare 25/26 vs 26/27 rosters without mixing
finished-season performance data with next-season transfer movement.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLAYERS_FULL = DATA / "players_full_2025_2026.csv"
TRANSFERS = DATA / "transfers_2025_2026.csv"
OUT = DATA / "roster_seasons_2025_2026.csv"


def norm(value) -> str:
    return unidecode(str(value or "")).lower().strip()


def season_label(sid: int) -> str:
    return f"{sid % 100:02d}/{(sid + 1) % 100:02d}"


def build_roster_snapshots(players: pd.DataFrame, transfers: pd.DataFrame) -> pd.DataFrame:
    players = players.copy()
    players["norm_key"] = players.get("norm_key", players["player"].map(norm))

    if transfers is None or transfers.empty:
        seasons = [2025]
    else:
        seasons = sorted(set([2025] + [
            int(s) for s in pd.to_numeric(transfers.get("season_id"), errors="coerce").dropna().unique()
        ]))

    rows = []
    for team, team_players in players.groupby("squad"):
        base = {
            str(row["norm_key"]): {
                "player": row["player"],
                "norm_key": row["norm_key"],
                "squad": team,
                "pos": row.get("tm_position") or row.get("fl_group") or row.get("pos") or "",
                "age": row.get("age"),
                "photo": row.get("tm_photo", ""),
            }
            for _, row in team_players.iterrows()
        }
        team_transfers = (
            transfers[transfers["squad"].astype(str) == str(team)].copy()
            if transfers is not None and not transfers.empty and "squad" in transfers.columns
            else pd.DataFrame()
        )

        for sid in seasons:
            roster = {k: {**v, "status": "carried"} for k, v in base.items()}
            if not team_transfers.empty:
                transfer_season = pd.to_numeric(team_transfers["season_id"], errors="coerce")
                cumulative_rows = team_transfers[transfer_season <= int(sid)].copy()
                season_rows = team_transfers[transfer_season == int(sid)].copy()
                ins = season_rows[season_rows["direction"].astype(str).str.lower() == "in"].copy()
                outs = cumulative_rows[cumulative_rows["direction"].astype(str).str.lower() == "out"].copy()
                in_norms = set(ins["norm_key"].astype(str))
                out_norms = set(outs["norm_key"].astype(str)) - in_norms

                for out_norm in out_norms:
                    roster.pop(out_norm, None)

                for _, tr in ins.iterrows():
                    nk = str(tr.get("norm_key") or norm(tr.get("player")))
                    fee_text = str(tr.get("fee_text") or "").lower()
                    prior = team_transfers[
                        (team_transfers["norm_key"].astype(str) == nk)
                        & (team_transfers["direction"].astype(str).str.lower() == "in")
                        & (team_transfers["fee_text"].astype(str).str.lower().str.contains("loan transfer", na=False))
                        & (pd.to_numeric(team_transfers["season_id"], errors="coerce") < int(sid))
                    ]
                    tr_season = pd.to_numeric(tr.get("season_id"), errors="coerce")
                    if pd.notna(tr_season) and int(tr_season) < int(sid):
                        status = "carried"
                    elif any(token in fee_text for token in ("end of loan", "loan return", "return from loan")):
                        status = "returning"
                    elif not prior.empty and "loan" not in fee_text:
                        status = "loan_to_buy"
                    else:
                        status = "new"
                    roster[nk] = {
                        "player": base.get(nk, {}).get("player", tr.get("player")),
                        "norm_key": nk,
                        "squad": team,
                        "pos": tr.get("pos", base.get(nk, {}).get("pos", "")),
                        "age": tr.get("age", base.get(nk, {}).get("age")),
                        "photo": tr.get("photo", base.get(nk, {}).get("photo", "")),
                        "status": status,
                    }

            for item in roster.values():
                rows.append({
                    "season_id": sid,
                    "season": season_label(sid),
                    "squad": team,
                    "player": item["player"],
                    "norm_key": item["norm_key"],
                    "pos": item.get("pos", ""),
                    "age": item.get("age"),
                    "photo": item.get("photo", ""),
                    "status": item.get("status", "carried"),
                })

    out = pd.DataFrame(rows)
    return out.sort_values(["season_id", "squad", "status", "player"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build season-specific squad snapshots.")
    parser.add_argument("--write", action="store_true", help="Write data/roster_seasons_2025_2026.csv")
    args = parser.parse_args(argv)

    players = pd.read_csv(PLAYERS_FULL)
    transfers = pd.read_csv(TRANSFERS) if TRANSFERS.exists() else pd.DataFrame()
    snapshots = build_roster_snapshots(players, transfers)

    summary = snapshots.groupby(["season", "status"]).size().unstack(fill_value=0)
    print(summary.to_string())

    if not args.write:
        print("[DRY] Run with --write to save the roster snapshot.")
        return 0

    snapshots.to_csv(OUT, index=False, encoding="utf-8")
    print(f"[OK] wrote {OUT.relative_to(ROOT)} ({len(snapshots)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
