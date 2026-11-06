"""
Ask Scout 답 평가 — 운영(또는 로컬) /api/scout 에 data/eval/scout_answers.csv 질문을 실제로 던져 답을 채점한다.

eval_scout.py 는 규칙 라우터 파싱만 본다. 이건 Gemini 가 고른 도구·그래프 질의 결과·답 문장을 본다(2026-11-06 사용자
'그래프 RAG 강화' — '아스날 이적설 기자 보도' 가 원천 48건인데 '데이터 없음'으로 답했다).

checks(세미콜론):
  tool:<이름>          그 도구를 불렀다(여러 단계 중 하나)
  nonempty             마지막 결과가 비지 않았다(그래프 0행·오류·빈 결과가 아님)
  grounded             답 속 숫자가 도구 결과에 있다(서버 grounding.ok)
  contains_any:a|b     답에 a 또는 b 가 있다
  no_empty             '데이터 없음·조회되지 않습니다' 류 문장이 없다
결과 → data/eval/scout_answers.json(점수·실패 목록) — watchdog check_scout_answers 가 읽는다.

    python scripts/eval_scout_answers.py [--base https://football26-smoky.vercel.app] [--limit 5]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "data" / "eval" / "scout_answers.csv"
OUT = ROOT / "data" / "eval" / "scout_answers.json"
BASE = "https://football26-smoky.vercel.app"
PASS_MIN = 0.8
EMPTY = ("데이터가 조회되지", "조회되지 않", "데이터가 없", "데이터 없음", "확인되지 않", "찾을 수 없", "no data")
EX_SOURCE_DOWN = 75


def ask(base: str, q: str, team: str, league: str) -> dict:
    body = json.dumps({"q": q, "team": team or None, "league": league or "EPL"}).encode("utf-8")
    req = urllib.request.Request(f"{base}/api/scout", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=150) as r:
        return json.loads(r.read())


# 단계 기록(steps)이 없는 예전 서버 응답은 intent 로 도구를 거꾸로 찾는다
_INTENT_TOOL = {"graph": "graph_query", "lead": "team_leadership", "news": "player_news", "pform": "player_form",
                "team_now": "team_now", "week": "league_week", "tform": "team_form", "recommend": "recommend_players",
                "similar": "find_similar", "fit": "evaluate_fit", "identity": "club_identity", "managersim": "simulate_manager"}


def _nonempty(res: dict) -> bool:
    steps = res.get("steps") or []
    if steps:
        last = steps[-1]
        if last.get("error"):
            return False
        if last.get("tool") == "graph_query":
            return bool(last.get("count"))
    r = res.get("result")
    if isinstance(r, dict):
        if r.get("error") or r.get("available") is False:
            return False
        if "count" in r:
            return bool(r["count"])
        return any(v for k, v in r.items() if k not in ("team", "league", "player", "note"))
    return bool(r)


def grade(res: dict, checks: str) -> list[str]:
    """실패한 검사 이름들(빈 목록 = 통과)."""
    fails = []
    ans = str(res.get("answer") or "")
    tools = [s.get("tool") for s in res.get("steps") or []] or [_INTENT_TOOL.get(res.get("intent"), res.get("intent"))]
    for c in [x.strip() for x in checks.split(";") if x.strip()]:
        if c.startswith("tool:"):
            if c[5:] not in tools:
                fails.append(f"{c} (불린 도구 {tools or res.get('intent')})")
        elif c == "nonempty":
            if not _nonempty(res):
                fails.append("nonempty")
        elif c == "grounded":
            g = res.get("grounding") or {}
            if g.get("ok") is False:
                fails.append(f"grounded {g.get('unverified')}")
        elif c.startswith("contains_any:"):
            if not any(w and w in ans for w in c.split(":", 1)[1].split("|")):
                fails.append(c)
        elif c == "no_empty":
            if any(w in ans for w in EMPTY):
                fails.append("no_empty")
    if not ans.strip():
        fails.append("빈 답")
    if res.get("engine") != "gemini":
        fails.append(f"engine={res.get('engine')}{' · ' + str(res.get('note'))[:60] if res.get('note') else ''}")
    return fails


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pause", type=float, default=3.0)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = list(csv.DictReader(QUESTIONS.open(encoding="utf-8")))
    if a.limit:
        rows = rows[:a.limit]
    results, down = [], 0
    for i, r in enumerate(rows):
        t0 = time.time()
        try:
            res = ask(a.base, r["q"], r.get("team", ""), r.get("league", ""))
            fails = grade(res, r.get("checks", ""))
        except Exception as e:  # noqa: BLE001
            res, fails = {}, [f"요청 실패 {type(e).__name__}: {str(e)[:80]}"]
            down += 1
        results.append({"q": r["q"], "ok": not fails, "fails": fails, "sec": round(time.time() - t0, 1),
                        "tools": [s.get("tool") for s in res.get("steps") or []],
                        "counts": [s.get("count") for s in res.get("steps") or []],
                        "answer": str(res.get("answer") or "")[:240]})
        print(f"{'OK ' if not fails else 'FAIL'} {r['q']}" + (f"  ← {'; '.join(fails)}" if fails else ""), flush=True)
        if i < len(rows) - 1:
            time.sleep(a.pause)
    if down == len(rows):
        print("[scout-eval] 서버에 닿지 않음 — 원천 중단(기존 결과 유지)")
        return EX_SOURCE_DOWN
    n_ok = sum(x["ok"] for x in results)
    score = round(n_ok / len(results), 3) if results else 0.0
    by = {}
    for x in results:
        for f in x["fails"]:
            k = f.split(" ")[0].split(":")[0]
            by[k] = by.get(k, 0) + 1
    OUT.write_text(json.dumps({"date": dt.date.today().isoformat(), "base": a.base, "n": len(results), "pass": n_ok,
                               "score": score, "min": PASS_MIN, "fail_by_check": by, "results": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[scout-eval] {n_ok}/{len(results)} 통과 · 점수 {score:.0%} · 실패 유형 {by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
