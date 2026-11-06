"""뉴스 본문 검색(src/news_vectors.py) + Ask Scout search_news — Qdrant·Gemini 없이(가짜)."""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import news_vectors as nv  # noqa: E402


def _db(tmp_path: Path) -> Path:
    p = tmp_path / "news.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE articles (link, team, source, headline, headline_ko, descr, descr_ko, published, image, first_seen, fetched_at, via, author)")
    c.execute("CREATE TABLE article_players (link, player, squad, league, how, tagged_at)")
    c.execute("CREATE TABLE article_meta (link, kind, stage, journalists, by, at)")
    today = dt.date.today().isoformat()
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    for link, kind, day, how in (("a", "injury", today, "full"), ("b", "match", today, "full"), ("c", "transfer", old, "full"),
                                 ("d", "transfer", today, "surname")):
        c.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (link, "Arsenal", "BBC", f"head {link}", f"제목 {link}", "desc", "", day, "", day, day, "wire", ""))
        c.execute("INSERT INTO article_players VALUES (?,?,?,?,?,?)", (link, "Bukayo Saka", "Arsenal", "EPL", how, day))
        c.execute("INSERT INTO article_meta VALUES (?,?,?,?,?,?)", (link, kind, "", "", "rule", day))
    c.commit()
    c.close()
    return p


def test_candidates_recent_tagged_non_match_only(tmp_path) -> None:
    got = nv.candidates(_db(tmp_path), days=30)
    assert [a["link"] for a in got] == ["a"]                      # 경기 리포트·30일 지난 기사·성만 태그된 기사는 빼고
    a = got[0]
    assert a["players"] == ["Bukayo Saka"] and a["squads"] == ["Arsenal"] and a["kind"] == "injury" and a["day"] > 20000000


def test_index_skips_existing_and_stops_on_quota(monkeypatch, tmp_path) -> None:
    import news_store
    db = _db(tmp_path)
    monkeypatch.setattr(news_store, "ensure", lambda: db)
    sent = []
    monkeypatch.setattr(nv, "_q", lambda m, path, body=None, timeout=30: sent.append((m, path, body)) or [])
    monkeypatch.setattr(nv, "embed", lambda texts, task="RETRIEVAL_DOCUMENT": [[0.1] * nv.DIM for _ in texts])
    r = nv.index(days=30, pause=0)
    assert r["new"] == 1 and any(p.startswith("/collections/news/points?wait") for _, p, _ in sent)
    monkeypatch.setattr(nv, "existing", lambda ids: set(ids))
    assert nv.index(days=30, pause=0)["new"] == 0                         # 이미 넣은 기사는 건너뜀

    def quota(texts, task="RETRIEVAL_DOCUMENT"):
        raise nv.QuotaError("429")
    monkeypatch.setattr(nv, "existing", lambda ids: set())
    monkeypatch.setattr(nv, "embed", quota)
    r = nv.index(days=30, pause=0)
    assert r["new"] == 0 and "429" in r["stopped"]                       # 한도면 멈추고 다음 실행이 잇는다


def test_search_filters_then_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(nv, "embed", lambda texts, task="RETRIEVAL_QUERY": [[0.2] * nv.DIM])
    calls = []

    def fake_q(m, path, body=None, timeout=30):
        calls.append(body)
        if body.get("filter"):
            return []                                                     # 조건으로는 0건
        return [{"score": 0.71, "payload": {"headline": "Saka injury update", "source": "BBC", "published": "2026-11-05", "link": "x"}}]
    monkeypatch.setattr(nv, "_q", fake_q)
    r = nv.search("사카 부상", players=["Bukayo Saka"], squad="Arsenal")
    assert r["count"] == 1 and r["articles"][0]["source"] == "BBC"
    assert calls[0]["filter"]["must"][0] == {"key": "players", "match": {"any": ["Bukayo Saka"]}} and "filter" not in calls[1]


def test_scout_search_news_tool(monkeypatch) -> None:
    import scout_agent as sa
    import scout_router as sr
    monkeypatch.setattr(sa, "_api", lambda: object())
    monkeypatch.setattr(sa, "_clubs", lambda: ["Arsenal"])
    monkeypatch.setattr(sr, "parse", lambda text, team, league: {"players": [{"name": "Bukayo Saka", "squad": "Arsenal", "league": "EPL"}]})
    got = {}
    monkeypatch.setattr(nv, "search", lambda q, players, squad, kind: got.update(q=q, players=players, squad=squad, kind=kind)
                        or {"query": q, "count": 0, "articles": []})
    intent, res = sa._execute("search_news", {"query": "부상 소식", "player": "사카", "team": "Arsenal"}, "EPL")
    assert intent == "news" and got == {"q": "부상 소식", "players": ["Bukayo Saka"], "squad": "Arsenal", "kind": None}
    assert "player_news" in sa._retry_hint(intent, res)                   # 0건이면 이름 태그 목록으로 다시
