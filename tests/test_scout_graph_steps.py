"""Ask Scout 그래프 RAG 1단계(2026-11-06) — 빈 결과 다시 시도·여러 도구 이어 부르기(최대 3)·답 숫자 대조."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import scout_agent as sa  # noqa: E402


def _call(name, args):
    return {"candidates": [{"content": {"parts": [{"functionCall": {"name": name, "args": args}}]}}]}


def _text(t):
    return {"candidates": [{"content": {"parts": [{"text": t}]}}]}


def _setup(monkeypatch, replies, results):
    bodies = []

    def fake_call(body):
        bodies.append(body)
        return replies[len(bodies) - 1]

    monkeypatch.setattr(sa, "_gemini_call", fake_call)
    monkeypatch.setattr(sa, "_clubs", lambda: ["Arsenal"])
    it = iter(results)
    monkeypatch.setattr(sa, "_execute", lambda name, args, league: next(it))
    return bodies


def test_empty_graph_result_gets_hint_and_retry(monkeypatch) -> None:
    # 기자(Journalist) 경로 0행 → 힌트 → 매체(Outlet) 경로로 다시 → 답
    bodies = _setup(monkeypatch,
                    [_call("graph_query", {"cypher": "MATCH (j:Journalist) RETURN j LIMIT 5"}),
                     _call("graph_query", {"cypher": "MATCH (o:Outlet) RETURN o LIMIT 5"}),
                     _text("아스날행 보도는 Bruno Guimarães 6건이 가장 많습니다.")],
                    [("graph", {"rows": [], "count": 0, "cypher": "j"}),
                     ("graph", {"rows": [{"k.player": "Bruno Guimarães", "articles": 6}], "count": 1, "cypher": "o"})])
    out = sa._answer_gemini("아스날 이적설 기자 보도 많은 선수", "Arsenal", "EPL", None)
    resps = [x["parts"][0]["functionResponse"] for x in bodies[-1]["contents"] if "functionResponse" in x["parts"][0]]
    first = resps[0]["response"]["content"]
    assert "hint" in first and "Outlet" in first["hint"]                     # 0행이면 넓히는 방법을 알려 준다
    assert [s["count"] for s in out["steps"]] == [0, 1] and out["intent"] == "graph"
    assert out["result"]["count"] == 1                                       # 카드 = 결과가 있는 단계
    assert out["grounding"]["ok"] and "Bruno" in out["answer"]


def test_last_step_forces_text_answer(monkeypatch) -> None:
    # 도구를 계속 부르면 3번째 뒤엔 글로만 답하게(예전엔 두 번째 도구 호출이 오면 답이 비었다)
    bodies = _setup(monkeypatch,
                    [_call("team_now", {"team": "Arsenal"}), _call("team_form", {"team": "Arsenal"}),
                     _call("player_news", {"player": "Saka"}), _text("아스날은 최근 흐름이 좋습니다.")],
                    [("team_now", {"team": "Arsenal"}), ("tform", {"team": "Arsenal"}), ("news", {"player": "Saka"})])
    out = sa._answer_gemini("아스날 요즘 어때", "Arsenal", "EPL", None)
    assert len(out["steps"]) == 3
    assert bodies[3].get("toolConfig", {}).get("functionCallingConfig", {}).get("mode") == "NONE"
    assert "toolConfig" not in bodies[2]
    assert out["answer"].startswith("아스날")


def test_unverified_number_is_rewritten(monkeypatch) -> None:
    bodies = _setup(monkeypatch,
                    [_call("graph_query", {"cypher": "MATCH ..."}), _text("Can Uzun 이적설 열기 88입니다."),
                     _text("Can Uzun 이적설 열기 46입니다.")],
                    [("graph", {"rows": [{"p.name": "Can Uzun", "l.heat": 46}], "count": 1, "cypher": "c"})])
    out = sa._answer_gemini("아스날 이적설", "Arsenal", "EPL", None)
    assert "88" in bodies[2]["contents"][-1]["parts"][0]["text"]               # 결과에 없는 숫자를 짚어 다시 쓰게(고쳐 쓰기는 새 리스트)
    assert out["answer"].endswith("46입니다.") and out["grounding"] == {"ok": True, "unverified": []}


def test_number_check_allows_units_and_list_numbers() -> None:
    facts = '{"rows": [{"p.name": "Doku", "market_value_eur": 75000000, "l.heat": 0.62}]}'
    assert sa._unverified_numbers("1. Doku — 몸값 €75M, 열기 62%", facts) == []
    assert sa._unverified_numbers("상위 3명 · 몸값 €90M", facts) == ["90"]
