from __future__ import annotations

import pandas as pd

import player_names as pn
import player_registry as pr


def test_score_rules() -> None:
    assert pr.score("Alisson Becker", "Alisson") == 60                 # 한 단어 이름
    assert pr.score("Kim Min-jae", "Min-jae Kim") == 95                 # 어순
    assert pr.score("Jay Da Silva", "Jay Dasilva") == 95                # 붙여 쓰기
    assert pr.score("Frank Anguissa", "Andre-Frank Zambo Anguissa") == 85
    assert pr.score("Josh King", "Joshua King") == 80 and pr.score("Charly Alcaraz", "Carlos Alcaraz") == 80
    assert pr.score("Mykhaylo Mudryk", "Mykhailo Mudryk") == 80         # 음역 차이
    assert pr.score("G. Magalhães", "Gabriel Magalhães") == 70
    assert pr.score("Raúl García", "Rubén García") == 0                 # 성만 같은 다른 사람


def test_best_match_refuses_ties() -> None:
    cands = {"Rubén García": "e1", "Raúl": "e2"}
    assert pr.best_match("Raúl García", cands) == ("e2", 60)
    ent, sc = pr.best_match("J. Silva", {"Jota Silva": "a", "João Silva": "b"})
    assert ent is None                                                  # 동점이면 붙이지 않음


def test_cleanse_uses_squad_scope(monkeypatch) -> None:
    monkeypatch.setattr(pn, "alias_map", lambda league, season=None: {("Liverpool", "alisson becker"): "Alisson"})
    df = pd.DataFrame({"squad": ["Liverpool", "Chelsea"], "player": ["Alisson Becker", "Alisson Becker"]})
    out = pn.cleanse(df, ["player"], "EPL")
    assert list(out["player"]) == ["Alisson", "Alisson Becker"] and list(out["player_src"]) == ["Alisson Becker"] * 2


def test_subs_get_squad_from_lineups() -> None:
    subs = pd.DataFrame({"event_id": [1, 1], "home_away": ["home", "away"], "player_in": ["A", "B"]})
    lu = pd.DataFrame({"event_id": [1, 1], "home_away": ["home", "away"], "squad": ["X", "Y"]})
    assert list(pn.with_squad(subs, lu)["squad"]) == ["X", "Y"]


def test_middle_name_variants_merge_into_one_identity() -> None:
    import player_registry as pr
    ents = {"pf:Inter:francesco esposito": {"squad": "Inter", "canonical": "Francesco Esposito", "tm_id": "", "src": "players_full"},
            "tm930781": {"squad": "Inter", "canonical": "Pio Esposito", "tm_id": "930781", "src": "transfermarkt_contracts"},
            "esp:Inter:francesco pio esposito": {"squad": "Inter", "canonical": "Francesco Pio Esposito", "tm_id": "", "src": "espn_subs"},
            "tm1": {"squad": "Sassuolo", "canonical": "Sebastiano Esposito", "tm_id": "1", "src": "players_full"}}
    root = pr.merge_middle_names(ents)
    assert root == {"tm930781": "pf:Inter:francesco esposito", "esp:Inter:francesco pio esposito": "pf:Inter:francesco esposito"}
