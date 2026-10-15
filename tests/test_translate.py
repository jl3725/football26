from __future__ import annotations

import json

import pytest

import news_db
import translate


class _Resp:
    def __init__(self, status: int, payload=None, text: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(translate, "_load_env", lambda: None)
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    monkeypatch.setattr(translate, "_GEMINI_GAP", 0)
    monkeypatch.setattr(translate, "_gemini_dead", set())
    monkeypatch.setattr(translate, "_google_dead_until", 0.0)
    monkeypatch.setattr(translate, "_gt_dead_until", 0.0)
    monkeypatch.setenv("OPENAI_API_KEY", "set-but-must-not-be-used")
    monkeypatch.delenv("TRANSLATE_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(translate, "_openai_batch", lambda texts: pytest.fail("OpenAI 는 기본 경로에서 쓰면 안 됨"))
    translate.STATS.clear()


def _gemini_ok(items: list[str]) -> _Resp:
    body = {"t": [f"번역:{x}" for x in items]}
    return _Resp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(body, ensure_ascii=False)}]}}]})


def test_gemini_first_and_falls_back_to_next_model_on_daily_quota(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = []

    def post(url, json, timeout, headers):
        calls.append(url.split("/models/")[1].split(":")[0])
        if len(calls) == 1:
            return _Resp(429, text="GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return _gemini_ok(__import__("json").loads(json["contents"][0]["parts"][0]["text"])["items"])

    monkeypatch.setattr(translate.requests, "post", post)
    monkeypatch.setattr(translate.requests, "get", lambda *a, **k: pytest.fail("Gemini 성공 시 구글 호출 금지"))
    out = translate.translate_many(["Arsenal win", "", "Bayern lose"])
    assert out == ["번역:Arsenal win", "", "번역:Bayern lose"]
    assert calls[0] != calls[1]
    assert translate.STATS["gemini"] == 2


def _gtx(text: str) -> _Resp:
    lines = text.split("\n")
    segs = [[f"번역{i}" + ("\n" if i < len(lines) - 1 else ""), ln] for i, ln in enumerate(lines)]
    return _Resp(200, [segs])


def test_clients5_batches_items_with_per_item_language(monkeypatch):
    """기본 구글 경로는 clients5 — 문장마다 q 로 보내 섞인 언어도 각각 번역(2026-10-15)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    sent = []

    def post(url, params, data, headers, timeout):
        sent.append([q for _, q in data])
        return _Resp(200, [[f"번역{i}", "xx"] for i, _ in enumerate(data)])

    monkeypatch.setattr(translate.requests, "post", post)
    monkeypatch.setattr(translate.requests, "get", lambda *a, **k: pytest.fail("clients5 성공 시 gtx 호출 금지"))
    out = translate.translate_many(["Terzic vuelve", "FC Twente presenteert", "Arsenal win"])
    assert out == ["번역0", "번역1", "번역2"] and len(sent) == 1
    assert translate.STATS["google"] == 3


def test_result_without_korean_is_rejected_and_next_provider_used(monkeypatch):
    """철자만 바뀐 원문('relutar') 같은 결과는 실패로 보고 다음 공급자(gtx)로."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(translate.requests, "post", lambda *a, **k: _Resp(200, ["Terzic vuelve a relutar", "es"]))
    monkeypatch.setattr(translate.requests, "get", lambda url, params, headers, timeout: _gtx(params["q"]))
    assert translate.translate_many(["Terzic vuelve a reclutar"]) == ["번역0"]
    assert translate.STATS["google"] == 0 and translate.STATS["google_gtx"] == 1


def test_google_batches_lines_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(translate.requests, "post", lambda *a, **k: _Resp(429))   # clients5 막힘 → gtx
    reqs = []

    def get(url, params, headers, timeout):
        reqs.append(params["q"])
        return _gtx(params["q"])

    monkeypatch.setattr(translate.requests, "get", get)
    out = translate.translate_many(["a", "b\nwith newline", "c"])
    assert out == ["번역0", "번역1", "번역2"]
    assert len(reqs) == 1                       # 한 요청으로 묶음
    assert translate.STATS["google_gtx"] == 3


def test_google_blocked_returns_none_not_original(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(translate.requests, "get", lambda *a, **k: _Resp(429))
    monkeypatch.setattr(translate.requests, "post", lambda *a, **k: _Resp(429))
    assert translate.translate_many(["Arsenal win"]) == [None]
    assert translate.STATS["failed"] == 1


def test_provider_none_skips(monkeypatch):
    monkeypatch.setenv("TRANSLATE_PROVIDER", "none")
    monkeypatch.setattr(translate.requests, "get", lambda *a, **k: pytest.fail("호출 금지"))
    assert translate.translate_many(["x", ""]) == [None, ""]


def test_news_db_reuses_translation_and_backfills(monkeypatch, tmp_path):
    monkeypatch.setattr(news_db, "DB_PATH", tmp_path / "news.db")
    news_db.init_db()
    a = {"link": "L1", "headline": "Arsenal win", "desc": "d"}
    news_db.upsert_articles([a], "Arsenal")
    assert [r["link"] for r in news_db.untranslated()] == ["L1"]
    assert news_db.set_translation("L1", "아스날 승리", "요약") == 1
    news_db.upsert_articles([a], "Chelsea")    # 같은 기사가 다른 팀으로 들어오면 번역 재사용
    assert news_db.untranslated() == []
    assert news_db.translation_stats("2000-01-01")["translated_pct"] == 100.0


def test_news_db_treats_non_korean_translation_as_untranslated(monkeypatch, tmp_path):
    monkeypatch.setattr(news_db, "DB_PATH", tmp_path / "news.db")
    news_db.init_db()
    news_db.upsert_articles([{"link": "L2", "headline": "Un repóker que lanza al Atlético", "desc": ""}], "Atlético")
    news_db.set_translation("L2", "Un repoker que lanza al Atlético", "")   # 철자만 바뀐 원문
    assert [r["link"] for r in news_db.untranslated()] == ["L2"]


def test_clients5_single_item_nested_response(monkeypatch):
    """문장이 하나여도 응답은 [["번역", "en"]] — 리스트 모양 그대로 저장되던 것(2026-10-15 이적 소식 1건)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(translate.requests, "post", lambda *a, **k: _Resp(200, [["맨유 마르티네스 미래 불확실", "en"]]))
    assert translate.translate_many(["Martinez future at Man Utd uncertain"]) == ["맨유 마르티네스 미래 불확실"]
