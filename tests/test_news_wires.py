"""넓힌 무료 원천(src/news_wires.py) — 팀 판정 규칙·피드 파싱·기자 계정 찾기, news.db 크기 안전장치, KG 루머 주장 그래프."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import news_store as ns  # noqa: E402
import news_wires as nw  # noqa: E402


def _idx(common: set[str] | None = None) -> nw.TeamIndex:
    """데이터 없이 — 별칭·선수·나라를 직접."""
    idx = object.__new__(nw.TeamIndex)
    idx.country = {"Arsenal": "England", "Liverpool": "England", "Brentford": "England", "Nice": "France",
                   "PSG": "France", "Standard Liège": "Belgium", "Real Sociedad": "Spain", "Chelsea": "England"}
    idx.terms = {"arsenal": "Arsenal", "liverpool": "Liverpool", "brentford": "Brentford", "nice": "Nice", "psg": "PSG",
                 "paris saint germain": "PSG", "standard": "Standard Liège", "standard liege": "Standard Liège",
                 "real sociedad": "Real Sociedad", "sociedad": "Real Sociedad", "chelsea": "Chelsea"}
    idx.players = {"bukayo saka": "Arsenal", "mohamed salah": "Liverpool"}
    idx.maxn = 3
    idx.common = set(common or ())
    return idx


def test_headline_clubs_win_over_summary() -> None:
    idx = _idx()
    # 제목에 클럽이 있으면 요약에 지나가듯 나온 클럽은 붙이지 않는다
    assert idx.match("Brentford press charges after pitch invader", "Liverpool were also involved", "England") == ["Brentford"]
    # 제목에 없으면 요약에서 — 선수 이름 전체·두 낱말 별칭만, 클럽 하나
    assert idx.match("Winger opens up on dark days", "Bukayo Saka said on Tuesday; Liverpool …", "England") == ["Arsenal"]
    assert idx.match("Manager reacts", "Liverpool lost again", "England") == []


def test_short_and_common_words_need_home_country() -> None:
    idx = _idx(common={"standard"})
    assert idx.match("What a Nice goal", "", "England") == []                  # 6자 미만 — 그 나라 매체만
    assert idx.match("Le gardien de Nice prolonge", "", "France") == ["Nice"]
    assert idx.match("nice weather in Lyon", "", "France") == []               # 소문자 = 일반 낱말
    assert idx.match("PSG beat Barcelona", "", "England") == ["PSG"]           # 대문자 약자는 어느 나라든
    assert idx.match("Club pays the Standard rate", "", "England") == []       # 소문자로도 쓰이는 낱말 — 그 나라 매체만
    assert idx.match("Un ancien du Standard signe", "", "Belgium") == ["Standard Liège"]
    assert idx.match("Standard procedure for the club", "", "Belgium") == []    # 일반 낱말이 문장 첫 낱말
    assert idx.match("Standard Liège sack coach", "", "England") == ["Standard Liège"]   # 두 낱말 별칭은 어디서나


def test_learn_common_and_cap() -> None:
    idx = _idx()
    idx.learn_common(["la sociedad española", "Arsenal win"])
    assert "sociedad" in idx.common and "arsenal" not in idx.common
    m = idx.match("Arsenal, Chelsea and Liverpool chase Bukayo Saka rival", "", "England")
    assert m == ["Arsenal", "Chelsea", "Liverpool"]                          # 최대 3개


RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>T</title>
<item><title>Arsenal &amp; Chelsea battle</title><link>https://x.test/a</link>
<description><![CDATA[<p>Long <b>summary</b> here</p>]]></description><pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate>
<dc:creator>Jane Writer</dc:creator><category>Transfers</category></item>
<item><title></title><link>https://x.test/b</link></item>
</channel></rss>"""


def test_parse_feed_fields() -> None:
    items = nw._parse_feed(RSS)
    assert len(items) == 1
    a = items[0]
    assert a["headline"] == "Arsenal & Chelsea battle" and a["desc"] == "Long summary here"
    assert a["published"] == "2026-10-20" and a["author"] == "Jane Writer" and a["_tags"] == "Transfers"


