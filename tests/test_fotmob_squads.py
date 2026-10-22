"""FotMob 팀 명단(src/fotmob_squads.py) — 포지션 매핑·빈 나이 채우기·부상 표시, 뉴스 '부상 보도' 낱말 규칙."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import fotmob_squads as fsq  # noqa: E402


def test_tm_position_mapping() -> None:
    assert fsq.tm_position("keepers", "GK") == "Goalkeeper"
    assert fsq.tm_position("midfielders", "RM,RB,LM") == "Right Midfield"
    assert fsq.tm_position("defenders", "LWB,LB") == "Left-Back"
    assert fsq.tm_position("attackers", "") == "Centre-Forward"          # 세부 포지션 없으면 묶음으로


def test_fill_frame_age_and_position() -> None:
    frame = pd.DataFrame([
        {"squad": "Chelsea", "player": "Mahdi Jazuli", "age": None, "tm_position": None},          # 명단엔 없고 선수 데이터에만
        {"squad": "Chelsea", "player": "Mike Penders", "age": 0, "tm_position": None},
        {"squad": "Chelsea", "player": "Cole Palmer", "age": 24, "tm_position": "Attacking Midfield"},
    ])
    squads = pd.DataFrame([{"squad": "Chelsea", "player": "Mike Penders", "tm_position": "Goalkeeper", "age": 21,
                            "birth_date": "2005-07-31"}])
    info = pd.DataFrame([{"squad": "Chelsea", "player": "Mahdi Jazuli", "fotmob_id": "1720243", "birth_date": "2010-01-06",
                          "primary_team": "Chelsea U21", "fetched": "2026-10-22"}])
    out = fsq.fill_frame(frame, squads, info)
    t = dt.date.today()
    want = lambda y, m, d: t.year - y - ((t.month, t.day) < (m, d))   # noqa: E731
    assert out.loc[0, "age"] == want(2010, 1, 6) and out.loc[1, "age"] == want(2005, 7, 31)
    assert out.loc[1, "tm_position"] == "Goalkeeper" and out.loc[2, "age"] == 24          # 있는 값은 그대로


def test_injured_rows() -> None:
    sq = pd.DataFrame([{"squad": "Chelsea", "player": "Emiliano Martínez", "fotmob_id": "268375", "injured": True,
                        "expected_return": "Early November 2026", "fetched": "2026-10-22"},
                       {"squad": "Chelsea", "player": "Cole Palmer", "fotmob_id": "1", "injured": False,
                        "expected_return": "", "fetched": "2026-10-22"}])
    rows = fsq.injured_rows(sq)
    assert [r["player"] for r in rows] == ["Emiliano Martínez"] and rows[0]["kind"] == "injury"


def test_news_injury_words() -> None:
    import api.main as M  # noqa: PLC0415
    bad = ["Saka forced off with injury after just ten minutes", "Casper Nielsen onzeker na voetblessure",
           "Bologna confirm Piccoli out for at least three weeks", "Marc Aguado, varias semanas por una lesión de tobillo"]
    good = ["NAPOLI, DE BRUYNE TORNA PROTAGONISTA DA PLAY", "Robin Zentner trainiert wieder im Tor",
            "Huge Man City injury worry relieved as Erling Haaland returns"]
    assert all(M._INJ_BAD.search(h) for h in bad)
    assert all(M._INJ_GOOD.search(h) for h in good)
    assert not M._INJ_BAD.search("DE BRUYNE TORNA PROTAGONISTA")                          # 'torn' ≠ 'TORNA'
