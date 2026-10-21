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


# ── 클럽 표기 맞추기(make_canon) — 다른 클럽·2군을 우리 클럽으로 묶지 않기 ─────────────────────────────────
CLUB_LEAGUE = {"Barcelona": "LaLiga", "Espanyol": "LaLiga", "Sevilla": "LaLiga", "Real Madrid": "LaLiga", "Real Betis": "LaLiga",
               "Racing Santander": "LaLiga", "Porto": "LigaPortugal", "Nacional": "LigaPortugal", "Arsenal": "EPL",
               "Liverpool": "EPL", "Manchester City": "EPL", "Tottenham Hotspur": "EPL", "Ipswich Town": "EPL",
               "Inter": "SerieA", "Lens": "Ligue1"}


def test_make_canon_does_not_merge_different_clubs() -> None:
    canon = rm.make_canon(CLUB_LEAGUE, {}, [])
    for raw in ("RCD Espanyol Barcelona", "Grêmio Foot-Ball Porto Alegrense", "Atlético Nacional", "Club Nacional Asunción",
                "Inter Miami", "Barcelona SC", "Liverpool Montevideo", "Racing Club"):
        assert canon(raw) is None, raw                                  # 8개 리그 밖 → 호출부가 원래 이름 유지
    assert canon("Barcelona") == "Barcelona"                            # 우리 표기 그대로
    # 같은 표기를 쓰는 우리 선수가 있으면 그 선수의 클럽으로 — Espanyol 선수 → Espanyol(Barcelona 아님)
    canon = rm.make_canon(CLUB_LEAGUE, {"roberto fernandez": {"Espanyol"}},
                          [{"player": "Roberto Fernández", "current_club": "RCD Espanyol Barcelona"}])
    assert canon("RCD Espanyol Barcelona") == "Espanyol"


def test_make_canon_never_maps_reserve_to_first_team() -> None:
    pc = {"youth guy": {"Manchester City"}, "espoir guy": {"Lens"}, "b team guy": {"Sevilla"}}
    tm = [{"player": "Youth Guy", "current_club": "Manchester City U18"}, {"player": "Espoir Guy", "current_club": "RC Lens Espoir"},
          {"player": "B Team Guy", "current_club": "Sevilla Atlético"}]
    canon = rm.make_canon(CLUB_LEAGUE, pc, tm)                          # 학습 행이 있어도 2군 표기는 1군으로 안 감
    for raw, lg in (("Manchester City U18", "EPL"), ("RC Lens Espoir", "Ligue1"), ("Sevilla Atlético", "LaLiga"),
                    ("Jong Ajax", None), ("Real Madrid Castilla", "LaLiga"), ("Inter Primavera", "SerieA")):
        assert canon(raw) is None and canon(raw, lg) is None, raw
    assert rm.reserve_marks("Willem II Tilburg") == frozenset() and rm.reserve_marks("Willem II") == {"ii"}
    assert rm.reserve_marks("Atlético Nacional") == frozenset() and rm.reserve_marks("Sevilla Atlético") == {"atletico"}
    # 자기 2군·유스 → 1군은 내부 승격(연결 아님), 다른 클럽 유스 → 표적(현 소속은 원래 이름)
    tm = [{"player": "Kid One", "target_club": "Manchester City", "current_club": "Manchester City U18", "league": "EPL",
           "date": "20/10/2026"},
          {"player": "Kid Two", "target_club": "Lens", "current_club": "RC Lens Espoir", "league": "Ligue1", "date": "20/10/2026"},
          {"player": "Kid Three", "target_club": "Arsenal", "current_club": "Borussia Dortmund Youth", "league": "EPL",
           "date": "20/10/2026"}]
    links = rm.collect(tm, [], canon, rm.outlet_factor({}), TODAY)
    assert set(links) == {("kid three", "Arsenal")} and links[("kid three", "Arsenal")]["from"] == "Borussia Dortmund Youth"


def test_make_canon_learned_mapping_and_ambiguity() -> None:
    pc = {"pedri": {"Barcelona"}, "kai": {"Arsenal"}, "real one": {"Real Madrid"}, "real two": {"Real Betis"}}
    tm = [{"player": "Pedri", "current_club": "FC Barcelona"}, {"player": "Kai", "current_club": "Arsenal FC"},
          {"player": "Real One", "current_club": "Real"}, {"player": "Real Two", "current_club": "Real"},   # 두 클럽 → 애매
          {"player": "Nobody", "current_club": "Barcelona SC"}]                                            # 우리 선수 아님
    canon = rm.make_canon(CLUB_LEAGUE, pc, tm)
    assert canon("FC Barcelona") == "Barcelona" and canon("Arsenal FC") == "Arsenal"
    assert canon("Real") is None and canon("Barcelona SC") is None


def test_make_canon_league_hint() -> None:
    canon = rm.make_canon(CLUB_LEAGUE, {}, [])
    assert canon("Arsenal FC") is None                                  # 리그를 모르면 비슷한 이름으로 고르지 않음
    assert canon("Arsenal FC", "EPL") == "Arsenal"                      # TM target_club — 리그별 파일이라 그 리그 안에서만
    assert canon("Tottenham", "EPL") == "Tottenham Hotspur"             # squads.canonical_squad 별칭
    assert canon("Inter Miami", "EPL") is None                          # 다른 리그 클럽(Inter)으로 새지 않음
    assert canon("Ipswich") == "Ipswich Town"                           # 리그 모름 — 사람이 확인한 별칭표에서 한 클럽뿐일 때
    tm = [{"player": "Some One", "target_club": "Arsenal FC", "current_club": "RCD Espanyol Barcelona", "league": "EPL",
           "date": "20/10/2026"}]
    links = rm.collect(tm, [], canon, rm.outlet_factor({}), TODAY)
    lk = links[("some one", "Arsenal")]
    assert lk["from"] == "RCD Espanyol Barcelona"                       # 8개 리그 밖 표기는 원래 이름
