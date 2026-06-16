"""
경기 라인업 스크래퍼 (API-Football / api-sports.io) — Sofascore 403 대체 소스.

기존 fetch_lineups.py와 '동일한 출력'을 만든다:
  1) 최다 사용 포메이션 → data/team_formations.json
  2) 선수별 최빈 슬롯(RB/RCB/.../ST) → data/player_slots_2025_2026.csv
     (컬럼 동일: squad, player, norm_key, formation, slot, apps, number, sofa_id, slot_dist)
     · sofa_id 컬럼에는 API-Football 'photo URL' 전체를 넣는다 → app.py sofa_photo()가
       http URL이면 그대로 통과시키므로 사진이 그대로 뜬다(앱 수정 최소화).

API-Football은 startXI 각 선수에 grid("row:col")를 주므로 슬롯을 정확히 도출한다.
  row 1 = GK, row 증가 = 공격 방향. 한 라인 안에서 col 로 좌우가 갈린다.

키: .env 의 APIFOOTBALL_KEY 또는 환경변수 APIFOOTBALL_KEY, 또는 apifootball.key 파일.
무료 플랜: 10req/분 · 100req/일 → 호출 사이 6.5초 대기, 일일 한도 도달 시 안전 종료.

사용:
    python src/fetch_lineups_apifootball.py            # EPL 전 팀
    python src/fetch_lineups_apifootball.py "Arsenal"  # 특정 팀만
    python src/fetch_lineups_apifootball.py --flip      # 좌우(col) 방향 반전
    python src/fetch_lineups_apifootball.py --max 10    # 팀당 표본 경기 수
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import requests
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FORMATIONS_PATH = DATA / "team_formations.json"
SLOTS_PATH = DATA / "player_slots_2025_2026.csv"

API = "https://v3.football.api-sports.io"
LEAGUE_ID = 39        # Premier League
SEASON = 2025         # 2025/26 시즌 = season 2025
PHOTO_URL = "https://media.api-sports.io/football/players/{pid}.png"

SLEEP = 6.5           # 무료 10req/분 → 호출 간 6.5초
MAX_PER_TEAM = 8      # 팀당 표본 경기(메인/서브 수렴 + 일일 한도 100 내 전팀 커버)

# 우리 데이터(squad) → API-Football 팀명 (다를 때만; 나머지는 퍼지 매칭)
NAME_OVERRIDE = {
    "Manchester Utd": "Manchester United",
    "Newcastle United": "Newcastle",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Leeds United": "Leeds",
}

# col 정렬 방향: 기본 내림차순(=col 큰 값이 우측 RB 먼저). 실제와 좌우가 뒤집히면 --flip.
COL_DESC_FIRST = True


def load_key() -> str | None:
    if os.environ.get("APIFOOTBALL_KEY"):
        return os.environ["APIFOOTBALL_KEY"].strip()
    for p in (ROOT / "apifootball.key", ROOT / ".env"):
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("APIFOOTBALL_KEY"):
                    return line.split("=", 1)[1].strip()
                if p.name == "apifootball.key" and line and "=" not in line:
                    return line
    return None


KEY = load_key()
_remaining_today: int | None = None


def api_get(path: str, params: dict | None = None) -> dict | None:
    """API-Football GET. 일일 한도/에러 시 None. 잔여 호출수를 전역에 기록."""
    global _remaining_today
    try:
        r = requests.get(API + path, headers={"x-apisports-key": KEY},
                         params=params or {}, timeout=25)
    except Exception as e:
        print(f"  [요청 실패] {e}")
        return None
    rem = r.headers.get("x-ratelimit-requests-remaining")
    if rem is not None:
        try:
            _remaining_today = int(rem)
        except ValueError:
            pass
    if r.status_code != 200:
        print(f"  [HTTP {r.status_code}] {path}")
        return None
    d = r.json()
    errs = d.get("errors")
    if errs:
        print(f"  [API 오류] {errs}")
        return None
    return d


def team_id_map() -> dict[str, int]:
    """API-Football EPL 팀명 → id."""
    d = api_get("/teams", {"league": LEAGUE_ID, "season": SEASON})
    if not d:
        return {}
    out = {}
    for item in d.get("response", []):
        t = item.get("team", {})
        if t.get("name") and t.get("id"):
            out[t["name"]] = t["id"]
    return out


def resolve_targets(squads: list[str], id_map: dict[str, int]) -> dict[int, str]:
    """우리 squad 이름 리스트 → {api_team_id: our_squad}."""
    out: dict[int, str] = {}
    for sq in squads:
        target = NAME_OVERRIDE.get(sq, sq)
        tid = id_map.get(target)
        if tid is None:                                  # 퍼지 매칭
            tn = unidecode(target).lower()
            for name, i in id_map.items():
                n = unidecode(name).lower()
                if tn in n or n in tn:
                    tid = i
                    break
        if tid is None:
            print(f"  [경고] 팀 매칭 실패: {sq}")
            continue
        out[tid] = sq
    return out


def league_finished_fixtures() -> list[dict]:
    """EPL 시즌 전 경기 → 종료된 경기만 최신순."""
    d = api_get("/fixtures", {"league": LEAGUE_ID, "season": SEASON})
    if not d:
        return []
    fin = [f for f in d.get("response", [])
           if f.get("fixture", {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
    fin.sort(key=lambda f: f["fixture"].get("date", ""), reverse=True)
    return fin


def slot_labels(size: int, kind: str) -> list[str]:
    """라인 인원수+종류(D/M/F)에 맞는 슬롯 라벨을 우→좌 순으로 (fetch_lineups와 동일)."""
    D = {2: ["RCB", "LCB"], 3: ["RCB", "CB", "LCB"], 4: ["RB", "RCB", "LCB", "LB"],
         5: ["RWB", "RCB", "CB", "LCB", "LWB"]}
    M = {1: ["CM"], 2: ["RDM", "LDM"], 3: ["RCM", "CM", "LCM"],
         4: ["RM", "RCM", "LCM", "LM"], 5: ["RM", "RCM", "CM", "LCM", "LM"]}
    F = {1: ["ST"], 2: ["RST", "LST"], 3: ["RW", "ST", "LW"]}
    table = {"D": D, "M": M, "F": F}[kind]
    return table.get(size, [f"{kind}{i+1}" for i in range(size)])


def slots_from_grid(start_xi: list[dict], formation: str) -> dict[str, str]:
    """startXI(grid 보유) → {선수명: 슬롯}. row=라인, col=좌우."""
    rows: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for p in start_xi:
        pl = p.get("player", {})
        grid = pl.get("grid")
        nm = pl.get("name")
        if not grid or not nm:
            return {}                       # grid 없으면 도출 불가
        rr, cc = grid.split(":")
        rows[int(rr)].append((int(cc), nm))
    parts = [int(x) for x in formation.split("-")]
    out: dict[str, str] = {}
    ordered_rows = sorted(rows)
    # 첫 row = GK
    if ordered_rows:
        gk_line = sorted(rows[ordered_rows[0]], key=lambda x: x[0])
        if gk_line:
            out[gk_line[0][1]] = "GK"
    # 나머지 row = 포메이션 라인 순서(D→M→F)
    line_rows = ordered_rows[1:]
    for li, rkey in enumerate(line_rows):
        kind = "D" if li == 0 else ("F" if li == len(line_rows) - 1 else "M")
        line = sorted(rows[rkey], key=lambda x: x[0], reverse=COL_DESC_FIRST)
        size = parts[li] if li < len(parts) else len(line)
        labels = slot_labels(size, kind)
        for j, (_, nm) in enumerate(line):
            out[nm] = labels[j] if j < len(labels) else kind
    return out


def collect(targets: dict[int, str], fixtures: list[dict], cap: int):
    """경기들을 돌며 팀별 포메이션/슬롯/등번호/사진을 누적."""
    form_counter: dict[str, Counter] = defaultdict(Counter)
    per_form_slots: dict[str, dict[tuple[str, str], Counter]] = defaultdict(lambda: defaultdict(Counter))
    name_number: dict[str, dict[str, str]] = defaultdict(dict)
    name_photo: dict[str, dict[str, str]] = defaultdict(dict)
    appearances: dict[str, int] = defaultdict(int)

    for fx in fixtures:
        if all(appearances[s] >= cap for s in targets.values()):
            break
        if _remaining_today is not None and _remaining_today <= 1:
            print("  [일일 한도 임박] 안전 종료 — 나중에 이어서 실행하세요.")
            break
        fid = fx["fixture"]["id"]
        # 이 경기에 아직 cap 안 찬 타깃이 있을 때만 호출
        involved = [t for t in (fx["teams"]["home"]["id"], fx["teams"]["away"]["id"])
                    if t in targets and appearances[targets[t]] < cap]
        if not involved:
            continue
        d = api_get("/fixtures/lineups", {"fixture": fid})
        time.sleep(SLEEP)
        if not d:
            continue
        for entry in d.get("response", []):
            tid = entry.get("team", {}).get("id")
            if tid not in targets:
                continue
            squad = targets[tid]
            if appearances[squad] >= cap:
                continue
            form = entry.get("formation")
            start_xi = entry.get("startXI", [])
            if not form or not start_xi:
                continue
            appearances[squad] += 1
            form_counter[squad][form] += 1
            # 등번호 + 사진 (선발 + 교체)
            for p in start_xi + entry.get("substitutes", []):
                pl = p.get("player", {})
                nm, num, pid = pl.get("name"), pl.get("number"), pl.get("id")
                if nm and num and nm not in name_number[squad]:
                    name_number[squad][nm] = str(num)
                if nm and pid and nm not in name_photo[squad]:
                    name_photo[squad][nm] = PHOTO_URL.format(pid=pid)
            for nm, slot in slots_from_grid(start_xi, form).items():
                per_form_slots[squad][(form, nm)][slot] += 1
        rem = f" · 잔여 {_remaining_today}" if _remaining_today is not None else ""
        cov = ", ".join(f"{s}:{appearances[s]}" for s in targets.values() if appearances[s])
        print(f"  fixture {fid}{rem} | {cov}")
    return form_counter, per_form_slots, name_number, name_photo, appearances


def build_team_output(squad, form_counter, per_form_slots, name_number, name_photo):
    fc = form_counter.get(squad)
    if not fc:
        return None, []
    top = fc.most_common(2)
    main_f = top[0][0]
    sub_f = top[1][0] if len(top) > 1 else None
    keep = {f for f in (main_f, sub_f) if f}
    rows = []
    for (form, name), slots in per_form_slots[squad].items():
        if form not in keep:
            continue
        slot, apps = slots.most_common(1)[0]
        rows.append({"squad": squad, "player": name,
                     "norm_key": unidecode(name).lower().strip(),
                     "formation": form, "slot": slot, "apps": apps,
                     "number": name_number[squad].get(name, ""),
                     "sofa_id": name_photo[squad].get(name, ""),   # photo URL 전체
                     "slot_dist": json.dumps(dict(slots), ensure_ascii=False)})
    return {"main": main_f, "sub": sub_f}, rows


def main(argv=None) -> int:
    global COL_DESC_FIRST
    args = list(argv if argv is not None else sys.argv[1:])
    cap = MAX_PER_TEAM
    if "--flip" in args:
        COL_DESC_FIRST = not COL_DESC_FIRST
        args.remove("--flip")
    if "--max" in args:
        i = args.index("--max")
        cap = int(args[i + 1]); del args[i:i + 2]

    if not KEY:
        print("[오류] APIFOOTBALL_KEY 가 없습니다. .env 또는 환경변수에 설정하세요.")
        return 1

    squads_all = sorted(pd.read_csv(DATA / "standings_2025_2026.csv")["squad"].tolist())
    squads = args if args else squads_all

    print("API-Football 팀 ID 조회...")
    id_map = team_id_map()
    if not id_map:
        print("[오류] 팀 목록을 가져오지 못했습니다. 키/플랜/시즌을 확인하세요.")
        return 1
    targets = resolve_targets(squads, id_map)
    if not targets:
        print("[오류] 매칭된 팀이 없습니다.")
        return 1
    print(f"대상 {len(targets)}팀 · 팀당 최대 {cap}경기 · col방향 {'desc' if COL_DESC_FIRST else 'asc'}")

    print("경기 목록 조회...")
    fixtures = league_finished_fixtures()
    print(f"종료 경기 {len(fixtures)}개")
    if not fixtures:
        return 1

    fc, pfs, nn, np_, apps = collect(targets, fixtures, cap)

    # 기존 파일에 병합 (요청 팀만 교체)
    formations = json.loads(FORMATIONS_PATH.read_text(encoding="utf-8")) \
        if FORMATIONS_PATH.exists() else {"_default": "4-3-3"}
    all_rows = pd.read_csv(SLOTS_PATH).to_dict("records") if SLOTS_PATH.exists() else []

    done = 0
    for squad in targets.values():
        pair, rows = build_team_output(squad, fc, pfs, nn, np_)
        if not pair:
            print(f"  [{squad}] 라인업 없음")
            continue
        formations[squad] = {k: v for k, v in pair.items() if v}
        all_rows = [r for r in all_rows if r.get("squad") != squad]
        all_rows += rows
        done += 1
        sub = f" · 서브 {pair['sub']}" if pair.get("sub") else ""
        print(f"  [{squad}] {apps[squad]}경기 → 메인 {pair['main']}{sub} ({len(rows)}명)")

    FORMATIONS_PATH.write_text(json.dumps(formations, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(all_rows).to_csv(SLOTS_PATH, index=False, encoding="utf-8")
    print(f"\n[OK] 저장: {FORMATIONS_PATH.name}, {SLOTS_PATH.name} "
          f"({len(all_rows)}행, {done}/{len(targets)}팀)")
    if _remaining_today is not None:
        print(f"[잔여 일일 호출] {_remaining_today}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
