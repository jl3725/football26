"""
FBref에서 2025-26 EPL 선수 시즌 스탯을 받아 PoC용 CSV로 병합한다.

soccerdata v1.9 의 read_player_season_stats 는 리그 단위에서 basic 테이블만
제공한다(고급 xG/진행/패스/수비 지표는 없음). 따라서 실제로 받을 수 있는
standard / shooting / misc 3개 테이블을 병합해 90분당 10개 지표를 만든다.

※ FBref의 defense/passing/possession/keepersadv 페이지도 시도했으나 25/26 시즌은
   대부분의 advanced 컬럼이 비어 있음 (StatsBomb→FBref 데이터 공급 축소 추정).
   고급 지표는 fetch_sofascore_stats.py 로 별도 수집한다.

실행: python src/fetch_fbref.py
※ FBref 속도 제한으로 수 분 소요. 캐시(soccerdata/data)에 저장되어 재실행은 빠름.
"""
from __future__ import annotations

import os
from pathlib import Path

# soccerdata 의 read_player_season_stats 는 진행 중 시즌도 캐시를 영원히 쓴다(MAXAGE=None, no_cache 없음) — 주간 빌드가
# 10/13 에 받은 HTML 만 3주 다시 읽으며 12초 만에 'ok'(2026-11-03 점검: 새로 받으니 EPL 최다 출전 540 → 810분).
# 캐시 유효기간(일) — soccerdata 를 가져오기 전에 정해야 한다(_config 가 import 때 읽음)
os.environ.setdefault("SOCCERDATA_MAXAGE", "2")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import soccerdata as sd  # noqa: E402

from leagues import SEASON_FBREF, data_path, league_config, register_soccerdata_custom_leagues
from squads import canonical_squad

register_soccerdata_custom_leagues()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = data_path("players")
SAMPLE = data_path("players_sample")
LEAGUE = league_config().fbref_id
LEAGUE_KEY = league_config().key
SEASON = SEASON_FBREF


def find_col(df: pd.DataFrame, child: str, parent: str | None = None) -> pd.Series:
    for c in df.columns:
        levels = [str(x) for x in (c if isinstance(c, tuple) else (c,))]
        non_empty = [x for x in levels if x != ""]
        sub = non_empty[-1] if non_empty else ""   # ('90s','') → '90s'
        top = levels[0]
        if sub == child and (parent is None or parent in top):
            return df[c]
    raise KeyError(f"컬럼을 찾을 수 없음: parent~='{parent}', child='{child}'")


def keyed(df: pd.DataFrame) -> pd.DataFrame:
    """인덱스(league,season,team,player)에서 team/player 키 컬럼을 뽑아낸다."""
    idx = df.index.to_frame(index=False)
    df = df.reset_index(drop=True).copy()
    df["_team"] = [canonical_squad(t, LEAGUE_KEY) for t in idx["team"].values]   # FBref 표기 → 앱 표준
    df["_player"] = idx["player"].values
    return df


