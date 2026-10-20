"""Ask Scout 무료 — 공급자 선택(유료는 허용 시만), Gemini 함수 호출 흐름(가짜 응답), 규칙 라우터 파싱."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import scout_agent as sa  # noqa: E402


def test_provider_never_defaults_to_paid(monkeypatch) -> None:
    monkeypatch.setattr(sa, "_load_dotenv", lambda: None)
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "SCOUT_ALLOW_PAID"):
        monkeypatch.delenv(k, raising=False)
    assert sa.provider() == "rules"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert sa.provider() == "rules"                         # 유료 키만 있으면 쓰지 않는다
    monkeypatch.setenv("SCOUT_ALLOW_PAID", "1")
    assert sa.provider() == "openai"
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    assert sa.provider() == "gemini"                        # 무료가 우선


def test_gemini_function_calling_flow(monkeypatch) -> None:
    calls = []

    def fake_call(body):
        calls.append(body)
        if len(calls) == 1:
            assert body["tools"][0]["functionDeclarations"][0]["parameters"]["type"] == "OBJECT"
            return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "team_now", "args": {"team": "Arsenal"}}}]}}]}
        last = body["contents"][-1]["parts"][0]["functionResponse"]
        assert last["name"] == "team_now" and last["response"]["content"]["team"] == "Arsenal"
        return {"candidates": [{"content": {"parts": [{"text": "아스날은 다음 경기에서 원정입니다."}]}}]}

    monkeypatch.setattr(sa, "_gemini_call", fake_call)
    monkeypatch.setattr(sa, "_clubs", lambda: ["Arsenal"])
    monkeypatch.setattr(sa, "_execute", lambda name, args, league: ("team_now", {"team": args["team"], "next": []}))
    out = sa._answer_gemini("아스날 다음 경기 어때?", None, "EPL", None)
    assert out["engine"] == "gemini" and out["intent"] == "team_now" and "원정" in out["answer"]


def test_rule_router_parses_korean_and_english(monkeypatch) -> None:
    import scout_router as r
    monkeypatch.setattr(r, "_index", lambda: {
        "clubs": [("manchester city", "Manchester City", "EPL"), ("arsenal", "Arsenal", "EPL"), ("맨시티", "Manchester City", "EPL"),
                  ("아스날", "Arsenal", "EPL")],
        "players": [("bukayo saka", "Bukayo Saka", "Arsenal", "EPL", 90.0), ("부카요 사카", "Bukayo Saka", "Arsenal", "EPL", 90.0),
                    ("사카", "Bukayo Saka", "Arsenal", "EPL", 90.0), ("saka", "Bukayo Saka", "Arsenal", "EPL", 90.0)]})
    p = r.parse("사카 최근 뉴스", None, "EPL")
    assert p["intent"] == "news" and p["players"] == [{"name": "Bukayo Saka", "squad": "Arsenal", "league": "EPL"}]
    p = r.parse("맨시티 A매치 차출", None, "EPL")
    assert p["intent"] == "team_now" and p["team"] == "Manchester City"
    p = r.parse("아스날 왼쪽 윙 추천", None, "EPL")
    assert p["intent"] == "recommend" and p["role"] == "Left Winger"
    p = r.parse("라리가 이번 주 요약", "Arsenal", "EPL")
    assert p["intent"] == "week" and p["league"] == "LaLiga" and p["team"] is None
    p = r.parse("Saka news", None, "EPL")
    assert p["intent"] == "news" and p["players"][0]["name"] == "Bukayo Saka"
