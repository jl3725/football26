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


INFOBOX = """{{Infobox football biography
| name = Vincent Kompany
| years1 = 2003–2006 | clubs1 = [[R.S.C. Anderlecht|Anderlecht]] | caps1 = 73
| years2 = 2006–2008 | clubs2 = [[Hamburger SV]]
| manageryears1 = 2020–2022 | managerclubs1 = [[R.S.C. Anderlecht|Anderlecht]]
| manageryears2 = 2022–2024 | managerclubs2 = [[Burnley F.C.|Burnley]]
| manageryears3 = 2024– | managerclubs3 = [[FC Bayern Munich|Bayern Munich]]
}}
Kompany is ..."""


def test_manager_infobox_career() -> None:
    import fetch_manager_careers as fm
    managed, played = fm.career(fm.infobox(INFOBOX))
    assert [(s["club"], s["start"], s["end"]) for s in managed] == [
        ("Anderlecht", 2020, 2022), ("Burnley", 2022, 2024), ("Bayern Munich", 2024, None)]
    assert [s["club"] for s in played] == ["Anderlecht", "Hamburger SV"]


def test_ties_dedupe_teammate_and_reunion() -> None:
    pairs, names = tn.lineup_pairs([__import__("pandas").DataFrame({
        "squad": ["Villa"] * 3 * 6 + ["Ars"] * 3 * 6,
        "event_id": [e for e in range(6) for _ in range(3)] + [e for e in range(10, 16) for _ in range(3)],
        "starter": [True] * 36,
        "player": ["Emi", "Rogers", "Watkins"] * 6 + ["Rice", "Saka", "Jackson"] * 6})])
    loc = {"Rogers": {"name": "Rogers", "club": "Chelsea"}, "Watkins": {"name": "Watkins", "club": "Spurs"},
           "Jackson": {"name": "Jackson", "club": "Villa"}, "Saka": {"name": "Saka", "club": "Ars"}, "Rice": {"name": "Rice", "club": "Ars"}}
    players = [{"name": "Emi", "prev_squad": "Villa"}, {"name": "Rogers", "prev_squad": "Villa"},
               {"name": "Rice", "prev_squad": "Ars"}, {"name": "Saka", "prev_squad": "Ars"}]
    ti = tn.ties("Chelsea", players, pairs, names, loc.get)
    assert [(r["ours"], r["mate"]) for r in ti["reunions"]] == [("Emi", "Rogers")]
    ti2 = tn.ties("Ars", players[2:], pairs, names, loc.get)
    villa = [c for c in ti2["clubs"] if c["club"] == "Villa"][0]
    assert len(villa["ties"]) == 1 and villa["ties"][0]["links"] == 2      # Jackson 한 명(우리 선수 2명과)


def test_national_web_groups_by_club() -> None:
    wc = [{"nation": "England", "player": p} for p in ("Saka", "Rice", "Kane", "Bellingham", "Nobody")]
    clubs = {"Saka": "Ars", "Rice": "Ars", "Kane": "Bayern", "Bellingham": "Real"}
    w = tn.national_web("Ars", {"England": ["Saka", "Rice"]}, wc,
                        lambda n: {"name": n, "club": clubs[n]} if n in clubs else None)["England"]
    assert w["n_ours"] == 2 and w["clubs"][0] == {"club": "Ars", "n": 2, "players": ["Saka", "Rice"]}
    assert w["clubs"][-1]["club"] == "OTHER"


def test_manager_graph_network_and_brought() -> None:
    careers = {"A": {"managed": [{"club": "X", "start": 2022, "end": 2026}, {"club": "Ars", "start": 2026, "end": None}],
                     "played": [{"club": "Y", "start": 2000, "end": 2005}]},
               "B": {"managed": [{"club": "Y", "start": 2020, "end": None}], "played": []}}
    mg = tn.manager_graph("Ars", {"name": "A"}, careers, {"A": {}, "B": {"team": "Y"}}, lambda c: c, lambda c: "",
                          [{"name": "P", "prev_squad": "X"}, {"name": "Q", "prev_squad": "Z"}], 2026)
    assert mg["network"][0]["manager"] == "B" and mg["network"][0]["shared"][0]["club"] == "Y"
    assert mg["brought"] == ["P"]


def test_prev_season_name_variant_same_club() -> None:
    import attach_prev_season as aps
    assert aps._variant("frank anguissa", "andre frank zambo anguissa")
    assert aps._variant("jair", "jair cunha")
    assert not aps._variant("marcos fernandez", "roberto fernandez")     # 성만 같은 다른 사람


