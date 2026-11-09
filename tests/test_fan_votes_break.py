"""팬 투표 — A매치 휴식기(앞으로 10일 경기 없음)는 정상, Sofascore 무응답만 실패(2026-11-09 11/08·11/09 빨간불)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import fetch_fan_votes as fv  # noqa: E402


def _run(monkeypatch, tmp_path, answer):
    out = tmp_path / "fan_votes.csv"
    out.write_text("keep\n", encoding="utf-8")
    monkeypatch.setattr(fv, "OUT", out)
    monkeypatch.setattr(fv, "_our_teams", lambda: [])
    monkeypatch.setattr(fv, "close", lambda: None)
    monkeypatch.setattr(fv, "_get", answer)
    return fv.main(), out.read_text(encoding="utf-8")


def test_international_break_is_ok(monkeypatch, tmp_path) -> None:
    def answer(path, tries=3):
        if path.endswith("/seasons"):
            return {"seasons": [{"id": 1}]}
        return {"events": [{"id": 9, "startTimestamp": 4102444800}], "hasNextPage": False}   # 2100년 — 10일 창 밖
    code, text = _run(monkeypatch, tmp_path, answer)
    assert code == 0 and text == "keep\n"                                    # 기존 파일 그대로


def test_source_down_is_failure(monkeypatch, tmp_path) -> None:
    code, text = _run(monkeypatch, tmp_path, lambda path, tries=3: None)
    assert code == 1 and text == "keep\n"
