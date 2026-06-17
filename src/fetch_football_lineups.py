"""
football-lineups.com 시즌 페이지 스크래퍼 — 팀별 상세 포지션 + 출전 경기수 + 포메이션.

Cloudflare Turnstile 보호 → FlareSolverr(헤드리스 브라우저 프록시) 경유로 우회.
사전 준비:
    docker run -d --name flaresolverr -p 8191:8191 --restart unless-stopped \\
        ghcr.io/flaresolverr/flaresolverr:latest

추출 데이터(선수별):
    fl_number(등번호) · fl_name(약식명) · age · fl_pos(주 포지션) · fl_pos2(부)
    starts(=전 대회 출전 경기수, 선발+교체 포함. EPL뿐 아니라 챔스·컵 합산) · move(in/out 이적 메모)
팀별:
    formation(최빈 포메이션)

저장: data/fl_positions_2025_2026.csv  (팀 단위 append/갱신)

사용:
    python src/fetch_football_lineups.py "Aston Villa"        # 한 팀
    python src/fetch_football_lineups.py "Aston Villa" --dry  # 저장 안 함
    python src/fetch_football_lineups.py --all                # 전 팀(차근차근)
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "fl_positions_2025_2026.csv"
MATCHES_OUT = DATA / "fl_matches_2025_2026.csv"   # 경기별 (날짜·대회·포메이션·match_id)
SEASON = "2025-2026"
FLARE = "http://localhost:8191/v1"

# 경기 목록 파싱용
_MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05",
           "Jun": "06", "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10",
           "Nov": "11", "Dec": "12"}
_H1 = {"Jan", "Feb", "Mar", "Apr", "May", "Jun"}     # 시즌 후반부 → 2026년
_COMPS = ["EPL", "Champions", "EFL Trophy", "FA Cup", "Carabao",
          "Club World", "Community", "Super Cup", "Europa", "Conference"]

# 우리 squad 표기 → football-lineups URL slug
TEAM_FL: dict[str, str] = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston_Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton_Hove_Albion",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal_Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds United": "Leeds_United",
    "Liverpool": "Liverpool",
    "Manchester City": "Manchester_City",
    "Manchester Utd": "Manchester_United",
    "Newcastle United": "Newcastle_United",
    "Nottingham Forest": "Nottingham_Forest",
    "Sunderland": "Sunderland",
    "Tottenham Hotspur": "Tottenham_Hotspur",
    "West Ham United": "West_Ham_United",
    "Wolves": "Wolverhampton_Wanderers",
}

# 유효 포지션 토큰 (football-lineups 표기)
VALID_POS = {
    "GK", "CB", "RB", "LB", "RWB", "LWB", "WB",
    "DM", "CM", "BX", "AM", "RM", "LM", "MF", "DF",
    "LW", "RW", "WF", "SS", "ST", "FW",
}


def flare_get(url: str, max_timeout: int = 60000) -> str | None:
    """FlareSolverr로 Cloudflare 우회해 HTML 획득. 실패 시 None."""
    try:
        r = requests.post(FLARE, json={
            "cmd": "request.get", "url": url, "maxTimeout": max_timeout,
        }, timeout=max_timeout / 1000 + 30)
    except Exception as e:
        print(f"  [FlareSolverr 연결 실패] {e}")
        return None
    d = r.json()
    if d.get("status") != "ok":
        print(f"  [FlareSolverr status={d.get('status')}] {d.get('message','')[:80]}")
        return None
    sol = d.get("solution", {})
    if sol.get("status") != 200:
        print(f"  [HTTP {sol.get('status')}]")
        return None
    return sol.get("response", "")


def _is_pos(s: str) -> bool:
    s = s.replace(" ", "")
    return bool(s) and all(p in VALID_POS for p in s.split("/"))


def _split_move(name: str) -> tuple[str, str]:
    """'Malen out15Jan' → ('Malen','out15Jan'),  'D. Luiz in28Jan' → ('D. Luiz','in28Jan')."""
    m = re.search(r"\b(in|out)\d{2}\w{3}$", name)
    if m:
        return name[:m.start()].strip(), m.group(0)
    return name.strip(), ""


def parse_team(html: str) -> tuple[str, list[dict]]:
    """HTML → (formation, players[]).  players: number/name/age/pos/pos2/starts/move.

    행 구조가 팀마다 조금씩 달라(<script> 팝업·번호 '-' 등), '나이(2자리)+포지션'
    조합을 앵커로 잡아 견고하게 파싱한다.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style"]):   # 셀 내부 팝업 스크립트 제거
        tag.decompose()

    # 포메이션 — EPL 등 경기별 표기 중 최빈값
    forms = re.findall(r"\b([1-5]-[1-5](?:-[1-5]){1,2})\b", html)
    formation = Counter(forms).most_common(1)[0][0] if forms else ""

    players: list[dict] = []
    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 4:
            continue
        # 나이(2자리) 바로 뒤가 포지션인 지점을 찾는다.
        j = None
        for k in range(1, len(cells) - 1):
            if re.fullmatch(r"\d{2}", cells[k]) and _is_pos(cells[k + 1]):
                j = k
                break
        if j is None or j < 1:
            continue
        number = cells[0] if re.fullmatch(r"\d{1,2}", cells[0]) else ""
        name, move = _split_move(cells[j - 1])
        if not name or name in {"-", "(c)"}:
            continue
        pos_parts = cells[j + 1].replace(" ", "").split("/")
        starts = cells[j + 2] if len(cells) > j + 2 and re.fullmatch(r"[\d-]+", cells[j + 2]) else ""
        players.append({
            "fl_number": number,
            "fl_name": name,
            "age": cells[j],
            "fl_pos": pos_parts[0],
            "fl_pos2": pos_parts[1] if len(pos_parts) > 1 else "",
            "starts": starts,
            "move": move,
        })

    # 이름 기준 dedup — 번호 있는 행 / 출전수 많은 행 우선(요약행 중복 제거)
    def _starts_int(p):
        return int(p["starts"]) if p["starts"].isdigit() else -1
    best: dict[str, dict] = {}
    for p in players:
        k = p["fl_name"]
        cur = best.get(k)
        if cur is None:
            best[k] = p
            continue
        better = (bool(p["fl_number"]), _starts_int(p)) > (bool(cur["fl_number"]), _starts_int(cur))
        if better:
            best[k] = p
    return formation, list(best.values())


