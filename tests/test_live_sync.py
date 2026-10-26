"""실행 중 데이터 받기(src/live_sync.py) · 뉴스 화면 DB(src/news_view.py) · 뉴스 표 경로(datastore.db_path).

2026-10-26: 뉴스 커밋마다 재배포(36시간 25번 중 7번)로 서버가 다시 뜨던 것 — 뉴스 표를 news_view.db 로 떼고, 운영 서버가
GitHub 에서 받아 갈아 끼운다.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import datastore as ds  # noqa: E402
import live_sync  # noqa: E402
import news_store  # noqa: E402
import news_view  # noqa: E402


def _news_db(path: Path, n: int = 3) -> Path:
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE articles (link, team, source, headline, headline_ko, descr, descr_ko, published, image, first_seen, via)")
    today = dt.date.today().isoformat()
    for i in range(n):
        c.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (f"l{i}", "Arsenal", "BBC", f"h{i}", "", "", "", today, "", today, "rss"))
    c.execute("INSERT INTO articles VALUES ('old','Arsenal','BBC','old','','','','2020-01-01','','2020-01-01','rss')")
    c.execute("CREATE TABLE article_meta (link, kind, stage, journalists, by)")
    c.execute("INSERT INTO article_meta VALUES ('l0','transfer','talks','','rule')")
    c.commit()
    c.close()
    return path


def test_news_view_build(tmp_path):
    src = _news_db(tmp_path / "news.db")
    dst = tmp_path / "news_view.db"
    assert news_view.build(src, dst, log=lambda *_: None) == 3            # 60일 넘은 기사는 뺀다
    c = sqlite3.connect(dst)
    tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tabs == {"news_articles", "news_meta"}                         # 태깅 전 news.db — news_players 없음
    assert not (tmp_path / "news_view.db.tmp").exists()


def test_db_path_routes_news_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "NEWS_VIEW_PATH", tmp_path / "news_view.db")
    assert ds.db_path("news_articles") == ds.DB_PATH                     # 파일 없으면(옛 빌드) football.db
    (tmp_path / "news_view.db").write_bytes(b"")
    assert ds.db_path("news_articles") == tmp_path / "news_view.db"
    assert ds.db_path("standings") == ds.DB_PATH


class _Resp:
    def __init__(self, code=200, body=b"", headers=None):
        self.status_code, self.content, self.headers = code, body, headers or {}

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sync_news_replaces_view(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    gz = gzip.compress(_news_db(tmp_path / "remote.db", n=5).read_bytes())
    monkeypatch.setattr(live_sync, "DATA", data)
    monkeypatch.setattr(news_store, "DB", data / "news.db")
    monkeypatch.setattr(news_store, "REF", data / "news_db.ref.json")
    monkeypatch.setattr(news_view, "VIEW_DB", data / "news_view.db")
    monkeypatch.setattr(news_view, "NEWS_DB", data / "news.db")
    (data / "news_db.ref.json").write_text(json.dumps({"sha": "old"}), encoding="utf-8")
    real_build = news_view.build
    monkeypatch.setattr(news_view, "build", lambda src=None, dst=None, log=print: real_build(src, data / "news_view.db", log))
    ref = json.dumps({"sha": "new123", "articles": 5}).encode()

    def get(url, **kw):
        return _Resp(body=ref) if url.endswith("news_db.ref.json") else _Resp(body=gz)
    assert live_sync.sync_news(get) is True
    assert json.loads((data / "news_db.ref.json").read_text(encoding="utf-8"))["sha"] == "new123"
    c = sqlite3.connect(data / "news_view.db")
    assert c.execute("SELECT count(*) FROM news_articles").fetchone()[0] == 5
    c.close()
    assert live_sync.sync_news(get) is False                              # 같은 sha 면 다시 안 받는다
    assert not list(data.glob("*.part"))


def test_sync_small_writes_changed_only(tmp_path, monkeypatch):
    monkeypatch.setattr(live_sync, "ROOT", tmp_path)
    monkeypatch.setattr(live_sync, "DATA", tmp_path / "data")
    monkeypatch.setattr(live_sync, "SMALL", ["data/ai/news_digest.json", "data/news_claims.csv"])
    monkeypatch.setattr(live_sync, "_ETAGS", {})
    (tmp_path / "data" / "ai").mkdir(parents=True)
    (tmp_path / "data" / "ai" / "news_digest.json").write_text("{}", encoding="utf-8")

    def get(url, **kw):
        if url.endswith("news_digest.json"):
            return _Resp(body=b"{}", headers={"ETag": "e1"})                 # 같음 — 안 씀
        return _Resp(body=b"a,b\n1,2\n")
    assert live_sync.sync_small(get) == 1
    assert (tmp_path / "data" / "news_claims.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert live_sync._ETAGS["data/ai/news_digest.json"] == "e1"


def test_disabled_outside_render(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("LIVE_SYNC", raising=False)
    assert live_sync.enabled() is False
