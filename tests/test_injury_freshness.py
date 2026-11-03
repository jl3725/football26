"""결장 표시 뒤 실제로 뛴 선수 — FotMob 다음 경기 결장 명단은 경기 직후에도 옛 '출전 불투명'을 한동안 둔다.

2026-11-02 사용자: 어제 아스날 경기에서 촐리스·칼라피오리·마두에케가 다 뛰었는데 왜 부상이냐.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import api.main as M  # noqa: E402
import fetch_fotmob_injuries as fi  # noqa: E402

TODAY = "2026-11-02"


def _games(*rows):
    return {("id", "1"): {d: {"m": m} for d, m in rows}}


def _r(until, kind="injury"):
    return {"squad": "Arsenal", "player": "Noni Madueke", "fotmob_id": "1", "kind": kind, "expected_return": until}


def test_doubtful_then_played_full_match_is_stale() -> None:
    seen = {("Arsenal", "noni madueke"): ("2026-10-29", "Late November 2026")}   # 처음엔 '11월 말' → 경기 전 '불투명'
    assert M._fm_played_since(_r("Doubtful"), {}, _games(("2026-11-01", 90)), seen, TODAY) == "2026-11-01"


def test_status_changed_after_playing_keeps_injury() -> None:
    # 로프터스치크: 10/23 '불투명' → 10/25 출전 → 지금 '11월 말' — 뛴 뒤 다시 다침(상태가 기록 뒤에 바뀜)
    seen = {("Arsenal", "noni madueke"): ("2026-10-23", "Doubtful")}
    assert M._fm_played_since(_r("Late November 2026"), {}, _games(("2026-10-25", 70)), seen, TODAY) is None


def test_unchanged_long_term_and_played_after_is_stale() -> None:
    seen = {("Arsenal", "noni madueke"): ("2026-10-25", "Mid November 2026")}
    assert M._fm_played_since(_r("Mid November 2026"), {}, _games(("2026-11-01", 25)), seen, TODAY) == "2026-11-01"
    assert M._fm_played_since(_r("Mid November 2026"), {}, _games(("2026-10-20", 90)), seen, TODAY) is None   # 그 전 출전


def test_unknown_first_seen_only_drops_doubtful_after_recent_full_match() -> None:
    assert M._fm_played_since(_r("Doubtful"), {}, _games(("2026-11-01", 84)), {}, TODAY) == "2026-11-01"
    assert M._fm_played_since(_r("Doubtful"), {}, _games(("2026-11-01", 20)), {}, TODAY) is None
    assert M._fm_played_since(_r("Early December 2026"), {}, _games(("2026-11-01", 90)), {}, TODAY) is None
    # 경기 중 부상 교체는 그 경기에 뛴 게 당연
    assert M._fm_played_since(_r("80′ 부상 교체", kind="in_match"), {}, _games(("2026-11-01", 80)), {}, TODAY) is None


def test_change_log_records_until_changes() -> None:
    prev = pd.DataFrame([{"squad": "Milan", "player": "Ruben Loftus-Cheek", "fotmob_id": "7", "kind": "injury",
                          "expected_return": "Doubtful", "match_date": "2026-10-25"}])
    cur = prev.assign(expected_return="Late November 2026")
    ev = fi.injury_changes(prev, cur, TODAY)
    assert [(e["event_type"], e["old_until"], e["new_until"]) for e in ev] == [("until_changed", "Doubtful", "Late November 2026")]
    assert fi.injury_changes(prev, prev, TODAY) == []


def test_injury_signals_settled_by_appearances(monkeypatch) -> None:
    """브리핑·Signals 의 '부상 발생'도 출전으로 정리 — 7일 안에 뛰었으면 결장 신호가 아니었다(칼라피오리 10/27 불투명 → 11/1 90분)."""
    import datastore as ds
    t = pd.DataFrame([{"squad": "Arsenal", "player": "Riccardo Calafiori", "date": "2026-11-01", "minutes": 90},
                      {"squad": "Arsenal", "player": "Bukayo Saka", "date": "2026-11-20", "minutes": 70}])
    monkeypatch.setattr(ds, "read_table", lambda name, league=None: t if name == "fotmob_match_ratings" else None)
    sig = lambda p: p.split()[-1].lower()  # noqa: E731
    ev = [{"date": "2026-10-27", "event": "new", "squad": "Arsenal", "player": "Riccardo Calafiori", "source": "FotMob", "injury": "부상", "until": ""},
          {"date": "2026-10-22", "event": "new", "squad": "Arsenal", "player": "Bukayo Saka", "source": "FotMob", "injury": "부상", "until": ""},
          {"date": "2026-10-30", "event": "new", "squad": "Arsenal", "player": "William Saliba", "source": "TM", "injury": "허리", "until": ""}]
    out = M._settle_by_appearances("EPL", ev, sig)
    got = [(e["event"], e["player"], e["date"]) for e in out]
    assert ("new", "Riccardo Calafiori", "2026-10-27") not in got                       # 5일 만에 90분 — 신호 아님
    assert ("new", "Bukayo Saka", "2026-10-22") in got and ("return", "Bukayo Saka", "2026-11-20") in got
    assert ("new", "William Saliba", "2026-10-30") in got                               # 뛴 기록 없음 — 그대로


def _inj_table(*rows):
    return pd.DataFrame([{"squad": s, "player": p, "injury": i, "until": "", "active": "1"} for s, p, i in rows])


def test_tm_until_update_is_not_a_return(monkeypatch) -> None:
    """TM 'updated'(복귀 예정일만 바뀜)는 복귀가 아님 — 살리바 허리 11/12 → 11/20 이 Inbox '부상 복귀'로 나왔다(2026-11-03)."""
    import datastore as ds
    tm = pd.DataFrame([
        {"run_date": "2026-10-21", "event_type": "updated", "squad": "Arsenal", "player": "William Saliba",
         "old_injury": "Back injury", "new_injury": "Back injury", "old_until": "11/12/2026", "new_until": "20/11/2026"},
        {"run_date": "2026-10-22", "event_type": "recovered_or_removed", "squad": "Arsenal", "player": "Kai Havertz",
         "old_injury": "Knee injury", "new_injury": "", "old_until": "", "new_until": ""}])
    monkeypatch.setattr(ds, "read_table", lambda name, league=None: tm if name == "transfermarkt_injury_changes" else None)
    monkeypatch.setattr(M, "_news_injury_rows", lambda league, days=7: [])
    monkeypatch.setattr(M, "_injuries_table", lambda league: _inj_table(("Arsenal", "William Saliba", "허리 부상")))
    got = [(e["event"], e["player"]) for e in M._injury_events("EPL", days=3650)]
    assert ("return", "William Saliba") not in got
    assert ("return", "Kai Havertz") in got


def test_return_while_still_listed_is_dropped(monkeypatch) -> None:
    """복귀 신호인데 지금도 결장 명단 — TM 목록 깜빡임(오로스 10/25 빠짐 → 10/26 다시)은 빼고,
    복귀 뒤 7일 넘어 따로 잡힌 새 부상(우아이사 햄스트링 복귀 → 9일 뒤 무릎)은 둘 다 둔다. 출전으로 확인한 복귀도 둔다."""
    monkeypatch.setattr(M, "_injuries_table", lambda league: _inj_table(
        ("Osasuna", "Aimar Oroz", "허벅지"), ("PSV", "Sami Ouaissa", "무릎"), ("Arsenal", "Bukayo Saka", "부상")))
    sig = lambda p: p.split()[-1].lower()  # noqa: E731
    ev = [{"date": "2026-10-25", "event": "return", "squad": "Osasuna", "player": "Aimar Oroz", "source": "Transfermarkt"},
          {"date": "2026-10-26", "event": "new", "squad": "Osasuna", "player": "Aimar Oroz", "source": "Transfermarkt"},
          {"date": "2026-10-20", "event": "return", "squad": "PSV", "player": "Sami Ouaissa", "source": "Transfermarkt"},
          {"date": "2026-10-29", "event": "new", "squad": "PSV", "player": "Sami Ouaissa", "source": "Transfermarkt"},
          {"date": "2026-11-01", "event": "return", "squad": "Arsenal", "player": "Bukayo Saka", "source": "출전"},
          {"date": "2026-10-28", "event": "return", "squad": "Arsenal", "player": "Kai Havertz", "source": "Transfermarkt"}]
    got = [(e["event"], e["player"]) for e in M._drop_returns_still_out("X", ev, sig)]
    assert ("return", "Aimar Oroz") not in got
    assert ("return", "Sami Ouaissa") in got
    assert ("return", "Bukayo Saka") in got and ("return", "Kai Havertz") in got


def test_absence_kind() -> None:
    """출장 정지는 부상(✚)과 다르게 — 다우먼 FotMob suspension → '출장 정지'(2026-11-03)."""
    assert M._absence_kind("출장 정지") == "suspension"
    assert M._absence_kind("Red card suspension") == "suspension"
    assert M._absence_kind("허리 부상") == "injury"
    assert M._absence_kind("") == "injury"
