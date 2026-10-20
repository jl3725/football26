"""이적시장 감시 — 리그 이적 페이지 파싱, 우리 데이터에 없는 이적이 있는 클럽만 다시 받기, 마감 직전 60분 간격."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import transfer_watch as tw  # noqa: E402

HTML = """
<div class="box"><h2>Transfer record</h2><table></table></div>
<div class="box"><h2><a>Arsenal FC</a></h2>
  <table><thead><tr><th>In</th></tr></thead><tbody>
    <tr><td><a>Bruno Guimarães</a></td></tr><tr><td><a>Ezri Konsa</a></td></tr></tbody></table>
  <table><thead><tr><th>Out</th></tr></thead><tbody><tr><td><a>Gabriel Martinelli</a></td></tr></tbody></table>
</div>
<div class="box"><h2>Chelsea FC</h2>
  <table><tbody><tr><td><a>New Signing</a></td></tr></tbody></table>
  <table><tbody></tbody></table>
</div>
"""


def test_parse_and_changed_clubs() -> None:
    page = tw.parse_league_page(HTML)
    assert set(page) == {"Arsenal FC", "Chelsea FC"}
    assert page["Arsenal FC"]["in"] == {"bruno guimaraes", "ezri konsa"}
    ours = pd.DataFrame([
        {"squad": "Arsenal", "season_id": 2026, "window": "summer", "direction": "in", "player": "Bruno Guimarães"},
        {"squad": "Arsenal", "season_id": 2026, "window": "summer", "direction": "in", "player": "Ezri Konsa"},
        {"squad": "Arsenal", "season_id": 2026, "window": "summer", "direction": "in", "player": "Karl Hein"},  # 임대 복귀 등 우리만 가진 행은 무관
        {"squad": "Arsenal", "season_id": 2026, "window": "summer", "direction": "out", "player": "Gabriel Martinelli"},
        {"squad": "Chelsea", "season_id": 2026, "window": "summer", "direction": "in", "player": "Old Name"},
    ])
    assert tw.changed_clubs(page, ours, 2026, "summer") == ["Chelsea"]
    # 겨울 창 기준이면 아스날 이적도 우리 데이터(여름 행)에 없으니 다시 받는다
    assert tw.changed_clubs(page, ours, 2026, "winter") == ["Arsenal", "Chelsea"]


def test_interval_tightens_before_deadline() -> None:
    assert tw.interval_min(dt.date(2027, 1, 10), "winter") == 180
    assert tw.interval_min(dt.date(2027, 1, 28), "winter") == 60
    assert tw.interval_min(dt.date(2026, 8, 30), "summer") == 60
    assert tw.interval_min(dt.date(2026, 7, 1), "summer") == 180
