"""
지난 시즌(25/26) 리그 경기 FotMob 상세 — 골 상황 + 선수별 시즌 합(xG·npxG·xA·슈팅·찬스 메이킹).

왜: ① 득점 구성 카드의 '지난 시즌 vs 이번 시즌' 비교가 StatBunker 있는 EPL·라리가·세리에A 에만 있었다(분데스리가·리그1·
포르투갈·네덜란드·벨기에는 이번 시즌만). ② 포르투갈·네덜란드·벨기에는 Understat 이 없어 지난 시즌 xG 가 대체값
(xG 0, npxG=골, 키패스=도움×3)이었다 — 26/27 시즌 초 안정화·유사 선수·이적 적합도가 그 값을 썼다.
fetch_fotmob_matches --season prev 는 유럽·컵만 받는다(리그 경기를 평점 파일에 넣으면 시즌 평점과 겹친다) — 그래서 따로.

출력
  data/fotmob_goals_{리그}_2025_2026.csv           골 상황(fetch_fotmob_matches.goal_rows 와 같은 열)
  data/fotmob_league_totals_{리그}_2025_2026.csv   선수별 리그 합(squad, player, matched, minutes, xg, npxg, xa, shots, chances)
  data/players_full_{포르투갈·네덜란드·벨기에}_2025_2026.csv — 대체값 행(xG·xG Chain 둘 다 0)만 FotMob 합으로(--write)
이미 받은 경기는 data/.cache 에 경기별로 남겨 다시 돌릴 때 건너뛴다. 끝난 시즌이라 한 번만 돌리면 된다.

    python scripts/backfill_prev_fotmob_league.py [--league Bundesliga] [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import fetch_fotmob_matches as fm  # noqa: E402
import player_registry as preg  # noqa: E402
from fix_fotmob_team_names import fix_frame  # noqa: E402
from leagues import SEASON_START, data_path  # noqa: E402

LEAGUES = ["Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague"]   # StatBunker 지난 시즌 없음
NO_UNDERSTAT = {"LigaPortugal", "Eredivisie", "BelgianProLeague"}                    # 지난 시즌 xG 원천 없음
CACHE = ROOT / "data" / ".cache" / "fotmob_prev_league"
SUM = ["minutes", "xg", "npxg", "xa", "shots", "chances"]


def _match_cached(m: dict, code: str, sides: dict) -> tuple[list[dict], list[dict]] | None:
    p = CACHE / f"{m['id']}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return d["players"], d["goals"]
    j = fm._details(m)                                           # noqa: SLF001
    if not (j.get("content") or {}).get("playerStats"):
        return None
    players = fm.player_rows(m, code, sides, j)
    goals = fm.goal_rows(j, m, code, sides)
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"players": players, "goals": goals}, ensure_ascii=False, default=str), encoding="utf-8")
    time.sleep(0.35)
    return players, goals


def season_totals(players: list[dict], ours: pd.DataFrame) -> pd.DataFrame:
    """FotMob 경기별 선수 행 → 선수별 리그 합 + 우리 표기 이름(같은 팀 안 player_registry.best_match)."""
    if not players:
        return pd.DataFrame(columns=["squad", "player", "matched", *SUM])
    df = pd.DataFrame(players)
    for c in SUM:
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0)
    agg = df.groupby(["squad", "fotmob_id"]).agg(player=("player", "last"), **{c: (c, "sum") for c in SUM}).reset_index()
    by_team = {sq: {str(n): str(n) for n in g["player"]} for sq, g in ours.groupby("squad")}
    agg["matched"] = [preg.best_match(str(p), by_team.get(sq, {}))[0] for sq, p in zip(agg["squad"], agg["player"])]
    return agg.drop(columns=["fotmob_id"])[["squad", "player", "matched", *SUM]]


def backfill_xg(full: pd.DataFrame, tot: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """대체값 행(xG·xG Chain 둘 다 0)만 FotMob 리그 합의 90분당 값으로. xG Chain 은 FotMob 에 없어 그대로."""
    full = full.copy()
    for col in ("xg_p90", "npxg_p90", "xa_p90", "shots_p90", "kp_p90"):
        full[col] = pd.to_numeric(full[col], errors="coerce").astype(float)
    t = tot.dropna(subset=["matched"])
    t = t[t["minutes"] >= 90].drop_duplicates(["squad", "matched"])
    look = {(sq, m): r for sq, m, r in zip(t["squad"], t["matched"], t.to_dict("records"))}
    miss = (pd.to_numeric(full["xg_p90"], errors="coerce").fillna(0) == 0) & \
           (pd.to_numeric(full["xg_chain_p90"], errors="coerce").fillna(0) == 0)
    n = 0
    for i in full.index[miss]:
        r = look.get((full.at[i, "squad"], full.at[i, "player"]))
        if r is None:
            continue
        n90 = r["minutes"] / 90
        for col, src in (("xg_p90", "xg"), ("npxg_p90", "npxg"), ("xa_p90", "xa"), ("shots_p90", "shots"), ("kp_p90", "chances")):
            full.at[i, col] = round(r[src] / n90, 3)
        n += 1
    return full, n


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    y = SEASON_START - 1
    season, fm_season = f"{y}_{y + 1}", f"{y}/{y + 1}"
    for lg in [a.league] if a.league else LEAGUES:
        sides, jobs = fm._sides([lg], season, fm_season, "")        # noqa: SLF001 — 지난 시즌 순위표 표기
        players, goals, skipped = [], [], 0
        t0 = time.time()
        for k, (m, code) in enumerate(jobs, 1):
            try:
                got = _match_cached(m, code, sides)
            except Exception as e:  # noqa: BLE001
                print(f"    [실패] {m.get('id')}: {e}")
                got = None
            if got is None:
                skipped += 1
                continue
            players += got[0]
            goals += got[1]
            if k % 100 == 0:
                print(f"  [{lg}] {k}/{len(jobs)} ({time.time() - t0:.0f}초)", flush=True)
        ours = pd.read_csv(data_path("players_full", lg, season))
        st = pd.read_csv(data_path("standings", lg, season))
        # 클럽 표기 — 캐시된 경기 행에 FotMob 표기('Sparta Rotterdam' …)가 남아 있을 수 있어 우리 표기로(squads.to_ours)
        pl, _ = fix_frame(pd.DataFrame(players), lg, list(st["squad"].astype(str))) if players else (pd.DataFrame(), {})
        players = pl.to_dict("records")
        tot = season_totals(players, ours)
        gd = pd.DataFrame(goals, columns=["league", *fm.GOAL_COLS]).reindex(columns=fm.GOAL_COLS)
        gd, _ = fix_frame(gd, lg, list(st["squad"].astype(str)))
        gsum = gd[gd["situation"] != "none"].groupby("squad").size()
        off = [sq for sq, gf in zip(st["squad"], st["gf"]) if int(gsum.get(sq, 0)) != int(gf)]
        rate = tot["matched"].notna().mean() if len(tot) else 0
        print(f"[{lg}] 경기 {len(jobs)}(못 받음 {skipped}) · 골 {int(gsum.sum())} · 순위표와 골 수 다른 팀 {len(off)} {off[:4]} · "
              f"선수 {len(tot)}명 이름 매칭 {rate:.0%}")
        if a.write:
            gd.sort_values(["date", "match_id", "minute"], na_position="last").to_csv(
                data_path("fotmob_goals", lg, season), index=False, encoding="utf-8", lineterminator="\n")
            tot.to_csv(data_path("fotmob_league_totals", lg, season), index=False, encoding="utf-8", lineterminator="\n")
        if lg in NO_UNDERSTAT:
            full = pd.read_csv(data_path("players_full", lg, season))
            new, n = backfill_xg(full, tot)
            print(f"    xG 대체값 행 → FotMob 합: {n}명")
            if a.write and n:
                new.to_csv(data_path("players_full", lg, season), index=False, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
