"""
전문가 기대치 검사 — data/eval/golden_expectations.csv (평점 밖: 영향력·주장·포지션·유사 선수·누적 스탯).

평점(OVR) 기대치는 data/eval/golden.csv(scripts/eval_ratings.py)에 있다. 이 파일은 2026-10-19~20 사용자 지적처럼
'계산 공식이 바뀌면 다시 틀어질 수 있는 판단'을 적어 두고, 코드가 바뀔 때(CI --check)와 매일(daily_data → watchdog)
화면과 같은 API 함수로 다시 확인한다. 선수별 하드코딩으로 값을 맞추지 않는다 — 실패하면 공식·수집을 고친다.

kind
  influence_top   team 의 영향력(NETWORK LEADERSHIP) 상위 expect 명 안에 player('|' 여러 명) 모두
  captain         team 의 주장 순번 expect 가 player
  captain_not     team 의 주장 순번 expect 가 player 가 아님
  bucket_in       player 의 세부 포지션 버킷(LW·CM…)이 expect('|' 허용) 중 하나
  fit_natural     적합도 평가(역할 비움) 기본 역할이 expect
  similar_not     player 의 유사 선수 목록에 expect 가 없음
  similar_bucket  player 의 유사 선수가 모두 expect('|') 버킷
  stat_ge         player 의 metric:값 이상(season 이 지금 시즌일 때만 — 시즌 누적)

    python scripts/eval_expectations.py                 # 결과 출력
    python scripts/eval_expectations.py --check         # 실패가 있으면 종료코드 1 (CI)
    python scripts/eval_expectations.py --out data/eval/expectations_audit.json   # watchdog 용 기록
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
GOLDEN = ROOT / "data" / "eval" / "golden_expectations.csv"


def _row(m, league: str, player: str):
    f = m._pf(league)
    if f is None:
        return None
    r = f[f["player"] == player]
    return None if r.empty else r.iloc[0]


def check_one(m, r: dict, season: str) -> tuple[bool | None, str]:
    """(True=통과 · False=실패 · None=건너뜀, 설명)."""
    kind, lg, team, player = r["kind"], r["league"], r.get("team") or "", r["player"]
    expect = str(r["expect"])
    if kind in ("influence_top", "captain", "captain_not"):
        lead = (m.network(team, lg).get("leadership") or {})
        if kind == "influence_top":
            top = sorted((lead.get("influence") or {}).items(), key=lambda x: -x[1])[: int(expect)]
            names = [n for n, _ in top]
            miss = [p for p in player.split("|") if p not in names]
            return not miss, f"{team} 영향력 상위 {expect}: {', '.join(f'{n} {v}' for n, v in top)}" + (
                f" — 빠짐: {', '.join(miss)}" if miss else "")
        caps = {c["captain_rank"]: c["name"] for c in lead.get("captains") or []}
        who = caps.get(int(expect))
        ok = (who == player) if kind == "captain" else (who != player)
        return ok, f"{team} {expect}순위 주장: {who}"
    if kind == "bucket_in":
        row = _row(m, lg, player)
        if row is None:
            return None, f"{player} 선수 표에 없음({lg})"
        b = m._pos_bucket(row)
        return b in expect.split("|"), f"{player} 버킷 {b}(기대 {expect})"
    if kind == "fit_natural":
        f = m.fit(player, team, "", "", lg)
        nat = f.get("natural_role") or f.get("role")
        return nat == expect, f"{player} → {team} 적합도 기본 역할 {nat}(기대 {expect})"
    if kind in ("similar_not", "similar_bucket"):
        res = m.similar(player, True, 0.6, lg).get("results") or []
        if not res:
            return None, f"{player} 유사 선수 결과 없음"
        if kind == "similar_not":
            names = [x["player"] for x in res]
            return expect not in names, f"{player} 유사: {', '.join(names)}"
        bad = [f"{x['player']}({x['pos']})" for x in res if x["pos"] not in expect.split("|")]
        return not bad, f"{player} 유사 버킷: {', '.join(x['pos'] for x in res)}" + (f" — 벗어남: {', '.join(bad)}" if bad else "")
    if kind == "stat_ge":
        if r.get("season") and str(r["season"]) != season:
            return None, f"시즌 {r['season']} 기준 — 지금 {season}, 건너뜀"
        row = _row(m, lg, player)
        if row is None:
            return None, f"{player} 선수 표에 없음({lg})"
        metric, lo = expect.split(":")
        v = pd.to_numeric(row.get(metric), errors="coerce")
        return bool(v == v and v >= float(lo)), f"{player} {metric} {v}(기대 {lo} 이상)"
    return None, f"모르는 kind {kind}"


def run() -> list[dict]:
    import api.main as m  # noqa: PLC0415
    from leagues import SEASON  # noqa: PLC0415
    g = pd.read_csv(GOLDEN, dtype=str).fillna("")
    out = []
    for r in g.to_dict("records"):
        try:
            ok, msg = check_one(m, r, SEASON)
        except Exception as e:  # noqa: BLE001 — 한 줄이 깨져도 나머지는 확인
            ok, msg = False, f"검사 오류 {type(e).__name__}: {str(e)[:120]}"
        out.append({"kind": r["kind"], "league": r["league"], "team": r.get("team", ""), "player": r["player"],
                    "ok": ok, "detail": msg, "note": r.get("note", "")})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    res = run()
    for x in res:
        tag = "PASS" if x["ok"] else ("SKIP" if x["ok"] is None else "FAIL")
        print(f"[{tag}] {x['kind']:15} {x['detail']}")
    fails = [x for x in res if x["ok"] is False]
    print(f"전문가 기대치 {len(res)}건 — 실패 {len(fails)}")
    if a.out:
        Path(a.out).write_text(json.dumps({"date": dt.date.today().isoformat(), "results": res, "failures": len(fails)},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if (a.check and fails) else 0


if __name__ == "__main__":
    raise SystemExit(main())
