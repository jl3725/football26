"""루머 기록 보관(2026-11-09 사용자 '뉴스가 지워지면 예전 루머가 날아가지 않나') — 주장 이어받기·이적설 이력·벡터 보관 기간."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import news_reliability as nr  # noqa: E402
import news_vectors as nv  # noqa: E402
import rumor_map as rm  # noqa: E402


def test_carry_keeps_claims_of_deleted_articles_and_rejudges(monkeypatch) -> None:
    old = pd.DataFrame([
        # 원문이 지워진 기사 — 그 시장에 실제로 옮김 → pending 이었던 게 hit 로
        {"link": "gone1", "date": "2026-07-10", "source": "Sky", "journalists": "", "stage": "talks", "player": "Ethan Nwaneri",
         "origin": "Arsenal", "dest": "Dortmund", "window": "2026 summer", "status": "pending", "headline": "h"},
        # 원문이 지워진 기사 — 시장이 닫혔는데 안 옮김 → miss
        {"link": "gone2", "date": "2026-07-12", "source": "Sky", "journalists": "", "stage": "interest", "player": "Bukayo Saka",
         "origin": "Arsenal", "dest": "Real Madrid", "window": "2026 summer", "status": "pending", "headline": "h"},
        # 원문이 남은 기사 — 여기서 빼고 claims() 가 새로 뽑는다
        {"link": "alive", "date": "2026-11-01", "source": "BBC", "journalists": "", "stage": "talks", "player": "X",
         "origin": "A", "dest": "B", "window": "2026 winter", "status": "pending", "headline": "h"},
    ])
    tr = pd.DataFrame([{"player": "Ethan Nwaneri", "season_id": 2026, "window": "summer", "direction": "in",
                        "squad": "Dortmund", "club": "Arsenal"}])
    monkeypatch.setattr(nr, "load_transfers", lambda: tr)
    out = nr.carry(old, {"alive"}, dt.date(2026, 11, 9)).set_index("link")
    assert list(out.index) == ["gone1", "gone2"]
    assert out.loc["gone1", "status"] == "hit" and out.loc["gone2", "status"] == "miss"


def test_rumor_history_accumulates_and_keeps_cooled_links(tmp_path) -> None:
    p = tmp_path / "rumor_history.csv"
    rm.update_history([{"pid": "tm:1", "name": "Bukayo Saka", "to": "Real Madrid", "heat": 40, "stage": "interest", "prob": 20,
                        "news": 2, "outlets": ["BBC"], "last": "2026-10-30"}], dt.date(2026, 11, 1), p)
    rm.update_history([{"pid": "tm:1", "name": "Bukayo Saka", "to": "Real Madrid", "heat": 25, "stage": "talks", "prob": None,
                        "news": 3, "outlets": ["Marca"], "last": "2026-11-05"}], dt.date(2026, 11, 6), p)
    h = rm.update_history([], dt.date(2026, 11, 20), p)                      # TM·기사에서 사라져도
    assert len(h) == 1
    x = h[0]
    assert (x["window"], x["first"], x["peak_heat"], x["max_stage"], x["outlets"], x["active"]) == \
        ("2026 winter", "2026-11-01", "40", "talks", "BBC|Marca", "0")


def test_news_vectors_keep_transfer_articles_longer(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(nv, "_q", lambda m, path, body=None, timeout=30: sent.append(body))
    nv.prune(45, 400)
    first, second = sent
    assert first["filter"]["must_not"] == [{"key": "kind", "match": {"value": "transfer"}}]   # 이적 기사 빼고 45일
    assert second["filter"]["must"][0]["range"]["lt"] < first["filter"]["must"][0]["range"]["lt"]   # 이적 기사는 400일
