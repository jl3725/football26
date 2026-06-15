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

# 데이터(squad) 팀명 → Sofascore 순위표 팀명 (다를 때만).
# search/all 엔드포인트는 Cloudflare challenge로 자주 막히므로 순위표로 ID를 받는다.
SOFA_NAME = {
    "Manchester Utd": "Manchester United",
    "Wolves": "Wolverhampton",
    "Brighton": "Brighton & Hove Albion",
}

# 한 경기당 최빈 포메이션은 시즌 전체가 아니어도 안정적으로 수렴한다.
# 콜 수(=차단 위험)를 줄이려 팀당 최근 N경기로 제한한다.
MAX_MATCHES = 24

_TEAM_ID_CACHE: dict[str, int] = {}


def get(path: str, retries: int = 3, sleep: float = 2.0):
    for _ in range(retries):
        r = tls_requests.get(BASE + path, headers=H, timeout=20)
        if r.status_code == 200:
            return r.json()
        time.sleep(sleep)
    return None


def _pl_season_id() -> int | None:
    d = get(f"/unique-tournament/{PL_UT_ID}/seasons")
    if not d:
        return None
    for s in d.get("seasons", []):
        if s.get("year") == "25/26":
            return s.get("id")
    return None


def _load_team_ids() -> dict[str, int]:
    """PL 순위표에서 {팀명: id} 를 한 번에 — search 엔드포인트 우회."""
    global _TEAM_ID_CACHE
    if _TEAM_ID_CACHE:
        return _TEAM_ID_CACHE
    sid = _pl_season_id()
    if sid is None:
        return {}
    d = get(f"/unique-tournament/{PL_UT_ID}/season/{sid}/standings/total")
    if not d:
        return {}
    out: dict[str, int] = {}
    for grp in d.get("standings", []):
        for row in grp.get("rows", []):
            t = row.get("team", {})
            if t.get("name") and t.get("id"):
                out[t["name"]] = t["id"]
    _TEAM_ID_CACHE = out
    return out


def resolve_team_id(fbref_name: str) -> int | None:
    ids = _load_team_ids()
    if not ids:
        return None
    target = SOFA_NAME.get(fbref_name, fbref_name)
    if target in ids:
        return ids[target]
    # 폴백: 악센트 제거 후 부분일치
    tnorm = unidecode(target).lower()
    for name, tid in ids.items():
        n = unidecode(name).lower()
        if tnorm in n or n in tnorm:
            return tid
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

    # 최근 경기 수집 (페이지 0~4) — MAX_MATCHES 채우면 조기 종료
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
        if len(matches) >= MAX_MATCHES:
            break
        time.sleep(1.0)
    matches = matches[:MAX_MATCHES]

    form_counter = Counter()
    # (formation, player) → Counter(slot → count)
    per_form_slots: dict[tuple[str, str], Counter] = defaultdict(Counter)
    name_number: dict[str, str] = {}   # 선수명 → 등번호(라인업에서 수집)
    name_id: dict[str, str] = {}       # 선수명 → Sofascore player id(사진 URL용)
    for e in matches:
        lu = get(f"/event/{e['id']}/lineups")
        time.sleep(1.0)
        if not lu:
            continue
        side = "home" if e["homeTeam"]["id"] == tid else "away"
        s = lu.get(side, {})
        form = s.get("formation")
        if not form:
            continue
        form_counter[form] += 1
        # 등번호 + player id 수집 (선발/교체 모두)
        for p in s.get("players", []):
            pl = p.get("player", {})
            nm = pl.get("name")
            num = pl.get("jerseyNumber") or p.get("shirtNumber")
            if nm and num and nm not in name_number:
                name_number[nm] = str(num)
            if nm and pl.get("id") and nm not in name_id:
                name_id[nm] = str(pl["id"])
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
                     "number": name_number.get(name, ""),
                     "sofa_id": name_id.get(name, ""),
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

    def save() -> None:
        FORMATIONS_PATH.write_text(json.dumps(formations, ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(all_rows).to_csv(SLOTS_PATH, index=False, encoding="utf-8")

    # 팀 간 대기(초). 짧은 버스트(=18팀 한번에)가 Cloudflare IP 차단을 유발하므로
    # 팀 하나당 ~30 콜 후 4분 대기를 두면 시간당 콜 수가 차단 임계 아래로 유지된다.
    TEAM_GAP = 240  # 4분
    done = 0
    for i, tm in enumerate(teams):
        if i > 0:
            remaining = TEAM_GAP
            while remaining > 0:
                print(f"  [대기] 다음 팀까지 {remaining}초 남음 (Cloudflare 차단 방지)...", end="\r", flush=True)
                time.sleep(min(10, remaining))
                remaining -= 10
            print()
        print(f"\n=== ({i+1}/{len(teams)}) {tm} ===")
        pair, rows = scrape_team(tm)
        if pair:
            formations[tm] = {k: v for k, v in pair.items() if v}
            all_rows = [r for r in all_rows if r.get("squad") != tm]
            all_rows += rows
            save()
            done += 1
            print(f"  [저장됨] 누적 {done}팀 / {len(all_rows)}행")

    print(f"\n[OK] 저장: {FORMATIONS_PATH.name}, {SLOTS_PATH.name} ({len(all_rows)}행, {done}/{len(teams)}팀 성공)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
