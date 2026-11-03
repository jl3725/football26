"""리그 출전인데 선수 표에 없는 선수 · 원천마다 이름이 다른 선수 — src/live_roster.py.

2026-11-03 사용자: '메슬리에 EFL컵 뛰었는데 출전 없음'. FBref 가 10월 초에서 멈춰 그 뒤 리그 데뷔 선수(펜더스·고레츠카)가
표에 없었고, 'Bachir' ↔ 'Mohamed Belloumi'·'Kostas' ↔ 'Konstantinos Tsimikas' 는 FotMob 분이 안 붙고 TM 명단 줄로 한 번 더 나왔다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import live_roster as lr  # noqa: E402


def test_match_in_squad_surname_only_when_unique() -> None:
    names = ["Bachir Belloumi", "Kostas Tsimikas", "Iñaki Williams", "Ruben Williams"]
    assert lr.match_in_squad("Mohamed Belloumi", names) == "Bachir Belloumi"
    assert lr.match_in_squad("Konstantinos Tsimikas", names) == "Kostas Tsimikas"
    assert lr.match_in_squad("Nico Williams", names) is None              # 같은 성이 둘(형제) — 이름만으로는 모름
    assert lr.match_in_squad("Bachir Belloumi", names) == "Bachir Belloumi"
    # 상대 쪽(FotMob 팀 명단)에도 같은 성이 둘이면 짝짓지 않는다
    assert lr.match_in_squad("Mohamed Belloumi", names, ["Mohamed Belloumi", "Ali Belloumi"]) is None


def _mr(*rows):
    cols = ["match_id", "date", "comp_code", "squad", "fotmob_id", "player", "minutes", "goals", "assists", "saves", "xgot_faced"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def _frame():
    return pd.DataFrame([
        {"player": "Bachir Belloumi", "squad": "Hull City", "minutes": 421.0, "pos": "FW", "team_attack_score": 0.4,
         "pass_pct": 80.0},
        {"player": "Declan Rice", "squad": "Arsenal", "minutes": 501.0, "pos": "MF", "team_attack_score": 0.9,
         "pass_pct": 88.0},
    ])


def test_add_debuts_adds_registered_league_debut_and_hints_alias() -> None:
    mr = _mr((1, "2026-10-17", "eng.1", "Arsenal", 777, "Mike Penders", 90, 0, 0, 3, 1.2),
             (2, "2026-10-24", "eng.1", "Hull City", 555, "Mohamed Belloumi", 90, 1, 0, 0, 0),
             (3, "2026-10-27", "eng.league_cup", "Arsenal", 888, "Illan Meslier", 90, 0, 0, 4, 1.0),
             (4, "2026-08-24", "eng.1", "Arsenal", 999, "Robert Sánchez", 90, 0, 0, 2, 0.8))
    squads = pd.DataFrame([{"squad": "Arsenal", "player": "Mike Penders", "fotmob_id": 777, "group": "keepers", "age": 21}])
    out = lr.add_debuts(_frame(), mr, "EPL", squads=squads, contracts=None)
    new = out[out["_live_debut"] == True]  # noqa: E712
    assert new["player"].tolist() == ["Mike Penders"]                     # 리그컵만 뛴 메슬리에 · 8월에 떠난 산체스는 아님
    p = new.iloc[0]
    assert p["pos"] == "GK" and p["minutes"] == 0 and p["pass_pct"] == 0.0   # 분·세부 지표는 뒤 단계가 FotMob 으로 채움
    assert p["team_attack_score"] == 0.9                                  # 팀 단위 값은 같은 팀 줄에서
    assert p["_fm_hint"] == "777"
    hint = out.loc[out["player"] == "Bachir Belloumi", "_fm_hint"].iloc[0]
    assert hint == "555"                                                  # 이름 다른 같은 사람 — FotMob 번호로 이어 줌


def test_rating_blend_uses_hint_when_names_differ() -> None:
    import rating_blend as rb
    frame = pd.DataFrame([{"player": "Bachir Belloumi", "squad": "Hull City", "minutes": 421.0, "_fm_hint": "555"}])
    cur = pd.DataFrame([{"squad": "Hull City", "player": "Mohamed Belloumi", "fotmob_id": 555, "rating": 7.1, "minutes": 690}])
    out = rb.attach(frame, "EPL", None, lambda lg, s: cur if lg == "EPL" else None)
    assert int(out.iloc[0]["fm_id"]) == 555 and float(out.iloc[0]["fm_rating"]) == 7.1
