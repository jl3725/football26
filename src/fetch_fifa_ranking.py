"""FIFA 남자 세계 랭킹 수집 — 위키피디아(최신) + FIFA API(폴백·전체 커버).

FIFA 무료 API(inside.fifa.com/api/ranking-overview)는 id 포맷 변경 후 2025-09 까지만
데이터를 주고 이후는 빈 응답이라, 최신 공식 랭킹은 위키피디아에서 가져온다:
- 위키 'FIFA Men's World Ranking' 표(Top 20, 현재 공식 기준일·점수·순위) = 최신.
- FIFA API(전체 ~210개국, 다소 과거) = 국가코드/국기/대륙 + 하위권 커버(월드컵 실시간
  예상 랭킹 산식이 전 참가국 base 점수를 필요로 함) 용도.
→ 위키 최신 Top20 점수/순위를 API 전체 위에 덮어써서 data/fifa_ranking.csv 생성.
stdlib(urllib/re)만 사용 → daily_wc.yml(무-pip) 에서도 동작.

사용:
    python src/fetch_fifa_ranking.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "fifa_ranking.csv"

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept": "application/json"}
PAGE = "https://www.fifa.com/fifa-world-ranking/men"
API = "https://inside.fifa.com/api/ranking-overview?locale=en&dateId={}"
WIKI = "https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking"
_MAX_PROBE = 12   # date-picker 최신 후보 중 데이터 있는 것까지만 탐색(무한루프 방지)
_MONTHS = {"january": "01", "february": "02", "march": "03", "april": "04",
           "may": "05", "june": "06", "july": "07", "august": "08",
           "september": "09", "october": "10", "november": "11", "december": "12"}
# 위키 팀명 → FIFA API 팀명 정합(대부분 동일, 예외만)
_WIKI_ALIAS = {"IR Iran": "Iran", "Korea Republic": "South Korea",
               "United States": "USA", "Ivory Coast": "Côte d'Ivoire"}


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _ranking_date_ids() -> list[str]:
    """랭킹 페이지 date-picker 에서 dateId 를 날짜(matchWindowEndDate) 내림차순으로.

    FIFA 가 id 포맷을 바꿔서(구: 'id14870' 숫자형, 신: 'FRS_Male_Football_YYYYMMDD')
    '가장 큰 숫자 id' 방식은 최신을 못 잡는다. date-picker 의 실제 날짜로 정렬해
    최신부터 후보를 만든 뒤, fetch() 가 '데이터가 실제로 있는 첫 dateId' 를 고른다.
    (신 포맷 날짜는 API 에 아직 데이터가 없어 빈 응답 → 자동으로 다음 후보로 폴백)
    """
    try:
        html = _get(PAGE)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[fifa] 페이지 로드 실패: {exc}", file=sys.stderr)
        return []
    entries = re.findall(
        r'"id":"([^"]+)","iso":"[^"]*","dateText":"[^"]*","matchWindowEndDate":"(\d{4}-\d{2}-\d{2})"',
        html,
    )
    uniq: dict[str, str] = {}
    for i, d in entries:
        uniq.setdefault(i, d)
    return [i for i, _ in sorted(uniq.items(), key=lambda x: x[1], reverse=True)]


def _parse_rows(data: dict) -> list[dict]:
    rows = []
    for e in data.get("rankings", []):
        it = e.get("rankingItem") or {}
        rank = it.get("rank")
        if rank is None:
            continue
        prev_rank = it.get("previousRank") or rank
        pts = float(it.get("totalPoints") or 0)
        prev_pts = float(e.get("previousPoints") or pts)
        rows.append({
            "rank": int(rank),
            "team": str(it.get("name") or ""),
            "code": str(it.get("countryCode") or ""),
            "points": round(pts, 2),
            "previous_rank": int(prev_rank),
            "previous_points": round(prev_pts, 2),
            "rank_change": int(prev_rank) - int(rank),      # +면 상승
            "points_change": round(pts - prev_pts, 2),
            "confederation": str((e.get("tag") or {}).get("text") or ""),
            "flag": str((it.get("flag") or {}).get("src") or ""),
            "updated": str(it.get("lastUpdateDate") or e.get("lastUpdateDate") or "")[:10],
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def fetch(date_id: str | None = None) -> list[dict]:
    """최신 날짜부터 후보 dateId 를 훑어 데이터가 있는 첫 랭킹을 반환."""
    candidates = [date_id] if date_id else _ranking_date_ids()[:_MAX_PROBE]
    for cid in candidates:
        try:
            data = json.loads(_get(API.format(cid), timeout=20))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[fifa] API 실패({cid}): {exc}", file=sys.stderr)
            continue
        rows = _parse_rows(data)
        if rows:
            return rows
    return []


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def fetch_wikipedia() -> tuple[str, list[dict]]:
    """위키 'FIFA Men's World Ranking' 최신 표 → (기준일 ISO, [{rank, team, points}])."""
    try:
        html = _get(WIKI, timeout=25)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[fifa] 위키 로드 실패: {exc}", file=sys.stderr)
        return "", []
    md = re.search(r"rankings as of (\d{1,2}) (\w+) (\d{4})", html)
    updated = ""
    if md:
        updated = f"{md.group(3)}-{_MONTHS.get(md.group(2).lower(), '01')}-{int(md.group(1)):02d}"
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(cells) < 4:
            continue
        rank_s, team_s, pts_s = _strip(cells[0]), _strip(cells[2]), _strip(cells[3])
        if not rank_s.isdigit():
            continue
        try:
            pts = float(pts_s.replace(",", ""))
        except ValueError:
            continue
        team = _WIKI_ALIAS.get(team_s, team_s)
        if team:
            rows.append({"rank": int(rank_s), "team": team, "points": pts})
    return updated, rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base = fetch()                       # FIFA API 전체(코드/국기/대륙 + 하위권 커버, 다소 과거)
    wdate, wiki = fetch_wikipedia()      # 위키 최신 Top20(공식 기준일·점수·순위)

    if not base and not wiki:
        print("[fifa] 항목 없음 — 기존 파일 유지", file=sys.stderr)
        return 1

    fields = ["rank", "team", "code", "points", "previous_rank", "previous_points",
              "rank_change", "points_change", "confederation", "flag", "updated"]

    if wiki and base:
        # 위키 최신 Top20 을 API 전체 위에 덮어씀 — 코드/국기/대륙은 API 에서 보존.
        by_name = {r["team"].lower(): r for r in base}
        used = set()
        merged = []
        for w in sorted(wiki, key=lambda x: x["rank"]):
            b = by_name.get(w["team"].lower())
            code = (b or {}).get("code", "")
            merged.append({
                "rank": w["rank"], "team": w["team"], "code": code,
                "points": round(w["points"], 2), "previous_rank": w["rank"],
                "previous_points": round(w["points"], 2), "rank_change": 0, "points_change": 0.0,
                "confederation": (b or {}).get("confederation", ""),
                "flag": (b or {}).get("flag", ""), "updated": wdate,
            })
            if b:
                used.add(b["code"])
        # 위키에 없는 하위권(21위~) = API 값 유지(월드컵 예상 산식의 전 참가국 base 확보)
        tail = [r for r in base if r["code"] not in used]
        tail.sort(key=lambda r: -_num_pts(r))
        for i, r in enumerate(tail, start=len(merged) + 1):
            r = dict(r)
            r["rank"] = i
            r["updated"] = wdate or r.get("updated", "")
            merged.append(r)
        rows = merged
        src = f"위키 Top{len(wiki)} 최신 + API 하위권"
    else:
        rows = wiki_to_rows(wiki, wdate) if wiki else base
        src = "위키 전용" if wiki else "API 전용(폴백)"

    with OUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    up = rows[0].get("updated", "")
    print(f"[fifa] {len(rows)}개국 기록 (기준일 {up} · {src}) -> {OUT_PATH}")
    print("  TOP5: " + " · ".join(f"{r['rank']}.{r['team']}({r['points']})" for r in rows[:5]))
    return 0


def _num_pts(r: dict) -> float:
    try:
        return float(r.get("points") or 0)
    except (TypeError, ValueError):
        return 0.0


def wiki_to_rows(wiki: list[dict], wdate: str) -> list[dict]:
    """API 폴백 실패 시 위키만으로 CSV 행 구성(코드/국기 없음 → 예상 산식은 제한적)."""
    out = []
    for w in sorted(wiki, key=lambda x: x["rank"]):
        out.append({"rank": w["rank"], "team": w["team"], "code": "",
                    "points": round(w["points"], 2), "previous_rank": w["rank"],
                    "previous_points": round(w["points"], 2), "rank_change": 0,
                    "points_change": 0.0, "confederation": "", "flag": "", "updated": wdate})
    return out


if __name__ == "__main__":
    raise SystemExit(main())
