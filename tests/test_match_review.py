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



def _fotmob(events, stats=None, shots=None, finished=True):
    """FotMob matchDetails 최소 꼴 — events: (분, 추가, 'Goal'|'Card', 이름, home?, newScore|card, 설명·도움)."""
    ev = []
    for t, ov, typ, name, is_home, extra, more in events:
        e = {"type": typ, "time": t, "overloadTime": ov, "nameStr": name, "isHome": is_home}
        if typ == "Goal":
            e.update({"newScore": extra, **(more or {})})
        else:
            e["card"] = extra
        ev.append(e)
    groups = [{"stats": [{"key": k, "stats": v} for k, v in (stats or {}).items()]}]
    return {"header": {"status": {"finished": finished, "started": True, "reason": {"short": "FT"}, "utcTime": "2026-11-01T13:00:00Z"},
                       "teams": [{"name": "Young Boys", "id": 1, "score": 3}, {"name": "FC Zürich", "id": 2, "score": 5}]},
            "content": {"matchFacts": {"events": {"events": ev}, "infoBox": {"Stadium": {"name": "Wankdorf"}, "Attendance": 29746}},
                        "stats": {"Periods": {"All": {"stats": groups}}}, "shotmap": {"shots": shots or []}}}


def test_parse_fotmob_same_shape_as_espn() -> None:
    """ESPN 이 없는 리그(스위스)는 FotMob 경기 상세로 같은 꼴 — 2026-11-02 AI 경기 리포트 6경기가 매번 '리뷰 없음'."""
    d = _fotmob([(12, None, "Goal", "Kény", False, [0, 1], {"goalDescriptionKey": "penalty", "suffix": "Pen"}),
                 (22, None, "Goal", "Essende", True, [1, 1], {"assistStr": "assist by Blum"}),
                 (35, None, "Card", "Zesiger", True, "Yellow", None),
                 (60, None, "Goal", "Hack", True, [1, 2], {"ownGoal": True}),          # 자책골 — 점수가 바뀐 쪽(원정) 득점
                 (90, 2, "Goal", "Umeh", False, [1, 3], {"assistStr": "assist by Hodza"}),
                 (70, None, "Card", "Blum", True, "Red", None)],
                stats={"BallPossesion": [50, 50], "total_shots": [16, 16], "accurate_passes": ["298 (79%)", "307 (78%)"]},
                shots=[{"situation": "Penalty", "eventType": "AttemptSaved", "min": 50, "teamId": 1, "playerName": "Sanches"}])
    p = mrv.parse_fotmob(d)
    assert p["state"] == "post" and p["detail"] == "FT" and p["venue"] == "Wankdorf"
    assert [(g["minute"], g["side"], g["kind"]) for g in p["goals"]] == [
        ("12'", "away", "pen"), ("22'", "home", ""), ("60'", "away", "og"), ("90'+2'", "away", "")]
    assert p["goals"][1]["assist"] == "Blum" and p["goals"][0]["assist"] == ""
    assert [c["color"] for c in p["cards"]] == ["yellow", "red"]
    assert p["pens"] == [{"minute": "50'", "m": 50, "side": "home", "player": "Sanches", "result": "saved"}]
    rv = mrv.build(p, "Young Boys", "FC Zürich")
    assert {s["label"]: (s["h"], s["a"]) for s in rv["stats"]}["패스 성공률"] == (79, 78)


def test_comeback_after_scoring_first_is_not_conceded_first() -> None:
    # 취리히 5-3(2026-11-02): 선제골을 넣고 한때 2-3 으로 뒤졌다 뒤집음 — '선제골을 내주고도'가 아니다
    s = _summary([("12'", "away", "Kény", "", "Penalty - Scored"), ("22'", "home", "Essende", "", "Goal"),
                  ("25'", "away", "Umeh", "", "Goal"), ("29'", "home", "Essende", "", "Goal"),
                  ("40'", "home", "Sanches", "", "Goal"), ("60'", "away", "Comenencia", "", "Goal"),
                  ("82'", "away", "Hodza", "", "Goal"), ("90'+2'", "away", "Umeh", "", "Goal")])
    lines = mrv.build(mrv.parse(s), "Young Boys", "FC Zürich")["lines"]
    assert not any("선제골을 내주고도" in x for x in lines)
    assert any("한때 리드를 내줬지만 다시 뒤집었다" in x for x in lines)
