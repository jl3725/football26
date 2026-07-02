"""
구단(팀) 설명을 위키백과에서 자동 수집한다. teammeta 의 하드코딩 desc(감독 이름이
박혀 금방 낡음)를 대체 — 한국어 위키백과 구단 요약 우선, 없으면 영어 요약 번역.

저장: data/team_profiles.json  { team: {desc_ko, desc_source, wiki_title, ko_title} }
API(overview)가 이 파일을 읽어 info.desc 를 덮어쓴다(없으면 teammeta 하드코딩 폴백).

사용:
    python src/enrich_team_profiles.py                 # 프리뷰
    python src/enrich_team_profiles.py --write
    python src/enrich_team_profiles.py --write --only-missing   # 신규(승격) 팀만 — 데일리용
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_manager_profiles import fetch_json
from enrich_manager_profiles import _ko_title, _translate_ko
import teammeta

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "team_profiles.json"

# 구단 → 영어 위키백과 문서 제목(안정적). 없으면 "{team} F.C." 폴백.
WIKI_TITLE: dict[str, str] = {
    "Arsenal": "Arsenal F.C.", "Aston Villa": "Aston Villa F.C.",
    "Bournemouth": "AFC Bournemouth", "Brentford": "Brentford F.C.",
    "Brighton": "Brighton & Hove Albion F.C.", "Burnley": "Burnley F.C.",
    "Chelsea": "Chelsea F.C.", "Crystal Palace": "Crystal Palace F.C.",
    "Everton": "Everton F.C.", "Fulham": "Fulham F.C.",
    "Leeds United": "Leeds United F.C.", "Liverpool": "Liverpool F.C.",
    "Manchester City": "Manchester City F.C.", "Manchester Utd": "Manchester United F.C.",
    "Newcastle United": "Newcastle United F.C.", "Nottingham Forest": "Nottingham Forest F.C.",
    "Sunderland": "Sunderland A.F.C.", "Tottenham Hotspur": "Tottenham Hotspur F.C.",
    "West Ham United": "West Ham United F.C.", "Wolves": "Wolverhampton Wanderers F.C.",
}


def _wiki_title(team: str) -> str:
    if team in WIKI_TITLE:
        return WIKI_TITLE[team]
    full = teammeta.team_fullname(team)  # 예: "Arsenal FC"
    if full:
        return full.replace(" FC", " F.C.").replace(" AFC", " A.F.C.")
    return f"{team} F.C."


def _summary(lang: str, title: str) -> tuple[str, str]:
    """(요약 텍스트, page type). 동음이의(disambiguation) 페이지는 걸러내기 위해 type 반환."""
    try:
        d = fetch_json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )
        return (d.get("extract") or "").strip(), str(d.get("type") or "")
    except Exception:
        return "", ""


def _trim(text: str, n: int = 2, limit: int = 210) -> str:
    parts = re.split(r"(?<=다[.])\s+|(?<=[.])\s+", text)
    return " ".join(p for p in parts[:n] if p).strip()[:limit]


def enrich_one(team: str) -> dict:
    wiki_title = _wiki_title(team)
    result: dict = {"wiki_title": wiki_title}
    ko_t = _ko_title(wiki_title)
    if ko_t:
        ext, typ = _summary("ko", ko_t)
        if ext and typ != "disambiguation":
            result["desc_ko"] = _trim(ext)
            result["desc_source"] = "ko-wiki"
            result["ko_title"] = ko_t
    if "desc_ko" not in result:
        ext, typ = _summary("en", wiki_title)
        if ext and typ != "disambiguation":
            ko = _translate_ko(_trim(ext, limit=260))
            result["desc_ko"] = ko or _trim(ext)
            result["desc_source"] = "en-wiki-translated" if ko else "en-wiki"
    return result


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--only-missing", action="store_true",
                    help="이미 desc_ko 있는 팀은 건너뜀 (승격 등 신규 팀만 — 데일리용)")
    ap.add_argument("--sleep", type=float, default=1.2)
    args = ap.parse_args(argv)

    profiles: dict = {}
    if args.out.exists():
        try:
            profiles = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            profiles = {}

    teams = list(teammeta.TEAM_INFO.keys())
    n_ok = 0
    for team in teams:
        if args.only and args.only.lower() not in team.lower():
            continue
        if args.only_missing and profiles.get(team, {}).get("desc_ko"):
            continue
        print(f"\n### {team}")
        try:
            r = enrich_one(team)
        except Exception as exc:
            print(f"    [실패 — 건너뜀] {team}: {exc}", file=sys.stderr)
            continue
        if r.get("desc_ko"):
            n_ok += 1
            print(f"  [{r.get('desc_source')}] {r['desc_ko']}")
        else:
            print("  (요약 없음)")
        if args.write:
            profiles[team] = r
            args.out.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        time.sleep(args.sleep)

    print(f"\n요약: desc {n_ok}")
    if args.write:
        print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
