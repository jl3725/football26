"""
뉴스 sqlite 저장소 — 매일 수집한 기사를 누적(추후 graph/vector RAG 코퍼스).

(link, team) 복합 PK로 중복 없이 누적한다. first_seen으로 '오늘 처음 수집된
기사'(NEW)를 판정하고, 앱은 이 DB만 읽어 즉시 렌더한다(실시간 fetch·번역 불필요).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"


_HANGUL = re.compile(r"[가-힣]")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.create_function("HAS_KO", 1, lambda t: 1 if t and _HANGUL.search(str(t)) else 0, deterministic=True)
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


# 한글이 한 글자도 없는 번역문(철자만 바뀐 원문 등 — 2026-10-14 Marca)도 미번역으로 본다. HAS_KO 는 _conn() 이 등록
_UNTRANSLATED = ("(headline_ko IS NULL OR headline_ko='' OR headline_ko=headline OR NOT HAS_KO(headline_ko)"
                 " OR (descr IS NOT NULL AND descr<>'' AND NOT HAS_KO(descr_ko)))")


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
                hk, dk = a.get("headline_ko", ""), a.get("desc_ko", "")
                if not hk:                       # 다른 팀으로 이미 번역된 같은 기사면 그 번역을 재사용
                    prev = c.execute(
                        f"SELECT headline_ko, descr_ko FROM articles WHERE link=? AND NOT {_UNTRANSLATED} LIMIT 1",
                        (link,)).fetchone()
                    if prev:
                        hk, dk = prev
                c.execute(
                    """INSERT INTO articles
                       (link, team, source, headline, headline_ko, descr, descr_ko,
                        published, image, first_seen, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (link, team, a.get("source", ""), a.get("headline", ""),
                     hk, a.get("desc", ""), dk,
                     a.get("published", ""), a.get("image", ""), today, today))
                new += 1
    return new


def untranslated(limit: int = 400) -> list[dict]:
    """번역이 비었거나 원문이 들어간 기사(최신순). 같은 링크는 한 번만."""
    with _conn() as c:
        rows = c.execute(
            f"""SELECT link, max(headline) AS headline, max(descr) AS descr FROM articles
                WHERE {_UNTRANSLATED} GROUP BY link ORDER BY max(first_seen) DESC, max(published) DESC LIMIT ?""",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def set_translation(link: str, headline_ko: str | None, descr_ko: str | None) -> int:
    """링크의 모든 팀 행에 번역을 채운다(헤드라인 번역이 없으면 건너뜀)."""
    if not headline_ko:
        return 0
    with _conn() as c:
        cur = c.execute("UPDATE articles SET headline_ko=?, descr_ko=? WHERE link=?",
                        (headline_ko, descr_ko or "", link))
        return cur.rowcount


def translation_stats(since: str) -> dict:
    """since(YYYY-MM-DD) 이후 수집 기사의 번역률 — 감시용."""
    with _conn() as c:
        tot, bad = c.execute(
            f"SELECT count(*), sum(CASE WHEN {_UNTRANSLATED} THEN 1 ELSE 0 END) FROM articles WHERE first_seen>=?",
            (since,)).fetchone()
    tot, bad = int(tot or 0), int(bad or 0)
    return {"since": since, "articles": tot, "untranslated": bad,
            "translated_pct": round(100 * (tot - bad) / tot, 1) if tot else None}


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
