"""한글 이름 — 영어 문서가 동명이인 안내면 '(footballer, born 생년)' 문서로, 한국어 제목 괄호는 떼기(2026-11-09 김민재)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import names_ko as nk  # noqa: E402


def test_disambiguation_falls_back_to_footballer_page(monkeypatch) -> None:
    pages = {"Lee Kang-in": "이강인", "Kim Min-jae (footballer, born 1996)": "김민재 (1996년생 축구 선수)",
             "Kim Min-jae (footballer)": "김민재 (다른 선수)", "Park Ji-sung (footballer)": "박지성"}
    monkeypatch.setattr(nk, "langlinks_ko", lambda titles: {t: pages[t] for t in titles if t in pages})
    out = nk.player_titles_ko(["Lee Kang-in", "Kim Min-jae", "Park Ji-sung", "Nobody"], {"Kim Min-jae": 1996})
    assert out == {"Lee Kang-in": "이강인", "Kim Min-jae": "김민재 (1996년생 축구 선수)", "Park Ji-sung": "박지성"}   # 생년 붙은 문서 먼저


def test_person_ko_strips_disambiguation_suffix() -> None:
    assert nk.person_ko("김민재 (1996년생 축구 선수)") == "김민재"
    assert nk.person_ko("이재성 (1992년)") == "이재성"
    assert nk.person_ko("데클런 라이스") == "데클런 라이스"
