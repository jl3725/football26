"""
Ask Scout 질문 평가 세트 — 무료 규칙 라우터(src/scout_router.py)가 질문을 의도·팀·리그·포지션·선수로 맞게 읽는지.

data/eval/scout_questions.csv 한 줄 = 질문 하나와 기대값. 빈 칸은 보지 않음, '-' 는 '비어 있어야 함'(엉뚱한 선수·팀을
잡지 않기). 실제 데이터(선수 표·한글 이름 사전)로 돌리므로 이적·사전 갱신으로 깨지면 CI 가 알려 준다.

    python scripts/eval_scout.py           # 결과 표
    python scripts/eval_scout.py --check   # 하나라도 틀리면 종료 코드 1 (CI)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import scout_router  # noqa: E402

CSV = ROOT / "data" / "eval" / "scout_questions.csv"
FIELDS = ("intent", "team", "league", "role", "player")


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def check_one(row: dict) -> list[str]:
    p = scout_router.parse(row["q"], _s(row.get("team_ctx")) or None, _s(row.get("league_ctx")) or "EPL")
    got = {"intent": p["intent"], "team": p["team"], "league": p["league"], "role": p["role"],
           "player": p["players"][0]["name"] if p["players"] else None}
    bad = []
    for f in FIELDS:
        want = _s(row.get(f))
        if not want:
            continue
        if want == "-" and got[f] is not None:
            bad.append(f"{f}: 비어 있어야 함, 실제 {got[f]}")
        elif want != "-" and _s(got[f]) != want:
            bad.append(f"{f}: 기대 {want}, 실제 {got[f]}")
    return bad


def run() -> list[tuple[str, list[str]]]:
    rows = pd.read_csv(CSV, dtype=str).to_dict("records")
    return [(r["q"], check_one(r)) for r in rows]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = argv if argv is not None else sys.argv[1:]
    res = run()
    for q, bad in res:
        print(f"[{'FAIL' if bad else ' OK '}] {q}" + ("".join(f"\n        {b}" for b in bad)))
    n_bad = sum(1 for _, b in res if b)
    print(f"\nAsk Scout 질문 {len(res) - n_bad}/{len(res)} 통과")
    return 1 if "--check" in args and n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
