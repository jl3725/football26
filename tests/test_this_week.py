"""THIS WEEK — 결장 반영 예상 XI(빠진 선수 본인 세부 포지션 우선), 연속 풀타임, 로테이션 부담 단계."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import this_week as tw  # noqa: E402

norm = str.lower
SLOT = {"LCB": "CB", "RCB": "CB", "RDM": "DM", "RCM": "CM", "ST": "ST"}.get
XI = [{"slot": "LCB", "player": "Gabriel", "kind": "DEF", "ovr": 89}, {"slot": "RDM", "player": "Rice", "kind": "MID", "ovr": 90},
      {"slot": "RCM", "player": "Saka", "kind": "MID", "ovr": 90}, {"slot": "ST", "player": "Havertz", "kind": "FWD", "ovr": 83}]
POOL = [{"player": "Hincapie", "ovr": 84, "bucket": "CB", "line": "DEF"}, {"player": "Mosquera", "ovr": 78, "bucket": "CB", "line": "DEF"},
        {"player": "Zubimendi", "ovr": 85, "bucket": "CM", "line": "MID"}, {"player": "Merino", "ovr": 84, "bucket": "CM", "line": "MID"},
        {"player": "Madueke", "ovr": 82, "bucket": "W", "line": "MID"}, {"player": "Gyokeres", "ovr": 86, "bucket": "ST", "line": "FWD"}]
OWN = {"saka": "W", "gabriel": "CB", "rice": "DM", "havertz": "ST"}


def test_pick_xi_prefers_own_position() -> None:
    xi, ch = tw.pick_xi(XI, {"saka": {"injury": "Hamstring"}, "gabriel": {"injury": "Knee"}}, POOL, norm, OWN, SLOT)
    by = {c["slot"]: c["in"] for c in ch}
    assert by["RCM"] == "Madueke"           # RCM 칸이어도 빠진 선수가 윙어면 윙어로(중앙 미드 Zubimendi 아님)
    assert by["LCB"] == "Hincapie"          # 같은 세부 포지션 최고 OVR
    assert [p["player"] for p in xi] == ["Hincapie", "Rice", "Madueke", "Havertz"]
    assert xi[0]["changed"] and xi[0]["out"] == "Gabriel"


def test_pick_xi_skips_absent_candidates_and_falls_back_to_line() -> None:
    absent = {"rice": {"injury": "Ban"}, "zubimendi": {"injury": "Ankle"}}
    _, ch = tw.pick_xi(XI, absent, POOL, norm, OWN, SLOT)
    assert ch[0]["in"] == "Merino"          # DM 후보 없음 → 슬롯 버킷 없음 → 같은 라인(MID) 최고 OVR, 결장 Zubimendi 제외
    xi, ch = tw.pick_xi(XI, {"havertz": {"injury": "x"}, "gyokeres": {"injury": "y"}}, POOL[:5], norm, OWN, SLOT)
    assert ch[0]["in"] is None and xi[3]["player"] == "—"      # 대체 없음은 빈칸으로 드러낸다


def test_full_streak_and_rotation() -> None:
    rows = [{"date": "2026-10-18", "minutes": 90}, {"date": "2026-10-14", "minutes": 88}, {"date": "2026-10-10", "minutes": 60},
            {"date": "2026-10-05", "minutes": 90}]
    assert tw.full_streak(rows) == 2
    rot = tw.rotation([("Rice", 270), ("Raya", 380)], {"Rice": 4, "Raya": 1})
    assert [(r["player"], r["level"]) for r in rot] == [("Raya", "high"), ("Rice", "high")]   # 360′+ 또는 4연속 → high
    assert tw.rotation([("Odegaard", 280)], {"Odegaard": 1})[0]["level"] == "mid"
