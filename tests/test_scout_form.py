"""Ask Scout 폼(P2 ⑦) — 판정(수준 + 방향), 답 문장(값만 인용)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import scout_agent as sa  # noqa: E402
import scout_router as sr  # noqa: E402


def test_form_verdict_level_and_direction() -> None:
    assert sa.form_word(96) == "절정" and sa.form_word(82) == "좋음" and sa.form_word(70) == "보통"
    assert sa.form_word(58) == "주춤" and sa.form_word(50) == "부진" and sa.form_word(None) is None
    assert sa._form_verdict(90, 96) == "최근 폼 절정 · 시즌 수준"           # 6 낮아도 절정은 하락세가 아니다(사카)
    assert sa._form_verdict(60, 94) == "최근 폼 주춤 · 시즌보다 하락세"     # 외데고르
    assert sa._form_verdict(88, 70) == "최근 폼 좋음 · 시즌보다 상승세"
    assert sa._form_verdict(None, 80).startswith("최근 출전 적음")


def test_player_form_sentence_quotes_values() -> None:
    r = {"player": "Bukayo Saka", "squad": "Arsenal", "verdict": "최근 폼 절정 · 시즌 수준", "ovr": 90, "ovr_change_2w": 1,
         "season": {"form": 96, "rating_fotmob": 7.31, "rating_two_sources": 7.43, "minutes": 598, "goals": 3, "assists": 0},
         "recent": {"form": 90, "n": 5, "avg5_fotmob": 7.51,
                    "matches": [{"opponent": "Nottingham Forest", "rating": 6.94, "goals": 0, "assists": 0},
                                {"opponent": "Lille", "rating": 7.94, "goals": 1, "assists": 1}]},
         "europe_cups": {"rating_fotmob": 7.53, "minutes": 98}}
    t = sr._say_player_form(r)
    for want in ("Bukayo Saka(Arsenal) — 최근 폼 절정", "평균 7.51 / 시즌 7.31(FotMob)", "최근 90 / 시즌 96", "598′ 3골 0도움",
                 "유럽·컵 평점 7.53(98′, FotMob)", "Lille 7.94(⚽1)(🅰1)", "OVR 90(2주 +1)"):
        assert want in t, (want, t)
    assert sr._say_player_form({"error": "선수 'X' 를 찾지 못했습니다"}) == "선수 'X' 를 찾지 못했습니다"


def test_team_form_sentence() -> None:
    r = {"team": "Arsenal", "last5": [{"opp": "Lille", "score": "3-0", "result": "W"}, {"opp": "Brighton", "score": "0-3", "result": "L"}],
         "record5": {"W": 1, "D": 0, "L": 1, "gf": 3, "ga": 3}, "table": {"rank": 2, "points": 18, "played": 7},
         "elo": {"now": 1943, "change_30d": 15}, "hot": [{"player": "Declan Rice", "recent_form": 94}],
         "cold": [{"player": "Martin Ødegaard", "season_form": 94, "recent_form": 60}]}
    t = sr._say_team_form(r)
    for want in ("최근 2경기 1승 0무 1패(득 3 실 3)", "Lille 3-0W", "리그 2위 18점(7경기)", "Elo 1943(30일 +15)",
                 "Declan Rice(94)", "Martin Ødegaard(94→60)"):
        assert want in t, (want, t)
