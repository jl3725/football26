"""뉴스 화면 DB — pandas 없이 SQLite 안에서 옮기기(news_view.build)와 필요한 줄만 읽기(datastore.news_articles).
2026-11-26 운영 메모리 초과 재시작: 새 뉴스를 받을 때 +120MB, 뉴스 화면이 기사 7만 행 전체를 캐시·사본으로 올림."""
from __future__ import annotations

import datetime as dt
import sqlite3

import datastore as ds
import news_view


def _news_db(path, n=1200):
    today = dt.date.today()
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE articles (link TEXT, team TEXT, source TEXT, headline TEXT, headline_ko TEXT, descr TEXT, "
              "descr_ko TEXT, published TEXT, image TEXT, first_seen TEXT, via TEXT, extra TEXT)")
    rows = []
    for i in range(n):
        day = (today - dt.timedelta(days=i % 90)).isoformat()          # 3분의 1은 60일 밖
        rows.append((f"https://x/{i}", "Arsenal" if i % 2 else "Chelsea", "S", f"h{i}", f"제목{i}", "d", "", day, "", day, "", "z"))
    c.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.execute("CREATE TABLE article_players (link TEXT, player TEXT, squad TEXT, league TEXT, how TEXT)")
    c.execute("INSERT INTO article_players VALUES ('https://x/1', 'Saka', 'Arsenal', 'EPL', 'full')")
    c.commit()
    c.close()


def test_build_copies_recent_articles_in_sqlite(tmp_path) -> None:
    src, dst = tmp_path / "news.db", tmp_path / "news_view.db"
    _news_db(src)
    n = news_view.build(src, dst, log=lambda *_: None)
    c = sqlite3.connect(dst)
    assert n == c.execute("SELECT count(*) FROM news_articles").fetchone()[0]
    assert 0 < n < 1200                                                   # 60일 밖 기사는 빠짐
    cols = [r[1] for r in c.execute("PRAGMA table_info(news_articles)")]
    assert cols == ["link", "team", "source", "headline", "headline_ko", "descr", "descr_ko", "published", "image",
                    "first_seen", "via"]
    assert c.execute("SELECT count(*) FROM news_players").fetchone()[0] == 1
    assert c.execute("SELECT name FROM sqlite_master WHERE name = 'news_meta'").fetchone() is None   # 분류 전 news.db
    c.close()


def test_news_articles_reads_only_needed_rows(tmp_path, monkeypatch) -> None:
    src, dst = tmp_path / "news.db", tmp_path / "news_view.db"
    _news_db(src)
    news_view.build(src, dst, log=lambda *_: None)
    monkeypatch.setattr(ds, "NEWS_VIEW_PATH", dst)
    a = ds.news_articles("team = ?", ("Arsenal",))
    assert len(a) and set(a["team"]) == {"Arsenal"}
    links = [f"https://x/{i}" for i in range(0, 1200, 1)]                # 900개씩 나눠 읽고 표 순서로
    b = ds.news_articles("link IN ({vals})", links)
    full = ds.news_articles()
    assert list(b["link"]) == list(full["link"])
    top = ds.news_articles("team IN (?, ?)", ["Arsenal", "Chelsea"], order="published DESC, rowid", limit=5)
    assert len(top) == 5 and list(top["published"]) == sorted(top["published"], reverse=True)
    assert ds.news_articles("first_seen >= ?", ("2999-01-01",), cols="link").empty
