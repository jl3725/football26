"""
Transfermarkt 스쿼드 스크래퍼 — 시장가치 + 포지션 + 나이 + 국적 + 사진.

players_2025_2026.csv 의 기존 행에 매칭해 다음 컬럼을 채운다(기존 스탯은 보존):
  · market_value_eur (현재 100% 결측 → 복원)
  · nationality, tm_position, tm_photo

팀당 1페이지(detailed kader)만 받으므로 20팀 ≈ 20요청. Sofascore Cloudflare보다
훨씬 가볍지만, 예의상 팀 간 3초 대기.

사용:
    python src/fetch_transfermarkt.py            # EPL 전 팀(저장)
    python src/fetch_transfermarkt.py "Arsenal"  # 특정 팀만
    python src/fetch_transfermarkt.py "Arsenal" --dry   # 저장 안 하고 매칭 확인
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

DATA = Path(__file__).resolve().parent.parent / "data"
from leagues import ACTIVE_LEAGUE, data_path  # noqa: E402

PLAYERS = data_path("players_full")
if not PLAYERS.exists():
    PLAYERS = data_path("players")
SEASON = 2025

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html"}

# 우리 squad 이름 → (Transfermarkt slug, verein id). id가 라우팅 핵심(slug는 표시용).
EPL_TEAM_TM: dict[str, tuple[str, int]] = {
    "Arsenal": ("fc-arsenal", 11),
    "Aston Villa": ("aston-villa", 405),
    "Bournemouth": ("afc-bournemouth", 989),
    "Brentford": ("fc-brentford", 1148),
    "Brighton": ("brighton-amp-hove-albion", 1237),
    "Burnley": ("fc-burnley", 1132),
    "Chelsea": ("fc-chelsea", 631),
    "Crystal Palace": ("crystal-palace", 873),
    "Everton": ("fc-everton", 29),
    "Fulham": ("fc-fulham", 931),
    "Leeds United": ("leeds-united", 399),
    "Liverpool": ("fc-liverpool", 31),
    "Manchester City": ("manchester-city", 281),
    "Manchester Utd": ("manchester-united", 985),
    "Newcastle United": ("newcastle-united", 762),
    "Nottingham Forest": ("nottingham-forest", 703),
    "Sunderland": ("afc-sunderland", 289),
    "Tottenham Hotspur": ("tottenham-hotspur", 148),
    "West Ham United": ("west-ham-united", 379),
    "Wolves": ("wolverhampton-wanderers", 543),
}

LALIGA_TEAM_TM: dict[str, tuple[str, int]] = {
    "Alavés": ("deportivo-alaves", 1108),
    "Athletic Club": ("athletic-bilbao", 621),
    "Atlético Madrid": ("atletico-madrid", 13),
    "Barcelona": ("fc-barcelona", 131),
    "Celta Vigo": ("celta-vigo", 940),
    "Elche": ("fc-elche", 1531),
    "Espanyol": ("espanyol-barcelona", 714),
    "Getafe": ("fc-getafe", 3709),
    "Girona": ("fc-girona", 12321),
    "Levante": ("ud-levante", 3368),
    "Mallorca": ("rcd-mallorca", 237),
    "Osasuna": ("ca-osasuna", 331),
    "Oviedo": ("real-oviedo", 2497),
    "Rayo Vallecano": ("rayo-vallecano", 367),
    "Real Betis": ("real-betis-sevilla", 150),
    "Real Madrid": ("real-madrid", 418),
    "Real Sociedad": ("real-sociedad-san-sebastian", 681),
    "Sevilla": ("fc-sevilla", 368),
    "Valencia": ("fc-valencia", 1049),
    "Villarreal": ("fc-villarreal", 1050),
}

SERIEA_TEAM_TM: dict[str, tuple[str, int]] = {
    "Atalanta": ("atalanta-bergamo", 800),
    "Bologna": ("fc-bologna", 1025),
    "Cagliari": ("cagliari-calcio", 1390),
    "Como": ("como-1907", 1047),
    "Cremonese": ("us-cremonese", 2239),
    "Fiorentina": ("ac-florenz", 430),
    "Genoa": ("fc-genua", 252),
    "Hellas Verona": ("hellas-verona", 276),
    "Inter": ("inter-mailand", 46),
    "Juventus": ("juventus-turin", 506),
    "Lazio": ("lazio-rom", 398),
    "Lecce": ("us-lecce", 1005),
    "Milan": ("ac-mailand", 5),
    "Napoli": ("ssc-neapel", 6195),
    "Parma": ("parma-calcio-1913", 130),
    "Pisa": ("pisa-sporting-club", 4171),
    "Roma": ("as-rom", 12),
    "Sassuolo": ("us-sassuolo", 6574),
    "Torino": ("fc-turin", 416),
    "Udinese": ("udinese-calcio", 410),
}

TEAM_TM_BY_LEAGUE: dict[str, dict[str, tuple[str, int]]] = {
    "EPL": EPL_TEAM_TM,
    "LaLiga": LALIGA_TEAM_TM,
    "SerieA": SERIEA_TEAM_TM,
}

TEAM_TM: dict[str, tuple[str, int]] = TEAM_TM_BY_LEAGUE.get(ACTIVE_LEAGUE, EPL_TEAM_TM)


# verein id → 우리 squad 표기 (현재 소속 클럽 역매핑용)
_VID_TO_SQUAD: dict[int, str] = {vid: sq for sq, (_slug, vid) in TEAM_TM.items()}


def norm(s) -> str:
    return unidecode(str(s)).lower().strip()


# 우리 CSV 표기 → TM 검색 질의 보정(별칭·애칭·단일이름 모호성 해소).
# key는 norm() 적용한 우리 player 이름. value는 TM에서 잘 잡히는 검색어.
TM_ALIAS: dict[str, str] = {
    "savio": "Savinho",            # Man City — TM 표기 Savinho
    "lucas": "Lucas Pires",        # Burnley — 단일이름 'Lucas'(브라질 LB)
    "yehor yarmoliuk": "Yarmolyuk",  # Brentford — 음역차(Yehor↔Yegor, i↔y)
    "igor": "Igor Julio",          # West Ham(→Brighton) — 단일이름 'Igor'(브라질 CB)
    "john": "John Victor",         # Nott'm Forest — 단일이름 'John'(브라질 GK)
}


def parse_mv(s: str) -> int | None:
    """'€30.00m' → 30000000, '€500k' → 500000, '-'/'' → None."""
    s = (s or "").strip().lower().replace("€", "").replace(",", "")
    m = re.match(r"([\d.]+)\s*([mk]?)", s)
    if not m or not m.group(1):
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return int(val * 1_000_000)
    if unit == "k":
        return int(val * 1_000)
    return int(val) if val else None


def search_player(name: str) -> dict | None:
    """TM 빠른검색으로 선수 1명 프로필을 가져온다(현 소속과 무관).

    스쿼드 페이지에서 못 찾은 선수(여름 이적·별칭 불일치 등) 보완용.
    예: 'Sávio' → Savinho, 'Antoine Semenyo' → 현 소속이 어디든 데이터 확보.
    반환 dict 키: name/norm/pos/age/nat/mv/photo/id. 결과 없으면 None.
    """
    from urllib.parse import quote
    url = ("https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
           f"?query={quote(name)}")
    try:
        r = requests.get(url, headers=H, timeout=20)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    row = soup.select_one("table.items tbody tr")
    if not row:
        return None
    a = row.select_one("td.hauptlink a")
    if not a:
        return None
    nm = a.get_text(strip=True)
    # 안전장치: 검색 결과의 성(last token)이 질의와 일치해야 채택(오매칭 방지)
    if norm(name).split()[-1] not in norm(nm):
        return None
    mid = re.search(r"/spieler/(\d+)", a.get("href", ""))
    pid = mid.group(1) if mid else ""
    # 포지션 = 첫 zentriert 셀 / 나이 = 숫자 zentriert / 국적 = 깃발 title
    zs = row.select("td.zentriert")
    pos = zs[0].get_text(strip=True) if zs else ""
    age = None
    for td in zs:
        t = td.get_text(strip=True)
        if t.isdigit():
            age = int(t); break
    flag = row.select_one("img.flaggenrahmen")
    nat = flag.get("title") if flag else ""
    mv_el = row.select_one("td.rechts.hauptlink") or row.select_one("td.rechts")
    mv = parse_mv(mv_el.get_text(strip=True)) if mv_el else None
    photo = (f"https://img.a.transfermarkt.technology/portrait/medium/{pid}.png"
             if pid else "")
    # 현재 소속 클럽 — 엠블럼 URL의 verein id로 우리 팀명 역매핑
    club_img = row.find("img", src=re.compile(r"/wappen/"))
    club_vid = None
    club_name = ""
    if club_img:
        club_name = (club_img.get("alt") or club_img.get("title") or "").strip()
        mvid = re.search(r"/wappen/\w+/(\d+)\.png", club_img.get("src", ""))
        if mvid:
            club_vid = int(mvid.group(1))
    club = _VID_TO_SQUAD.get(club_vid, "")   # PL 팀이면 우리 표기, 아니면 ""
    return {"name": nm, "norm": norm(nm), "pos": pos, "age": age,
            "nat": nat, "mv": mv, "photo": photo, "id": pid,
            "club": club, "club_vid": club_vid, "club_name": club_name}


def scrape_team(team: str) -> list[dict]:
    slug, vid = TEAM_TM[team]
    url = f"https://www.transfermarkt.com/{slug}/kader/verein/{vid}/saison_id/{SEASON}/plus/1"
    r = requests.get(url, headers=H, timeout=25)
    if r.status_code != 200:
        print(f"  [{team}] HTTP {r.status_code}")
        return []
    soup = BeautifulSoup(r.text, "lxml")
    tbl = soup.select_one("table.items")
    if not tbl:
        print(f"  [{team}] 스쿼드 테이블 없음")
        return []
    out = []
    for tr in tbl.select("tbody > tr.odd, tbody > tr.even"):
        name_a = tr.select_one("td.posrela .hauptlink a") or tr.select_one("td.hauptlink a")
        if not name_a:
            continue
        name = name_a.get_text(strip=True)
        # 포지션 — 이름 셀 내부 inline-table 2번째 행
        pos = ""
        inline = tr.select_one("td.posrela table.inline-table")
        if inline:
            trs = inline.select("tr")
            if len(trs) > 1:
                pos = trs[1].get_text(strip=True)
        # 나이 — DOB 셀의 (NN)
        age = None
        for td in tr.select("td.zentriert"):
            m = re.search(r"\((\d{1,2})\)", td.get_text())
            if m:
                age = int(m.group(1)); break
        # 국적(첫 번째)
        flag = tr.select_one("img.flaggenrahmen")
        nat = flag.get("title") if flag else ""
        # 시장가치
        mv_el = tr.select_one("td.rechts.hauptlink") or tr.select_one("td.rechts")
        mv = parse_mv(mv_el.get_text(strip=True)) if mv_el else None
        # 사진
        img = tr.select_one("img.bilderrahmen-fixed")
        photo = (img.get("data-src") or img.get("src")) if img else ""
        out.append({"name": name, "norm": norm(name), "pos": pos, "age": age,
                    "nat": nat, "mv": mv, "photo": photo})
    return out


def mark_transfers(dry: bool = False, min_minutes: int = 500) -> int:
    """이적 선수의 옛 소속 행에 left_for(현재 클럽명)를 기록.

    두 종류를 모두 처리:
      (A) 다중 소속(겨울 이적) — 한 시즌 PL 두 팀 → 옛 팀 행에 새 PL팀명
      (B) 단일 소속이지만 현재 타 클럽(리그 외 이적 등) — 옛 팀 행에 현 클럽명
          예: Lucas Paquetá(West Ham 1511분) → 'CR Flamengo'
    판정 기준: TM 검색의 '현재 소속 클럽'.
      · squad == 현재클럽  → left_for = "" (현 소속, 정상 노출)
      · squad != 현재클럽  → left_for = 현재클럽 (이 팀에서 떠남)
    앱은 left_for가 있는 행을 '이적' 배지로 표시하고 전술판/벤치에서 제외한다.
    min_minutes: 단일소속 선수는 이 출전시간 이상만 조회(요청량 절감).
    """
    df = pd.read_csv(PLAYERS)
    if "left_for" not in df.columns:
        df["left_for"] = pd.NA
    df["left_for"] = df["left_for"].astype("object")
    df["__norm"] = df["player"].map(norm)

    # 다중 소속(겨울 PL→PL 이적) 선수 — 출전시간 무관 전 행을 후보에 포함
    cnt = df.groupby("player")["squad"].nunique()
    multi = set(cnt[cnt > 1].index)

    # ── 1단계: 팀별 현재 스쿼드 스크랩 → '현 로스터에 없는' 우리 선수 = 이적 후보 ──
    # 250명 전수 검색 대신, 스쿼드 페이지(20요청)로 후보(~수십명)만 추린다.
    cand_idx: set[int] = set()
    candidates: list[tuple[int, str, str]] = []   # (idx, player, squad)

    def add_cand(idx, player, squad):
        if idx not in cand_idx:
            cand_idx.add(idx)
            candidates.append((idx, player, squad))

    for ti, team in enumerate(TEAM_TM):
        if ti > 0:
            time.sleep(2)
        recs = scrape_team(team)
        present_full = {r["norm"] for r in recs}
        present_last = {r["norm"].split()[-1] for r in recs}
        sub = df[df["squad"] == team]
        for idx, r in sub.iterrows():
            nk = r["__norm"]
            here = nk in present_full or nk.split()[-1] in present_last
            # 출전 多 + 로스터 부재, 또는 다중소속(전 행) → 후보
            if (r["minutes"] >= min_minutes and not here) or (r["player"] in multi):
                add_cand(idx, r["player"], team)
        print(f"  [{team}] 이적후보 {sum(1 for c in candidates if c[2]==team)}명")

    print(f"\n이적 후보 {len(candidates)}명 — TM 현재 소속 확인 중 ...")

    # ── 2단계: 후보만 검색해 현재 클럽 확정 → left_for 기록 ──────────────────────
    n_left = 0
    for idx, player, squad in candidates:
        q = TM_ALIAS.get(norm(player), player)
        rec = search_player(q)
        time.sleep(1.2)
        if not rec:
            continue
        cur = rec.get("club") or rec.get("club_name") or ""   # PL이면 우리표기, 아니면 텍스트
        if not cur or cur == squad:
            continue                                          # 현 소속 동일 → 이적 아님(별칭 등)
        df.at[idx, "left_for"] = cur
        n_left += 1
        print(f"  {player:24} {squad:18} → {cur}")

    df = df.drop(columns="__norm")
    print(f"\n이적 표시: {n_left}개 행")
    if dry:
        print("[DRY] 저장 안 함."); return 0
    df.to_csv(PLAYERS, index=False, encoding="utf-8")
    print(f"[OK] 저장: {PLAYERS.name} (left_for 기록)")
    return 0


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    if dry:
        args.remove("--dry")
    if "--mark-transfers" in args:
        return mark_transfers(dry=dry)
    no_search = "--no-search" in args
    if no_search:
        args.remove("--no-search")
    search_min = 300
    for a in list(args):
        if a.startswith("--search-min="):
            search_min = int(a.split("=", 1)[1]); args.remove(a)
    teams = args if args else list(TEAM_TM)

    df = pd.read_csv(PLAYERS)
    df["__norm"] = df["player"].map(norm)
    for col in ("market_value_eur", "nationality", "tm_position", "tm_photo"):
        if col not in df.columns:
            df[col] = pd.NA

    grand_m = grand_t = 0
    for i, team in enumerate(teams):
        if team not in TEAM_TM:
            print(f"  [건너뜀] 알 수 없는 팀: {team}")
            continue
        if i > 0:
            time.sleep(3)
        recs = scrape_team(team)
        sub = df[df["squad"] == team]
        used: set[int] = set()    # 이미 채운 우리 CSV 행 (중복 배정 방지)

        def apply(idx: int, rec: dict) -> None:
            if rec["mv"] is not None:
                df.at[idx, "market_value_eur"] = rec["mv"]
            df.at[idx, "nationality"] = rec["nat"]
            df.at[idx, "tm_position"] = rec["pos"]
            df.at[idx, "tm_photo"] = rec["photo"]
            if pd.isna(df.at[idx, "age"]) and rec["age"]:
                df.at[idx, "age"] = rec["age"]
            used.add(idx)

        # ── 1차: 정확 일치(full norm)부터 확정 ───────────────────────────
        # 단일 이름(예: TM "Gabriel" = Magalhães)이 성 폴백으로 다른 Gabriel을
        # 가로채지 않도록, 확실한 정확 매칭을 먼저 소비한다.
        pending: list[dict] = []
        for rec in recs:
            cand = sub[sub["__norm"] == rec["norm"]]
            if not cand.empty:
                apply(cand.index[0], rec)
            else:
                pending.append(rec)

        # ── 2차: 남은 TM 레코드를 '아직 안 쓰인' 우리 행과 성(last token) 매칭 ─
        unmatched: list[str] = []
        for rec in pending:
            ln = rec["norm"].split()[-1]
            cand = sub[(sub["__norm"].str.contains(re.escape(ln), regex=True))
                       & (~sub.index.isin(used))]
            if cand.empty:                       # TM 이름 전체로 부분일치 재시도
                cand = sub[(sub["__norm"].str.contains(re.escape(rec["norm"]), regex=True))
                           & (~sub.index.isin(used))]
            if cand.empty:
                unmatched.append(rec["name"]); continue
            apply(cand.index[0], rec)

        # ── 3차: 우리 CSV에 남은 주력 선수(출전 多)를 이름 검색으로 보완 ──────
        # 스쿼드 페이지는 '현재 로스터'라, 시즌 중 이적/방출된 선수(Semenyo·
        # Paquetá 등)·별칭 불일치(Sávio→Savinho)는 여기서만 채워진다.
        searched = 0
        if not no_search:
            ours_miss = sub[(~sub.index.isin(used)) & (sub["minutes"] >= search_min)]
            for idx, row in ours_miss.iterrows():
                alias = TM_ALIAS.get(norm(row["player"]))
                q = alias or row["player"]
                # 단일 토큰 이름은 모호('Lucas'→Lucas Hernández 오매칭) → 스킵.
                # 단, 큐레이션된 별칭이면 단일 토큰이라도 신뢰하고 검색.
                if alias is None and len(norm(q).split()) < 2:
                    continue
                time.sleep(1.5)
                rec = search_player(q)
                if rec and rec["mv"] is not None:
                    apply(idx, rec)
                    searched += 1

        matched = len(used)
        grand_m += matched; grand_t += len(sub)
        msg = f"  [{team}] TM {len(recs)}명 · 매칭 {matched}/{len(sub)}"
        if searched:
            msg += f" (검색보완 {searched})"
        if unmatched:
            msg += f" · TM에만: {', '.join(unmatched[:5])}" + (" ..." if len(unmatched) > 5 else "")
        print(msg)

    print(f"\n총 매칭 {grand_m}/{grand_t}")
    if dry:
        print("[DRY] 저장 안 함.")
        return 0
    df = df.drop(columns="__norm")
    df.to_csv(PLAYERS, index=False, encoding="utf-8")
    print(f"[OK] 저장: {PLAYERS.name} (market_value_eur 등 채움)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
