"""
일일 뉴스 수집 배치 — ESPN + Guardian/BBC RSS → 번역 → sqlite 누적.

GitHub Actions cron이 매일 실행하고 data/news.db를 repo에 커밋한다.
(link, team) 복합키로 중복 없이 누적되며, 새 기사만 first_seen=오늘으로 들어간다.

수동 실행:
    python scripts/fetch_news_daily.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ui.news import (  # noqa: E402
    fetch_espn_news, fetch_rss_news, team_articles, merge_news, translate_articles,
    SQUAD_TO_NEWSTAG,
)
from news_db import init_db, upsert_articles, stats  # noqa: E402

TEAMS = list(SQUAD_TO_NEWSTAG)


def main() -> int:
    init_db()
    espn = fetch_espn_news()
    print(f"ESPN 기사 {len(espn)}건 수집. {len(TEAMS)}팀 처리 시작...")
    total_new = total = 0
    for i, team in enumerate(TEAMS, 1):
        e = team_articles(espn, team, 12)
        r = fetch_rss_news(team)
        merged = merge_news(e, r, 16)
        translated = translate_articles(merged)   # 헤드라인·요약 한국어 번역
        n = upsert_articles(translated, team)
        total_new += n
        total += len(translated)
        print(f"  [{i:2}/{len(TEAMS)}] {team:18} {len(translated):2}건 (신규 {n})")
        time.sleep(0.3)   # 번역 API 매너
    s = stats()
    print(f"\n완료 — 이번 신규 {total_new} / 처리 {total} · DB 누적 {s['articles']}건 "
          f"({s['teams']}팀, 최신 {s['last_fetch']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
