from __future__ import annotations

import datetime as dt

import fetch_wiki_squads as ws
import team_network as tn

WIKI = """
==Players==
===First-team squad===
{{Fs start}}
{{Fs player|no=1|nat=GER|pos=GK|name=[[Manuel Neuer]]|other=[[captain (association football)|captain]]}}
{{Fs player|no=6|nat=GER|pos=MF|name=[[Joshua Kimmich]]|other=[[Vice-captain (association football)|vice-captain]]}}
{{Fs player|no=9|nat=ENG|pos=FW|name=[[Harry Kane]]|other=[[Vice-captain (association football)|3rd captain]]}}
{{Fs player|no=17|nat=FRA|pos=FW|name=[[Michael Olise]]}}
{{Fs end}}
===Out on loan===
{{Fs player|no=—|nat=GER|pos=MF|name=[[Paul Wanner]]|other=at [[PSV Eindhoven|PSV]]}}
==Youth==
{{Fs player|no=40|nat=GER|pos=DF|name=[[Some Kid]]|other=captain}}
"""


def test_parse_wiki_squad_roles_and_sections() -> None:
    rows = {r["player"]: r for r in ws.parse_squad(WIKI)}
    assert rows["Manuel Neuer"]["role_rank"] == 1 and rows["Joshua Kimmich"]["role_rank"] == 2
    assert rows["Harry Kane"]["role_rank"] == 3 and rows["Michael Olise"]["role_rank"] is None
    assert rows["Paul Wanner"]["section"] == "loan" and "Some Kid" not in rows      # 유스 표는 제외
    assert rows["Manuel Neuer"]["no"] == "1" and rows["Harry Kane"]["nat"] == "ENG"


def test_name_index_matches_accents_and_initials() -> None:
    idx = tn.NameIndex(["Vinicius Júnior", "Gabriel Magalhães", "Rodri"])
    assert idx.find("Vinícius Júnior") == "Vinicius Júnior"
    assert idx.find("G. Magalhaes") == "Gabriel Magalhães"
    assert idx.find("Rodri") == "Rodri" and idx.find("Unknown Guy") is None


def test_armband_passes_to_vice_when_captain_out() -> None:
    today = dt.date(2026, 10, 15)
    ps = [{"name": "A", "captain_rank": 1, "minutes": 400, "age": 30, "joined": "2018-07-01", "wc": True, "injured": True},
          {"name": "B", "captain_rank": 2, "minutes": 800, "age": 27, "joined": "2021-07-01", "wc": True, "injured": False},
          {"name": "C", "captain_rank": None, "minutes": 810, "age": 24, "joined": "2025-07-01", "wc": False, "injured": False}]
    chem = {"strength": {"A": 0.4, "B": 1.0, "C": 0.9}, "minutes": {}}
    lead = tn.leadership(ps, chem, today)
    assert lead["armband"] == "B" and [c["name"] for c in lead["captains"]] == ["A", "B"]
    assert lead["core"][0]["name"] == "B"                    # 출전·연결·완장이 모두 높은 쪽


def test_chemistry_graph_minutes_together() -> None:
    games = {1: {"A": (0, 90), "B": (0, 60), "C": (60, 90)}, 2: {"A": (0, 90), "B": (0, 90)}}
    g = tn.chemistry_graph(games, ["A", "B", "C"], min_edge=10)
    e = {(x["a"], x["b"]): x["minutes"] for x in g["edges"]}
    assert e[("A", "B")] == 150 and e[("A", "C")] == 30 and ("B", "C") not in e
    assert g["hub_rank"]["A"] == 1


def test_links_dedupes_alumni_already_sold() -> None:
    tr = [{"player": "X", "club": "Porto", "direction": "out"}, {"player": "Y", "club": "FC Porto", "direction": "in"}]
    alumni = [{"player": "X", "club": "Porto"}, {"player": "Z", "club": "Porto"}]
    lk = tn.links("Arsenal", tr, alumni, [], lambda c: "Porto" if "porto" in c.lower() else c, lambda c: "", lambda c: None)
    c = lk["clubs"][0]
    assert c["club"] == "Porto" and len(c["in"]) == 1 and len(c["out"]) == 1
    assert [a["player"] for a in c["alumni"]] == ["Z"]
