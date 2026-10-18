"""
FotMob 시즌 평점 → data/fotmob_ratings_{리그}_{시즌}.csv — Sofascore 와 함께 '두 출처 평균 평점'을 만든다.

2026-10-19 사용자 제안('Sofascore 하나는 이상할 때가 있다, 여러 사이트 평균'): WhoScored 는 봇 차단이 강해
자동 수집이 어렵고, FotMob 은 공개 JSON(리그 → 시즌별 통계 링크 → rating.json)이라 GH Actions 에서도 받는다.
- 이번 시즌 + 직전 + 2시즌 전(시즌 목록은 SEASON_START 기준 자동). 2시즌 전은 선수 OVR 의 hist_* 에 쓴다.
- 행: fotmob_id(시즌을 넘어 같은 선수), 이름, 팀(우리 표기로 맞춤), 평점, 출전 분·경기 수.
- 팀 이름은 그 시즌 우리 순위표 표기(team_names.best)로, 없으면 FotMob 표기 그대로.
- 끝난 시즌 파일이 이미 있으면 다시 받지 않는다(이번 시즌만 매번).

사용: python src/fetch_fotmob_ratings.py [--league EPL]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time

import pandas as pd
import requests

from leagues import LEAGUES, SEASON_START, data_path
import team_names as tn

FOTMOB_ID = {"EPL": 47, "LaLiga": 87, "SerieA": 55, "Bundesliga": 54, "Ligue1": 53,
             "LigaPortugal": 61, "Eredivisie": 57, "BelgianProLeague": 40}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) football26-research"}
BACK = 2          # 직전 · 2시즌 전까지


def _get(url: str):
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                raw = r.content
                if raw[:2] == b"\x1f\x8b":            # data.fotmob.com 은 gzip 본문을 그대로 줄 때가 있다
                    raw = gzip.decompress(raw)
                return json.loads(raw)
            print(f"    [{r.status_code}] {url}")
        except (requests.RequestException, ValueError) as e:
            print(f"    [재시도 {i + 1}] {e}")
        time.sleep(2 + 2 * i)
    return None


def season_links(fid: int) -> dict[str, str]:
    """{'2026_2027': 'https://data.fotmob.com/stats/47/season/36781/rating.json', …}"""
    d = _get(f"https://www.fotmob.com/api/data/leagues?id={fid}")
    out = {}
    for s in ((d or {}).get("stats") or {}).get("seasonStatLinks") or []:
        name = str(s.get("Name") or "")                 # '2026/2027'
        a, _, b = name.partition("/")
        if a.isdigit() and b.isdigit() and s.get("TournamentId"):
            out[f"{a}_{b}"] = f"https://data.fotmob.com/stats/{fid}/season/{s['TournamentId']}/rating.json"
    return out


def parse(j: dict, league: str, season: str) -> pd.DataFrame:
    rows = []
    for tl in (j or {}).get("TopLists") or []:
        for x in tl.get("StatList") or []:
            rows.append({"fotmob_id": x.get("ParticiantId") or x.get("ParticipantId"), "player": x.get("ParticipantName"),
                         "team_fm": x.get("TeamName"), "rating": x.get("StatValue"), "minutes": x.get("MinutesPlayed"),
                         "matches": x.get("MatchesPlayed"), "nat": x.get("ParticipantCountryCode")})
    df = pd.DataFrame(rows).drop_duplicates(subset=["fotmob_id"]) if rows else pd.DataFrame()
    if df.empty:
        return df
    try:
        st = pd.read_csv(data_path("standings", league, season))
        ours = list(st["squad"].astype(str))
    except (FileNotFoundError, KeyError):
        ours = []
    m = {t: (tn.best(t, ours) if ours else None) or t for t in df["team_fm"].astype(str).unique()}
    df["squad"] = df["team_fm"].map(m)
    df["league"] = league
    df["season"] = season
    return df[["fotmob_id", "player", "squad", "team_fm", "rating", "minutes", "matches", "nat", "league", "season"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    a = ap.parse_args()
    seasons = [f"{y}_{y + 1}" for y in range(SEASON_START, SEASON_START - BACK - 1, -1)]
    bad = 0
    for lg in ([a.league] if a.league else LEAGUES):
        fid = FOTMOB_ID.get(lg)
        if not fid:
            continue
        links = season_links(fid)
        for season in seasons:
            out = data_path("fotmob_ratings", lg, season)
            if season != seasons[0] and out.exists():
                continue                                  # 끝난 시즌은 한 번만
            url = links.get(season)
            if not url:
                print(f"  {lg:16} {season}: 링크 없음")
                continue
            df = parse(_get(url), lg, season)
            time.sleep(1.0)
            if df.empty:
                print(f"  {lg:16} {season}: 0명")
                bad += season == seasons[0]
                continue
            df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
            print(f"  {lg:16} {season}: {len(df)}명 · 평균 {df['rating'].mean():.2f} -> {out.name}")
        time.sleep(1.0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
