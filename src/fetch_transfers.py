"""
Transfermarkt 이적시장 IN/OUT 스크래퍼 (달력상 현재 시즌의 여름·겨울 창).

시즌 소속 클럽(season_clubs — 승격·강등 자동 반영)의 transfers 페이지에서
Arrivals(영입)·Departures(방출)를 긁어 data/transfers[_<리그>]_<시즌>.csv 에 누적한다.
컬럼: squad, season_id, window, direction(in/out), player, pos, age, nat, club, fee_eur, fee_text, photo

저장은 팀 단위 교체 — 두 창(여름·겨울)을 모두 받아온 팀의 이번 시즌 행만 바꾸고,
요청이 실패한 팀(차단·타임아웃)은 기존 행을 그대로 둔다. 한 팀도 못 받으면 저장하지 않고 exit 1.

사용:
    python src/fetch_transfers.py            # EPL 전 팀
    python src/fetch_transfers.py "Arsenal"  # 특정 팀
    python src/fetch_transfers.py "Arsenal" --dry
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

import tm_http  # noqa: E402  — 클라우드(WAF 202)에서도 열리게: 202 면 브라우저 토큰 후 재요청
from bs4 import BeautifulSoup

from fetch_transfermarkt import H, norm, parse_mv, season_clubs  # 재사용

DATA = Path(__file__).resolve().parent.parent / "data"
from leagues import data_path

OUT = data_path("transfers")


def current_season_id(today: date | None = None) -> int:
    """현재 활성 TM 시즌 id(=시작 연도). 여름이적이 열리는 6월부터 새 시즌으로 본다.
    예: 2026-06 → 2026(26/27), 2026-01 → 2025(25/26 겨울)."""
    today = today or date.today()
    return today.year if today.month >= 6 else today.year - 1


SEASON = current_season_id()


def _parse_row(tr) -> dict | None:
    a = tr.select_one("td.posrela a") or tr.select_one("td.hauptlink a")
    if not a:
        return None
    name = a.get_text(strip=True)
    if not name:
        return None
    pos = ""
    inline = tr.select_one("table.inline-table")
    if inline:
        trs = inline.select("tr")
        if len(trs) > 1:
            pos = trs[1].get_text(strip=True)
    age = None
    for td in tr.select("td.zentriert"):
        t = td.get_text(strip=True)
        if t.isdigit():
            age = int(t); break
    flag = tr.select_one("img.flaggenrahmen")
    nat = flag.get("title") if flag else ""
    tds = tr.select("td")
    club = tds[-3].get_text(" ", strip=True) if len(tds) >= 3 else ""
    fee_text = tds[-1].get_text(" ", strip=True) if tds else ""
    fee_eur = parse_mv(fee_text)
    img = tr.select_one("img.bilderrahmen-fixed")
    photo = (img.get("data-src") or img.get("src")) if img else ""
    return {"player": name, "norm_key": norm(name), "pos": pos, "age": age,
            "nat": nat, "club": club, "fee_eur": fee_eur, "fee_text": fee_text,
            "photo": photo}


def scrape_transfers(team: str, slug: str, vid: int, window: str = "s") -> list[dict] | None:
    """window: 's'=여름, 'w'=겨울 (?w_s 쿼리 파라미터). 요청 실패(차단 202 포함) 시 None."""
    url = f"https://www.transfermarkt.com/{slug}/transfers/verein/{vid}/saison_id/{SEASON}"
    r = None
    for attempt in range(3):
        try:
            r = tm_http.get(url, headers=H, params={"w_s": window}, timeout=30)
            break
        except requests.exceptions.RequestException:
            time.sleep(4)
    if r is None:
        print(f"  [{team}/{window}] 요청 실패(타임아웃)")
        return None
    if r.status_code != 200:
        print(f"  [{team}/{window}] HTTP {r.status_code}")
        return None
    soup = BeautifulSoup(r.text, "lxml")
    rows = []
    for box in soup.select("div.box"):
        hl = box.select_one(".content-box-headline, h2")
        tbl = box.select_one("table.items")
        if not hl or not tbl:
            continue
        title = hl.get_text(strip=True)
        if title.startswith("Arrivals"):
            direction = "in"
        elif title.startswith("Departures"):
            direction = "out"
        else:
            continue
        for tr in tbl.select("tbody > tr"):
            rec = _parse_row(tr)
            if rec and rec["club"]:
                rec.update({"squad": team, "direction": direction})
                rows.append(rec)
    return rows


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    if dry:
        args.remove("--dry")
    clubs = season_clubs(season=SEASON)
    teams = args if args else list(clubs)

    WINDOWS = {"s": "summer", "w": "winter"}
    all_rows = []
    ok_teams: list[str] = []
    failed: list[str] = []
    first = True
    for team in teams:
        if team not in clubs:
            print(f"  [건너뜀] {team} — {SEASON} 시즌 소속 아님")
            continue
        slug, vid = clubs[team]
        counts = {}
        team_rows: list[dict] = []
        complete = True
        for wk, wname in WINDOWS.items():
            if not first:
                time.sleep(3)
            first = False
            rows = scrape_transfers(team, slug, vid, wk)
            if rows is None:
                complete = False
                break
            for r in rows:
                r["window"] = wname
            counts[wname] = (sum(1 for r in rows if r["direction"] == "in"),
                             sum(1 for r in rows if r["direction"] == "out"))
            team_rows += rows
        if not complete:
            failed.append(team)
            continue
        ok_teams.append(team)
        all_rows += team_rows
        print(f"  [{team}] 여름 IN{counts['summer'][0]}/OUT{counts['summer'][1]} · "
              f"겨울 IN{counts['winter'][0]}/OUT{counts['winter'][1]}")

    if failed:
        print(f"  [실패] {len(failed)}팀 — 기존 행 유지: {', '.join(failed)}")
    if not ok_teams:
        print("[FAIL] 수집 성공 팀 없음 — 저장 안 함.")
        return 1
    if dry:
        print(f"\n[DRY] season {SEASON} · 총 {len(all_rows)}건 — 저장 안 함.")
        return 0
    cols = ["squad", "season_id", "window", "direction", "player", "norm_key", "pos",
            "age", "nat", "club", "fee_eur", "fee_text", "photo"]
    df_new = pd.DataFrame(all_rows, columns=[c for c in cols if c != "season_id"])
    df_new["season_id"] = SEASON
    df_new = df_new[cols]
    # 누적 — 이번에 받아온 팀의 이번 시즌 행만 교체. 과거 시즌·실패 팀 행은 보존.
    if OUT.exists():
        old = pd.read_csv(OUT)
        if "season_id" not in old.columns:        # 기존 25/26 데이터 마이그레이션
            old.insert(1, "season_id", 2025)
        old = old[~((old["season_id"] == SEASON) & old["squad"].isin(ok_teams))]
        df_new = pd.concat([old.reindex(columns=cols), df_new], ignore_index=True)
    df_new.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {OUT.name} · season {SEASON} {len(ok_teams)}팀 {len(all_rows)}건 · 누적 {len(df_new)}건")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
