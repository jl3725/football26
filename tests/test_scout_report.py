"""스카우팅 리포트 판단 규칙 — 강약점 백분위, 가용성 위험, 계약 상태, 가치 변화, 이적설 합치기, 판단 문장."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import scout_report as sr  # noqa: E402

CATS = [{"name": "공격", "metrics": [{"label": "슈팅/90", "pct": 92, "raw": 3.1}, {"label": "빅찬스/90", "pct": 0, "raw": 0.0}]},
        {"name": "패스", "metrics": [{"label": "전진패스/90", "pct": 75, "raw": 6.2}, {"label": "롱패스%", "pct": 20, "raw": 41.0},
                                    {"label": "패스%", "pct": 50, "raw": 82.0}]}]


def test_strengths_and_weaknesses() -> None:
    s, w = sr.strengths(CATS)
    assert [x["label"] for x in s] == ["슈팅/90", "전진패스/90"]       # 70 이상, 높은 순
    assert [x["label"] for x in w] == ["빅찬스/90", "롱패스%"]          # 30 이하, 낮은 순
    assert sr._top_pct(92) == 8


def test_availability_contract_market() -> None:
    assert sr.availability([{"season": "26/27", "games_missed": 0}, {"season": "25/26", "games_missed": 15}], None)["risk"] == "high"
    assert sr.availability([{"season": "26/27", "games_missed": 0}, {"season": "25/26", "games_missed": 2}], None)["risk"] == "low"
    assert sr.availability([], {"injury": "Knee", "until": "2026-11-01"})["risk"] == "mid"         # 지금 결장이면 적어도 보통
    today = dt.date(2026, 10, 21)
    assert sr.contract("2027-06-30", today)["status"] == "expiring"
    assert sr.contract("2028-06-30", today)["status"] == "short"
    assert sr.contract("2030-06-30", today)["status"] == "long"
    assert sr.contract(None, today)["status"] == "unknown"
    m = sr.market(120e6, [{"date": "2025-09-01", "value_eur": 100e6}, {"date": "2026-06-01", "value_eur": 130e6}], today)
    assert m["change_12m_pct"] == 20 and m["peak_eur"] == 130e6


def test_talk_merge_keeps_higher_stage_and_outlet_rate() -> None:
    tm = [{"target_club": "Real Madrid", "date": "2026-10-10", "probability": None}]
    news = [{"to_club": "Real Madrid", "date": "2026-10-15", "source": "BBC Sport", "stage": "talks", "headline": "x"},
            {"to_club": "Chelsea", "date": "2026-10-12", "source": "Mirror", "stage": "interest", "headline": "y"}]
    track = {"outlets": {"BBC Sport": {"rate": 0.81, "few": False}}}
    t = sr.talk_items(tm, news, track)
    assert [x["to_club"] for x in t] == ["Real Madrid", "Chelsea"]                     # 최신순
    assert t[0]["stage"] == "talks" and t[0]["outlet_rate"] == 0.81


def test_verdict_uses_input_numbers_only() -> None:
    d = {"line": "ATT", "minutes": 598, "goals": 3, "assists": 0, "ovr": 90, "comp_usage": {"role": "주전"},
         "recent": {"score": 90, "n": 5, "avg5": 7.51}, "form": 97}
    s, w = sr.strengths(CATS)
    av = sr.availability([{"season": "26/27", "games_missed": 0}, {"season": "25/26", "games_missed": 15}], None)
    v = sr.verdict(d, s, w, av, sr.contract("2030-06-30", dt.date(2026, 10, 21)), sr.market(110e6, []), [])
    assert v[0].startswith("주전 · 리그 598′ 3골 0도움 · OVR 90")
    assert "슈팅/90(같은 공격수 상위 8%)" in v[1] and "빅찬스/90(하위 1%)" in v[2]   # 0% 는 1% 로
    assert "하락세" in v[3] and "주의" in v[4] and "장기 계약" in v[5] and "1년" not in v[5]
