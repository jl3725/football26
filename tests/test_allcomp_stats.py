"""전 대회 기록 — 대회 수준·가중, 척도 맞추기, 리그 값과 섞기, OVR 평점 표본(src/allcomp_stats.py · ratings_v3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import allcomp_stats as acs  # noqa: E402
import ratings_v3 as rv3  # noqa: E402
from rating_blend import fm_to_ss  # noqa: E402

LV = {"EPL": 100.0, "Ligue1": 93.0, "LaLiga": 98.0}
TL = {"PSG": "Ligue1", "Barcelona": "LaLiga", "Arsenal": "EPL"}


def _rows(**kw) -> pd.DataFrame:
    base = {"match_id": "1", "date": "2026-10-01", "squad": "PSG", "opponent": "Barcelona", "home_away": "home",
            "fotmob_id": "100", "player": "A", "minutes": 90, "rating": 8.0, "goals": 0, "assists": 0, "det": 1}
    return pd.DataFrame([{**base, **r} for r in kw["rows"]])


def test_levels_and_weights() -> None:
    assert acs.kind("fra.1") == "league" and acs.kind("uefa.champions") == "euro" and acs.kind("fra.coupe_de_france") == "cup"
    assert acs.match_level("uefa.champions", 93, 100) == 100        # 상대가 EPL 팀
    assert acs.match_level("uefa.champions", 93, 93) == 93          # 상대가 리그1 팀
    assert acs.match_level("uefa.champions", 93, None) == 90        # 우리 8개 리그 밖(슬로반)
    assert acs.match_level("uefa.europa.conf", 100, None) == 82
    assert acs.match_level("fra.coupe_de_france", 93, None) == 81   # 하부 리그 상대
    x = acs.prep(_rows(rows=[{"comp_code": "fra.1"}, {"comp_code": "uefa.champions", "match_id": "2"},
                             {"comp_code": "fra.coupe_de_france", "match_id": "3", "opponent": "Rouen"}]), LV, TL)
    assert list(x["comp_code"]) == ["uefa.champions", "fra.coupe_de_france"]   # 리그 경기는 뺀다
    assert list(x["_w"]) == [1.0, 0.5] and list(x["_lvl"]) == [98.0, 81.0]
    # 상대 팀 Elo 가 있으면 그날 Elo 의 수준(80 + (Elo − 1500)/10, 75~115) — 맨시티 1934 → 115(상한), 약체 1450 → 75
    elo = {("Barcelona", "2026-10-01"): 1934.0, ("Rouen", "2026-10-01"): 1450.0}
    y = acs.prep(_rows(rows=[{"comp_code": "uefa.champions"}, {"comp_code": "fra.coupe_de_france", "match_id": "3", "opponent": "Rouen"},
                             {"comp_code": "uefa.europa", "match_id": "4", "opponent": "Nobody"}]), LV, TL,
                 lambda n, d: elo.get((n, d)))
    assert list(y["_lvl"]) == [115.0, 75.0, 86.0] and acs.elo_level(1700) == 100.0


def test_rating_table_and_attach() -> None:
    x = acs.prep(_rows(rows=[{"comp_code": "uefa.champions", "rating": 8.6},
                             {"comp_code": "fra.coupe_de_france", "match_id": "3", "opponent": "Rouen", "rating": 7.0}]), LV, TL)
    by_id, _ = acs.rating_table(x)
    t = by_id["100"]
    assert t["minutes"] == 135 and t["raw_minutes"] == 180            # 컵은 절반 가중
    assert round(t["fm_rating"], 3) == round((8.6 * 90 + 7.0 * 45) / 135, 3)
    frame = pd.DataFrame([{"player": "A", "squad": "PSG", "fm_id": 100.0}, {"player": "B", "squad": "PSG", "fm_id": None}])
    out = acs.attach_x(frame, (by_id, {}), ({}, {}))
    assert round(float(out.loc[0, "x_ss_rating"]), 3) == round(fm_to_ss(t["fm_rating"]), 3)
    assert pd.isna(out.loc[1, "x_ss_rating"]) and out.loc[0, "x_comps"] == {"fra.coupe_de_france": 90, "uefa.champions": 90}


def test_calibrate_and_combine() -> None:
    # 리그 경기 — 우리 표 태클이 FotMob 의 2배인 척도(40명), 성공률은 5%p 높음
    lr = []
    for i in range(40):
        lr += [{"_key": str(i), "minutes": 90, "tackles": 1, "aer_won": 2, "aer_tot": 4} for _ in range(6)]
    fm = acs.per90(pd.DataFrame(lr))
    ours = pd.DataFrame({"_key": [str(i) for i in range(40)], "minutes": [540] * 40,
                         "tackles_won_per90_ss": [2.0] * 40, "aerial_won_pct": [55.0] * 40})
    cal = acs.calibrate(ours, fm)
    assert cal["tackles_won_per90_ss"] == ("ratio", 2.0) and cal["aerial_won_pct"] == ("diff", 5.0)
    # 리그 밖: 0번 선수 UCL 180′(가중 1.0) 태클 4회 → 2.0/90 → 척도 ×2 = 4.0/90
    x = pd.DataFrame([{"_key": "0", "minutes": 90, "_w": 1.0, "tackles": 2, "aer_won": 3, "aer_tot": 4}] * 2)
    x90 = acs.per90(x, weight="_w")
    frame = pd.DataFrame({"_key": ["0", "1"], "minutes": [540, 540], "tackles_won_per90_ss": [2.0, 2.0],
                          "aerial_won_pct": [55.0, 55.0]}, index=[5, 6])
    out = acs.combine(frame, x90, cal)
    assert list(out.index) == [5, 6]
    assert round(out.loc[5, "tackles_won_per90_ss"], 3) == round((2.0 * 540 + 4.0 * 180) / 720, 3)
    assert round(out.loc[5, "aerial_won_pct"], 2) == round((55 * 540 + 80 * 180) / 720, 2)   # 75% + 5%p
    assert out.loc[5, "minutes"] == 720 and out.loc[5, "_x_minutes"] == 180 and out.loc[5, "_league_minutes"] == 540
    assert out.loc[6, "tackles_won_per90_ss"] == 2.0 and out.loc[6, "minutes"] == 540   # 리그 밖 기록 없음 = 그대로


def test_ovr_class_uses_euro_sample() -> None:
    base = dict(ss_rating=6.9, minutes=600, prev_ss_rating=6.9, prev_minutes=2000, ln="MID", league_level=93.0,
                prev_league_level=93.0)
    rel0, off0 = rv3._class_parts(**{k: v for k, v in base.items()})
    rel1, off1 = rv3._class_parts(**base, extra=[(7.8, 270, 100.0, False), (7.6, 1000, 98.0, True)])
    assert rel1 > rel0 + 0.2                                           # 챔스 고평점이 클래스 평점을 끌어올림
    assert off1 < off0                                                 # 챔스(수준 100)는 리그 보정이 없어 평균 보정도 줄어듦
    _, off3 = rv3._class_parts(**base, extra=[(7.8, 270, 115.0, False)])
    _, off4 = rv3._class_parts(**base, extra=[(7.8, 270, 100.0, False)])
    assert off3 < off4                                                 # 강팀 상대(수준 115)는 가산(보정이 음수)
    rel2, _ = rv3._class_parts(**base, extra=[(None, None, None, False), (pd.NA, pd.NA, pd.NA, True)])
    assert rel2 == rel0                                                # 표본 없으면 예전과 같다


def test_form_rating_blends_euro_on_league_scale() -> None:
    row = {"ss_rating": 7.0, "minutes": 600, "_league_level": 93.0, "x_ss_rating": 7.6, "x_minutes": 300, "x_level": 100.0}
    x_lg = 7.6 - 0.0 + 0.02 * 7                                        # UCL(EPL 평균 상대) 7.6 → 리그1 척도 7.74
    assert abs(rv3.ss_all_comps(row) - (7.0 * 600 + x_lg * 300) / 900) < 1e-9
    assert rv3.ss_all_comps({"ss_rating": 7.0, "minutes": 600}) == 7.0   # 유럽·컵 없으면 리그 평점 그대로