def main() -> int:
    fb = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("→ standard ..."); standard = keyed(fb.read_player_season_stats("standard"))
    print("→ shooting ..."); shooting = keyed(fb.read_player_season_stats("shooting"))
    print("→ misc ...");     misc = keyed(fb.read_player_season_stats("misc"))

    misc_90s = pd.to_numeric(find_col(misc, "90s"), errors="coerce").replace(0, np.nan)

    def misc_per90(child: str) -> np.ndarray:
        return (pd.to_numeric(find_col(misc, child, "Performance"), errors="coerce") / misc_90s).values

    base = pd.DataFrame({
        "player": standard["_player"].values,
        "squad": standard["_team"].values,
        "pos": find_col(standard, "pos").values,
        "age": pd.to_numeric(find_col(standard, "age"), errors="coerce").values,
        "minutes": pd.to_numeric(find_col(standard, "Min", "Playing Time"), errors="coerce").values,
        # standard 는 이미 90분당 컬럼 제공
        "npg_per90": pd.to_numeric(find_col(standard, "G-PK", "Per 90"), errors="coerce").values,
        "ast_per90": pd.to_numeric(find_col(standard, "Ast", "Per 90"), errors="coerce").values,
    })
    base["_key"] = base["squad"] + "|" + base["player"]

    sh = pd.DataFrame({
        "_key": shooting["_team"].values + "|" + shooting["_player"].values,
        "sh_per90": pd.to_numeric(find_col(shooting, "Sh/90", "Standard"), errors="coerce").values,
        "sot_per90": pd.to_numeric(find_col(shooting, "SoT/90", "Standard"), errors="coerce").values,
    })

    ms = pd.DataFrame({
        "_key": misc["_team"].values + "|" + misc["_player"].values,
        "crosses_per90": misc_per90("Crs"),
        "interceptions_per90": misc_per90("Int"),
        "tackles_won_per90": misc_per90("TklW"),
        "fouls_per90": misc_per90("Fls"),
        "fouled_per90": misc_per90("Fld"),
        "offsides_per90": misc_per90("Off"),
    })

    out = base.merge(sh, on="_key", how="left").merge(ms, on="_key", how="left")
    out["market_value_eur"] = np.nan  # FBref 미제공 → Transfermarkt 보강 전까지 공란

    # GK는 유지(포메이션 보드 GK 슬롯용). 필드 지표는 0으로 채워 둔다.
    # 출전시간 결측만 제거.
    out = out.dropna(subset=["minutes"]).reset_index(drop=True)
    is_gk = out["pos"].fillna("").str.contains("GK")
    field_cols = ["npg_per90", "ast_per90", "sh_per90", "sot_per90", "crosses_per90",
                  "interceptions_per90", "tackles_won_per90", "fouls_per90",
                  "fouled_per90", "offsides_per90"]
    out.loc[is_gk, field_cols] = 0.0

    cols = [
        "player", "squad", "pos", "age", "minutes",
        "npg_per90", "ast_per90", "sh_per90", "sot_per90", "crosses_per90",
        "interceptions_per90", "tackles_won_per90", "fouls_per90", "fouled_per90",
        "offsides_per90", "market_value_eur",
    ]
    out = out[cols].round(3)
    out.to_csv(OUT, index=False, encoding="utf-8")

    # 오프라인 데모용 샘플 = 출전시간 상위 30명 슬라이스(스키마 동일)
    out.sort_values("minutes", ascending=False).head(30).to_csv(SAMPLE, index=False, encoding="utf-8")

    print(f"\n[OK] 저장: {OUT.name}  ({len(out)} 명),  {SAMPLE.name} (상위 30명)")
    print(out.sort_values("minutes", ascending=False).head(8).to_string(index=False))
    lag = games_behind(out)
    if lag is not None and lag[0] - lag[1] >= STALE_GAMES:
        # 받은 표가 FotMob 경기 기록보다 늦음(캐시 재사용·원천 지연) — 2026-10 캐시만 다시 읽어 팀당 5~8경기에서 멈춘 동안
        # 주간 빌드가 'ok' 였고 그 뒤 리그 데뷔 선수가 선수 표에 없었다(메슬리에·펜더스, 2026-11-03). 선수 줄·분·세부 지표는
        # FotMob 이 보강(src/live_roster·season_totals·allcomp_stats) — 여기선 원천 문제로 알린다
        print(f"[fbref] 표가 뒤처짐 — 팀당 FBref {lag[1]:.0f}경기 · FotMob {lag[0]:.0f}경기 (SOURCE STALE)")
        return EX_SOURCE_STALE
    return 0


STALE_GAMES = 2          # FotMob 리그 경기 수보다 이만큼 뒤면 원천 문제
EX_SOURCE_STALE = 75     # 외부 원천 문제(scripts/ci_try.sh · 운영 원장 SOURCE DOWN, 빨간불 아님)


def games_behind(out: pd.DataFrame) -> tuple[float, float] | None:
    """(FotMob 팀당 리그 경기 수 중앙값, FBref 팀당 경기 수 ≈ 팀 최다 출전 분 ÷ 90 중앙값) — FotMob 기록이 없으면 None."""
    from season_totals import league_code
    path = data_path("fotmob_match_ratings")
    if not path.exists() or out.empty:
        return None
    mr = pd.read_csv(path, usecols=["match_id", "comp_code", "squad"])
    mr = mr[mr["comp_code"].astype(str) == league_code(LEAGUE_KEY)]
    if mr.empty:
        return None
    fm = float(mr.groupby("squad")["match_id"].nunique().median())
    fb = float((pd.to_numeric(out["minutes"], errors="coerce").groupby(out["squad"]).max() / 90).median())
    return fm, fb


if __name__ == "__main__":
    raise SystemExit(main())
