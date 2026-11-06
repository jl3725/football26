"""Ask Scout 답 평가 채점(scripts/eval_scout_answers.grade) — 서버 없이."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts")]

import eval_scout_answers as ev  # noqa: E402


def test_grade_catches_empty_graph_and_no_data_phrase() -> None:
    res = {"engine": "gemini", "intent": "graph", "answer": "현재 관련 데이터가 조회되지 않습니다.",
           "steps": [{"tool": "graph_query", "count": 0, "error": None}], "grounding": {"ok": True, "unverified": []}}
    fails = ev.grade(res, "tool:graph_query;nonempty;no_empty;grounded")
    assert fails == ["nonempty", "no_empty"]


def test_grade_passes_good_answer_and_reads_old_responses() -> None:
    res = {"engine": "gemini", "intent": "lead", "answer": "아스날 주장은 Martin Ødegaard 입니다.",
           "result": {"team": "Arsenal", "captains": [{"name": "Martin Ødegaard"}]}}          # 단계 기록 없는 예전 응답
    assert ev.grade(res, "tool:team_leadership;contains_any:Ødegaard|외데고르;grounded") == []


def test_grade_flags_rule_fallback_and_ungrounded_numbers() -> None:
    res = {"engine": "rules", "intent": "graph", "answer": "열기 88", "note": "Gemini 실패",
           "steps": [{"tool": "graph_query", "count": 2}], "grounding": {"ok": False, "unverified": ["88"]}}
    fails = ev.grade(res, "grounded")
    assert fails[0].startswith("grounded") and fails[-1].startswith("engine=rules")
