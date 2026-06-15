"""
FBref 리그 standings 에서 25/26 EPL 팀별 시즌 수비+공격 통계 수집.

평가 보정 용도:
  - team_defense_score (GA 기반): CB/FB/GK/DM 평가에 가중치로 사용
  - team_attack_score (GF 기반): FW/AM/CM 평가에 가중치로 사용
약팀 인플레이션을 해소하고 우승팀 멤버에게 합당한 컨텍스트 반영.

출력: data/team_defense_2025_2026.csv (파일명은 history 유지, 공격 컬럼도 포함)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import soccerdata as sd
from lxml import etree, html as lh

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "team_defense_2025_2026.csv"


def main() -> int:
    fb = sd.FBref(leagues="ENG-Premier League", seasons="2025-2026")
    url = "https://fbref.com/en/comps/9/Premier-League-Stats"
    fp = fb.data_dir / "league_ENG-Premier League_2526_standings.html"
    reader = fb.get(url, fp)
    tree = lh.parse(reader)

    # 메인 standings 표 — overall_standings 또는 results
    tbls = tree.xpath("//table[contains(@id, 'overall')]")
    if not tbls:
        tbls = tree.xpath("//table[contains(@id, 'results')]")
    if not tbls:
        print("standings 표 못 찾음")
        return 1
    tbl = tbls[0]
    df_html = pd.read_html(etree.tostring(tbl))[0]
    print("수신 컬럼:", list(df_html.columns))
    print(df_html.head().to_string())

    # 컬럼 이름이 시즌마다 다를 수 있음 — 안전하게 매핑
    def find(name: str):
        for c in df_html.columns:
            cs = str(c).strip()
            if cs == name:
                return c
        return None

    sq = find("Squad")
    mp = find("MP")
    ga = find("GA")
    gf = find("GF")
    if not (sq and mp and ga and gf):
        print(f"필수 컬럼 누락 (Squad/MP/GA/GF): {sq}/{mp}/{ga}/{gf}")
        return 1

    out = pd.DataFrame({
        "squad": df_html[sq].astype(str),
        "games_played": pd.to_numeric(df_html[mp], errors="coerce"),
        "goals_for": pd.to_numeric(df_html[gf], errors="coerce"),
        "goals_against": pd.to_numeric(df_html[ga], errors="coerce"),
    })
    out = out.dropna(subset=["games_played", "goals_for", "goals_against"])
    out["goals_for_per_game"] = out["goals_for"] / out["games_played"]
    out["goals_against_per_game"] = out["goals_against"] / out["games_played"]
    # 정규화: 0(최악) ~ 1(최고)
    g = out["goals_against_per_game"]
    out["defense_score"] = (g.max() - g) / (g.max() - g.min())
    f = out["goals_for_per_game"]
    out["attack_score"] = (f - f.min()) / (f.max() - f.min())
    out = out.sort_values("goals_against").reset_index(drop=True)

    out.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {OUT.name} ({len(out)} 팀)")
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
