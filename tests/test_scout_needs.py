from __future__ import annotations

import datetime as dt


def test_weeks_out_parses_tm_and_fotmob_labels() -> None:
    from api.main import _weeks_out
    today = dt.date(2026, 10, 19)
    assert abs(_weeks_out("02/11/2026", today) - 2.0) < 0.01               # TM dd/mm/yyyy
    assert 6 < _weeks_out("12월 초 복귀 예상", today) < 8                     # FotMob 한국어 변환값
    assert _weeks_out("약 1~2주", today) == 1.5
    assert _weeks_out("출전 불투명", today) == 0.5
    assert _weeks_out("시즌 아웃", today) == 30.0
    assert _weeks_out("", today) == 4.0                                      # 모르면 4주


def test_policy_fit_flags_age_and_fee() -> None:
    from api.main import _policy_fit
    pol = {"age_lo": 23, "age_hi": 28, "fee_max": 87.5e6}
    assert _policy_fit(pol, 25, 50e6)["ok"] is True
    bad = _policy_fit(pol, 32, 120e6)
    assert bad["ok"] is False and len(bad["notes"]) == 2
    assert _policy_fit(None, 25, 50e6)["ok"] is None


def test_position_needs_shape() -> None:
    """포지션 니즈 v2 — 10개 포지션, 시급도 0~100 내림차순, 이유·뎁스·이번 창 이동이 붙는다."""
    from api import main as m
    pf = m._pf("EPL")
    team = str(pf.sort_values("_ovr", ascending=False)["squad"].iloc[0])
    r = m._position_needs(team, "EPL")
    roles = r["roles"]
    assert len(roles) == 10 and r["team_ovr"]
    assert all(0 <= x["urgency"] <= 100 for x in roles)
    assert [x["urgency"] for x in roles] == sorted((x["urgency"] for x in roles), reverse=True)
    for x in roles:
        assert x["level"] in ("urgent", "need", "watch", "ok") and x["when"] in ("1월 창", "여름 창")
        assert set(x["window"]) >= {"in", "out", "verdict"}
        if x["urgency"] >= 15:
            assert x["reasons"]


def test_local_style_search_same_position_sorted() -> None:
    """리크루트 풀 스타일 검색(서버 메모리, Qdrant 없이) — 같은 세부 포지션만, 유사도 높은 순."""
    import transfer_fit as tf
    vec = tf._local_elite("Left Winger")
    hits = tf._local_search(vec, "Left Winger", limit=50)
    pool = tf._pool()
    assert len(hits) >= 20
    assert all(pool.loc[i, "_pos_detail"] == "Left Winger" for i, _ in hits)
    sims = [s for _, s in hits]
    assert sims == sorted(sims, reverse=True)
