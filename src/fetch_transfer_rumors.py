"""Transfermarkt 구단 루머(Gerüchte) 수집 — 클럽에 링크된 이적 후보 + 확률(%).

각 클럽 /geruechte/verein/{verein_id} 페이지에서 '영입 링크' 선수를 긁는다:
  target_club · player · pos_detail · age · current_club · market_value_eur · probability · date · source
→ data/transfer_rumors_<리그>.csv  (AI 1차 분석 rumor_eval.py 의 입력)

리그: FB_LEAGUE 환경변수(기본 EPL). 사용: FB_LEAGUE=EPL python src/fetch_transfer_rumors.py
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import requests

import tm_http  # noqa: E402  — 클라우드(WAF 202)에서도 열리게: 202 면 브라우저 토큰 후 재요청
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_transfermarkt import season_clubs  # noqa: E402  (시즌 소속 팀→(slug, verein))
from leagues import ACTIVE_LEAGUE, data_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "en"}
URL = "https://www.transfermarkt.com/{slug}/geruechte/verein/{vid}"


def _mv_eur(txt: str):
    m = re.search(r"€\s*([\d.]+)\s*(m|k|bn)?", txt or "", re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    return val * {"m": 1e6, "k": 1e3, "bn": 1e9}.get(unit, 1.0)


def _club_name(td) -> str:
    a = td.find("a")
    if a:
        if a.get("title"):
            return a["title"].strip()
        img = a.find("img")
        if img and img.get("alt"):
            return img["alt"].strip()
        if a.get_text(strip=True):
            return a.get_text(strip=True)
    return ""


def confirmed_empty(html: str) -> bool:
    """TM 이 '루머 없음'을 보여 주는 진짜 페이지인지 — 루머 표가 없고 'Rumours about signings … No information' 상자가 있다.
    2026-10-22 Eredivisie·스위스가 18팀·12팀 전부 0건이라 '수집 0 — 실패'로 빨간불이 떴는데, 실제로 TM 에 루머가 없었다.
    차단·챌린지 페이지(표도 상자도 없음)는 False → 예전처럼 실패로 둔다."""
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one("table.items tbody tr"):
        return False
    for box in soup.select(".box"):
        t = box.get_text(" ", strip=True)
        if "Rumours" in t and re.search(r"No information|No entries", t):
            return True
    return False


def _parse(html: str, club: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tbl = soup.select_one("table.items") or soup.select_one("table")
    rows = tbl.select("tbody > tr") if tbl else []
    out = []
    for tr in rows:
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 8:
            continue
        # 선수셀엔 사진링크(빈 텍스트)가 먼저 옴 → 텍스트 있는 첫 링크가 이름
        name = next((a.get_text(strip=True) for a in tds[1].find_all("a") if a.get_text(strip=True)), "")
        if not name:
            continue
        full = re.sub(r"\s+", " ", tds[1].get_text(" ", strip=True))
        pos = full.replace(name, "", 1).strip() or None
        age = tds[3].get_text(strip=True)
        prob_txt = tds[7].get_text(strip=True)
        pm = re.search(r"(\d{1,3})", prob_txt)
        out.append({
            "target_club": club, "player": name, "pos_detail": pos,
            "age": int(age) if age.isdigit() else None,
            "current_club": _club_name(tds[4]),
            "market_value_eur": _mv_eur(tds[5].get_text(strip=True)),
            "probability": int(pm.group(1)) if pm else None,
            "date": tds[6].get_text(strip=True),
        })
    return out


def main() -> int:
    league = ACTIVE_LEAGUE
    allrows: list[dict] = []
    failed: list[str] = []
    teams = sorted(season_clubs(league).items())
    empty: set[str] = set()      # TM 이 '루머 없음'이라고 보여 준 팀

    def fetch(team, slug, vid):
        r = tm_http.get(URL.format(slug=slug, vid=vid), headers=H, timeout=20)
        if r.status_code != 200:   # 202 = WAF 챌린지
            raise requests.RequestException(f"HTTP {r.status_code}")
        rows = _parse(r.text, team)
        if not rows and confirmed_empty(r.text):
            empty.add(team)
        return rows

    for i, (team, (slug, vid)) in enumerate(teams, 1):
        try:
            rows = fetch(team, slug, vid)
        except requests.RequestException as exc:
            print(f"  [{team}] 실패: {str(exc)[:50]}", file=sys.stderr)
            failed.append(team)
            continue
        allrows.extend(rows)
        print(f"  [{i:2}/{len(teams)}] {team:18} 루머 {len(rows)}")
        time.sleep(1.5)
    # 실패 팀만 잠시 뒤 한 번 더 — TM 차단(202·끊김)은 순간적인 경우가 많아 하루 두 번 중 한 번씩 실패로 끝났다(2026-10-19 점검)
    if failed:
        time.sleep(20)
        retry, failed = failed, []
        for team in retry:
            slug, vid = dict(teams)[team]
            try:
                rows = fetch(team, slug, vid)
            except requests.RequestException as exc:
                print(f"  [{team}] 재시도 실패: {str(exc)[:50]}", file=sys.stderr)
                failed.append(team)
                continue
            allrows.extend(rows)
            print(f"  [재시도] {team:18} 루머 {len(rows)}")
            time.sleep(3)

    if not allrows and not (teams and not failed and len(empty) == len(teams)):
        # 0건인데 '루머 없음' 페이지로 확인되지 않은 팀이 있으면(차단·화면 바뀜) 기존 파일을 지키고 실패로
        print(f"[rumors] 수집 0 — 기존 파일 유지(루머 없음 확인 {len(empty)}/{len(teams)}팀)", file=sys.stderr)
        return 1
    if not allrows:
        print(f"[rumors] {league}: 전 팀 루머 없음(TM 'No information' {len(empty)}팀) — 빈 표로 갱신")
    out = data_path("transfer_rumors", league)
    fields = ["target_club", "player", "pos_detail", "age", "current_club",
              "market_value_eur", "probability", "date"]
    if failed and out.exists():
        # 요청이 실패한 팀은 이전 루머를 유지(부분 실패로 팀 루머가 통째로 사라지지 않게).
        with out.open(newline="", encoding="utf-8") as fh:
            allrows += [r for r in csv.DictReader(fh) if r.get("target_club") in failed]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(allrows)
    withp = sum(1 for r in allrows if r["probability"] is not None)
    print(f"[rumors] {league}: {len(allrows)}건 (확률표기 {withp}) -> {out.name}")
    if failed:
        print(f"[rumors] 실패 {len(failed)}팀(이전 루머 유지): {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
