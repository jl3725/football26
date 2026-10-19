"""
ClubElo 예측 — 유럽 클럽 Elo 레이팅으로 만든 독립 예측 모델(clubelo.com)의 다가오는 경기 승·무·패 확률.

원천은 웹 페이지 clubelo.com/Fixtures 의 표(경기마다 두 줄: 윗줄 홈팀·'1'·'X', 아랫줄 원정팀·'2'). 한 번에 페이지 1회 요청.
예전 1순위였던 api.clubelo.com/Fixtures(CSV 골득실 분포)는 2026-10-20 확인 결과 'Fixtures API deactivated' 를 돌려줘
부르지 않는다(from_api 는 API 가 돌아오면 쓰려고 남김 — CLUBELO_API=1).
팀 표기는 우리 standings 표기로 맞춰 저장(team_names.best) — 챔스 등 리그 밖 상대는 원래 이름 그대로.
출력: data/clubelo_fixtures.csv (시즌 무관 · 매번 새로 씀)

    python src/fetch_clubelo.py
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402
import team_names  # noqa: E402

API = "http://api.clubelo.com/Fixtures"
PAGE = "https://clubelo.com/Fixtures"
OUT = Path(__file__).resolve().parent.parent / "data" / "clubelo_fixtures.csv"
UA = {"User-Agent": "Mozilla/5.0 (football26 data; daily)"}


def _our_teams() -> dict[str, str]:
    """우리 표기 → 리그."""
    out: dict[str, str] = {}
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if p.exists():
            for t in pd.read_csv(p)["squad"].astype(str):
                out[t] = lg
    return out


def _gd(col: str) -> int | None:
    c = col.replace(" ", "")
    if c.startswith("GD<"):
        return -99
    if c.startswith("GD>"):
        return 99
    m = re.match(r"GD=(-?\d+)$", c)
    return int(m.group(1)) if m else None


def from_api() -> list[dict]:
    r = requests.get(API, timeout=25, headers=UA)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    gd = {c: _gd(c) for c in df.columns if _gd(c) is not None}
    out = []
    for _, x in df.iterrows():
        ph = sum(float(x[c]) for c, g in gd.items() if g > 0)
        pd_ = sum(float(x[c]) for c, g in gd.items() if g == 0)
        pa = sum(float(x[c]) for c, g in gd.items() if g < 0)
        out.append({"date": str(x["Date"])[:10], "home_src": str(x["Home"]), "away_src": str(x["Away"]), "h": ph, "d": pd_, "a": pa})
    return out


def _pct(seg: str) -> list[float]:
    return [float(v) for v in re.findall(r'<span class="min1081">([\d.]+)</span>', seg)]


def from_page() -> list[dict]:
    """웹 표 — 경기 블록마다 [윗줄: 날짜·홈팀·…·'1'·'X'] [아랫줄: 원정팀·…·'2']."""
    r = requests.get(PAGE, timeout=40, headers=UA)
    r.raise_for_status()
    h = r.text
    starts = [m.start() for m in re.finditer(r'data-live-status-game-id="', h)]
    out = []
    for i, s in enumerate(starts):
        block = h[s: starts[i + 1] if i + 1 < len(starts) else s + 6000]
        t = re.search(r'data-utc-time="(\d{4}-\d{2}-\d{2})T', block)
        names = re.findall(r'<span class="min641">([^<]+)</span>', block)
        if not t or len(names) < 2:
            continue
        cut = block.find(f'<span class="min641">{names[1]}</span>')
        top, bottom = _pct(block[:cut]), _pct(block[cut:])
        if len(top) < 2 or not bottom:
            continue
        out.append({"date": t.group(1), "home_src": names[0].strip(), "away_src": names[1].strip(),
                    "h": top[0], "d": top[1], "a": bottom[0]})
    return out


def main() -> int:
    raw, src = [], "api"
    if os.getenv("CLUBELO_API") == "1":
        try:
            raw = from_api()
        except Exception as e:  # noqa: BLE001
            print(f"[clubelo] API 실패({type(e).__name__})", flush=True)
    if not raw:
        import time as _time
        for attempt in (1, 2):        # 웹 표도 가끔 시간 초과 — 30초 뒤 한 번 더(2026-10-19 점검: 주 2회꼴 실패)
            try:
                raw, src = from_page(), "page"
            except Exception as e:  # noqa: BLE001
                print(f"[clubelo] 웹 표 실패({type(e).__name__}) {attempt}/2", flush=True)
                raw = []
            if raw or attempt == 2:
                break
            _time.sleep(30)
    ours = _our_teams()
    names = list(ours)
    rows = []
    for x in raw:
        h, a = team_names.best(x["home_src"], names), team_names.best(x["away_src"], names)
        if not h and not a:
            continue                      # 우리 리그와 무관한 경기
        t = (x["h"] + x["d"] + x["a"]) or 1.0
        rows.append({"date": x["date"], "league": ours.get(h or a, ""), "home": h or x["home_src"], "away": a or x["away_src"],
                     "p_home": round(x["h"] / t, 3), "p_draw": round(x["d"] / t, 3), "p_away": round(x["a"] / t, 3),
                     "home_src": x["home_src"], "away_src": x["away_src"], "source": src})
    if not rows:
        print(f"[clubelo] 우리 리그 경기 0건(원자료 {len(raw)}) — 기존 파일 유지")
        return 1
    new = pd.DataFrame(rows)
    if OUT.exists():   # 페이지에서 빠진 지난 경기 예측도 7일간 보관(경기 리뷰의 예측 적중 판정용)
        import datetime as _dt
        old = pd.read_csv(OUT)
        cut = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
        key = lambda d: d["date"].astype(str) + "|" + d["home"].astype(str) + "|" + d["away"].astype(str)  # noqa: E731
        old = old[(old["date"].astype(str) >= cut) & ~key(old).isin(set(key(new)))]
        new = pd.concat([old, new], ignore_index=True)
    new.sort_values("date").to_csv(OUT, index=False)
    print(f"[OK] {OUT.name} · {len(rows)}경기 ({src}, 지난 7일 보관 {len(new) - len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
