from __future__ import annotations

import match_review as mrv


def _summary(goals, stats=None, state="post", hs=None, as_=None):
    """ESPN /summary 최소 형태 — goals: (분, 'home'|'away', 득점자, 도움, 종류)."""
    events = []
    for minute, side, scorer, assist, typ in goals:
        ps = [{"athlete": {"displayName": scorer}}] + ([{"athlete": {"displayName": assist}}] if assist else [])
        events.append({"type": {"text": typ}, "team": {"id": "1" if side == "home" else "2"},
                       "clock": {"displayValue": minute}, "participants": ps})
    h = sum(1 for g in goals if g[1] == "home") if hs is None else hs
    a = sum(1 for g in goals if g[1] == "away") if as_ is None else as_
    teams = []
    for tid, side in (("1", "home"), ("2", "away")):
        teams.append({"team": {"id": tid}, "statistics": [{"name": k, "displayValue": v[side]} for k, v in (stats or {}).items()]})
    return {"header": {"competitions": [{"status": {"type": {"state": state, "shortDetail": "FT"}},
                                         "competitors": [{"homeAway": "home", "team": {"id": "1"}, "score": str(h)},
                                                         {"homeAway": "away", "team": {"id": "2"}, "score": str(a)}]}]},
            "keyEvents": events, "boxscore": {"teams": teams}, "gameInfo": {"venue": {"fullName": "Stadio"}, "attendance": 50000}}


def test_late_comeback_headline_and_no_particles_after_names() -> None:
    s = _summary([("20'", "home", "De Roon", "", "Goal"), ("25'", "away", "Mbappé", "", "Goal"),
                  ("51'", "home", "Malen", "", "Goal"), ("57'", "home", "Malen", "", "Goal"),
                  ("83'", "away", "Espí", "", "Goal"), ("85'", "away", "Endrick", "", "Goal - Header"),
                  ("90'", "away", "Rüdiger", "Güler", "Goal")])
    rv = mrv.build(mrv.parse(s), "Roma", "Real Madrid", fans={"h": 0.15, "d": 0.12, "a": 0.73})
    assert rv["headline"] == "Real Madrid, 원정에서 4-3 극장 역전승"
    assert "Real Madrid, 2골 차로 끌려가다 뒤집었다." in rv["lines"]
    assert "결승골은 90' Rüdiger(도움 Güler)." in rv["lines"]
    assert any(line.startswith("2골 — Malen(Roma)") for line in rv["lines"])
    assert rv["predictions"][0]["hit"] is True
    # 외국 이름 바로 뒤 조사(가·는·이) 금지
    assert not any(n + suf in line for line in rv["lines"] for n in ("Malen", "Real Madrid", "Roma") for suf in ("가 ", "는 ", "이 "))


def test_loser_outshot_on_target_too_is_not_called_finishing_gap() -> None:
    stats = {"possessionPct": {"home": "53", "away": "47"}, "totalShots": {"home": "30", "away": "18"},
             "shotsOnTarget": {"home": "12", "away": "8"}}
    s = _summary([("30'", "away", "Tresoldi", "", "Penalty - Scored"), ("44'", "home", "Lautaro", "", "Goal"),
                  ("63'", "away", "Tresoldi", "", "Goal"), ("74'", "away", "Tresoldi", "", "Goal")], stats)
    rv = mrv.build(mrv.parse(s), "Inter", "Club Brugge")
    joined = " ".join(rv["lines"])
    assert "앞서고도 졌다" in joined and "밀렸다" not in joined
    assert any(line.startswith("해트트릭 — Tresoldi(Club Brugge)") for line in rv["lines"])
    assert rv["star"]["player"] == "Tresoldi" and rv["star"]["goals"] == 3


def test_rout_skips_decisive_goal_and_draw_comeback() -> None:
    rout = _summary([(f"{m}'", "home", f"P{i}", "", "Goal") for i, m in enumerate((12, 31, 39, 68))])
    rv = mrv.build(mrv.parse(rout), "Aston Villa", "Fenerbahce")
    assert rv["headline"] == "Aston Villa, 홈에서 4-0 대승"
    assert not any(line.startswith("결승골") for line in rv["lines"])

    draw = _summary([("2'", "home", "A", "", "Goal"), ("38'", "home", "B", "", "Goal"),
                     ("54'", "away", "Kane", "", "Penalty - Scored"), ("60'", "away", "Kane", "", "Goal")])
    rv = mrv.build(mrv.parse(draw), "Viking FK", "Bayern Munich")
    assert rv["headline"] == "Viking FK·Bayern Munich 2-2 무승부"
    assert "Bayern Munich, 2골 차를 따라잡아 승점 1을 챙겼다." in rv["lines"]
    assert rv["ht"] == {"home": 2, "away": 0}


def test_live_state_headline() -> None:
    s = _summary([("10'", "away", "Saka", "", "Goal")], state="in")
    rv = mrv.build(mrv.parse(s), "Chelsea", "Arsenal")
    assert rv["state"] == "in" and "리드 중" in rv["headline"]
    assert rv["predictions"] == []
