"""적정 이적료(src/fee_comps.py) — 사례 표 만들기, 배수 학습, 범위·비슷한 이적, 저장본 정확도."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import fee_comps as fc  # noqa: E402


def _synthetic(n: int = 160, seed: int = 3) -> pd.DataFrame:
    """EPL 구단은 시장가치의 1.4배, 그 외 1.0배, 21세 이하 ×1.2 를 내는 가짜 이적 기록(잡음 ±25%)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        buyer = "EPL" if i % 3 == 0 else ("LaLiga" if i % 3 == 1 else None)
        age = int(rng.integers(18, 33))
        mv = float(rng.choice([5, 10, 20, 40])) * 1e6
        mult = (1.4 if buyer == "EPL" else 1.0) * (1.2 if age <= 21 else 1.0) * math.exp(rng.normal(0, 0.25))
        rows.append({"norm_key": f"p{i}", "player": f"Player {i}", "season_id": 2026, "window": "summer", "fee_eur": mv * mult,
                     "pos": "Centre-Back" if i % 2 else "Left Winger", "pg": "CB" if i % 2 else "W", "line": 1 if i % 2 else 3,
                     "age": age, "seller": f"Club {i}", "buyer": f"Buyer {i}", "buyer_lg": buyer, "seller_lg": "SerieA",
                     "ovr": 70 + (mv / 1e6) / 4 + rng.normal(0, 2), "mv_eur": mv, "photo": ""})
    return pd.DataFrame(rows)


def test_fit_learns_buyer_and_age_multipliers() -> None:
    m = fc.fit(_synthetic())
    epl = math.exp(m["base"] + m["buyer"]["EPL"])
    other = math.exp(m["base"] + m["buyer"]["other"])
    assert 1.2 < epl < 1.6 and 0.8 < other < 1.15            # 줄임(shrink) 때문에 참값(1.4·1.0)보다 조금 안쪽
    assert math.exp(m["age"]["21세 이하"]) > math.exp(m["age"]["27~30세"])
    a = m["acc"]
    assert a["med_err"] < a["mv_only_err"]                   # 배수가 시장가치 하나보다 잘 맞아야
    assert 0.35 <= a["in50"] <= 0.65 and a["in80"] >= 0.65   # 범위 = 하나 빼고 맞힌 잔차의 분위수
    assert m["q"]["q10"] < m["q"]["q25"] < 0 < m["q"]["q75"] < m["q"]["q90"]
    assert m["ovr_reg"]["acc"]["n"] == 160


def test_price_range_and_fallback() -> None:
    m = fc.fit(_synthetic())
    p = fc.price(20e6, 25, "EPL", model=m)
    assert p["basis"] == "mv" and p["lo80"] <= p["lo"] < p["mid"] < p["hi"] <= p["hi80"]
    q = fc.price(20e6, 25, "LaLiga", model=m)
    assert q["mid"] < p["mid"]                                # EPL 구단이 살 때 더 비싸다
    anyb = fc.price(20e6, 25, None, model=m)
    assert anyb["buyer_known"] is False and anyb["factors"][0]["label"].startswith("사는 구단 미정")
    est = fc.price(None, 24, "EPL", ovr=80, pg="CB", seller_lg="SerieA", model=m)
    assert est and est["basis"] == "ovr" and est["lo"] < est["mid"] < est["hi"]
    assert fc.price(None, 24, "EPL", model=m) is None          # 시장가치·OVR 둘 다 없으면 값 없음
    assert fc._round_eur(36_400_000) == 36_000_000 and fc._round_eur(4_440_000) == 4_400_000


