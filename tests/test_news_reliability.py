"""뉴스 2단계 — 이적 루머 적중 판정 규칙(목표 시장·제목의 행선지 클럽·사후 보도 제외·점수 보정)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import news_reliability as nr  # noqa: E402


def test_target_window() -> None:
    assert nr.target_window(dt.date(2026, 7, 10))[:2] == (2026, "summer")
    assert nr.target_window(dt.date(2026, 10, 20))[:2] == (2026, "winter")     # 9/2 뒤 = 다음 겨울(시즌 2026)
    assert nr.target_window(dt.date(2027, 1, 20))[:2] == (2026, "winter")
    assert nr.target_window(dt.date(2027, 3, 1))[:2] == (2027, "summer")


def test_club_index_destination_rules() -> None:
    idx = nr.ClubIndex({"Fulham": {"Fulham"}, "Real Madrid": {"Real Madrid", "Real Madrid CF"}, "Como": {"Como", "Como 1907"},
                        "Santos": {"Santos"}, "Defensa y Justicia": {"Defensa y Justicia"},
                        "Manchester City": {"Manchester City"}, "Manchester Utd": {"Manchester United"}},
                       ours={"Fulham", "Real Madrid", "Como", "Manchester City", "Manchester Utd"})
    # 출신 앞말 뒤 클럽은 'from:' — 행선지는 앞의 주어 클럽
    assert idx.find("Fulham agree to sign Manuel Angel from Real Madrid") == ["Fulham", "from:Real Madrid"]
    # 선수 이름 속 클럽 낱말(Andrey Santos)은 지운 뒤 찾는다
    assert idx.find("Manchester United target Andrey Santos", ["Andrey Santos"]) == ["Manchester Utd"]
    # 한 낱말 이름은 대문자일 때만(스페인어 como), 우리 리그 밖 클럽은 이름 전체만(defensa)
    assert idx.find("La primera vez de Sarr como realista") == []
    assert idx.find("El Elche refuerza su defensa con Revivo") == []
    assert idx.find("Como reach deal to keep Nico Paz") == ["Como"]
    # 여러 클럽이 나눠 가진 말('manchester')은 단독으로 안 쓴다
    assert idx.find("Manchester derby preview") == []


def test_reliability_scores_shrink_small_samples() -> None:
    cl = pd.DataFrame([
        *[{"link": f"a{i}", "player": f"p{i}", "dest": "X", "source": "Big", "journalists": "", "stage": "agreed",
           "status": "hit" if i < 16 else "miss"} for i in range(20)],
        *[{"link": f"b{i}", "player": f"q{i}", "dest": "Y", "source": "Tiny", "journalists": "Fabrizio Romano", "stage": "done",
           "status": "hit"} for i in range(2)],
        {"link": "c", "player": "r", "dest": "Z", "source": "Tiny", "journalists": "", "stage": "talks", "status": "pending"},
    ])
    r = nr.reliability(cl).set_index(["kind", "name"])
    assert r.loc[("outlet", "Big"), "rate"] == 0.8
    tiny = r.loc[("outlet", "Tiny")]
    assert tiny["rate"] == 1.0 and tiny["score"] < 1.0 and bool(tiny["few"]) and tiny["pending"] == 1   # 2건 100% 는 평균 쪽으로
    assert r.loc[("journalist", "Fabrizio Romano"), "n"] == 2
    assert r.loc[("all", "ALL"), "by_stage"] == "agreed:16/20 done:2/2"
