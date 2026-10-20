"""2026-10-20 대시보드 점검 P0-B — 이름·팀 매칭이 다시 깨지지 않게(실제 데이터로)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import squads as sq  # noqa: E402


def test_reserve_parent_resolution() -> None:
    clubs = ["Club Brugge", "Barcelona", "Real Madrid", "Arsenal", "Dortmund", "Gent", "PSG", "Juventus", "Willem II"]
    assert sq.is_own_reserve("Club NXT", "Club Brugge", clubs)
    assert sq.is_own_reserve("Barça Atlètic", "Barcelona", clubs)
    assert sq.is_own_reserve("RM Castilla", "Real Madrid", clubs)
    assert sq.is_own_reserve("Arsenal U21", "Arsenal", clubs)
    assert sq.is_own_reserve("B. Dortmund II", "Dortmund", clubs)
    assert sq.is_own_reserve("Jong KAA Gent", "Gent", clubs)
    assert not sq.is_own_reserve("Club NXT", "Barcelona", clubs)      # 브뤼헤 2군 → 바르사 = 진짜 이적(Bisiwu €8.5m)
    assert not sq.is_own_reserve("Paris SG U19", "Club Brugge", clubs)
    assert not sq.is_own_reserve("Willem II", "Arsenal", clubs)       # 'II' 로 끝나는 실제 클럽


def test_transfers_exclude_own_reserve_promotions() -> None:
    from api.main import transfers
    r = transfers("Barcelona", "LaLiga")
    ins, outs = {x["player"] for x in r["in"]}, {x["player"] for x in r["out"]}
    assert not any("Atlètic" in x["club"] for x in r["in"])
    assert not (ins & outs)                                           # 승격 후 판 선수가 IN·OUT 양쪽에 있던 것


def test_cross_league_opponent_linked() -> None:
    """다른 리그 상대(ESPN 'Paris Saint-Germain')가 우리 표기·리그로 이어져 순위·모델이 붙는다."""
    import match_center as mc
    from api.main import _fx_sources
    ids = mc.espn_id_names(_fx_sources()["rows"])
    assert len(ids) >= 100
    name, lg = mc.our_opponent("Paris Saint-Germain", "https://a.espncdn.com/i/teamlogos/soccer/500/160.png", ids)
    assert (name, lg) == ("PSG", "Ligue1")


def test_signing_audit_matches_reordered_names() -> None:
    from api.main import _signing_audit
    from api.services.player_data import player_frame
    a = {x["player"]: x for x in _signing_audit("Club Brugge", "BelgianProLeague", player_frame("BelgianProLeague"))}
    if "Han-beom Lee" in a:                                           # 스쿼드 표기 'Lee Han-beom'
        assert a["Han-beom Lee"]["minutes"] > 0
