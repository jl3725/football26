"""이적설 지도 — TM·뉴스 원천 합치기, 열기(최근성·매체 신뢰), 표적·경쟁 구단·우리 선수 이적설(src/rumor_map.py)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import rumor_map as rm  # noqa: E402

TODAY = dt.date(2026, 10, 21)
CANON = {"FC Barcelona": "Barcelona", "Arsenal FC": "Arsenal", "Paris Saint-Germain": "PSG"}.get


def test_collect_merges_sources_and_heat() -> None:
    tm = [{"player": "Xavi Espart", "target_club": "Arsenal", "current_club": "FC Barcelona", "probability": None, "date": "19/10/2026"},
          {"player": "Xavi Espart", "target_club": "Tottenham", "current_club": "FC Barcelona", "probability": 40, "date": "01/08/2026"},
          {"player": "Old Guy", "target_club": "Arsenal", "current_club": "X", "date": "01/01/2026"}]   # 120일 넘음 → 버림
    claims = [{"player": "Xavi Espart", "origin": "Barcelona", "dest": "Arsenal FC", "stage": "talks", "source": "Marca",
               "date": "2026-10-20", "link": "u1", "headline": "Arsenal in talks for Espart"},
              {"player": "Xavi Espart", "origin": "Barcelona", "dest": "Arsenal", "stage": "interest", "source": "Tabloid",
               "date": "2026-10-20", "link": "u2", "headline": "Arsenal eye Espart"}]
    rel = rm.outlet_factor({"Marca": 0.9, "Tabloid": 0.3})          # 평균 0.6 → Marca ×1.5, Tabloid ×0.6(하한)
    links = rm.collect(tm, claims, CANON, rel, TODAY)
    a = links[("xavi espart", "Arsenal")]
    assert a["from"] == "Barcelona" and a["stage"] == "talks" and a["tm"]["date"] == "2026-10-19"
    want = 1.0 * rm.decay(2, rm.HALF_TM) + 1.6 * 1.5 * rm.decay(1, rm.HALF_NEWS) + 1.0 * 0.6 * rm.decay(1, rm.HALF_NEWS)
    assert abs(a["raw"] - want) < 1e-9 and a["heat"] == rm.heat(want)
    assert a["outlets"] == ["Marca", "Tabloid"] and a["news"][0]["trust"] in (1.5, 0.6)
    t = links[("xavi espart", "Tottenham")]
    assert t["heat"] < a["heat"]                                        # 두 달 반 된 TM 루머는 많이 식었다
    assert ("old guy", "Arsenal") not in links


def test_denied_and_same_club() -> None:
    claims = [{"player": "A B", "origin": "PSG", "dest": "Paris Saint-Germain", "stage": "talks", "source": "x", "date": "2026-10-20"},
              {"player": "C D", "origin": "PSG", "dest": "Arsenal", "stage": "denied", "source": "x", "date": "2026-10-20"}]
    links = rm.collect([], claims, CANON, rm.outlet_factor({}), TODAY)
    assert ("a b", "PSG") not in links                                  # 원래 클럽 = 행선지는 연결 아님
    d = links[("c d", "Arsenal")]
    assert d["stage"] == "denied" and d["heat"] == 0                    # 부인만 있으면 열기 0


def test_team_map_in_out_competition() -> None:
    tm = [{"player": "Target One", "target_club": "Arsenal", "current_club": "Roma", "date": "20/10/2026"},
          {"player": "Target One", "target_club": "Chelsea", "current_club": "Roma", "date": "20/10/2026"},
          {"player": "Target Two", "target_club": "Arsenal", "current_club": "Lille", "date": "20/10/2026"},
          {"player": "Target Two", "target_club": "Chelsea", "current_club": "Lille", "date": "10/10/2026"},
          {"player": "Our Guy", "target_club": "Real Madrid", "current_club": "Arsenal FC", "probability": 30, "date": "20/10/2026"}]
    links = rm.collect(tm, [], CANON, rm.outlet_factor({}), TODAY)
    m = rm.team_map("Arsenal", links, {"our guy"})
    assert [x["player"] for x in m["in"]] == ["Target One", "Target Two"]
    assert m["in"][0]["rivals"][0]["club"] == "Chelsea"
    assert m["out"][0]["player"] == "Our Guy" and m["out"][0]["suitors"][0]["to"] == "Real Madrid"
    assert m["competition"][0]["club"] == "Chelsea" and len(m["competition"][0]["players"]) == 2

    ins = rm.insight("Arsenal", m)
    assert ins["lens"] == "rumors" and ins["who"] == ["Target One"] and "경쟁 1개 클럽" in ins["text"]
