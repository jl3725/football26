"""
IDENTITY 에이전트 — 출처마다 다른 클럽 표기를 매일 표준 이름(순위표, ESPN 기준)과 대조해 별칭을 자동 등록한다
(설계도 '사람이 손대는 마지막 큰 작업').

예전엔 `python src/squads.py` 가 순위표만 대조했고(이미 ESPN 기준이라 늘 일치) 별칭 추가는 손으로 했다. 그 사이
FotMob('Sparta Rotterdam'·'Vitória de Guimarães'·'St.Truiden')·TM·Sofascore('Málaga CF'·'SC Paderborn 07') 표기가
표준('Sparta R.'·'Vit. Guimarães'·'Sint-Truiden'·'Málaga'·'SC Paderborn')과 이어지지 않아, 그 클럽 선수의 FotMob 평점·
결장·Sofascore 지표가 빠질 수 있었다(2026-10-20 점검).

규칙
  - 대조 대상: 이번 시즌 파일의 '우리 리그 클럽' 열(SOURCES). 지난 시즌 표준 이름(강등팀 — 이적 기록 등)은 무시.
  - 점수: 일반어(FC·SC·Calcio…) 뺀 토큰끼리 정확 1.0 · 접두어(Vit.→Vitória) 0.8 · 머리글자(OH→Oud-Heverlee) 0.9 ·
    St↔Sint/Saint 0.9, 양방향 평균. 표준 이름 토큰이 모두 들어 있으면(ESTAC Troyes ⊃ Troyes) 0.9.
  - 자동 등록: 최고 점수 ≥ 0.85 이고 2등보다 0.15 이상 높을 때 → data/club_aliases_auto.csv (squads.canonical_squad 가 읽음)
  - 그 밖(애매)은 data/eval/identity_audit.json 의 review — watchdog 'identity' 가 '확인 필요'로 알린다.

    python src/identity.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUTO = ROOT / "data" / "club_aliases_auto.csv"
AUDIT = ROOT / "data" / "eval" / "identity_audit.json"
AUTO_MIN, MARGIN = 0.85, 0.15

# (파일 stem, 클럽 열) — '우리 리그 클럽'만 담는 열
SOURCES = [("players", "squad"), ("players_full", "squad"), ("players_sofascore_stats", "squad"),
           ("understat_players", "squad"), ("fotmob_match_ratings", "squad"), ("fotmob_injuries", "squad"),
           ("fotmob_ratings", "squad"), ("transfermarkt_injuries", "squad"), ("tm_injury_history", "squad"),
           ("wiki_squads", "squad"), ("espn_lineups", "squad"), ("team_unit_metrics", "squad"),
           ("player_comp_usage", "squad"), ("market_value", "squad"), ("player_registry", "squad"),
           ("transfers", "squad"), ("rating_history", "squad")]
GENERIC = {"fc", "cf", "sc", "ac", "as", "sv", "sk", "kv", "vv", "rc", "cd", "ud", "sd", "ca", "cs", "afc", "bk", "fk",
           "ssc", "us", "club", "calcio", "de", "da", "do", "di", "del", "of", "the", "a", "1", "04", "05", "07", "08",
           "1846", "1899", "1900", "1907", "1909", "1913"}
SAINT = {"st", "sint", "saint", "san", "sankt"}


def toks(name: str) -> list[str]:
    t = re.sub(r"[.\-'’/()]", " ", unidecode(str(name or "")).lower()).split()
    return [x for x in t if x not in GENERIC and not x.isdigit()]


def _tok_score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a in SAINT and b in SAINT:
        return 0.9
    if len(a) >= 1 and len(b) >= 1 and (a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 1:
        return 0.8 if min(len(a), len(b)) >= 2 or max(len(a), len(b)) >= 4 else 0.0
    return 0.0


def _initials(x: list[str], y: list[str]) -> set[int]:
    """y 의 토큰 중 x 의 연속 토큰 머리글자와 같은 것 → x 쪽에서 덮인 위치들(OH ↔ oud heverlee, SG ↔ st gilloise)."""
    covered = set()
    for tok in y:
        n = len(tok)
        if n < 2:
            continue
        for i in range(len(x) - n + 1):
            if "".join(w[0] for w in x[i:i + n]) == tok:
                covered.update(range(i, i + n))
    return covered


def similarity(src: str, canon: str) -> float:
    a, b = toks(src), toks(canon)
    if not a or not b:
        return 0.0
    if all(any(_tok_score(x, y) == 1.0 for x in a) for y in b) and any(len(y) >= 4 for y in b):
        contain = 0.9
    else:
        contain = 0.0
    ia, ib = _initials(a, b), _initials(b, a)
    # 머리글자로 덮인 짝도 0.9 — 'sg' 와 'st gilloise'
    sa = [0.9 if i in ia else max(_tok_score(x, y) for y in b) for i, x in enumerate(a)]
    sb = [0.9 if (i in ib or (len(y) >= 2 and any("".join(w[0] for w in a[j:j + len(y)]) == y
                                                   for j in range(len(a) - len(y) + 1))))
          else max(_tok_score(y, x) for x in a) for i, y in enumerate(b)]
    # 한 글자 토큰만 이어진 이름(N.E.C.)은 붙여서도 본다
    if all(len(x) == 1 for x in a) and len(a) >= 2:
        joined = "".join(a)
        if joined in b:
            return max(contain, 0.9)
    return max(contain, round((sum(sa) + sum(sb)) / (len(sa) + len(sb)), 3))


def best_match(src: str, canon: list[str]) -> tuple[str | None, float, float]:
    sc = sorted(((similarity(src, c), c) for c in canon), reverse=True)
    if not sc:
        return None, 0.0, 0.0
    return sc[0][1], sc[0][0], (sc[1][0] if len(sc) > 1 else 0.0)


def load_auto() -> dict[str, dict[str, str]]:
    if not AUTO.exists():
        return {}
    d = pd.read_csv(AUTO, dtype=str).fillna("")
    out: dict[str, dict[str, str]] = {}
    for r in d.to_dict("records"):
        out.setdefault(r["league"], {})[r["source_name"]] = r["canonical"]
    return out


def _canon_list(league: str, season_start: int) -> list[str]:
    p = data_path("standings", league, f"{season_start}_{season_start + 1}")
    return sorted(pd.read_csv(p)["squad"].dropna().astype(str).unique()) if p.exists() else []


def scan(today: str | None = None) -> dict:
    import squads  # noqa: PLC0415 — canonical_squad(수동 ALIASES + 자동 별칭 + 악센트 무시)
    today = today or dt.date.today().isoformat()
    auto_rows = pd.read_csv(AUTO, dtype=str).fillna("").to_dict("records") if AUTO.exists() else []
    known = {(r["league"], r["source_name"]) for r in auto_rows}
    added, review = [], []
    for lg in LEAGUES:
        canon = _canon_list(lg, SEASON_START)
        if not canon:
            continue
        prev = set(_canon_list(lg, SEASON_START - 1))
        seen: dict[str, set] = {}
        for stem, col in SOURCES:
            p = data_path(stem, lg)
            if not p.exists():
                continue
            try:
                vals = pd.read_csv(p, usecols=[col])[col].dropna().astype(str).unique()
            except (ValueError, KeyError):
                continue
            for v in vals:
                if squads.canonical_squad(v, lg) not in canon:
                    seen.setdefault(v, set()).add(stem)
        for name, stems in sorted(seen.items()):
            if name in prev or (lg, name) in known:
                continue                                  # 지난 시즌 클럽(강등) · 이미 등록
            best, s1, s2 = best_match(name, canon)
            item = {"league": lg, "source_name": name, "canonical": best, "score": s1, "second": s2,
                    "sources": sorted(stems)}
            if best and s1 >= AUTO_MIN and s1 - s2 >= MARGIN:
                added.append(item)
                auto_rows.append({"league": lg, "source_name": name, "canonical": best, "score": f"{s1:.3f}",
                                  "sources": "|".join(sorted(stems)), "first_seen": today})
            elif s1 >= 0.5:
                review.append(item)
    if added:
        AUTO.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(auto_rows).to_csv(AUTO, index=False, encoding="utf-8")
    return {"date": today, "added": added, "review": review, "auto_total": len(auto_rows)}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    res = scan()
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in res["added"]:
        print(f"[identity] 자동 등록 {x['league']}: '{x['source_name']}' → '{x['canonical']}' ({x['score']:.2f}, {', '.join(x['sources'])})")
    for x in res["review"]:
        print(f"[identity] 확인 필요 {x['league']}: '{x['source_name']}' ≈ '{x['canonical']}' ({x['score']:.2f} vs {x['second']:.2f})")
    print(f"[identity] 자동 등록 {len(res['added'])} · 확인 필요 {len(res['review'])} · 누적 자동 별칭 {res['auto_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
