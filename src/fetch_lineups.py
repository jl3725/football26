"""
경기 라인업 스크래퍼 (Sofascore 비공식 API) — 실제 포메이션 + RB/CB/LB 도출.

팀별 25/26 PL 전 경기 라인업을 모아서:
  1) 최다 사용 포메이션 → data/team_formations.json 갱신
  2) 선수별 최빈 슬롯(RB/RCB/.../ST) → data/player_slots_2025_2026.csv

원리: Sofascore 라인업의 선수 배열은 포메이션 순서(GK→수비→중원→공격)로,
각 라인 안에서 우→좌로 정렬된다. 포메이션 숫자로 배열을 분할하면 슬롯이 나온다.

사용:
    python src/fetch_lineups.py "Arsenal"
    python src/fetch_lineups.py "Arsenal" "Manchester Utd"
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import tls_requests
from unidecode import unidecode

DATA = Path(__file__).resolve().parent.parent / "data"
FORMATIONS_PATH = DATA / "team_formations.json"
SLOTS_PATH = DATA / "player_slots_2025_2026.csv"

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept": "application/json",
     "Referer": "https://www.sofascore.com/"}
BASE = "https://api.sofascore.com/api/v1"
PL_UT_ID = 17  # Premier League uniqueTournament id

# FBref 팀명 → Sofascore 검색어 (다를 때만)
SEARCH_ALIAS = {
    "Manchester Utd": "Manchester United",
    "Newcastle Utd": "Newcastle United",
    "Nott'ham Forest": "Nottingham Forest",
    "Tottenham": "Tottenham Hotspur",
    "Wolves": "Wolverhampton",
    "West Ham": "West Ham United",
}


def get(path: str, retries: int = 3):
    for _ in range(retries):
        r = tls_requests.get(BASE + path, headers=H, timeout=20)
        if r.status_code == 200:
            return r.json()
        time.sleep(1.5)
    return None


def resolve_team_id(fbref_name: str) -> int | None:
    q = SEARCH_ALIAS.get(fbref_name, fbref_name)
    d = get(f"/search/all?q={q.replace(' ', '%20')}")
    if not d:
        return None
    for r in d.get("results", []):
        if r.get("type") == "team" and r.get("entity", {}).get("sport", {}).get("name") == "Football":
            return r["entity"]["id"]
    return None


def slot_labels(size: int, kind: str) -> list[str]:
    """라인 인원수+종류(D/M/F)에 맞는 슬롯 라벨을 우→좌 순으로."""
    D = {2: ["RCB", "LCB"], 3: ["RCB", "CB", "LCB"], 4: ["RB", "RCB", "LCB", "LB"],
         5: ["RWB", "RCB", "CB", "LCB", "LWB"]}
    M = {1: ["CM"], 2: ["RDM", "LDM"], 3: ["RCM", "CM", "LCM"],
         4: ["RM", "RCM", "LCM", "LM"], 5: ["RM", "RCM", "CM", "LCM", "LM"]}
    F = {1: ["ST"], 2: ["RST", "LST"], 3: ["RW", "ST", "LW"]}
    table = {"D": D, "M": M, "F": F}[kind]
    return table.get(size, [f"{kind}{i+1}" for i in range(size)])


def assign_slots(starters: list[dict], formation: str) -> dict[str, str]:
    """선수명(원본) → 슬롯. 포메이션 숫자로 배열을 분할."""
    parts = [int(x) for x in formation.split("-")]
    out, idx = {}, 0
    # 0번 = GK
    if starters:
        out[starters[0]["player"]["name"]] = "GK"
    idx = 1
    for bi, size in enumerate(parts):
        kind = "D" if bi == 0 else ("F" if bi == len(parts) - 1 else "M")
        labels = slot_labels(size, kind)
        for j in range(size):
            if idx >= len(starters):
                break
            out[starters[idx]["player"]["name"]] = labels[j] if j < len(labels) else kind
            idx += 1
    return out


def scrape_team(fbref_name: str) -> tuple[dict | None, list[dict]]:
    """팀 라인업 수집.

    반환: ({"main": "4-3-3", "sub": "4-2-3-1" or None}, slot_rows).
    slot_rows는 (포메이션, 선수) 쌍마다 한 행씩 — 메인/서브가 같은 선수도 다른 슬롯을 가질 수 있음.
    """
    tid = resolve_team_id(fbref_name)
    if tid is None:
        print(f"  [{fbref_name}] 팀 ID 해석 실패")
        return None, []
    print(f"  [{fbref_name}] Sofascore id={tid}")

    # 시즌 경기 수집 (페이지 0~4)
    matches, seen = [], set()
    for page in range(5):
        d = get(f"/team/{tid}/events/last/{page}")
        if not d:
            break
        for e in d.get("events", []):
            if (e.get("tournament", {}).get("uniqueTournament", {}).get("id") == PL_UT_ID
                    and e.get("status", {}).get("type") == "finished"
                    and str(e.get("season", {}).get("year")) == "25/26"
                    and e["id"] not in seen):
                seen.add(e["id"]); matches.append(e)
        time.sleep(0.7)

    form_counter = Counter()
    # (formation, player) → Counter(slot → count)
    per_form_slots: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for e in matches:
        lu = get(f"/event/{e['id']}/lineups")
        time.sleep(0.5)
        if not lu:
            continue
        side = "home" if e["homeTeam"]["id"] == tid else "away"
        s = lu.get(side, {})
        form = s.get("formation")
        if not form:
            continue
        form_counter[form] += 1
        starters = [p for p in s.get("players", []) if not p.get("substitute")]
        for name, slot in assign_slots(starters, form).items():
            per_form_slots[(form, name)][slot] += 1

    if not form_counter:
        print(f"  [{fbref_name}] 라인업 없음")
        return None, []

    top = form_counter.most_common(2)
    main_formation = top[0][0]
    sub_formation = top[1][0] if len(top) > 1 else None
    pair = {"main": main_formation, "sub": sub_formation}
    print(f"  [{fbref_name}] {len(matches)}경기 · {dict(form_counter)} → 메인 {main_formation}"
          + (f" · 서브 {sub_formation}" if sub_formation else ""))

    # 메인+서브에 해당하는 슬롯 행만 출력
    keep_forms = {f for f in (main_formation, sub_formation) if f}
    rows = []
    for (form, name), slots in per_form_slots.items():
        if form not in keep_forms:
            continue
        slot, apps = slots.most_common(1)[0]
        rows.append({"squad": fbref_name, "player": name,
                     "norm_key": unidecode(name).lower().strip(),
                     "formation": form,
                     "slot": slot, "apps": apps,
                     "slot_dist": json.dumps(dict(slots), ensure_ascii=False)})
    return pair, rows


def main(argv=None) -> int:
    teams = argv if argv else sys.argv[1:]
    if not teams:
        print("사용법: python src/fetch_lineups.py \"Arsenal\" [\"Manchester Utd\" ...]")
        return 1

    formations = json.loads(FORMATIONS_PATH.read_text(encoding="utf-8")) if FORMATIONS_PATH.exists() else {"_default": "4-3-3"}
    all_rows = []
    if SLOTS_PATH.exists():
        all_rows = pd.read_csv(SLOTS_PATH).to_dict("records")

    for tm in teams:
        print(f"\n=== {tm} ===")
        pair, rows = scrape_team(tm)
        if pair:
            # 항상 dict 저장; sub 없으면 main만 키로 둠
            formations[tm] = {k: v for k, v in pair.items() if v}
            all_rows = [r for r in all_rows if r.get("squad") != tm]  # 기존 갱신
            all_rows += rows

    FORMATIONS_PATH.write_text(json.dumps(formations, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(all_rows).to_csv(SLOTS_PATH, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {FORMATIONS_PATH.name}, {SLOTS_PATH.name} ({len(all_rows)}행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
