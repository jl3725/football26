"""
ClubElo 예측 — 유럽 클럽 Elo 레이팅으로 만든 독립 예측 모델(clubelo.com)의 다가오는 리그 경기 승·무·패 확률.

api.clubelo.com/Fixtures 는 경기별 골득실 분포(GD<-5 … GD>5)를 준다 → 홈 승 = GD>0 합, 무 = GD=0, 원정 승 = GD<0 합.
팀 표기는 우리 standings 표기로 맞춰 저장한다(team_names.best). 회사 PC 회선에선 막혀 있어 GH Actions(daily_data)가 돈다.
출력: data/clubelo_fixtures.csv (시즌 무관 · 매번 새로 씀)

    python src/fetch_clubelo.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import data_path  # noqa: E402
import team_names  # noqa: E402

URL = "http://api.clubelo.com/Fixtures"
OUT = Path(__file__).resolve().parent.parent / "data" / "clubelo_fixtures.csv"
COUNTRY = {"ENG": "EPL", "ESP": "LaLiga", "ITA": "SerieA", "GER": "Bundesliga", "FRA": "Ligue1",
           "NED": "Eredivisie", "POR": "LigaPortugal", "BEL": "BelgianProLeague"}


def _gd(col: str) -> int | None:
    """'GD<-5' → -6, 'GD=-2' → -2, 'GD=0' → 0, 'GD>5' → 6. 골득실 열이 아니면 None."""
    c = col.replace(" ", "")
    if c.startswith("GD<"):
        return -99
    if c.startswith("GD>"):
        return 99
    m = re.match(r"GD=(-?\d+)$", c)
    return int(m.group(1)) if m else None


def main() -> int:
    r = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 (football26 data)"})
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    gd_cols = {c: _gd(c) for c in df.columns if _gd(c) is not None}
    if not gd_cols:
        print(f"[clubelo] 골득실 열 없음 — 형식 변경? 열: {list(df.columns)[:12]}")
        return 1
    teams = {}
    for c, lg in COUNTRY.items():
        p = data_path("standings", lg)
        teams[lg] = list(pd.read_csv(p)["squad"].astype(str)) if p.exists() else []
    rows, unmatched = [], set()
    for _, x in df.iterrows():
        lg = COUNTRY.get(str(x.get("Country")))
        if not lg:
            continue
        h, a = team_names.best(str(x["Home"]), teams[lg]), team_names.best(str(x["Away"]), teams[lg])
        if not h or not a:
            unmatched |= {str(x["Home"]) if not h else "", str(x["Away"]) if not a else ""} - {""}
            continue
        ph = sum(float(x[c]) for c, g in gd_cols.items() if g > 0)
        pd_ = sum(float(x[c]) for c, g in gd_cols.items() if g == 0)
        pa = sum(float(x[c]) for c, g in gd_cols.items() if g < 0)
        t = ph + pd_ + pa or 1.0
        rows.append({"date": str(x["Date"])[:10], "league": lg, "home": h, "away": a,
                     "p_home": round(ph / t, 3), "p_draw": round(pd_ / t, 3), "p_away": round(pa / t, 3),
                     "home_src": x["Home"], "away_src": x["Away"]})
    if unmatched:
        print(f"[clubelo] 이름 못 맞춤 {len(unmatched)}: {sorted(unmatched)[:15]}")
    if not rows:
        print("[clubelo] 0건 — 기존 파일 유지")
        return 1
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"[OK] {OUT.name} · {len(rows)}경기")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
