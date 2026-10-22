"""recent_form — 팀별 결과 색인(한 번 만들어 재사용, 2026-10-22 성능 점검)이 예전 규칙과 같은 답."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import match_center as mc  # noqa: E402


def _rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"squad": "Arsenal", "date": "2026-10-04", "status": "completed", "comp_code": "eng.1", "result": "W"},
        {"squad": "Arsenal", "date": "2026-09-20", "status": "completed", "comp_code": "eng.1", "result": "D"},
        {"squad": "Arsenal", "date": "2026-10-01", "status": "completed", "comp_code": "uefa.champions", "result": "L"},  # 리그 아님
        {"squad": "Arsenal", "date": "2026-10-18", "status": "scheduled", "comp_code": "eng.1", "result": ""},           # 안 끝남
        {"squad": "Arsenal", "date": "2026-09-27", "status": "completed", "comp_code": "eng.1", "result": "L"},
        {"squad": "Chelsea", "date": "2026-10-04", "status": "completed", "comp_code": "eng.1", "result": "W"},
    ])


def test_recent_form_rules() -> None:
    rows = _rows()
    assert mc.recent_form(rows, "Arsenal") == ["D", "L", "W"]          # 리그·끝난 경기만, 날짜순
    assert mc.recent_form(rows, "Arsenal", 2) == ["L", "W"]
    assert mc.recent_form(rows, "Chelsea") == ["W"] and mc.recent_form(rows, "Nobody") == []
    assert mc.recent_form(pd.DataFrame(), "Arsenal") == [] and mc.recent_form(None, "Arsenal") == []


def test_recent_form_new_table_not_stale() -> None:
    a = _rows()
    assert mc.recent_form(a, "Chelsea") == ["W"]
    b = pd.concat([a, pd.DataFrame([{"squad": "Chelsea", "date": "2026-10-18", "status": "completed",
                                     "comp_code": "eng.1", "result": "L"}])], ignore_index=True)
    assert mc.recent_form(b, "Chelsea") == ["W", "L"]                  # 다른 표는 새로 색인
