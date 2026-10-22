"""
리그별 '빅5로 보낸 선수' — 최근 두 시즌, 빅5 구단이 그 리그에서 사 간 완전 이적(임대·임대 복귀 제외) → data/league_exports.json

홈 리그 지도(2026-10-22 사용자와 정함)의 TIER 3 원 크기·숫자 = 이적료 합. 처음엔 '21세 이하 주전급 수'였는데 MLS·사우디처럼
노장이 모이는 리그에 맞지 않아(사용자 지적) 리그 성격과 상관없이 같은 잣대인 이 값으로 바꿨다.
- 원천: Transfermarkt 리그 이적 페이지(/transfers/wettbewerb/<코드>/saison_id/<연도>) — 클럽마다 In/Out 표. 리그·시즌당 1요청.
- 빅5 구단 판정: 행선지 링크의 verein id 가 빅5 정적 맵(여러 시즌 합집합 — 강등팀 포함)에 있으면.
- 후보 리그(leagues.CANDIDATE_LEAGUES — 브라질·아르헨티나·MLS)도 센다: 수집 전이라도 지도에 실제 크기로 보이게.
- 한 리그가 실패(표 0개)하면 그 리그는 지난 값을 둔다.

    python src/fetch_league_exports.py [--league Brazil]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import CANDIDATE_LEAGUES, LEAGUES, SEASON_START  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "league_exports.json"
BIG5 = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1")


def _targets() -> dict[str, tuple[str, str]]:
    """{리그 키: (TM slug, TM 코드)} — 빅5 밖 우리 리그 + 후보 리그."""
    out = {k: (c.tm_slug, c.tm_id) for k, c in LEAGUES.items() if k not in BIG5}
    out.update({k: (c.tm_slug, c.tm_id) for k, c in CANDIDATE_LEAGUES.items()})
    return out


def big5_vereins() -> set[int]:
    from fetch_transfermarkt import TEAM_TM_BY_LEAGUE  # noqa: PLC0415
    return {int(vid) for lg in BIG5 for _sq, (_slug, vid) in TEAM_TM_BY_LEAGUE.get(lg, {}).items()}


def parse_outs(html: str, big5: set[int]) -> tuple[int, list[dict]]:
    """(Out 표 수, 빅5로 간 완전 이적 행들)."""
    from bs4 import BeautifulSoup  # noqa: PLC0415
    from fetch_transfermarkt import parse_mv  # noqa: PLC0415
    soup = BeautifulSoup(html, "lxml")
    tables, rows = 0, []
    for box in soup.select("div.box"):
        club = (box.select_one("h2") or {}).get_text(strip=True) if box.select_one("h2") else ""
        for t in box.select("table"):
            ths = [th.get_text(strip=True) for th in t.select("thead th")]
            if not ths or ths[0] != "Out":
                continue
            tables += 1
            for tr in t.select("tbody tr"):
                tds = tr.select("td")
                if len(tds) < 4:
                    continue
                fee_txt = tds[-1].get_text(" ", strip=True)
                if "loan" in fee_txt.lower():
                    continue
                vids = {int(m.group(1)) for a in tr.select("a[href*='/verein/']")
                        for m in [re.search(r"/verein/(\d+)", a.get("href", ""))] if m}
                if not vids & big5:
                    continue
                name_a = tr.select_one("td.hauptlink a") or tr.select_one("a[href*='/profil/spieler/']")
                to_a = [a for a in tr.select("a[href*='/verein/']") if a.get_text(strip=True)]
                try:
                    age = int(tds[1].get_text(strip=True))
                except ValueError:
                    age = None
                rows.append({"player": name_a.get_text(strip=True) if name_a else "", "from": club,
                             "to": to_a[-1].get_text(strip=True) if to_a else "", "age": age,
                             "fee_eur": parse_mv(fee_txt) or 0})
    return tables, rows


def collect(key: str, slug: str, code: str, big5: set[int]) -> dict | None:
    import tm_http  # noqa: PLC0415
    from fetch_transfermarkt import H  # noqa: PLC0415
    seasons = [SEASON_START - 1, SEASON_START]
    rows: list[dict] = []
    for s in seasons:
        r = tm_http.get(f"https://www.transfermarkt.com/{slug}/transfers/wettbewerb/{code}/saison_id/{s}", headers=H, timeout=30)
        tables, got = parse_outs(r.text if r.status_code == 200 else "", big5)
        if tables == 0:
            print(f"  [{key}] {s}: 이적 표 없음(HTTP {r.status_code}) — 지난 값 유지")
            return None
        rows += got
        time.sleep(1.5)
    ages = [x["age"] for x in rows if x["age"]]
    top = sorted(rows, key=lambda x: -x["fee_eur"])[:5]
    return {"n": len(rows), "fee_eur": int(sum(x["fee_eur"] for x in rows)),
            "avg_age": round(sum(ages) / len(ages), 1) if ages else None, "seasons": seasons, "top": top}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    a = ap.parse_args(argv)
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    leagues = dict(prev.get("leagues") or {})
    big5 = big5_vereins()
    targets = _targets()
    bad = 0
    for key in [a.league] if a.league else list(targets):
        slug, code = targets[key]
        try:
            res = collect(key, slug, code, big5)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패가 다른 리그를 멈추지 않게
            print(f"  [{key}] 실패 {type(e).__name__}: {e}")
            res = None
        if res is None:
            bad += 1
            continue
        leagues[key] = res
        print(f"  {key:18s} 빅5로 {res['n']:3d}명 · €{res['fee_eur'] / 1e6:5.0f}M · 평균 {res['avg_age']}세")
    OUT.write_text(json.dumps({"at": dt.date.today().isoformat(), "leagues": leagues}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return 1 if bad > len(targets) // 3 else 0


if __name__ == "__main__":
    raise SystemExit(main())