def test_wiki_name_templates_keep_the_name() -> None:
    # 안쪽 틀({{ill|…}})에서 끊겨 이름이 '{{ill|Pascal Kuiper|nl' 로 남던 것(Eredivisie 61명)
    t = ("{{Fs player|no=1|nat=NED|pos=GK|name={{ill|Pascal Kuiper|nl}}|other=captain}}\n"
         "{{Fs player|no=3|nat=KOR|pos=DF|name={{sortname|Min-jae|Kim}}}}")
    names = [r["player"] for r in ws.parse_squad(t)]
    assert names == ["Pascal Kuiper", "Min-jae Kim"]
    assert ws.clean_name("{{ill|Nick Verschuren|de|Nick Verschuren (Fußballspieler)|es||fr") == "Nick Verschuren"
    assert ws.clean_name("Thijs Verbaan") == "Thijs Verbaan"


def test_insights_carry_tile_fields() -> None:
    lead = {"captains": [{"name": "Martin Ødegaard", "label": "C", "tenure": 5.2},
                         {"name": "Bukayo Saka", "label": "VC"}], "armband": "Martin Ødegaard"}
    chem = {"nodes": [{"name": "A B", "degree": 3}], "edges": [{"a": "A B", "b": "C D", "minutes": 400}], "hub_rank": {}}
    ins = tn.insights("Arsenal", lead, chem, [], {"acq": {}, "sources": []}, {"countries": []}, {"clubs": []}, [])
    cap = next(i for i in ins if i["title"] == "주장단")
    assert cap["big"] == "5" and cap["who"][0] == "Martin Ødegaard" and "Saka" in cap["line"]
    hub = next(i for i in ins if i["title"] == "연결 허브")
    assert hub["big"] == "1" and hub["who"] == ["A B"]


def test_wrapped_captain_markup_is_kept() -> None:
    # 2026-10-18 회귀: {{small|…}} 로 감싼 주장 표기를 통째로 지워 분데스리가 주장 18→10팀
    t = ("{{Fs player|no=4|nat=GER|pos=DF|name=[[Robin Koch]]|other={{small|[[Captain (association football)|captain]]}}}}\n"
         "{{Fs player|no=27|nat=GER|pos=MF|name=[[Mario Götze]]|other={{small|[[Captain (association football)#Vice-captain|vice-captain]]}}}}\n"
         "{{Fs player|no=9|nat=GER|pos=FW|name={{nowrap|[[Jonathan Burkardt]]}}|other={{abbr|C|Captain}}}}")
    rows = {r["player"]: r for r in ws.parse_squad(t)}
    assert rows["Robin Koch"]["role_rank"] == 1 and rows["Mario Götze"]["role_rank"] == 2
    assert "Jonathan Burkardt" in rows and rows["Jonathan Burkardt"]["role_rank"] == 1


def test_captain_ordinals_parsed_as_rank() -> None:
    """'5th captain' 을 주장(1순위)으로 읽던 버그 — 바르사 야말이 메인 주장으로 보였다(2026-10-20)."""
    import fetch_wiki_squads as w

    link = "[[Captain (association football)#Vice-captain|{}]]"
    assert w.role_of(link.format("5th captain")) == ("5th captain", 5)
    assert w.role_of(link.format("vice-captain")) == ("vice-captain", 2)
    assert w.role_of("[[Captain (association football)|captain]]") == ("captain", 1)
    assert w.role_of("{{small|third captain}}") == ("3rd captain", 3)


def test_influence_weighs_quality_and_play_over_tenure() -> None:
    """근속 6년·풀타임 센터백보다 실력·볼 관여가 큰 미드필더(주장 포함)가 위 — 아스날 사례(사용자 지적)."""
    import datetime as dt

    import team_network as tn

    base = {"wc": True, "injured": False}
    players = [
        {**base, "name": "CB", "ovr": 89, "form": 90, "minutes": 630, "age": 28, "joined": "2020-09-01", "ft90": 8.7, "kp90": 0.29},
        {**base, "name": "Captain10", "ovr": 86, "form": 93, "minutes": 561, "age": 27, "joined": "2021-08-20",
         "ft90": 23.9, "kp90": 2.09, "captain_rank": 1},
        {**base, "name": "DM", "ovr": 90, "form": 97, "minutes": 594, "age": 27, "joined": "2023-07-15", "ft90": 21.8, "kp90": 1.67},
        {**base, "name": "Sub", "ovr": 80, "form": 70, "minutes": 120, "age": 23, "joined": "2025-07-01", "ft90": 30.0, "kp90": 3.0},
    ]
    chem = {"strength": {"CB": 1.0, "Captain10": 0.72, "DM": 0.84}, "minutes": {}}
    out = tn.leadership(players, chem, dt.date(2026, 10, 20))
    order = [p["name"] for p in out["core"]]
    assert order.index("Captain10") < order.index("CB") and order.index("DM") < order.index("CB")
    sub = next(p for p in out["core"] if p["name"] == "Sub")
    assert sub["components"]["play"] == 0.0               # 270분 미만은 볼 관여 판단 안 함(짧은 출전 per90 부풀림)
    assert out["captains"][0]["name"] == "Captain10"
