"""
ClubElo 예측 — 유럽 클럽 Elo 레이팅으로 만든 독립 예측 모델(clubelo.com)의 다가오는 경기 승·무·패 확률.

원천은 웹 페이지 clubelo.com/Fixtures 의 표(경기마다 두 줄: 윗줄 홈팀·'1'·'X', 아랫줄 원정팀·'2'). 한 번에 페이지 1회 요청.
예전 1순위였던 api.clubelo.com/Fixtures(CSV 골득실 분포)는 2026-10-20 확인 결과 'Fixtures API deactivated' 를 돌려줘
부르지 않는다(from_api 는 API 가 돌아오면 쓰려고 남김 — CLUBELO_API=1).
팀 표기는 우리 standings 표기로 맞춰 저장(team_names.best) — 챔스 등 리그 밖 상대는 원래 이름 그대로.
출력: data/clubelo_fixtures.csv (시즌 무관 · 매번 새로 씀)

2026-10-25 부터 웹 페이지가 Cloudflare 봇 확인('Just a moment…', 403), 레이팅 API 도 502 — 사이트가 자동 접근을 막았다.
우회하지 않는다. 막혔으면 종료 코드 75(외부 원천 중단, scripts/ci_try.sh) — 워크플로는 빨갛게 안 하고 DATA 화면에
'원천 중단'으로 보이며, 다시 열리면 다음 실행부터 그대로 이어 받는다. 기존 파일(지난 예측)은 유지.

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
    if _blocked(r):
        raise SourceBlocked(f"HTTP {r.status_code} 봇 확인 페이지")
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


class SourceBlocked(Exception):
    """원천이 자동 접근을 막음(봇 확인 페이지) — 다시 시도해도 같다."""


def _blocked(r: requests.Response) -> bool:
    return r.status_code in (403, 429, 503) and ("Just a moment" in r.text[:3000] or "cf-chl" in r.text[:5000]
                                                 or "challenge" in r.text[:3000].lower())


def main() -> int:
    raw, src = [], "api"
    down = None                                          # 원천 중단 사유(차단·서버 오류) — 있으면 75
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
                down = None
            except SourceBlocked as e:
                print(f"[clubelo] 원천 차단 — {e}(우회하지 않음)", flush=True)
                down, raw = str(e), []
                break                                     # 봇 확인은 다시 해도 같다 — 30초 기다리지 않는다
            except Exception as e:  # noqa: BLE001
                print(f"[clubelo] 웹 표 실패({type(e).__name__}) {attempt}/2", flush=True)
                code = getattr(getattr(e, "response", None), "status_code", None)
                down = f"HTTP {code}" if code and code >= 500 else None   # 사이트 서버 오류도 외부 중단
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
        return 75 if down else 1
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
