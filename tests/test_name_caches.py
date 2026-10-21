"""이름 정규화·클럽 매칭 결과 기억(lru_cache, 2026-10-22 성능 점검) — 기억 전과 같은 답."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import player_registry as pr  # noqa: E402
import positions as ps  # noqa: E402
import team_names as tn  # noqa: E402


def test_norm_same_answers() -> None:
    assert tn.norm("FC Barcelona") == tn.norm("Barcelona") == "barcelona"      # 접두어(FC) 떼기
    assert tn.norm(None) == "" and tn.norm("") == ""
    assert pr.norm("Martin Ødegaard") == "martin odegaard" and pr.norm(None) == ""
    assert ps.norm_name("Jean-Philippe Mateta") == "jean philippe mateta" and ps.norm_name(float("nan")) == "nan"


def test_best_list_tuple_generator_agree() -> None:
    clubs = ["Manchester City", "Manchester United", "Real Madrid", "Barcelona", "Espanyol"]
    for name in ("Man City", "Manchester Utd", "RCD Espanyol Barcelona", "Real Madrid B", "Nowhere FC"):
        a = tn.best(name, clubs)
        assert a == tn.best(name, tuple(clubs)) == tn.best(name, (c for c in clubs))
    assert tn.best("Real Madrid B", clubs) is None          # 2군은 1군과 다른 팀(기억해도 같은 규칙)
    assert tn.best("Manchester United", clubs) == "Manchester United"