def test_refresh_insiders_name_then_follows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(nw, "INSIDERS", tmp_path / "ins.json")
    prof = {"real.bsky": {"handle": "real.bsky", "displayName": "Ann Reporter", "followersCount": 9000, "description": ""},
            "mir.bsky": {"handle": "mir.bsky", "displayName": "Ann Reporter MIRROR", "followersCount": 20000, "description": ""},
            "tiny.bsky": {"handle": "tiny.bsky", "displayName": "Ann Reporter", "followersCount": 50, "description": ""},
            "foot.bsky": {"handle": "foot.bsky", "displayName": "Bob Writer ⚽️", "followersCount": 5000,
                          "description": "Chief football writer at The Paper"},
            "pol.bsky": {"handle": "pol.bsky", "displayName": "Cat Politics", "followersCount": 90000,
                         "description": "Senior political reporter"}}

    def fake(method, **p):
        if method == "app.bsky.actor.searchActors":
            return {"actors": [{"handle": h, "displayName": prof[h]["displayName"]} for h in ("real.bsky", "mir.bsky", "tiny.bsky")]}
        if method == "app.bsky.graph.getFollows":
            return {"follows": [{"handle": "foot.bsky"}, {"handle": "pol.bsky"}]}
        return None

    monkeypatch.setattr(nw, "_bsky", fake)
    monkeypatch.setattr(nw, "_profiles", lambda hs: [prof[h] for h in hs if h in prof])
    monkeypatch.setattr(nw.time, "sleep", lambda s: None)
    reg = nw.refresh_insiders(["Ann Reporter"])
    acc = reg["accounts"]
    assert set(acc) == {"real.bsky", "foot.bsky"}                     # 공식 > 미러(팔로워 많아도), 정치 기자 제외
    assert acc["real.bsky"]["via"] == "name" and acc["foot.bsky"]["name"] == "Bob Writer"
    assert json.loads((tmp_path / "ins.json").read_text(encoding="utf-8"))["names"]["Ann Reporter"]["handle"] == "real.bsky"


