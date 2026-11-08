"""build_kg --fast(매일) — 빠른 관계만 쓰고, 감독(MANAGES)·팀동료·이적 기록은 건드리지도 지우지도 않는다(2026-11-06)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT)]

import build_kg as kg  # noqa: E402


class _Res:
    def single(self):
        return {"n": 0, "pl": 0, "mates": 0, "reps": 0, "euro": 0}

    def data(self):
        return []

    def __iter__(self):
        return iter([])


class _Session:
    def __init__(self, log):
        self.log = log

    def run(self, q, **kw):
        self.log.append(q)
        return _Res()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(monkeypatch, argv):
    log: list[str] = []

    class _Driver:
        def verify_connectivity(self):
            pass

        def session(self, **kw):
            return _Session(log)

        def close(self):
            pass

    fake = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda *a, **k: _Driver()))
    monkeypatch.setitem(sys.modules, "neo4j", fake)
    monkeypatch.setattr(kg, "LEAGUE_META", {"EPL": ("Premier League", "England", 100)})
    one = [{"id": "tm:1", "name": "A", "club": "Arsenal"}]
    monkeypatch.setattr(kg, "_players_and_map", lambda lg: (one, {"a": "tm:1"}))
    for f in ("_live", "_load_influence", "_load_injured"):
        monkeypatch.setattr(kg, f, lambda *a, **k: {})
    for f in ("_load_captains", "_load_managers", "_load_transfers", "_load_reps", "_load_comp_played", "_load_injuries",
              "_load_teammates", "_load_callups", "_load_rumor_links"):
        monkeypatch.setattr(kg, f, lambda *a, **k: [])
    monkeypatch.setattr(kg, "_load_news_pairs", lambda *a, **k: ([], {}))
    monkeypatch.setattr(kg, "_load_matches", lambda *a, **k: ([], []))
    monkeypatch.setattr(kg, "_rumor_history", lambda rumors: [])            # 실제 data/rumor_history.csv 를 건드리지 않게
    monkeypatch.setattr(kg, "_load_injury_spells", lambda *a, **k: [])
    monkeypatch.setattr(kg, "_rumor_base", lambda *a, **k: {})
    monkeypatch.setattr(kg, "_load_claims", lambda *a, **k: {"claims": [], "nodes": [], "reports": [], "writes": []})
    monkeypatch.setattr(kg, "_batched", lambda s, q, rows, **kw: s.run(q, **kw))
    for f in ("_enrich_club_coef", "_enrich_country_fifa"):
        monkeypatch.setattr(kg, f, lambda *a, **k: None)
    assert kg.main(argv) == 0
    return "\n".join(x for x in log if not x.startswith("CREATE CONSTRAINT"))   # 제약 조건 문장엔 라벨 이름이 다 나온다


def test_fast_skips_slow_relations_and_keeps_managers(monkeypatch) -> None:
    q = _run(monkeypatch, ["--fast"])
    assert "PLAYS_FOR" in q and "LINKED_TO" in q and "MENTIONED_WITH" in q and "Claim" in q and ":PLAYED]" in q   # 최근 경기도 매일
    assert "Injury" not in q                                                   # 부상 구간은 주 1회
    assert "WAS_LINKED" in q                                                   # 이적설 이력은 매일
    assert "MANAGES" not in q and "TEAMMATE_OF" not in q and "TransferEvent" not in q   # 쓰지도 지우지도 않는다


def test_full_run_still_writes_and_cleans_managers(monkeypatch) -> None:
    q = _run(monkeypatch, [])
    assert "MANAGES" in q and "TEAMMATE_OF" in q and "TransferEvent" in q and "Injury" in q and ":PLAYED]" in q
