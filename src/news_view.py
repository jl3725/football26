"""
뉴스 화면용 DB(data/news_view.db) — news.db(보관소 원본, src/news_store.py)에서 화면이 쓰는 표만 옮긴다.
  news_articles  최근 60일 기사(src/news_relevance.MAX_DAYS) — 오래된 기사가 40% 를 차지하며 무료 인스턴스(512MB) 메모리만 썼다
  news_players   기사 선수 태그(src/news_tags.py) — 선수 화면 IN THE NEWS · Ask Scout
  news_meta      기사 분류(src/news_classify.py) — 뉴스 탭 종류·이적 단계·기자·STORY

예전엔 scripts/build_db.py 가 football.db 안에 구워 넣어, 뉴스가 바뀔 때마다(2시간) Render 가 재배포했다 — 서버가 다시 뜨고
모든 캐시가 비었다(2026-10-24~25 36시간에 재배포 25번 중 7번이 뉴스). 이제 따로 둔 파일: 배포 때 만들고, 실행 중엔
src/live_sync.py 가 새 뉴스 DB 를 받아 이 파일만 바꾼다. 뉴스 캐시(datastore · api _memo(news=True))는 이 파일 시각으로만 무효화.
루머 판정·적중률(news_reliability·rumor_map)은 news.db 원본을 직접 읽는다.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NEWS_DB = ROOT / "data" / "news.db"
VIEW_DB = ROOT / "data" / "news_view.db"
DAYS = 60


def build(src: Path = NEWS_DB, dst: Path = VIEW_DB, log=print) -> int:
    """news.db → news_view.db(임시 파일에 만든 뒤 한 번에 바꿔 넣는다 — 읽는 중인 연결은 옛 파일을 그대로 본다). 기사 수."""
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.unlink(missing_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(tmp)
    try:
        ndf = pd.read_sql("SELECT link, team, source, headline, headline_ko, descr, descr_ko, published, image, first_seen, via "
                          "FROM articles WHERE coalesce(nullif(substr(published, 1, 10), ''), first_seen) >= "
                          f"date('now', '-{DAYS} day')", s)
        ndf.to_sql("news_articles", d, index=False)
        d.execute("CREATE INDEX idx_news_articles_team ON news_articles(team)")
        d.execute("CREATE INDEX idx_news_articles_link ON news_articles(link)")
        log(f"  · {'news_articles':38s} {len(ndf):6d} rows  (news.db → news_view.db)")
        for name, sql in (("news_players", "SELECT link, player, squad, league, how FROM article_players"),
                          ("news_meta", "SELECT link, kind, stage, journalists, by FROM article_meta")):
            try:
                t = pd.read_sql(sql, s)
            except Exception:  # noqa: BLE001 — 태깅·분류 전 news.db
                continue
            t.to_sql(name, d, index=False)
            d.execute(f"CREATE INDEX idx_{name}_link ON {name}(link)")
            log(f"  · {name:38s} {len(t):6d} rows  (news.db → news_view.db)")
        d.commit()
    finally:
        s.close()
        d.close()
    os.replace(tmp, dst)
    return len(ndf)
