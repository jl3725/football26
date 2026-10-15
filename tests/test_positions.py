from __future__ import annotations

from collections import Counter

import pandas as pd

import positions as ps


def test_slot_roles_follow_formation_context() -> None:
    assert ps.slot_roles("4-2-3-1") == ["GK", "RB", "CB", "CB", "LB", "DM", "DM", "RW", "AM", "LW", "ST"]
    assert ps.slot_roles("4-3-3")[6] == "DM"                      # 단일 피벗
    assert ps.slot_roles("3-4-3")[4] == "RB" and ps.slot_roles("3-4-3")[7] == "LB"   # 3백의 윙 미드 = 윙백
    assert ps.slot_roles("4-1-4-1")[7:9] == ["CM", "CM"]          # 4-1-4-1 의 두 중앙은 8번
    assert ps.slot_roles("4-4-2")[5] == "RW"


def test_profile_from_lineups_primary_and_secondary() -> None:
    p = ps.profile(Counter({"LB": 11.5, "CB": 5.5}), "Centre-Back")     # Hincapié: 실제론 주로 LB
    assert p["primary"] == "LB" and p["secondary"] == ["CB"]
    p = ps.profile(Counter({"DM": 19.5, "CM": 12.5, "RB": 0.5}), "Central Midfield")
    assert p["primary"] == "DM" and "CM" in p["secondary"] and "RB" not in p["secondary"]


def test_profile_falls_back_to_tm_with_few_starts() -> None:
    p = ps.profile(Counter({"ST": 1.0}), "Left Winger")
    assert p["primary"] == "LW" and p["source"] == "tm"


def test_role_counts_from_espn_lineup() -> None:
    pos = ["G", "RB", "CD-R", "CD-L", "LB", "DM-R", "DM-L", "AM-R", "AM-C", "AM-L", "F"]
    names = [f"P{i}" for i in range(11)]
    df = pd.DataFrame({"squad": "X", "event_id": 1, "formation": "4-2-3-1", "starter": 1, "player": names,
                       "espn_pos": pos, "formation_place": range(1, 12)})
    rc = ps.role_counts([df], [1.0])
    assert rc["p4"]["LB"] == 1 and rc["p9"]["LW"] == 1 and rc["p8"]["AM"] == 1 and rc["p5"]["DM"] == 1


def test_fit_scores() -> None:
    prof = {"primary": "LB", "secondary": ["CB"]}
    assert ps.fit(prof, "LB") == 1.0 and ps.fit(prof, "CB") == 0.95
    assert ps.fit(prof, "RB") == 0.75 and ps.fit(prof, "GK") == 0.2


def test_lookup_by_last_name_and_initial() -> None:
    counts = {"gabriel magalhaes": Counter({"CB": 10})}
    assert ps.lookup(counts, "Gabriel Magalhães")["CB"] == 10
    assert ps.lookup(counts, "G. Magalhaes") is not None
    assert ps.lookup(counts, "Unknown Player") is None
