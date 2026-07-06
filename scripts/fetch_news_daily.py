"""
일일 뉴스 수집 배치 — ESPN + Guardian/BBC RSS → 번역 → sqlite 누적.

GitHub Actions cron이 매일 실행하고 data/news.db를 repo에 커밋한다.
(link, team) 복합키로 중복 없이 누적되며, 새 기사만 first_seen=오늘으로 들어간다.

수동 실행:
    python scripts/fetch_news_daily.py                 # EPL (기본)
    python scripts/fetch_news_daily.py --league LaLiga # ESPN esp.1 (Guardian/BBC 없이)
    python scripts/fetch_news_daily.py --all           # 전 리그
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ui.news import (  # noqa: E402
    fetch_espn_news, fetch_rss_news, team_articles, merge_news, translate_articles, newstags,
    fetch_es_wire, es_wire_for_team,
)
from news_db import init_db, upsert_articles, stats  # noqa: E402

LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal"]


def run_league(league: str) -> tuple[int, int]:
    tags = newstags(league)
    espn = fetch_espn_news(league)
    wire = fetch_es_wire() if league == "LaLiga" else []   # AS·MD·Sport 리그 와이어 1회
    print(f"[{league}] ESPN {len(espn)}건 · ES와이어 {len(wire)}건 · {len(tags)}팀 처리…")
    new = tot = 0
    for i, team in enumerate(tags, 1):
        e = team_articles(espn, team, 12)
        r = fetch_rss_news(team)                    # EPL: Guardian/BBC · LaLiga: Marca 팀별
        w = es_wire_for_team(wire, team)            # LaLiga: AS/MD/Sport 팀명 매칭
        merged = merge_news(e, r + w, 20)
        translated = translate_articles(merged)
        n = upsert_articles(translated, team)
        new += n; tot += len(translated)
        print(f"  [{i:2}/{len(tags)}] {team:18} {len(translated):2}건 (신규 {n})")
        time.sleep(0.3)
    return new, tot


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--all" in args:
        leagues = LEAGUES
    elif "--league" in args:
        leagues = [args[args.index("--league") + 1]]
    else:
        leagues = ["EPL"]
    init_db()
    tn = tt = 0
    for lg in leagues:
        n, t = run_league(lg)
        tn += n; tt += t
    s = stats()
    print(f"\n완료 — 신규 {tn} / 처리 {tt} · DB 누적 {s['articles']}건 ({s['teams']}팀)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