def scrape_team(team: str) -> tuple[str, list[dict]] | None:
    slug = TEAM_FL.get(team)
    if not slug:
        print(f"  [건너뜀] slug 없음: {team}")
        return None
    url = f"https://www.football-lineups.com/season/{slug}/{SEASON}"
    print(f"  [{team}] {url}")
    html = flare_get(url)
    if not html:
        return None
    formation, players = parse_team(html)
    print(f"    포메이션={formation} · 선수 {len(players)}명")
    return formation, players


def parse_match_list(html: str) -> list[dict]:
    """시즌 페이지 → 경기별 [{date, comp, opponent, formation, match_id}] (날짜순).

    football-lineups는 같은 달 2번째 경기부터 월을 생략("23 Tottenham")하므로
    직전 경기의 월을 상속한다. 날짜 없는 광고/추천 행은 자동 제외된다.
    """
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    cur_mon: str | None = None
    seen: set[str] = set()
    for a in soup.select('a[href*="/match/"]'):
        tr = a.find_parent("tr")
        if not tr:
            continue
        mid_m = re.search(r"/match/(\d+)", a.get("href", ""))
        if not mid_m:
            continue
        mid = mid_m.group(1)
        txt = tr.get_text(" ", strip=True)
        dm = re.match(r"^\s*(\d{1,2})(?:-([A-Z][a-z]{2}))?\b", txt)
        if not dm:
            continue
        day, mon = dm.group(1), dm.group(2)
        if mon:
            cur_mon = mon
        if not cur_mon or cur_mon not in _MONTHS or mid in seen:
            continue
        seen.add(mid)
        yr = "2026" if cur_mon in _H1 else "2025"
        date = f"{yr}-{_MONTHS[cur_mon]}-{int(day):02d}"
        fm = re.search(r"\b([1-5]-[1-5](?:-[1-5]){1,2})\b", txt)
        comp = next((c for c in _COMPS if c in txt), "")
        rest = txt[dm.end():]
        opp = re.split(r"\b(?:%s)\b" % "|".join(_COMPS), rest)[0].strip()
        rows.append({
            "date": date, "comp": comp, "opponent": opp,
            "formation": fm.group(1) if fm else "", "match_id": mid,
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def scrape_team_matches(team: str) -> list[dict] | None:
    slug = TEAM_FL.get(team)
    if not slug:
        print(f"  [건너뜀] slug 없음: {team}")
        return None
    url = f"https://www.football-lineups.com/season/{slug}/{SEASON}"
    print(f"  [{team}] {url}")
    html = flare_get(url)
    if not html:
        return None
    rows = parse_match_list(html)
    for r in rows:
        r["squad"] = team
    n_epl = sum(1 for r in rows if r["comp"] == "EPL")
    print(f"    경기 {len(rows)}개 (EPL {n_epl})")
    return rows


def save_matches(team: str, rows: list[dict]) -> None:
    cols = ["squad", "date", "comp", "opponent", "formation", "match_id"]
    df_new = pd.DataFrame(rows)[cols]
    if MATCHES_OUT.exists():
        old = pd.read_csv(MATCHES_OUT)
        old["match_id"] = old["match_id"].astype(str)
        old = old[old["squad"] != team]            # 해당 팀 기존 행 교체
        df_new = pd.concat([old, df_new], ignore_index=True)
    df_new.to_csv(MATCHES_OUT, index=False, encoding="utf-8")
    print(f"  [OK] 저장: {MATCHES_OUT.name} ({team} {len(rows)}경기)")


def save(team: str, formation: str, players: list[dict]) -> None:
    df_new = pd.DataFrame(players)
    df_new.insert(0, "squad", team)
    df_new["formation"] = formation
    if OUT.exists():
        old = pd.read_csv(OUT)
        old = old[old["squad"] != team]            # 해당 팀 기존 행 교체
        df_new = pd.concat([old, df_new], ignore_index=True)
    df_new.to_csv(OUT, index=False, encoding="utf-8")
    print(f"  [OK] 저장: {OUT.name} ({team} {len(players)}명)")


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    if dry:
        args.remove("--dry")
    all_teams = "--all" in args
    if all_teams:
        args.remove("--all")
    matches_mode = "--matches" in args        # 경기 목록(날짜·대회·포메이션) 수집
    if matches_mode:
        args.remove("--matches")
    teams = list(TEAM_FL) if all_teams else args
    if not teams:
        print("팀 이름을 지정하거나 --all 을 사용하세요.")
        print("예: python src/fetch_football_lineups.py \"Aston Villa\"")
        print("    python src/fetch_football_lineups.py --all --matches  (경기 목록)")
        return 1

    if matches_mode:
        for i, team in enumerate(teams):
            if i > 0:
                time.sleep(3)
            rows = scrape_team_matches(team)
            if not rows:
                continue
            if dry:
                for r in rows[-12:]:
                    print(f"      {r['date']} {r['comp']:11} "
                          f"{r['opponent'][:16]:16} {r['formation']}")
                print("    [DRY] 저장 안 함.")
            else:
                save_matches(team, rows)
        return 0

    for i, team in enumerate(teams):
        if i > 0:
            time.sleep(3)
        res = scrape_team(team)
        if not res:
            continue
        formation, players = res
        if dry:
            for p in players:
                pos = p["fl_pos"] + (f"/{p['fl_pos2']}" if p["fl_pos2"] else "")
                print(f"      #{p['fl_number']:>2} {p['fl_name']:18} {p['age']}세 "
                      f"{pos:8} 출전{p['starts']:>3} {p['move']}")
            print("    [DRY] 저장 안 함.")
        else:
            save(team, formation, players)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
