from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

import predict_model as pm
import team_elo as te

ROOT = Path(__file__).resolve().parents[1]


def test_team_elo_updates_and_promoted_start_lower() -> None:
    sch = pd.DataFrame([
        ["A", "eng.1", "2025-08-10", "H", "B", 3, 0, "completed", "1"],
        ["B", "eng.1", "2025-08-10", "A", "A", 0, 3, "completed", "1"],
        ["C", "eng.1", "2026-08-15", "H", "A", 1, 1, "completed", "2"],     # 다음 시즌 처음 보는 팀 = 승격팀
    ], columns=["squad", "comp_code", "date", "home_away", "opponent", "gf", "ga", "status", "event_id"])
    ms = te.matches_from({"EPL": sch})
    assert len(ms) == 2 and ms.iloc[0]["home"] == "A" and ms.iloc[0]["hg"] == 3
    elo, snaps = te.run(ms, {"EPL": te.league_base(100.0)}, {"2026-08-15"})
    assert elo["A"] > te.league_base(100.0) > elo["B"]                       # 이긴 팀 오르고 진 팀 내림
    assert snaps["2026-08-15"]["A"] > snaps["2026-08-15"]["B"] and "C" not in snaps["2026-08-15"]
    assert elo["C"] < te.league_base(100.0)                                  # 승격팀은 리그 기본값보다 낮게 시작


def test_v3_inputs_move_probabilities() -> None:
    mt = pd.DataFrame([{"event_id": str(i), "date": f"2026-09-{i + 1:02d}", "home": h, "away": a, "hg": hg, "ag": ag,
                        "hxg": float("nan"), "axg": float("nan"), "hsh": float("nan"), "ash": float("nan")}
                       for i, (h, a, hg, ag) in enumerate([("X", "Y", 1, 1), ("Y", "X", 1, 1), ("X", "Y", 1, 1)])])
    st = pm.build_state(mt, {"X": 80, "Y": 80}, asof="2026-09-10")
    base = pm.predict(st, "X", None, "Y", {**pm.PARAMS, "b_elo": 0, "b_av": 0})
    elo = pm.predict(st, "X", None, "Y", extra={"elo_d": 150.0})
    hurt = pm.predict(st, "X", None, "Y", extra={"miss_h": 3.0, "miss_a": 0.0})
    assert elo["h"] > base["h"] and elo["a"] < base["a"]                      # Elo 가 높은 홈팀 쪽으로
    assert hurt["h"] < base["h"]                                              # 홈 결장 손실 → 홈 승 확률 내려감
    assert hurt["inputs"]["miss_h"] == 3.0


def test_fotmob_return_labels() -> None:
    from api.main import _fm_return_kr
    assert _fm_return_kr("Early December 2026") == "12월 초 복귀 예상"
    assert _fm_return_kr("Late October 2026") == "10월 말 복귀 예상"
    assert _fm_return_kr("Doubtful") == "출전 불투명"
    assert _fm_return_kr("About 1-2 weeks") == "약 1~2주"


def test_ovr_same_on_every_screen_for_one_team() -> None:
    """OVR 검증 에이전트(scripts/check_ovr_consistency.py)를 한 팀에 — 화면마다 같은 OVR(하베르츠 83 vs 84 재발 방지)."""
    spec = importlib.util.spec_from_file_location("chk", ROOT / "scripts" / "check_ovr_consistency.py")
    chk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chk)
    from api import main as m
    pf = m._pf("EPL")
    team = str(pf.sort_values("_ovr", ascending=False)["squad"].iloc[0])
    truth = {str(p): int(o) for p, o in zip(pf[pf["squad"] == team]["player"], pf[pf["squad"] == team]["_ovr"])}
    src = chk.team_sources(m, team, "EPL", [], list(truth)[:2])
    bad = [(name, p, v, truth[p]) for name, vals in src.items() for p, v in vals.items() if p in truth and v != truth[p]]
    assert src and not bad, bad
