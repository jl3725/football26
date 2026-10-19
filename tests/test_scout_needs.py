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


def test_fit_and_manager_sim_work_without_qdrant(monkeypatch) -> None:
    """적합도 평가·감독 시뮬레이션 — Qdrant 없이(서버 메모리 벡터). 예전엔 운영 서버에서 available=False 였다."""
    import transfer_fit as tf
    from api import main as m

    def no_qdrant():
        raise RuntimeError("Qdrant 없음")
    monkeypatch.setattr(tf, "_qdrant", no_qdrant)
    pool = tf._pool()
    lw = pool[(pool["_pos_detail"] == "Left Winger") & (pool["_min"] >= 300)].sort_values("_ovr", ascending=False)
    cand = str(lw.iloc[0]["player"])
    club = str(pool[pool["_league"] == "EPL"]["squad"].iloc[0])
    r = m.fit(cand, club, "Left Winger", str(lw.iloc[0]["_league"]))
    assert r["available"] is True and not r.get("error"), r
    s = m.managersim(club, club)
    assert s["available"] is True and not s.get("error"), s


def test_cross_league_projection_no_double_discount() -> None:
    """OVR 은 이미 리그 수준을 담은 절대 척도 — 리그 이동 환산은 작은 적응 할인만(크바라 87 → 80 같은 이중 할인 금지).
    2026-10-19 검증: 리그를 옮긴 41명 실제 변화 +1.4 vs 예전 환산 −2.2."""
    from api.main import _project_ovr
    assert _project_ovr(87, "Ligue1", "EPL", True, 25, "LW")[0] >= 86
    assert _project_ovr(80, "BelgianProLeague", "EPL", False, 24, "LW")[0] >= 78
    assert _project_ovr(85, "EPL", "LaLiga", False, 26, "CB")[0] == 85          # 약한 리그로 가도 부풀리지 않음
    assert _project_ovr(85, "LaLiga", "EPL", False, 31, "CM")[0] == 84          # 30세+ 적응 −1


def test_similar_players_same_position() -> None:
    """유사 선수는 실제 포지션 기준 — 사카(RW) 유사 1위가 만잠비(AM)였다(2026-10-19 사용자)."""
    from api import main as m
    df, _ = m._sim_engine()
    wing = df[df["tm_position"].astype(str).str.contains("Right Winger")]
    if wing.empty:
        return
    res = m.similar(str(wing.iloc[0]["player"]))["results"]
    assert res and all(x["pos"] in ("RW", "LW") for x in res), res


def test_fit_defaults_to_natural_position() -> None:
    """적합도 평가 — 역할을 비우면 후보의 본 포지션(크바라츠헬리아 LW 를 CM 으로 평가하던 문제, 2026-10-19)."""
    import transfer_fit as tf
    from api import main as m
    pool = tf._pool()
    lw = pool[(pool["_pos_detail"] == "Left Winger") & (pool["_min"] >= 300)].sort_values("_ovr", ascending=False)
    cand = str(lw.iloc[0]["player"])
    club = str(pool[pool["_league"] == "EPL"]["squad"].iloc[0])
    r = m.fit(cand, club)
    assert r["role"] == "Left Winger" and r["natural_role"] == "Left Winger" and not r["role_note"]
    r2 = m.fit(cand, club, "Central Midfield")
    assert r2["role"] == "Central Midfield" and r2["role_note"]
