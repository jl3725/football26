"""SCOUT TAKE(src/scout_take.py) — 사실·관점 고르기, AI 문장 검증, 화면용 응답(규칙 문장 없음).

2026-10-27 사용자: 팬이 주 사용자·고급 스카우트 느낌, '룰베이스는 싫다', '명사체로'.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import scout_take as st  # noqa: E402


def payload(**kw) -> dict:
    p = {"player": "Matheus Cunha", "team": "Manchester Utd", "line": "ATT", "ovr": 86, "form": 78, "age": 27,
         "ss_rating": 6.81, "goals": 1, "assists": 2, "minutes": 550, "value_eur": 75e6,
         "template": {"ko": "스트라이커", "enough": True},
         "recent": {"score": 84}, "ratings": {"prev_blend": 7.12},
         "ovr_parts": [{"key": "base", "value": 86.5}, {"key": "slump", "value": -0.9}],
         "comp_usage": {"role": "핵심 주전", "role_evidence": "리그 550′ · 챔피언스리그 2선발",
                        "comps": [{"key": "ucl", "starts": 2}], "injury_missed": 0},
         "radar_line": [{"axis": "창조", "value": 79}, {"axis": "피지컬·듀얼", "value": 18}, {"axis": "공격", "value": 45}],
         "badges": [{"label": "태클", "rank": 3}],
         "season_log": {"matches": [{"comp": "리그", "minutes": 90}] * 7 + [{"comp": "리그", "minutes": 0}]}}
    p.update(kw)
    return p


def test_facts_and_scene_from_screen_values():
    f = st.facts(payload(), team_rank=16, n_teams=20)
    assert f["OVR_등급"] == "엘리트" and f["이번시즌_폼_뜻"] == "보통" and f["리그_출전경기"] == 7
    assert f["몸값_백만유로"] == 75 and f["이번시즌_부진으로_OVR에서_뺀_점수"] == -0.9 and f["유럽대항전_선발"] == 2
    assert f["강점"] == ["창조 상위 21%", "태클 리그 3위"] and f["약점"] == ["피지컬·듀얼 하위 18%"]
    assert "정상급" in f["허용_표현"] and "1위" not in f["허용_표현"]
    assert st.scene(f) == "class_slump"
    # 부상으로 출전이 적으면 '로테이션'이 아니라 부상 관점(팀버·기마랑이스 2026-10-27)
    inj = st.facts(payload(minutes=156, comp_usage={"role": "로테이션", "comps": [], "injury_missed": 3}))
    assert st.scene(inj) == "injury_return"
    # 리그 출전이 적어도 유럽대항전 선발이 있으면 벤치 시작(에제)
    eze = st.facts(payload(minutes=210, comp_usage={"role": "주전·유럽 로테이션", "comps": [{"key": "ucl", "starts": 2}]}))
    assert st.scene(eze) == "bench_start"


def test_check_rejects_made_up_numbers_endings_leaks_and_wrong_direction():
    f = st.facts(payload(), team_rank=16, n_teams=20)
    good = {"l1": "이름값에 비해 아쉬운 스트라이커의 올 시즌", "l2": "평점 6.81 — 리그 1골 2도움, 몸값(€75M)에 못 미치는 활약"}
    assert st.check(good, f) == []
    assert any("숫자" in b or b == "9" for b in st.check({"l1": good["l1"], "l2": "리그 9골 — 득점 선두"}, f)) or \
        "9" in st.check({"l1": good["l1"], "l2": "리그 9골 — 득점 선두"}, f)
    assert any("끝" in b for b in st.check({"l1": "올 시즌은 아쉬운 활약을 보이고 있다", "l2": good["l2"]}, f))
    assert any("사실 이름" in b for b in st.check({"l1": good["l1"], "l2": "리그 골 1 — 아쉬움"}, f))
    assert any("이번시즌" in b for b in st.check({"l1": "이번시즌 폼 보통의 스트라이커", "l2": good["l2"]}, f))
    assert any("근거 없는" in b for b in st.check({"l1": "리그 최고의 스트라이커", "l2": good["l2"]}, f))
    hot = st.facts(payload(form=94))
    assert any("부정" in b for b in st.check({"l1": "이름값에 비해 아쉬운 시즌", "l2": "평점 6.81 — 1골 2도움"}, hot))
    assert any("상투적" in b for b in st.check({"l1": "리그 정상급 스트라이커의 시즌", "l2": "평점 6.81 — 1골 2도움"}, hot))


def test_pick_prefers_ai_order_and_skips_failures():
    f = st.facts(payload())
    cands = [{"l1": "올 시즌은 아쉬운 활약을 보이고 있다", "l2": "평점 6.81"},          # '~다' 끝 — 탈락
             {"l1": "이름값에 비해 아쉬운 스트라이커의 올 시즌", "l2": "평점 6.81 — 1골 2도움"},
             {"l1": "아쉬운 시즌", "l2": "평점 6.81"}]
    assert st._pick(cands, f)["l1"] == "이름값에 비해 아쉬운 스트라이커의 올 시즌"
    assert st._pick([{"l1": "올 시즌은 아쉬운 활약을 보이고 있다", "l2": "x"}], f) is None


def test_for_payload_shows_only_verified_ai_text_never_rules(tmp_path, monkeypatch):
    out = tmp_path / "scout_takes.json"
    monkeypatch.setattr(st, "OUT", out)
    monkeypatch.setattr(st, "_TAKES_CACHE", {})
    p = payload()
    none = st.for_payload(p, "EPL", 16, 20)
    assert "l1" not in none and none["strengths"]                        # 저장된 AI 문장이 없으면 칩만(규칙 문장 없음)
    k = st.key_of("EPL", "Manchester Utd", "Matheus Cunha")
    takes = {k: {"l1": "이름값에 비해 아쉬운 스트라이커의 올 시즌", "l2": "평점 6.81 — 리그 1골 2도움", "at": "2026-10-27T07:00:00+00:00"}}
    out.write_text(json.dumps({"takes": takes}, ensure_ascii=False), encoding="utf-8")
    hit = st.for_payload(p, "EPL", 16, 20)
    assert hit["l1"].startswith("이름값") and hit["l2"].startswith("평점 6.81") and hit["src"] == "ai"
    # 숫자가 낡은 근거 줄(골이 늘었다)은 빼고 평가 줄만
    stale = st.for_payload(payload(goals=3, ss_rating=6.95), "EPL", 16, 20)
    assert stale.get("l1") and "l2" not in stale
