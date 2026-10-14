"""팀 이름 맞추기(외부 예측 출처 → 우리 표기) — 오매칭이 화면 예측을 엉뚱한 경기에 붙이지 않게."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import team_names  # noqa: E402


def test_common_aliases_match():
    for src, ours in [("FC Bayern München", "Bayern Munich"), ("Liverpool FC", "Liverpool"), ("Manchester United", "Manchester Utd"),
                      ("Paris Saint-Germain", "PSG"), ("Borussia Dortmund", "Dortmund"), ("Man City", "Manchester City")]:
        assert team_names.score(src, ours) >= 0.9, (src, ours)


def test_similar_names_stay_apart():
    assert team_names.best("Paris FC", ["PSG", "Paris FC", "Lyon"]) == "Paris FC"
    assert team_names.best("Manchester City", ["Manchester Utd", "Manchester City"]) == "Manchester City"
    assert team_names.best("Newcastle United", ["Manchester Utd", "Newcastle United"]) == "Newcastle United"
    assert team_names.best("Totally Unknown", ["Arsenal", "Chelsea"]) is None