def _news_db(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE articles (link TEXT, team TEXT, first_seen TEXT, via TEXT, headline TEXT)")
        c.execute("CREATE TABLE article_meta (link TEXT, kind TEXT)")
        c.execute("CREATE TABLE article_players (link TEXT, player TEXT)")
        for link, via, first, kind in rows:
            c.execute("INSERT INTO articles VALUES (?,?,?,?,?)", (link, "Arsenal", first, via, "h " * 50))
            c.execute("INSERT INTO article_meta VALUES (?,?)", (link, kind))
            c.execute("INSERT INTO article_players VALUES (?,?)", (link, "X"))


def test_trim_keeps_transfers_and_core_sources(tmp_path) -> None:
    db = tmp_path / "news.db"
    old = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    new = dt.date.today().isoformat()
    _news_db(db, [("w-old", "wire", old, "match"), ("w-old-tr", "wire", old, "transfer"), ("w-new", "wire", new, "match"),
                  ("espn-old", "", old, "match"), ("g-old", "gnews", old, "injury")])
    assert ns.trim(db, days=14) == 2
    with sqlite3.connect(db) as c:
        left = {r[0] for r in c.execute("SELECT link FROM articles")}
        meta = {r[0] for r in c.execute("SELECT link FROM article_meta")}
    assert left == {"w-old-tr", "w-new", "espn-old"} and meta == left


def test_push_size_guard(tmp_path, monkeypatch) -> None:
    db = tmp_path / "news.db"
    old = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    _news_db(db, [(f"l{i}", "wire", old, "match") for i in range(300)] + [("keep", "", old, "match")])
    monkeypatch.setattr(ns, "DB", db)
    monkeypatch.setattr(ns, "REF", tmp_path / "ref.json")
    monkeypatch.setattr(ns, "_git", lambda *a, **k: "sha")
    monkeypatch.setattr(ns, "MIN_RATIO", 0.0)
    monkeypatch.setattr(ns, "HARD_BYTES", 10)                       # 줄여도 한도 넘음 → 올리지 않음
    monkeypatch.setattr(ns, "SOFT_BYTES", 10)
    with pytest.raises(SystemExit):
        ns.push(min_ratio=0.0)
    assert ns.articles(db) == 1                                       # 넓힌 경로 오래된 비이적 기사는 정리됨
    monkeypatch.setattr(ns, "HARD_BYTES", 10**9)
    monkeypatch.setattr(ns, "SOFT_BYTES", 10**9)
    ref = ns.push(min_ratio=0.0)
    assert ref["articles"] == 1 and not (tmp_path / "news.db.gz").exists()


def test_claim_graph_rows() -> None:
    import build_kg as kg  # noqa: PLC0415
    today = dt.date(2026, 10, 21)
    claims = [
        {"link": "a", "date": "2026-10-01", "source": "Marca", "journalists": "Ann Reporter", "stage": "interest",
         "player": "Mateo Chávez", "origin": "AZ", "dest": "Cambuur FC", "window": "2026 winter", "status": "pending"},
        {"link": "b", "date": "2026-10-05", "source": "Marca", "journalists": "", "stage": "talks",
         "player": "Mateo Chavez", "origin": "AZ", "dest": "Cambuur", "window": "2026 winter", "status": "pending"},
        {"link": "c", "date": "2026-10-06", "source": "AS", "journalists": "Ann Reporter|Bob Writer", "stage": "denied",
         "player": "Mateo Chávez", "origin": "AZ", "dest": "Cambuur", "window": "2026 winter", "status": "pending"},
        {"link": "d", "date": "2024-01-01", "source": "AS", "journalists": "", "stage": "done",       # 보관 기간 밖
         "player": "Old Guy", "origin": "", "dest": "Ajax", "window": "2023 winter", "status": "hit"},
    ]
    canon = {"Cambuur FC": "Cambuur", "AZ": "AZ Alkmaar"}.get
    g = kg.claim_graph(claims, canon, lambda k, frm: "tm:7" if frm == "AZ Alkmaar" else None,
                       [{"kind": "outlet", "name": "Marca", "n": 43, "hits": 38, "rate": 0.884, "score": 0.875, "few": False}],
                       today=today)
    assert len(g["claims"]) == 1
    c = g["claims"][0]
    assert c["id"] == "mateo chavez|Cambuur|2026 winter" and c["pid"] == "tm:7" and c["origin"] == "AZ Alkmaar"
    assert c["stage"] == "talks" and c["n"] == 3 and (c["first"], c["last"]) == ("2026-10-01", "2026-10-06")
    rep = {(r["kind"], r["name"]): r for r in g["reports"]}
    assert rep[("Outlet", "Marca")]["n"] == 2 and rep[("Outlet", "Marca")]["stage"] == "talks"
    assert rep[("Journalist", "Ann Reporter")]["n"] == 2 and rep[("Journalist", "Bob Writer")]["stage"] == "denied"
    assert {(w["j"], w["o"]): w["n"] for w in g["writes"]} == {("Ann Reporter", "Marca"): 1, ("Ann Reporter", "AS"): 1,
                                                              ("Bob Writer", "AS"): 1}
    marca = next(x for x in g["nodes"] if x["name"] == "Marca")
    assert marca["rate"] == pytest.approx(0.884) and marca["few"] is False


def test_bsky_author_becomes_journalist() -> None:
    import news_classify as nc  # noqa: PLC0415
    row = {"link": "l", "headline": "Here we go! Bukayo Saka to Real Madrid", "descr": "", "source": "Bluesky · Ann Reporter",
           "teams": "Arsenal", "via": "bsky", "author": "Ann Reporter"}
    assert nc.rule_meta(row, {})["journalists"].split("|")[0] == "Ann Reporter"
    assert nc.rule_meta({**row, "via": "wire"}, {})["journalists"] == ""     # 매체 바이라인은 '출처 기자'가 아니다
