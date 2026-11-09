"""투톱 세컨드 스트라이커 · 대표 포지션 동점 처리 결정성(2026-11-09 사용자 '이강인은 ST 가 메인이 아니다')."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import position_ovr as po  # noqa: E402
import positions as ps  # noqa: E402


def _lineup(eid, players_pos, formation):
    return pd.DataFrame([{"event_id": eid, "squad": "Atlético Madrid", "formation": formation, "starter": 1, "player": p,
                          "espn_pos": pos, "formation_place": i + 1} for i, (p, pos) in enumerate(players_pos)])


def test_two_striker_starts_are_marked_and_converted_for_attacking_mids() -> None:
    xi = [("GK", "G"), ("RB", "RB"), ("CB1", "CD-R"), ("CB2", "CD-L"), ("LB", "LB"), ("RM", "RM"), ("CM1", "CM-R"),
          ("CM2", "CM-L"), ("LM", "LM"), ("Lee Kang-In", "CF-L"), ("Lookman", "CF-R")]
    rc = ps.role_counts([_lineup("1", xi, "4-4-2")], [1.0])
    lee, lookman = ps.lookup(rc, "Lee Kang-in"), ps.lookup(rc, "Lookman")
    assert lee["ST"] == 1.0 and lee[ps.PAIR] == 1.0
    assert ps.as_second_striker(lee, "Attacking Midfield") == Counter({"AM": 1.0})       # 2선 출신 투톱 = AM
    assert ps.as_second_striker(lookman, "Left Winger") == Counter({"ST": 1.0})          # 윙어 출신 투톱은 ST 그대로
    assert ps.profile(lee, "Attacking Midfield")["primary"] == "AM" and ps.PAIR not in ps.profile(lee)["roles"]
    # 원톱(4-3-3 의 CF)은 투톱 표시가 없다
    one = [(p, pos) for p, pos in xi[:9]] + [("Lee Kang-In", "CF"), ("W", "LW")]
    rc1 = ps.role_counts([_lineup("2", one, "4-3-3")], [1.0])
    assert ps.PAIR not in (ps.lookup(rc1, "Lee Kang-in") or {})


def test_main_position_is_deterministic_on_ties() -> None:
    # LW·RW 같은 경험·같은 OVR — 예전엔 집합 순서(프로세스마다 다름)로 대표가 바뀌었다
    exp = po.experience(Counter({"LW": 6.0, "RW": 6.0}), [], ())
    assert list(exp) == sorted(exp, key=po._ORDER.get)
    res = po.choose(78.0, exp, {"W": 0.0}, [], ())
    assert res["main"] == "RW"                                  # 고정 순서(RW 먼저)
    assert po.choose(78.0, exp, {"W": 0.0}, ["LW"], ())["main"] == "LW"   # 지금 쓰이는 자리(FotMob 첫 포지션)가 먼저
