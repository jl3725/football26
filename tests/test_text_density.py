"""글 줄이기(2026-10-23) — 위키 소개 첫 괄호, TM 부상명 한글, TM 복귀 날짜, 라이브 블로그 요약 거르기."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import injury_names as inj  # noqa: E402
from wiki_text import tidy_intro  # noqa: E402


def test_tidy_intro_drops_native_name_and_birth() -> None:
    bio = ("미켈 아르테타 아마트리아인(스페인어: Mikel Arteta Amatriain, 1982년 3월 26일 산세바스티안 ~ )은 "
           "스페인의 축구 지도자이다. 그는 (한때) 주장이었다.")
    assert tidy_intro(bio) == "미켈 아르테타 아마트리아인은 스페인의 축구 지도자이다. 그는 (한때) 주장이었다."
    club = "아스널 FC(영어: Arsenal Football Club→아스널 축구단)는 잉글랜드의 축구단이다."
    assert tidy_intro(club) == "아스널 FC는 잉글랜드의 축구단이다."
    # 뜻이 있는 짧은 한글 괄호·빈 값은 그대로
    assert tidy_intro("토트넘 홋스퍼(스퍼스)는 축구단이다.") == "토트넘 홋스퍼(스퍼스)는 축구단이다."
    assert tidy_intro("") == "" and tidy_intro(None) == ""


def test_injury_names_ko(tmp_path, monkeypatch) -> None:
    p = tmp_path / "injury_names_ko.json"
    p.write_text(json.dumps({"Ankle injury": "발목 부상"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(inj, "PATH", p)
    inj._table.cache_clear()
    assert inj.ko("Ankle injury") == "발목 부상"
    assert inj.ko("ankle injury ") == "발목 부상"          # 대소문자·공백 무관
    assert inj.ko("Some new injury") == "Some new injury"   # 모르는 이름은 원문(다음 실행에서 옮김)
    assert inj.ko("부상") == "부상" and inj.ko(None) == ""
    inj._table.cache_clear()


def test_injury_names_file_covers_current_tm_names() -> None:
    """저장본이 지금 TM 부상 표의 이름을 덮는지 — 새 이름은 tm_data 'injury_names' 단계가 채운다."""
    have = json.loads((ROOT / "data" / "injury_names_ko.json").read_text(encoding="utf-8"))
    assert all(inj._HANGUL.search(v) for v in have.values())
    missing = inj.collect() - set(have)
    assert len(missing) <= 20, sorted(missing)[:20]


def test_tm_until_and_news_desc() -> None:
    import api.main as M
    y = datetime.date.today().year
    assert M._tm_until_kr(f"23/10/{y}") == "10/23 복귀 예상"
    assert M._tm_until_kr(f"05/01/{y + 1}") == f"{y + 1}/1/5 복귀 예상"
    assert M._tm_until_kr("") == "" and M._tm_until_kr("12월 초 복귀 예상") == "12월 초 복귀 예상"
    # 라이브 블로그 머리글(| 구분자 둘 이상 · 이모지 시작)은 버리고, 보통 요약은 한글 우선
    assert M._news_desc("⚽ 킥오프 업데이트 | 라이브 스코어 | 순위표", "⚽ Updates | Live scores | Table") == ""
    assert M._news_desc("", "Live scoreboard | Table | Top scorers") == ""
    assert M._news_desc("해리 케인은 아스널을 괴롭힌다.", "Harry Kane ...") == "해리 케인은 아스널을 괴롭힌다."
    assert M._news_desc(None, "Harry Kane keeps scoring.") == "Harry Kane keeps scoring."


def test_injury_returns_deduped(monkeypatch) -> None:
    """TM 목록이 며칠 사이 빠졌다 다시 차면 같은 선수 '부상 복귀'가 여러 번 — 2주 안이면 가장 늦은 한 번만."""
    import pandas as pd
    import api.main as M
    today = datetime.date.today()
    d = lambda n: (today - datetime.timedelta(days=n)).isoformat()   # noqa: E731
    tm = pd.DataFrame([
        {"run_date": d(8), "event_type": "returned", "squad": "Liverpool", "player": "Dominik Szoboszlai", "old_injury": "Thigh problems"},
        {"run_date": d(7), "event_type": "returned", "squad": "Liverpool", "player": "Dominik Szoboszlai", "old_injury": "Thigh problems"},
        {"run_date": d(7), "event_type": "returned", "squad": "Liverpool", "player": "Dominik Szoboszlai", "old_injury": "Thigh problems"},
        {"run_date": d(2), "event_type": "new_injury", "squad": "Liverpool", "player": "Dominik Szoboszlai", "new_injury": "Thigh problems",
         "new_until": ""},
        {"run_date": d(40), "event_type": "returned", "squad": "Liverpool", "player": "Cody Gakpo", "old_injury": "Ankle injury"},
        {"run_date": d(7), "event_type": "returned", "squad": "Liverpool", "player": "Cody Gakpo", "old_injury": "Ankle injury"},
    ])
    monkeypatch.setattr(M.ds, "read_table", lambda name, league=None: tm if name == "transfermarkt_injury_changes" else None)
    monkeypatch.setattr(M, "_news_injury_rows", lambda league, days=7: [])
    ev = M._injury_events("EPL", days=60)
    rets = [(e["player"], e["date"]) for e in ev if e["event"] == "return"]
    assert rets.count(("Dominik Szoboszlai", d(7))) == 1 and len([r for r in rets if r[0] == "Dominik Szoboszlai"]) == 1
    assert len([r for r in rets if r[0] == "Cody Gakpo"]) == 2          # 한 달 넘게 떨어진 복귀는 따로
    assert any(e["event"] == "new" and e["player"] == "Dominik Szoboszlai" for e in ev)
