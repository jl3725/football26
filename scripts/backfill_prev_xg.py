"""
지난 시즌(25/26) Understat 지표 다시 채우기 — Understat 팀 표기가 우리 표기와 달라 못 붙었던 선수만.

배경: 25/26 수집 때는 Understat 클럽 이름('Manchester United'·'Wolverhampton Wanderers'·'Paris Saint Germain' …)을
우리 표기로 바꾸지 못해, EPL 5팀·분데스리가 9팀·세리에A 3팀·라리가·리그1 1팀씩의 선수가 전부 '미매칭'이 되었다.
미매칭은 fetch_understat 가 대체값을 넣는다(xG·xG Chain 0, npxG=골, xA=도움, 키패스=도움×3) — 26/27 시즌 초
안정화(지난 시즌 최대 1,350′ 섞기)·유사 선수·이적 적합도가 이 대체값을 그대로 썼다.
26/27 부터는 squads.canonical_squad 로 고쳐졌고, 25/26 은 다시 처리하지 않았었다(memory: season-2627-followup).

방법: soccerdata Understat 25/26 선수 시즌 기록을 받아 canonical_squad 로 팀을 맞추고, 지난번에 못 붙은 행
(xg_p90 == 0 이고 xg_chain_p90 == 0 인데 Understat 에 있는 선수)만 Understat 열을 바꾼다. 붙었던 행은 건드리지 않는다.
Understat 이 다루지 않는 리그(포르투갈·네덜란드·벨기에)는 대상 밖.

    python scripts/backfill_prev_xg.py            # 바꿀 행 수만 보고(파일 그대로)
    python scripts/backfill_prev_xg.py --write    # 파일에 쓴다
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402
from squads import canonical_squad  # noqa: E402

UNDERSTAT_LEAGUES = ("EPL", "LaLiga", "Bundesliga", "SerieA", "Ligue1")
COLS = ["xg_p90", "npxg_p90", "xa_p90", "kp_p90", "shots_p90", "xg_chain_p90"]


def _key(team, player) -> str:
    return f"{unidecode(str(team)).lower().strip()}|{unidecode(str(player)).lower().strip()}"


def understat_rows(league: str, season: str) -> pd.DataFrame:
    import soccerdata as sd  # noqa: PLC0415
    us = sd.Understat(leagues=LEAGUES[league].fbref_id, seasons=season)
    u = us.read_player_season_stats().reset_index()
    n90 = u["minutes"] / 90
    for c, src in (("xg_p90", "xg"), ("npxg_p90", "np_xg"), ("xa_p90", "xa"), ("kp_p90", "key_passes"),
                   ("shots_p90", "shots"), ("xg_chain_p90", "xg_chain")):
        u[c] = (u[src] / n90).round(3)
    u["_key"] = [_key(canonical_squad(t, league), p) for t, p in zip(u["team"], u["player"])]
    return u.drop_duplicates("_key")


def backfill(df: pd.DataFrame, u: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """못 붙었던 행(xG·xG Chain 둘 다 0)만 Understat 값으로. (새 표, 바꾼 행 수)"""
    df = df.copy()
    keys = [_key(t, p) for t, p in zip(df["squad"], df["player"])]
    um = u.set_index("_key")
    miss = (pd.to_numeric(df["xg_p90"], errors="coerce").fillna(0) == 0) & \
           (pd.to_numeric(df["xg_chain_p90"], errors="coerce").fillna(0) == 0)
    n = 0
    for i, k in enumerate(keys):
        if not miss.iloc[i] or k not in um.index:
            continue
        r = um.loc[k]
        for c in COLS:
            df.iat[i, df.columns.get_loc(c)] = r[c]
        n += 1
    return df, n


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(argv if argv is not None else sys.argv[1:])
    season = f"{SEASON_START - 1}-{SEASON_START}"
    prev = f"{SEASON_START - 1}_{SEASON_START}"
    for lg in UNDERSTAT_LEAGUES:
        path = data_path("players_full", lg, prev)
        if not path.exists():
            continue
        df = pd.read_csv(path)
        try:
            u = understat_rows(lg, season)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패는 건너뛴다
            print(f"[{lg}] Understat 실패 {type(e).__name__}: {e}")
            continue
        new, n = backfill(df, u)
        zero = lambda d: int((d.assign(_x=pd.to_numeric(d["xg_p90"], errors="coerce").fillna(0))  # noqa: E731
                              [pd.to_numeric(d["minutes"], errors="coerce").fillna(0) >= 300]
                              .groupby("squad")["_x"].sum() == 0).sum())
        print(f"[{lg}] Understat {len(u)}명 · 다시 채운 선수 {n} · xG 0 인 팀 {zero(df)} → {zero(new)}")
        if "--write" in args and n:
            new.to_csv(path, index=False, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
