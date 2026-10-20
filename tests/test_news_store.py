"""news.db 보관소(data-news 브랜치) — 받은 압축본 검사, 기사 급감 시 올리기 거부(빈 DB 로 덮어쓰기 방지)."""
from __future__ import annotations

import gzip
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import news_store as ns  # noqa: E402


def _db(path: Path, n: int) -> Path:
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE articles (link TEXT, team TEXT)")
        c.executemany("INSERT INTO articles VALUES (?, ?)", [(f"l{i}", "Arsenal") for i in range(n)])
    return path


def test_install_validates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ns, "DB", tmp_path / "data" / "news.db")
    good = gzip.compress(_db(tmp_path / "src.db", 3).read_bytes())
    assert ns._install(good, "test") and ns.articles(ns.DB) == 3
    # 기사 0건·압축 아님 → 거부하고 기존 파일 유지
    assert not ns._install(gzip.compress(_db(tmp_path / "empty.db", 0).read_bytes()), "empty")
    assert not ns._install(b"not gzip", "junk")
    assert ns.articles(ns.DB) == 3


def test_pull_keeps_existing_and_strict_stops(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ns, "DB", _db(tmp_path / "news.db", 2))
    assert ns.pull() is True                                   # 이미 있으면 받지 않는다
    monkeypatch.setattr(ns, "DB", tmp_path / "missing.db")
    monkeypatch.setattr(ns, "REF", tmp_path / "ref.json")

    class Boom:
        def get(self, *a, **k):
            import requests
            raise requests.ConnectionError("offline")
    monkeypatch.setitem(sys.modules, "requests", __import__("requests"))
    monkeypatch.setattr(sys.modules["requests"], "get", Boom().get)
    monkeypatch.setattr(ns.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    assert ns.pull() is False
    with pytest.raises(SystemExit):
        ns.pull(strict=True)


def test_push_refuses_big_drop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ns, "DB", _db(tmp_path / "news.db", 10))
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"sha": "abc", "articles": 1000}), encoding="utf-8")
    monkeypatch.setattr(ns, "REF", ref)
    monkeypatch.setattr(ns, "_git", lambda *a, **k: pytest.fail("git 을 부르면 안 된다"))
    with pytest.raises(SystemExit):
        ns.push()
