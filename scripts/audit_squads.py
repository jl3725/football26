"""
스쿼드 빈칸 점검 — 등록된 1군 선수가 화면 스쿼드(이번 시즌 출전자 + 출전 없는 등록 선수)에 다 있는가,
나이·포지션이 비어 '0세'·포지션 없음으로 보이는 선수가 있는가.

계기(2026-10-22 사용자): 첼시 GK 마르티네스 부상인데 '대체 없음' — 백업 마이크 펜더르스(이번 시즌 0분)가 스쿼드에 없었고,
'Mahdi Jazuli MF 0세'처럼 나이가 빈 선수가 보였다. "스쿼드에 모든 팀에 빠진 선수들 있는 거 아닌가 — 다 잡아야".

등록 명단 = FotMob 1군 명단(TM 계약 명단·위키 1군 칸은 유스·2군·표기 변형이 섞여 기준에서 뺌). 화면 스쿼드 = api.main._with_roster(임대 보낸 선수 제외).
    python scripts/audit_squads.py [--league EPL] [--json data/eval/squad_audit.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def audit(leagues: list[str] | None = None) -> dict:
    import pandas as pd  # noqa: PLC0415

    import api.main as M  # noqa: PLC0415
    import player_registry as preg  # noqa: PLC0415
    out = {"leagues": {}, "missing": [], "no_age": [], "no_pos": []}
    for lg in leagues or list(M.ds.available_leagues()):
        full = M._pf(lg)
        if full is None:
            continue
        fm = M.ds.read_table("fotmob_squads", league=lg)
        wk = M.ds.read_table("wiki_squads", league=lg)
        teams = sorted(full["squad"].dropna().astype(str).unique())
        n_reg = n_miss = 0
        for t in teams:
            shown = M._with_roster(full, t, lg)
            names = {str(n): str(n) for n in shown["player"].dropna()} if shown is not None else {}
            lo = M._loans_out(t, lg)
            reg: dict[str, str] = {}
            # 1군 등록 = FotMob 1군 명단(src/fotmob_squads.py) ∪ 위키 1군 칸. TM 계약 명단은 유스·2군까지 있어 기준에서 뺀다
            # (브렌트퍼드 B팀 10여 명이 '빠짐'으로 잡혔다)
            if fm is not None and "squad" in fm.columns:
                for n in fm.loc[fm["squad"] == t, "player"].dropna().astype(str):
                    reg.setdefault(preg.norm(n), n)
            # 위키 1군 칸은 유스·표기 변형(Yegor Yarmolyuk ↔ Yehor Yarmoliuk)이 섞여 기준에서 뺀다 — FotMob 1군 명단만
            for n in reg.values():
                if lo and M._is_loaned(n, lo):
                    continue
                n_reg += 1
                if not preg.best_match(n, names)[0]:
                    n_miss += 1
                    out["missing"].append({"league": lg, "squad": t, "player": n})
            if shown is not None and not shown.empty:
                for _, r in shown.iterrows():
                    a = pd.to_numeric(r.get("age"), errors="coerce")
                    if pd.isna(a) or a <= 0:
                        out["no_age"].append({"league": lg, "squad": t, "player": str(r["player"]), "minutes": int(M._num(r.get("minutes")))})
                    if not (isinstance(r.get("tm_position"), str) and r.get("tm_position")) and not str(r.get("pos") or "").strip():
                        out["no_pos"].append({"league": lg, "squad": t, "player": str(r["player"])})
        out["leagues"][lg] = {"teams": len(teams), "registered": n_reg, "missing": n_miss,
                              "no_age": sum(1 for x in out["no_age"] if x["league"] == lg),
                              "no_pos": sum(1 for x in out["no_pos"] if x["league"] == lg)}
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = audit([a.league] if a.league else None)
    for lg, s in res["leagues"].items():
        print(f"{lg:16} 팀 {s['teams']:2} · 등록 {s['registered']:4} · 스쿼드에 없음 {s['missing']:3} · 나이 없음 {s['no_age']:3} · 포지션 없음 {s['no_pos']:3}")
    for k in ("missing", "no_age", "no_pos"):
        print(f"\n[{k}] 예:", [f"{x['squad']}·{x['player']}" for x in res[k][:14]])
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
