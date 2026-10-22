"""
대회별 선수 사용량(역할 축) 매일 갱신 — 이미 수집한 컵·유럽 라인업·교체(src/fetch_cup_lineups.py, match_refresh)에서 집계.

player_comp_usage_* 는 예전엔 로컬 주간 시즌 빌드(src/fetch_comp_usage.py)에서만 만들어져, 10/14 이후 멈춘 탓에
UCL 2경기 모두 선발인 Haaland·Mbappé 가 '주전·유럽 로테이션'으로 나왔다(2026-10-20 점검). 같은 경기 기록을
SEASON LOG 가 쓰는 라인업 데이터에서 바로 세어, 화면의 SEASON LOG 와 역할 근거가 같은 원천이 되게 한다.

    python src/comp_usage_live.py            # 8개 리그 현재 시즌
    python src/comp_usage_live.py --league EPL

기존 파일 값과 칸별 큰 값을 취한다(라인업을 못 받은 경기는 기존 수집분 유지). 집계가 0명이면 기존 파일을 둔다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datastore as ds  # noqa: E402
from leagues import LEAGUE_CODES, LEAGUES, data_path  # noqa: E402

GROUP = {"uefa.champions": "ucl", "uefa.europa": "uel", "uefa.europa.conf": "conf",
         "eng.fa": "facup", "eng.league_cup": "lcup", "esp.copa_del_rey": "copa"}
EURO = ("ucl", "uel", "conf")
COLS = ["ucl", "uel", "conf", "facup", "lcup", "copa"]


def _norm(n) -> str:
    return unidecode(str(n or "")).lower().strip()


def build(league: str) -> pd.DataFrame | None:
    lu = ds.read_table("espn_lineups_cups", league=league)          # 이름 정규화(player_names) 거침
    su = ds.read_table("espn_subs_cups", league=league)
    sch = ds.read_table("schedule_full", league=league)
    if lu is None or lu.empty or sch is None or sch.empty:
        return None
    eid = lambda s: s.astype(str).str.replace(r"\.0$", "", regex=True)  # noqa: E731
    comp = dict(zip(eid(sch["event_id"].dropna()), sch.loc[sch["event_id"].notna(), "comp_code"].astype(str)))
    lu = lu.assign(ev=eid(lu["event_id"]))
    lu["cc"] = lu["ev"].map(comp)
    lu = lu[lu["cc"].notna() & ~lu["cc"].isin(LEAGUE_CODES)]
    if lu.empty:
        return None
    rec: dict[tuple, dict] = {}

    def add(squad, player, code, start):
        g = GROUP.get(code, "cup_other")
        r = rec.setdefault((str(squad), str(player)), {})
        r[f"{g}_apps"] = r.get(f"{g}_apps", 0) + 1
        if start:
            r[f"{g}_starts"] = r.get(f"{g}_starts", 0) + 1

    for r in lu[lu["starter"].astype(str).isin(("1", "1.0", "True", "true"))].itertuples(index=False):
        add(r.squad, r.player, r.cc, True)
    if su is not None and not su.empty:
        side = {(e, str(h)): (s, c) for e, h, s, c in zip(lu["ev"], lu["home_away"], lu["squad"], lu["cc"])}
        for e, h, p in zip(eid(su["event_id"]), su["home_away"].astype(str), su["player_in"]):
            hit = side.get((e, h))
            if hit and isinstance(p, str) and p:
                add(hit[0], p, hit[1], False)
    rows = []
    for (sq, pl), v in rec.items():
        row = {"squad": sq, "player": pl, "norm_key": _norm(pl)}
        for c in COLS + ["cup_other"]:
            row[f"{c}_starts"], row[f"{c}_apps"] = int(v.get(f"{c}_starts", 0)), int(v.get(f"{c}_apps", 0))
        row["euro_starts"] = sum(row[f"{c}_starts"] for c in EURO)
        row["euro_apps"] = sum(row[f"{c}_apps"] for c in EURO)
        row["cup_starts"] = sum(row[f"{c}_starts"] for c in ("facup", "lcup", "copa", "cup_other"))
        row["cup_apps"] = sum(row[f"{c}_apps"] for c in ("facup", "lcup", "copa", "cup_other"))
        rows.append(row)
    return pd.DataFrame(rows)


def merge_existing(new: pd.DataFrame, path: Path) -> pd.DataFrame:
    """기존 파일과 (squad, norm_key) 로 합쳐 칸별 큰 값 — 라인업을 못 받은 경기의 기존 집계를 잃지 않게."""
    if not path.exists():
        return new
    old = pd.read_csv(path)
    num = [c for c in new.columns if c.endswith(("_starts", "_apps"))]
    allc = list(dict.fromkeys(["squad", "player", "norm_key"] + [c for c in old.columns if c not in ("squad", "player", "norm_key")] + num))
    both = pd.concat([old.reindex(columns=allc), new.reindex(columns=allc)], ignore_index=True)
    agg = {c: "max" for c in allc if c not in ("squad", "norm_key")}
    agg["player"] = "last"
    out = both.groupby(["squad", "norm_key"], as_index=False).agg(agg)
    for c in allc:
        if c.endswith(("_starts", "_apps")):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)
    return out[allc]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = argv if argv is not None else sys.argv[1:]
    leagues = [args[args.index("--league") + 1]] if "--league" in args else list(LEAGUES)
    bad = 0
    for lg in leagues:
        df = build(lg)
        if df is None or df.empty:
            print(f"[comp-usage] {lg}: 컵·유럽 라인업 없음 — 기존 파일 유지")
            continue
        path = data_path("player_comp_usage", lg)
        out = merge_existing(df, path)
        out.to_csv(path, index=False, encoding="utf-8")
        print(f"[comp-usage] {lg}: {len(df)}명 집계 → {len(out)}행 · 유럽 선발 합 {int(out['euro_starts'].sum())}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
