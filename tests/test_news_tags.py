"""뉴스 선수 태깅 — 이름 전체는 태그, 성만은 클럽 이름과 함께일 때만(감독·같은 성·다른 사람 이름 앞 단어는 막기)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import news_tags as nt  # noqa: E402

PLAYERS = pd.DataFrame([
    {"league": "EPL", "squad": "Arsenal", "player": "Bukayo Saka"},
    {"league": "EPL", "squad": "Arsenal", "player": "Declan Rice"},
    {"league": "EPL", "squad": "Chelsea", "player": "Pedro Neto"},
    {"league": "EPL", "squad": "Chelsea", "player": "João Pedro"},
    {"league": "LaLiga", "squad": "Atlético Madrid", "player": "Giuliano Simeone"},
    {"league": "LaLiga", "squad": "Atlético Madrid", "player": "Julián Álvarez"},
    {"league": "LaLiga", "squad": "Real Madrid", "player": "Kylian Mbappé"},
    {"league": "LaLiga", "squad": "Athletic Club", "player": "Nico Williams"},
    {"league": "LaLiga", "squad": "Athletic Club", "player": "Iñaki Williams"},
    {"league": "LaLiga", "squad": "Espanyol", "player": "Urko González"},
])
MANAGERS = {"Atlético Madrid": "Diego Simeone", "Espanyol": "Manolo González"}
IDX = nt.Index(PLAYERS, MANAGERS)


def names(text: str) -> dict[str, str]:
    return {p: how for p, _, _, how in IDX.tag(text)}


def test_full_name_and_surname_with_club() -> None:
    assert names("Bukayo Saka scores twice") == {"Bukayo Saka": "full"}
    assert names("Saka and Rice star as Arsenal win") == {"Bukayo Saka": "surname", "Declan Rice": "surname"}
    assert names("Rice prices are up; Saka is a dish") == {}                 # 클럽 이름이 없으면 성만으로는 안 붙인다
    assert names("Kylian Mbappe double for Madrid") == {"Kylian Mbappé": "full"}   # 악센트 무시


def test_blocks_manager_and_other_person_surnames() -> None:
    assert names("Atlético Madrid coach Diego Simeone praises Álvarez") == {"Julián Álvarez": "surname"}
    assert names("Simeone furious after Atlético Madrid derby") == {}         # 그 클럽 감독과 같은 성
    assert names("Los de Manolo González ganan; Espanyol líder") == {}
    assert "Urko González" in names("Urko González renews with Espanyol")


def test_same_surname_and_full_name_spans() -> None:
    assert names("Iñaki Williams scores for Athletic Club") == {"Iñaki Williams": "full"}   # 형제 — 성만으론 안 붙음
    assert names("Chelsea hand Pedro Neto new deal") == {"Pedro Neto": "full"}           # 'Pedro' 는 주앙 페드루 아님


def test_run_tags_untagged_articles_once(tmp_path, monkeypatch) -> None:
    db = tmp_path / "news.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE articles (link TEXT, team TEXT, headline TEXT, descr TEXT)")
        c.executemany("INSERT INTO articles VALUES (?,?,?,?)", [
            ("l1", "Arsenal", "Bukayo Saka injury update", ""), ("l1", "Chelsea", "Bukayo Saka injury update", ""),
            ("l2", "Chelsea", "Chelsea hand Pedro Neto new deal", "")])
    monkeypatch.setattr(nt, "load_players", lambda: PLAYERS)
    monkeypatch.setattr(nt, "load_managers", lambda: MANAGERS)
    assert nt.run(db=db) == (2, 2)                     # 같은 기사(링크)는 한 번만
    assert nt.run(db=db) == (0, 0)                     # 이미 태깅한 기사는 건너뜀
    with sqlite3.connect(db) as c:
        assert sorted(c.execute("SELECT link, player FROM article_players").fetchall()) == [("l1", "Bukayo Saka"), ("l2", "Pedro Neto")]
