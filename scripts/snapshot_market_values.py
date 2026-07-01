"""
시장가치 변동 추적 agent — 매일 선수 시장가치 스냅샷을 남기고 직전 스냅샷과 diff.

동작
----
1. players_full(datastore)에서 (squad, player, tm_id, market_value_eur) 스냅샷을 뜬다.
2. data/market_value_history.csv 에 오늘 날짜로 append (같은 날 재실행은 멱등 — 스킵).
3. 직전 스냅샷 날짜와 비교해 변동분을 data/market_value_changes_2025_2026.csv 로 기록.
   → build_db 가 market_value_changes 테이블로 싣고, /api/signals 가 급등/급락 신호로 노출.

첫 실행은 baseline 만 생성(비교 대상 없음). 값은 TM 동기화(fetch_transfermarkt)로 갱신될 때
변한다 — 즉 이 agent 는 그 변화를 델타로 포착하는 역할.

    python scripts/snapshot_market_values.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import datastore as ds  # noqa: E402
from leagues import DATA_DIR, SEASON  # noqa: E402

HISTORY = DATA_DIR / "market_value_history.csv"
CHANGES = DATA_DIR / f"market_value_changes_{SEASON}.csv"
MIN_DELTA_EUR = 1_000_000     # 100만 유로 미만 변동은 노이즈로 무시
MIN_DELTA_PCT = 8.0           # 또는 8% 이상


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def snapshot() -> None:
    full = ds.read_table("players_full")
    if full is None or full.empty:
        print("! players_full 없음 — 중단")
        return
    cols = [c for c in ["squad", "player", "tm_id", "market_value_eur"] if c in full.columns]
    snap = full[cols].copy()
    snap["market_value_eur"] = pd.to_numeric(snap["market_value_eur"], errors="coerce")
    snap = snap.dropna(subset=["market_value_eur"])
    today = _today()
    snap.insert(0, "date", today)

    if HISTORY.exists():
        hist = pd.read_csv(HISTORY)
        if today in set(hist["date"].astype(str)):
            print(f"= {today} 스냅샷 이미 존재 — append 스킵")
        else:
            hist = pd.concat([hist, snap], ignore_index=True)
            hist.to_csv(HISTORY, index=False)
            print(f"+ {today} 스냅샷 추가 ({len(snap)} 선수)")
    else:
        snap.to_csv(HISTORY, index=False)
        hist = snap
        print(f"+ baseline 생성 ({len(snap)} 선수)")

    # 직전 스냅샷과 비교
    dates = sorted(hist["date"].astype(str).unique())
    if len(dates) < 2:
        print("· 비교 대상 스냅샷 없음(첫 실행) — 변동 기록 생략")
        # 빈 changes 파일 생성(스키마 유지)
        pd.DataFrame(columns=["run_date", "squad", "player", "old_value", "new_value",
                              "delta", "pct"]).to_csv(CHANGES, index=False)
        return

    prev, cur = dates[-2], dates[-1]
    a = hist[hist["date"] == prev][["player", "squad", "market_value_eur"]].rename(columns={"market_value_eur": "old_value"})
    b = hist[hist["date"] == cur][["player", "squad", "market_value_eur"]].rename(columns={"market_value_eur": "new_value"})
    m = a.merge(b, on=["player", "squad"], how="inner")
    m["delta"] = m["new_value"] - m["old_value"]
    m["pct"] = (m["delta"] / m["old_value"].replace(0, pd.NA) * 100).round(1)
    changed = m[(m["delta"].abs() >= MIN_DELTA_EUR) | (m["pct"].abs() >= MIN_DELTA_PCT)].copy()
    changed.insert(0, "run_date", cur)
    changed = changed.sort_values("delta", key=lambda s: s.abs(), ascending=False)
    changed.to_csv(CHANGES, index=False)
    print(f"✓ 변동 {len(changed)}건 기록 ({prev} → {cur})")


if __name__ == "__main__":
    snapshot()
