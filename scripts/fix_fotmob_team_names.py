"""
FotMob 에서 받은 표의 클럽 표기를 우리 표기로 고친다(squad·opponent 열) — 한 번 돌리면 되는 정리.

2026-10-22 검수: FotMob 수집기들이 team_names.best(낱말 유사도)만 써서 'Vitória de Guimarães'·'Sparta Rotterdam'·
'St.Truiden'·'Union St.Gilloise' 를 우리 표기('Vit. Guimarães'·'Sparta R.'·'Sint-Truiden'·'Union SG')로 못 바꿨다.
그 팀 선수의 경기별 평점(최근 폼·전 대회 지표)·골 상황·시즌 평점·점유율·결장이 FotMob 표기로 쌓여 화면에서 빠졌다.
수집기는 squads.to_ours 로 고쳤고, 이미 쌓인 파일은 이 스크립트로 — 순위표에 없는 표기만 to_ours 로 바꾼다.

    python scripts/fix_fotmob_team_names.py            # 바꿀 값만 보고
    python scripts/fix_fotmob_team_names.py --write
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402
from squads import to_ours  # noqa: E402

STEMS = ["fotmob_match_ratings", "fotmob_goals", "fotmob_ratings", "team_possession", "fotmob_injuries", "fotmob_league_totals"]
COLS = ["squad", "opponent"]


def fix_frame(df: pd.DataFrame, league: str, ours: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """순위표에 없는 클럽 표기 → 우리 표기(to_ours 가 찾은 것만). (새 표, {옛: 새}).
    바꿀 표기는 squad 열에서만 고른다(우리 리그 팀 행) — opponent 열엔 하부 리그 컵 상대('Lyon La Duchere'·
    'Excelsior Maassluis')가 있어 낱말 유사도로 우리 팀('Lyon'·'Excelsior')에 잘못 붙는다. 같은 표기의 opponent 만 함께 바꾼다."""
    raw = set(df["squad"].dropna().astype(str)) if "squad" in df.columns else set()
    m = {x: y for x in sorted(raw - set(ours)) if (y := to_ours(x, league, ours)) and y != x}
    if not m:
        return df, {}
    df = df.copy()
    for c in COLS:
        if c in df.columns:
            df[c] = df[c].map(lambda v: m.get(v, v) if isinstance(v, str) else v)
    return df, m


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    write = "--write" in (argv if argv is not None else sys.argv[1:])
    for season in (f"{SEASON_START}_{SEASON_START + 1}", f"{SEASON_START - 1}_{SEASON_START}"):
        for lg in LEAGUES:
            try:
                ours = list(pd.read_csv(data_path("standings", lg, season))["squad"].astype(str))
            except (FileNotFoundError, KeyError):
                continue
            for stem in STEMS:
                p = data_path(stem, lg, season)
                if not p.exists():
                    continue
                df = pd.read_csv(p, dtype={"match_id": str, "fotmob_id": str})
                new, m = fix_frame(df, lg, ours)
                if m:
                    n = sum(int((df[c].astype(str).isin(m)).sum()) for c in COLS if c in df.columns)
                    print(f"[{season} {lg}] {p.name}: {m} · {n}칸")
                    if write:
                        new.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
