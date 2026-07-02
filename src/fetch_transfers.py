"""
Transfermarkt 여름 이적시장 IN/OUT 스크래퍼 (2025/26).

각 팀의 transfers 페이지에서 Arrivals(영입)·Departures(방출)를 긁어
data/transfers_2025_2026.csv 로 저장한다.
컬럼: squad, direction(in/out), player, pos, age, nat, club, fee_eur, fee_text, photo

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
from bs4 import BeautifulSoup

from fetch_transfermarkt import H, TEAM_TM, norm, parse_mv  # 재사용

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


def scrape_transfers(team: str, window: str = "s") -> list[dict]:
    """window: 's'=여름, 'w'=겨울 (?w_s 쿼리 파라미터)."""
    slug, vid = TEAM_TM[team]
    url = f"https://www.transfermarkt.com/{slug}/transfers/verein/{vid}/saison_id/{SEASON}"
    r = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=H, params={"w_s": window}, timeout=30)
            break
        except requests.exceptions.RequestException:
            time.sleep(4)
    if r is None:
        print(f"  [{team}/{window}] 요청 실패(타임아웃)")
        return []
    if r.status_code != 200:
        print(f"  [{team}] HTTP {r.status_code}")
        return []
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
    teams = args if args else list(TEAM_TM)

    WINDOWS = {"s": "summer", "w": "winter"}
    all_rows = []
    first = True
    for team in teams:
        if team not in TEAM_TM:
            print(f"  [건너뜀] {team}")
            continue
        counts = {}
        for wk, wname in WINDOWS.items():
            if not first:
                time.sleep(3)
            first = False
            rows = scrape_transfers(team, wk)
            for r in rows:
                r["window"] = wname
            counts[wname] = (sum(1 for r in rows if r["direction"] == "in"),
                             sum(1 for r in rows if r["direction"] == "out"))
            all_rows += rows
        print(f"  [{team}] 여름 IN{counts['summer'][0]}/OUT{counts['summer'][1]} · "
              f"겨울 IN{counts['winter'][0]}/OUT{counts['winter'][1]}")

    if dry:
        print(f"\n[DRY] season {SEASON} · 총 {len(all_rows)}건 — 저장 안 함.")
        return 0
    cols = ["squad", "season_id", "window", "direction", "player", "norm_key", "pos",
            "age", "nat", "club", "fee_eur", "fee_text", "photo"]
    df_new = pd.DataFrame(all_rows)
    df_new["season_id"] = SEASON
    df_new = df_new[cols]
    # 누적 — 같은 시즌 행만 교체하고 과거 시즌은 보존(윈도우로 추가).
    if OUT.exists():
        old = pd.read_csv(OUT)
        if "season_id" not in old.columns:        # 기존 25/26 데이터 마이그레이션
            old.insert(1, "season_id", 2025)
        old = old[old["season_id"] != SEASON]
        df_new = pd.concat([old.reindex(columns=cols), df_new], ignore_index=True)
    df_new.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {OUT.name} · season {SEASON} {len(all_rows)}건 · 누적 {len(df_new)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
