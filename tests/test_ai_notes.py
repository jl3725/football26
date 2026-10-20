"""해석 계층(Gemini 무료) — 공용 호출(모델 넘김·하루 상한)·숫자/이름 검증·경기 리포트·뉴스 요약. 네트워크 없이 가짜 응답."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import ai_notes as an  # noqa: E402
import llm  # noqa: E402


class _Resp:
    def __init__(self, code: int, text: str = "", body: str = ""):
        self.status_code, self.text, self._text = code, body, text

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}


def _setup(monkeypatch, tmp_path, responses, daily=10):
    import requests
    calls = []

    def fake_post(url, params=None, json=None, timeout=None):
        calls.append(url.split("/models/")[1].split(":")[0])
        return responses.pop(0)

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("LLM_DAILY_MAX", raising=False)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(llm, "MIN_GAP", 0)
    monkeypatch.setattr(llm, "USAGE_DIR", tmp_path)
    llm.start("test", daily)
    return calls


def test_number_and_name_checks() -> None:
    facts = {"score": "Arsenal 1-0 Nottingham Forest", "goal": {"minute": "80'", "scorer": "Noni Madueke"},
             "possession": 73.8, "p": 0.861, "attendance": "60,123"}
    assert llm.problems("Arsenal이 1-0으로 이겼다. 80' Madueke 결승골, 점유율 74%, 모델 86% 적중, 관중 60,123명.", facts) == []
    assert llm.unverified_numbers("3연승을 달렸다", facts) == ["3"]
    assert llm.unverified_names("Saka가 도움을 기록했다", facts) == ["Saka"]
    assert llm.unverified_names("Arsenal's 승리", facts) == []
    assert llm.unverified_names("value_eur_m 규모", {"value_eur_m": 9.0}) == ["value_eur_m"]   # 키 이름은 근거 아님


def test_generate_falls_back_and_respects_daily_cap(monkeypatch, tmp_path) -> None:
    calls = _setup(monkeypatch, tmp_path, [_Resp(404), _Resp(200, "두 번째 모델 답"), _Resp(500)], daily=3)
    assert llm.generate("q") == "두 번째 모델 답" and calls == llm.models()[:2]
    assert llm.last_model() == llm.models()[1]
    # 404 난 모델은 다시 부르지 않음 · 하루 상한(3)에 닿으면 남은 모델도 안 부르고 None
    calls.clear()
    assert llm.generate("q") is None and calls == [llm.models()[1]]
    u = llm.finish()
    assert u["today"] == 3 and (tmp_path / "usage_test.json").exists()
    assert llm.start("test", 3) == 0                                   # 다음 실행도 오늘 쓴 만큼 빼고 시작


def test_daily_quota_429_stops_model(monkeypatch, tmp_path) -> None:
    calls = _setup(monkeypatch, tmp_path, [_Resp(429, body="GenerateRequestsPerDayPerProjectPerModel"),
                                           _Resp(429, body="PerMinute"), _Resp(200, "ok")])
    assert llm.generate("q") == "ok"
    assert llm.models()[0] in llm._S["dead"] and llm.models()[1] not in llm._S["dead"]
    assert len(calls) == 3


def test_write_checked_retries_once_then_drops(monkeypatch) -> None:
    facts = {"final_score": "Arsenal 1-0 Everton", "goals": [{"minute": "80'", "scorer": "Saka"}]}
    out = iter(["Arsenal이 3연승을 이어 갔다.", "Arsenal이 1-0으로 이겼다. 80' Saka 결승골."])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(out))
    assert an.write_checked("p", facts) == "Arsenal이 1-0으로 이겼다. 80' Saka 결승골."
    out2 = iter(["Rice가 2골", "Rice가 2골"])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(out2))
    assert an.write_checked("p", facts) is None


def test_match_facts_shape() -> None:
    rv = {"date": "2026-10-18", "home": {"team": "Nottingham Forest"}, "away": {"team": "Arsenal"},
          "score": {"home": 0, "away": 1}, "ht": {"home": 0, "away": 0},
          "goals": [{"minute": "80'", "m": 80, "side": "away", "scorer": "Noni Madueke", "assist": "Declan Rice", "kind": ""}],
          "cards": [{"minute": "55'", "m": 55, "side": "home", "player": "X", "color": "yellow"}], "pens": [],
          "stats": [{"key": "possessionPct", "label": "점유율", "h": 26.2, "a": 73.8, "fmt": "pct"}],
          "star": {"player": "Noni Madueke", "side": "away", "goals": 1, "assists": 0},
          "predictions": [{"source": "모델", "pick": "Arsenal 승", "p": 0.612, "hit": True}], "lines": ["결승골은 80'"]}
    f = an.match_facts(rv, "리그")
    assert f["final_score"] == "Nottingham Forest 0-1 Arsenal" and f["half_time"] == "0-0"
    assert f["goals"][0]["team"] == "Arsenal" and f["yellow_cards"] == {"Nottingham Forest": 1, "Arsenal": 0}
    assert f["pre_match_predictions"][0]["probability_pct"] == 61 and f["player_of_match"]["team"] == "Arsenal"


def test_news_brief_keeps_only_verified_lines(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(an.FILES, "news", tmp_path / "news.json")
    arts = [{"link": f"l{i}", "source": "ESPN", "title": "Saka scores twice", "title_ko": "사카 2골", "summary": ""}
            for i in range(3)]
    monkeypatch.setattr(an, "_news_window", lambda: {"Arsenal": arts, "Everton": arts[:1]})
    monkeypatch.setattr(llm, "remaining", lambda: 5)
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"Arsenal": ["Saka가 2골을 넣었다.", "Odegaard가 3도움."]})
    an.run_news()
    t = an._read("news")["teams"]
    assert set(t) == {"Arsenal"}                                      # 기사 1건 팀은 건너뜀
    assert t["Arsenal"]["lines"] == ["Saka가 2골을 넣었다."] and t["Arsenal"]["dropped"] == 1
