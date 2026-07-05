"""FIFA 남자 세계 랭킹 수집 — 공식 FIFA API(무료).

fifa.com/fifa-world-ranking/men 페이지에서 최신 dateId 를 자동 탐지한 뒤
inside.fifa.com/api/ranking-overview 로 전체 랭킹을 받아 data/fifa_ranking.csv 에 기록.
순위·점수 + 직전 대비 변동(순위/점수)까지 담아 월드컵 탭 상단에 사용한다.

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
_MAX_PROBE = 12   # date-picker 최신 후보 중 데이터 있는 것까지만 탐색(무한루프 방지)


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


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = fetch()
    if not rows:
        print("[fifa] 항목 없음 — 기존 파일 유지", file=sys.stderr)
        return 1
    fields = ["rank", "team", "code", "points", "previous_rank", "previous_points",
              "rank_change", "points_change", "confederation", "flag", "updated"]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    up = rows[0]["updated"]
    print(f"[fifa] {len(rows)}개국 기록 (기준일 {up}) -> {OUT_PATH}")
    print("  TOP5: " + " · ".join(f"{r['rank']}.{r['team']}({r['points']})" for r in rows[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
