"""뉴스 보관소 압축 형식(gz·xz) — 읽는 쪽은 앞 바이트로 가리고 ref 'file' 을 따른다 · 지운 기사의 태그 줄 정리(2026-11-10)."""
from __future__ import annotations

import gzip
import lzma
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import news_store as ns  # noqa: E402


def _db(path: Path) -> None:
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE articles (link TEXT PRIMARY KEY, via TEXT, first_seen TEXT)")
    c.execute("CREATE TABLE article_tagged (link TEXT PRIMARY KEY, tagged_at TEXT)")
    c.execute("CREATE TABLE article_meta (link TEXT PRIMARY KEY, kind TEXT)")
    c.executemany("INSERT INTO articles VALUES (?,?,?)", [("a", "gnews", "2026-01-01"), ("b", "", "2026-01-01")])
    c.executemany("INSERT INTO article_tagged VALUES (?,?)", [("a", "x"), ("b", "x")])
    c.commit()
    c.close()


def test_readers_accept_gzip_and_xz(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "n.db"
    _db(raw)
    blob = raw.read_bytes()
    assert ns.decompress(gzip.compress(blob)) == blob and ns.decompress(lzma.compress(blob)) == blob
    for name, comp in (("a.gz", gzip.compress), ("a.xz", lzma.compress)):
        p = tmp_path / name
        p.write_bytes(comp(blob))
        with ns.open_archive(p) as fh:
            assert fh.read() == blob
    monkeypatch.setattr(ns, "DB", tmp_path / "out.db")
    assert ns._install(lzma.compress(blob), "test") and ns.articles(ns.DB) == 2
    assert ns.archive_name({"file": "news.db.xz"}) == "news.db.xz" and ns.archive_name({}) == ns.NAME


def test_writer_xz_switch(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "n.db"
    _db(raw)
    monkeypatch.setattr(ns, "DB", raw)
    monkeypatch.setattr(ns, "ARCHIVE", "xz")
    out = ns._gzip(str(tmp_path))
    assert out.name == "news.db.xz" and lzma.decompress(out.read_bytes()) == raw.read_bytes()


def test_trim_drops_tag_rows_of_deleted_articles(tmp_path) -> None:
    p = tmp_path / "n.db"
    _db(p)
    assert ns.trim(p, days=1) == 1                            # gnews 'a' 만(기본 원천 'b' 는 그대로)
    c = sqlite3.connect(p)
    assert [r[0] for r in c.execute("SELECT link FROM article_tagged")] == ["b"]
    c.close()
