"""데이터 배포본(scripts/publish_data.py) · 운영 서버 데이터 받기(src/live_sync.sync_data) · 캐시 비우기(reset_caches).

2026-10-26: 데이터 커밋마다 재배포(3일 72번)하던 것을 — 클라우드가 서버 DB·캐시를 만들어 data-live 에 올리고, 서버가 바뀐
파일만 받아 바꿔 넣는다.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import live_sync  # noqa: E402
import publish_data as pdp  # noqa: E402


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_plan_detects_changes():
    remote = {"db_sha": "d1", "files": {"data/a.csv": "1", "data/b.csv": "2", "data/runtime_cache/x.pkl": "9"}}
    pl = pdp.plan({"data/a.csv": "1", "data/b.csv": "3", "data/c.csv": "4"}, "d1", {**remote, "code_sig": "s1"}, "s1")
    assert pl == {"changed": ["data/b.csv", "data/c.csv"], "removed": [], "db_changed": False, "cache_changed": False}
    assert pdp.plan({"data/a.csv": "1"}, "d2", remote)["removed"] == ["data/b.csv"]   # 캐시 묶음은 '지움'으로 안 본다
    assert pdp.plan({}, "d2", {})["db_changed"] is True
    # 모델 코드만 바뀌어도(DB 그대로) 캐시 묶음은 새로 — 2026-10-27 옛 OVR 캐시가 그대로 가던 것
    moved = pdp.plan({"data/a.csv": "1", "data/b.csv": "2"}, "d1", {**remote, "code_sig": "s1"}, "s2")
    assert moved["db_changed"] is False and moved["cache_changed"] is True
    assert pdp.plan({}, "d1", remote, "s1")["cache_changed"] is True     # 지문 없는 옛 배포본


class _Resp:
    def __init__(self, body: bytes, code: int = 200):
        self.content, self.status_code = body, code

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _setup(tmp_path, monkeypatch, remote: dict[str, bytes], db: bytes, main_sha="m1", sig="sig1"):
    monkeypatch.setattr(live_sync, "ROOT", tmp_path)
    monkeypatch.setattr(live_sync, "_SIG", ["sig1"])                 # 이 서버 코드의 지문
    monkeypatch.setattr(live_sync, "_HASHES", {})
    monkeypatch.setattr(live_sync, "_ON_DB_SWAP", [])
    monkeypatch.setitem(live_sync.STATE, "data_sha", "")
    (tmp_path / "data").mkdir(exist_ok=True)
    man = {"main_sha": main_sha, "db_sha": _h(db), "db_gz": "data/football.db.gz", "code_sig": sig,
           "files": {p: _h(b) for p, b in remote.items()}}
    store = {"manifest.json": json.dumps(man).encode(), "data/football.db.gz": gzip.compress(db), **remote}

    def get(url, **kw):
        path = url.split("/data-live/", 1)[1]
        return _Resp(store[path])
    return get, store


def test_sync_data_replaces_changed_and_swaps_db(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "same.csv").write_bytes(b"a\n1\n")
    (tmp_path / "data" / "old.csv").write_bytes(b"a\n1\n")
    (tmp_path / "data" / "football.db").write_bytes(b"OLD-DB")
    get, _ = _setup(tmp_path, monkeypatch, {"data/same.csv": b"a\n1\n", "data/old.csv": b"a\n2\n",
                                            "data/runtime_cache/x.pkl": b"PICKLE"}, b"NEW-DB")
    called = []
    live_sync.on_db_swap(lambda: called.append(1))
    monkeypatch.setattr(live_sync, "reset_caches", lambda: 7)
    n = live_sync.sync_data(get)
    assert n == 3                                                    # old.csv · 새 캐시 파일 · DB (same.csv 는 그대로)
    assert (tmp_path / "data" / "old.csv").read_bytes() == b"a\n2\n"
    assert (tmp_path / "data" / "runtime_cache" / "x.pkl").read_bytes() == b"PICKLE"
    assert (tmp_path / "data" / "football.db").read_bytes() == b"NEW-DB"
    assert called == [1] and live_sync.STATE["data_sha"] == "m1"
    assert not list((tmp_path / "data").rglob("*.part"))
    assert live_sync.sync_data(get) == 0                             # 같은 배포본이면 다시 안 받는다


def test_sync_data_skips_caches_built_by_other_code(tmp_path, monkeypatch):
    # 배포본 캐시를 만든 코드 ≠ 이 서버 코드 → 캐시는 안 받고(서버가 자기 코드로 만든 것을 지킨다) 데이터·DB 만
    (tmp_path / "data" / "runtime_cache").mkdir(parents=True)
    (tmp_path / "data" / "runtime_cache" / "x.pkl").write_bytes(b"MINE")
    (tmp_path / "data" / "football.db").write_bytes(b"DB")
    get, _ = _setup(tmp_path, monkeypatch, {"data/a.csv": b"A", "data/runtime_cache/x.pkl": b"OLD-CODE",
                                            "data/team_units.json": b"{}"}, b"DB", sig="other")
    assert live_sync.sync_data(get) == 1
    assert (tmp_path / "data" / "a.csv").read_bytes() == b"A"
    assert (tmp_path / "data" / "runtime_cache" / "x.pkl").read_bytes() == b"MINE"
    assert not (tmp_path / "data" / "team_units.json").exists()


def test_sync_data_uses_head_commit_and_skips_when_same(tmp_path, monkeypatch):
    # 머리 커밋을 보면 그 커밋 주소로 받고(브랜치 주소는 raw CDN 이 5분까지 옛것), 머리가 그대로면 manifest 도 안 받는다
    # (3분 주기 · 2026-10-29 사용자 '실시간 느낌')
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "football.db").write_bytes(b"OLD")
    _, store = _setup(tmp_path, monkeypatch, {"data/a.csv": b"A"}, b"NEW")
    monkeypatch.setitem(live_sync.STATE, "data_ref", "")
    monkeypatch.setitem(live_sync.STATE, "mark_read", True)
    monkeypatch.setattr(live_sync, "reset_caches", lambda: 0)
    head, seen = "c" * 40, []

    def get(url, **kw):
        seen.append(url)
        if url.endswith("info/refs?service=git-upload-pack"):
            return _Resp(f"0045{'d' * 40} refs/heads/data-livex\n0042{head} refs/heads/data-live\n".encode())
        return _Resp(store[url.split(f"/{head}/", 1)[1]])
    assert live_sync.sync_data(get, notify=False) == 2                # a.csv · DB
    assert live_sync.STATE["data_ref"] == head
    seen.clear()
    assert live_sync.sync_data(get, notify=False) == 0 and len(seen) == 1   # 머리만 보고 끝
    # 다시 뜬 서버(빌드에서 받은 그대로)는 기록(runtime_cache/live_sync.json)으로 같은 배포본임을 안다 — 지문 재계산 없음
    for k, v in (("data_ref", ""), ("data_sha", ""), ("mark_read", False)):
        monkeypatch.setitem(live_sync.STATE, k, v)
    seen.clear()
    assert live_sync.sync_data(get, notify=False) == 0 and len(seen) == 1 and live_sync.STATE["data_sha"] == "m1"


def test_sync_data_aborts_on_hash_mismatch(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.csv").write_bytes(b"OLD")
    (tmp_path / "data" / "football.db").write_bytes(b"DB")
    get, store = _setup(tmp_path, monkeypatch, {"data/x.csv": b"NEW", "data/y.csv": b"Y"}, b"DB")
    store["data/y.csv"] = b"STALE-CDN"                               # CDN 이 옛 파일을 준 경우
    try:
        live_sync.sync_data(get)
        raise AssertionError("지문이 다르면 실패해야 한다")
    except ValueError:
        pass
    assert (tmp_path / "data" / "x.csv").read_bytes() == b"OLD"      # 아무것도 반쯤 바꾸지 않는다
    assert live_sync.STATE["data_sha"] == ""


def test_reset_caches_clears_lru_and_named_dicts(monkeypatch):
    import functools
    mod = types.ModuleType("fake_live_mod")
    mod.__file__ = str(ROOT / "src" / "fake_live_mod.py")

    @functools.lru_cache(maxsize=None)
    def loader():
        return object()
    loader.__module__ = "fake_live_mod"
    mod.loader = loader
    mod._THING_CACHE = {"a": 1}
    mod._HUB_CACHE = {"key": "k", "body": b"x"}
    mod._LABELS = {"x": "y"}                                         # 상수 — 안 비운다
    mod._LAZY_CACHE = {"EPL": 100}                                   # '_LAZY_CACHE: dict | None' — None 이 '아직 안 읽음'
    mod._VALS_CACHE = {("a", "b"): None}                             # 값에만 None — 비우기만(None 으로 바꾸면 .get 이 깨진다)
    mod.__annotations__ = {"_LAZY_CACHE": "dict | None", "_VALS_CACHE": "dict[tuple[str, str], list[dict] | None]"}
    first = loader()
    live_sync.reset_caches([mod])                                    # 실제 모듈 캐시는 건드리지 않게 이 모듈만
    assert loader() is not first
    assert mod._THING_CACHE == {} and mod._HUB_CACHE == {"key": None, "body": None} and mod._LABELS == {"x": "y"}
    assert mod._LAZY_CACHE is None                                   # 빈 dict 면 '읽었음'으로 보고 다시 안 읽는다
    assert mod._VALS_CACHE == {}
