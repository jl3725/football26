"""전체 홈 13개 리그(2026-10-23) — 등급 묶음·가중, 빅매치 라이벌전 가점, 등급 순 라운드로빈, 실력 순 + 리그당 상한, VALUE PICKS."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import league_level as ll  # noqa: E402
import match_center as mc  # noqa: E402


def test_hub_rank_and_weight() -> None:
    assert ll.hub_rank("EPL") == 0 and ll.hub_rank("LaLiga") == 0
    assert ll.hub_rank("SuperLig") == 1 and ll.hub_rank("Eredivisie") == 1
    assert ll.hub_rank("Championship") == 2 and ll.hub_rank("AustrianBundesliga") == 2   # 2부 · TIER 3
    assert ll.hub_weight("EPL") == 1.0 > ll.hub_weight("SuperLig") > ll.hub_weight("Championship")


def _match(code, lg, home, away, hr, ar, ho=80, ao=80):
    side = lambda t, r, o: {"team": t, "league": lg, "rank": r, "ovr": o}   # noqa: E731
    return {"comp_code": code, "home": side(home, hr, ho), "away": side(away, ar, ao)}


def test_big_score_tier_weight_and_rivalry() -> None:
    riv = {"Galatasaray": ["Fenerbahçe"], "Fenerbahçe": ["Galatasaray"]}
    epl, _ = mc.big_score(_match("eng.1", "EPL", "A", "B", 1, 2, 85, 85), riv)
    champ, _ = mc.big_score(_match("eng.2", "Championship", "C", "D", 1, 2, 85, 85), riv)
    assert epl > champ                       # 같은 1·2위전이라도 2부는 등급 가중으로 낮게
    plain, _ = mc.big_score(_match("tur.1", "SuperLig", "Trabzonspor", "Başakşehir", 1, 3, 81, 79), riv)
    derby, tags = mc.big_score(_match("tur.1", "SuperLig", "Galatasaray", "Fenerbahçe", 1, 3, 81, 79), riv)
    assert derby == plain + mc.DERBY_BONUS and tags[0] == "라이벌전"
    assert derby >= 35 > plain               # TIER 2 상위권 라이벌전은 빅매치(BIG_MIN 35), 그냥 상위권 경기는 아님
    ucl, _ = mc.big_score(_match("uefa.champions", "EPL", "A", "E", None, None, 85, 85), riv)
    assert ucl >= 30                         # 유럽대회 가산은 등급 가중 밖


def test_tier_interleave_and_merit() -> None:
    import api.main as M
    items = [{"league": lg, "i": i} for lg in ("AustrianBundesliga", "SuperLig", "EPL", "LaLiga") for i in range(5)]
    out = M._tier_interleave(items, 6)
    # 한 바퀴: TIER 1 리그 2건씩(EPL·LaLiga) → TIER 2 1건 → 2부·TIER 3 1건
    assert [x["league"] for x in out] == ["EPL", "EPL", "LaLiga", "LaLiga", "SuperLig", "AustrianBundesliga"]
    ranked = [{"league": "EPL", "v": 9}, {"league": "EPL", "v": 8}, {"league": "EPL", "v": 7}, {"league": "EPL", "v": 6},
              {"league": "SwissSuperLeague", "v": 5}]
    top = M._merit(ranked, key=lambda x: -x["v"], limit=4, cap=3)
    assert [x["v"] for x in top] == [9, 8, 7, 5]          # 리그당 3명까지 → 다음 리그
    assert M._hub_leagues()[:2] == ["EPL", "LaLiga"]       # 같은 등급 안에선 리그 설정 순서


def test_value_picks_expected_ovr() -> None:
    import api.main as M
    rows = []
    for i in range(60):                                    # OVR = 30 + 2.5·ln(시장가치) 근처, 한 명만 크게 위
        mv = 1e6 * (1 + i % 20)
        ovr = int(round(30 + 2.5 * __import__("math").log(mv))) + (8 if i == 7 else 0)
        rows.append(({"player": f"P{i}", "league": "EPL" if i % 2 else "SerieA", "ovr": ovr}, mv, 22 + i % 6, "ATT", ovr))
    out = M._value_picks(rows)
    assert out and out[0]["player"] == "P7" and out[0]["ovr_gap"] >= 6
    assert all(x["ovr"] >= 70 for x in out)
