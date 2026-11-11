"""Ask Scout 답 평가 — 서버 재시작(502·503)·Gemini 일시 오류는 다시 묻기(2026-11-10 평가가 정기 배포와 겹쳐 11문항 '실패')."""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT)]

import eval_scout_answers as ev  # noqa: E402


def test_retries_on_restart_and_gemini_hiccup(monkeypatch) -> None:
    calls = []
    seq = [urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None),
           {"engine": "rules", "note": "Gemini 실패(503) — 규칙 기반 답", "answer": "x"},
           {"engine": "gemini", "answer": "ok"}]

    def fake(base, q, team, league):
        calls.append(1)
        x = seq[len(calls) - 1]
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(ev, "_ask_once", fake)
    monkeypatch.setattr(ev, "wait_ready", lambda base, max_wait=0, sleep=None: True)
    res = ev.ask("b", "q", "", "", tries=3, sleep=lambda s: None)
    assert res["engine"] == "gemini" and len(calls) == 3


def test_other_http_errors_are_not_retried(monkeypatch) -> None:
    def fake(*a):
        raise urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
    monkeypatch.setattr(ev, "_ask_once", fake)
    try:
        ev.ask("b", "q", "", "", sleep=lambda s: None)
        raise AssertionError("should raise")
    except urllib.error.HTTPError as e:
        assert e.code == 400
