"""
뉴스 sqlite 저장소 — 매일 수집한 기사를 누적(추후 graph/vector RAG 코퍼스).

(link, team) 복합 PK로 중복 없이 누적한다. first_seen으로 '오늘 처음 수집된
기사'(NEW)를 판정하고, 앱은 이 DB만 읽어 즉시 렌더한다(실시간 fetch·번역 불필요).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                link        TEXT NOT NULL,
                team        TEXT NOT NULL,
                source      TEXT,
                headline    TEXT,
                headline_ko TEXT,
                descr       TEXT,
                descr_ko    TEXT,
                published   TEXT,
                image       TEXT,
                first_seen  TEXT,
                fetched_at  TEXT,
                PRIMARY KEY (link, team)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_team_pub ON articles(team, published)")


def upsert_articles(articles: list[dict], team: str) -> int:
    """기사 리스트를 (link, team) 기준 upsert. 신규 삽입 건수를 반환."""
    today = date.today().isoformat()
    new = 0
    with _conn() as c:
        for a in articles:
            link = a.get("link") or ""
            if not link:
                continue
            exists = c.execute(
                "SELECT 1 FROM articles WHERE link=? AND team=?", (link, team)
            ).fetchone()
            if exists:
                c.execute("UPDATE articles SET fetched_at=? WHERE link=? AND team=?",
                          (today, link, team))
            else:
                c.execute(
                    """INSERT INTO articles
                       (link, team, source, headline, headline_ko, descr, descr_ko,
                        published, image, first_seen, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (link, team, a.get("source", ""), a.get("headline", ""),
                     a.get("headline_ko", ""), a.get("desc", ""), a.get("desc_ko", ""),
                     a.get("published", ""), a.get("image", ""), today, today))
                new += 1
    return new


def read_team_news(team: str, limit: int = 16) -> list[dict]:
    """팀 기사를 발행일 내림차순으로. is_new(오늘 처음 수집) 플래그 포함."""
    try:
        with _conn() as c:
            rows = c.execute(
                """SELECT * FROM articles WHERE team=?
                   ORDER BY published DESC, first_seen DESC LIMIT ?""",
                (team, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    today = date.today().isoformat()
    out = []
    for r in rows:
        d = dict(r)
        d["desc"] = d.pop("descr", "")
        d["desc_ko"] = d.pop("descr_ko", "")
        d["teams"] = [d["team"]]
        d["is_new"] = (d.get("first_seen") == today)
        out.append(d)
    return out


def stats() -> dict:
    """DB 요약(총 기사 수, 팀 수, 최신 수집일)."""
    try:
        with _conn() as c:
            n = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            teams = c.execute("SELECT COUNT(DISTINCT team) FROM articles").fetchone()[0]
            last = c.execute("SELECT MAX(fetched_at) FROM articles").fetchone()[0]
    except sqlite3.OperationalError:
        return {"articles": 0, "teams": 0, "last_fetch": None}
    return {"articles": n, "teams": teams, "last_fetch": last}