def test_comparables_same_line_nearest_and_not_self() -> None:
    t = _synthetic()
    me = t.iloc[1]                                           # 센터백
    out = fc.comparables(me["norm_key"], me["age"], me["ovr"], "Centre-Back", "SerieA", "EPL", table=t)
    assert len(out) == 5
    assert all(c["player"] != me["player"] for c in out)
    lines = t.set_index("player")["line"]
    assert all(lines[c["player"]] == 1 for c in out)         # 같은 라인(수비)만
    assert out == sorted(out, key=lambda c: c["dist"])
    assert all(c["ratio"] is not None and c["when"] == "26 여름" for c in out)
    assert fc.pos_group("LW") == "W" and fc.pos_group("ST") == "CF" and fc.pos_group("Goalkeeper") == "GK"


def test_build_table_dedupes_and_picks_pre_transfer_value(tmp_path) -> None:
    cols = ["squad", "season_id", "window", "direction", "player", "norm_key", "pos", "age", "nat", "club", "fee_eur", "fee_text", "photo"]
    rows = [
        # 같은 이적이 산 리그(EPL in)·판 리그(SerieA out)에 둘 다 — 한 줄로, 사는/판 리그 둘 다 채움
        ["Arsenal", 2026, "summer", "in", "A One", "a one", "Centre-Back", 24, "Italy", "Roma", 30e6, "€30.00m", ""],
        ["Roma", 2026, "summer", "out", "A One", "a one", "Centre-Back", 24, "Italy", "Arsenal", 30e6, "€30.00m", ""],
        ["Arsenal", 2026, "summer", "in", "B Two", "b two", "Left Winger", 20, "Spain", "Sevilla", 3e6, "Loan fee:€3.00m", ""],  # 임대 제외
        ["Arsenal", 2026, "summer", "in", "C Three", "c three", "Goalkeeper", 30, "Spain", "Getafe", 300_000, "€300k", ""],   # €0.5M 미만 제외
    ]
    pd.DataFrame([r[:12] + [r[12]] for r in rows], columns=cols).iloc[[0, 2, 3]].to_csv(tmp_path / "transfers_2026_2027.csv", index=False)
    pd.DataFrame([rows[1]], columns=cols).to_csv(tmp_path / "transfers_SerieA_2026_2027.csv", index=False)
    frames = {"2025_2026": pd.DataFrame([{"norm_key": "a one", "squad": "Roma", "league": "SerieA", "ovr": 82, "market_value_eur": 25e6, "minutes": 2500}]),
              "2026_2027": pd.DataFrame([{"norm_key": "a one", "squad": "Arsenal", "league": "EPL", "ovr": 84, "market_value_eur": 30e6, "minutes": 600}])}
    t = fc.build_table(tmp_path, frames)
    assert len(t) == 1
    r = t.iloc[0]
    assert r["buyer_lg"] == "EPL" and r["seller_lg"] == "SerieA"
    assert r["ovr"] == 82 and r["ovr_season"] == "2025_2026"   # 여름 2026 이적 → 25/26 시즌(이적 직전)
    assert r["mv_eur"] == 25e6                                  # 이적 뒤(30M)가 아니라 판 구단 시절 값


def test_saved_model_is_sane() -> None:
    """저장본(data/fee_model.json) — 매일 daily_data 가 다시 만든다. 정확도가 시장가치 하나보다 나쁘면 실패."""
    m = json.loads((ROOT / "data" / "fee_model.json").read_text(encoding="utf-8"))
    a = m["acc"]
    assert a["med_err"] <= a["mv_only_err"] + 0.02 and a["med_err"] < 0.45
    assert 0.35 <= a["in50"] <= 0.65
    assert m["n_mv"] >= 40


def test_comparables_json_safe() -> None:
    """CSV 빈 칸(NaN)이 응답에 섞이면 JSON 직렬화가 500 을 낸다(2026-10-23 리포트 QA)."""
    t = _synthetic()
    t.loc[:, "pos"] = np.nan
    t.loc[:, "seller_lg"] = np.nan
    me = t.iloc[1]
    out = fc.comparables(me["norm_key"], me["age"], me["ovr"], "CB", None, "EPL", table=t)
    json.dumps(out, allow_nan=False)
    assert all(c["pos"] == "" and c["from_lg"] == "" for c in out)
