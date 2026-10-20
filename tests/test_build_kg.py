"""그래프 적재 재료 — 기사 동시 언급 쌍(최근 60일)·대표팀 소집·주장단 매핑(Neo4j 없이)."""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import build_kg as kg  # noqa: E402

N2P = {"EPL": {"declan rice": "tm:1", "bukayo saka": "tm:2", "martin odegaard": "tm:3"},
       "LaLiga": {"pedri": "tm:9"}}


def test_news_pairs_recent_only(tmp_path, monkeypatch) -> None:
    (tmp_path / "data").mkdir()
    db = tmp_path / "data" / "news.db"
    today = dt.date.today().isoformat()
    old = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE articles (link TEXT, team TEXT, first_seen TEXT)")
        c.execute("CREATE TABLE article_players (link TEXT, player TEXT, squad TEXT, league TEXT, how TEXT, tagged_at TEXT)")
        c.executemany("INSERT INTO articles VALUES (?,?,?)", [("a1", "Arsenal", today), ("a2", "Arsenal", today), ("a3", "Arsenal", old)])
        c.executemany("INSERT INTO article_players VALUES (?,?,?,?,?,?)", [
            ("a1", "Declan Rice", "Arsenal", "EPL", "full", today), ("a1", "Bukayo Saka", "Arsenal", "EPL", "full", today),
            ("a2", "Declan Rice", "Arsenal", "EPL", "full", today), ("a2", "Bukayo Saka", "Arsenal", "EPL", "surname", today),
            ("a2", "Martin Ødegaard", "Arsenal", "EPL", "full", today),
            ("a3", "Declan Rice", "Arsenal", "EPL", "full", old), ("a3", "Martin Ødegaard", "Arsenal", "EPL", "full", old)])
    monkeypatch.setattr(kg, "ROOT", tmp_path)
    pairs, count = kg._load_news_pairs(N2P)
    by = {(p["a"], p["b"]): p["n"] for p in pairs}
    assert by[("tm:1", "tm:2")] == 2 and by[("tm:1", "tm:3")] == 1      # 90일 전 기사(a3)는 빠짐
    assert count == {"tm:1": 2, "tm:2": 2, "tm:3": 1}


def test_callups_and_captains_map_to_ids(tmp_path, monkeypatch) -> None:
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"nation": "England", "our_player": "Declan Rice", "our_league": "EPL", "squad_for": "2026-10-06", "caps": 80, "goals": 6},
                  {"nation": "Spain", "our_player": "Pedri", "our_league": "LaLiga", "squad_for": "2026-10-06", "caps": 40, "goals": 3},
                  {"nation": "Brazil", "our_player": "Nobody", "our_league": "EPL", "squad_for": None, "caps": 1, "goals": 0}]
                 ).to_csv(tmp_path / "data" / "intl_callups.csv", index=False)
    monkeypatch.setattr(kg, "ROOT", tmp_path)
    calls = kg._load_callups(N2P)
    assert {(c["pid"], c["nation"]) for c in calls} == {("tm:1", "England"), ("tm:9", "Spain")}

    wiki = tmp_path / "wiki.csv"
    pd.DataFrame([{"squad": "Arsenal", "section": "first", "player": "Martin Ødegaard", "role": "captain", "role_rank": 1},
                  {"squad": "Arsenal", "section": "first", "player": "Bukayo Saka", "role": "vice-captain", "role_rank": 2},
                  {"squad": "Arsenal", "section": "first", "player": "Declan Rice", "role": None, "role_rank": None},
                  {"squad": "Arsenal", "section": "loan", "player": "Nobody", "role": "captain", "role_rank": 1}]).to_csv(wiki, index=False)
    monkeypatch.setattr(kg, "data_path", lambda stem, league=None: wiki)
    caps = kg._load_captains("EPL", N2P["EPL"])
    assert [(c["pid"], c["rank"]) for c in caps] == [("tm:3", 1), ("tm:2", 2)]
