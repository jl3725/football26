"""
대회별 선수 사용량 수집기 — Role-aware Recruitment.

ESPN 대회별 라인업(summary.rosters[].roster[].starter / subbedIn)에서 선수별 대회별
**선발/출전 수**를 집계한다. 리그 minutes 는 능력치(OVR), 이 데이터는 '역할' 축 전용.

대회: 유럽(UCL/UEL/컨퍼런스, 공통) + 국내컵(EPL: FA·EFL / LaLiga: 코파델레이)
저장: data/player_comp_usage[_LaLiga]_2025_2026.csv

사용:
    python src/fetch_comp_usage.py                 # EPL
    python src/fetch_comp_usage.py --league LaLiga
    python src/fetch_comp_usage.py --dry
"""
from __future__ import annotations

import sys
import time

import pandas as pd
import requests
from unidecode import unidecode

from espn_common import EURO_COMPS, DOMESTIC_CUPS, squad_of
from leagues import data_path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

SEASON_RANGE = "20250701-20260630"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def norm(name: str) -> str:
    return unidecode(str(name or "")).lower().strip()


def _get(url: str, tries: int = 3) -> dict | None:
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.ok:
                return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"    [재시도 {i+1}] {e}")
        time.sleep(0.7)
    return None


def season_events(code: str, league: str) -> list[str]:
    data = _get(f"{BASE}/{code}/scoreboard?dates={SEASON_RANGE}&limit=500")
    out = []
    for e in (data or {}).get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed"):
            continue
        if any(squad_of(c.get("team", {}), league) for c in comp.get("competitors", [])):
            out.append(e.get("id"))
    return [x for x in out if x]


def collect_comp(code: str, league: str) -> dict[tuple, dict]:
    eids = season_events(code, league)
    print(f"  [{code}] 관련 완료경기 {len(eids)}개 — 라인업 수집…")
    acc: dict[tuple, dict] = {}
    for i, eid in enumerate(eids):
        s = _get(f"{BASE}/{code}/summary?event={eid}")
        for r in (s or {}).get("rosters", []):
            squad = squad_of(r.get("team", {}), league)
            if not squad:
                continue
            for p in r.get("roster", []):
                disp = (p.get("athlete", {}) or {}).get("displayName") or ""
                nk = norm(disp)
                if not nk:
                    continue
                started = bool(p.get("starter"))
                if not (started or p.get("subbedIn")):
                    continue
                cell = acc.setdefault((squad, nk), {"player": disp, "starts": 0, "apps": 0})
                cell["starts"] += 1 if started else 0
                cell["apps"] += 1
        time.sleep(0.12)
        if (i + 1) % 30 == 0:
            print(f"    {i+1}/{len(eids)} · 누적 선수 {len(acc)}")
    return acc


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    league = "EPL"
    if "--league" in args:
        league = args[args.index("--league") + 1]

    comps = list(EURO_COMPS) + list(DOMESTIC_CUPS.get(league, []))  # (code, label, key)
    euro_keys = [k for _, _, k in EURO_COMPS]
    cup_keys = [k for _, _, k in DOMESTIC_CUPS.get(league, [])]

    rows: dict[tuple, dict] = {}
    for code, _label, key in comps:
        acc = collect_comp(code, league)
        for (squad, nk), cell in acc.items():
            row = rows.setdefault((squad, nk), {"squad": squad, "norm_key": nk, "player": cell["player"]})
            row[f"{key}_starts"] = cell["starts"]
            row[f"{key}_apps"] = cell["apps"]

    if not rows:
        print("수집 결과 없음.")
        return 1

    df = pd.DataFrame(list(rows.values()))
    all_keys = euro_keys + cup_keys
    for key in all_keys:
        for suf in ("starts", "apps"):
            col = f"{key}_{suf}"
            if col not in df.columns:
                df[col] = 0
            df[col] = df[col].fillna(0).astype(int)
    df["euro_starts"] = df[[f"{k}_starts" for k in euro_keys]].sum(axis=1)
    df["euro_apps"] = df[[f"{k}_apps" for k in euro_keys]].sum(axis=1)
    df["cup_starts"] = df[[f"{k}_starts" for k in cup_keys]].sum(axis=1) if cup_keys else 0
    df["cup_apps"] = df[[f"{k}_apps" for k in cup_keys]].sum(axis=1) if cup_keys else 0

    cols = ["squad", "player", "norm_key"] + [f"{k}_{s}" for k in all_keys for s in ("starts", "apps")] \
        + ["euro_starts", "euro_apps", "cup_starts", "cup_apps"]
    df = df[cols].sort_values(["squad", "euro_starts"], ascending=[True, False])

    print(f"\n[{league}] 선수 {len(df)}명 · 팀 {df['squad'].nunique()}")
    print(df.sort_values("euro_starts", ascending=False)[["squad", "player", "euro_starts", "cup_starts"]].head(10).to_string(index=False))
    if dry:
        print("\n[DRY] 저장 안 함.")
    else:
        out = data_path("player_comp_usage", league)
        df.to_csv(out, index=False, encoding="utf-8")
        print(f"\n[OK] 저장: {out.name} ({len(df)}행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
