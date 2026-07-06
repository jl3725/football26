"""휴먼 스카우트 리포트 ↔ AI Fit 매핑/비교 (Transfer Fit Evaluator Phase 2).

data/scout_reports.csv 의 휴먼 스카우트 추천에 AI evaluate_fit 을 돌려:
- 합의/이견 비교 리포트 (스카우트 확신 vs AI 적합도)
- KG 적재: (Scout)-[:FILED]->(ScoutReport)-[:ON_PLAYER]->(Player)/-[:FOR_CLUB]->(Club)
           + ScoutReport 에 AI Fit 결과 저장(추후 영입 outcome 으로 양측 검증)
- AI 발굴: 특정 클럽·역할에 AI 상위 후보 중 스카우트가 안 다룬 선수

로컬 전용(KG/Qdrant docker). 사용: python src/scout_eval.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import transfer_fit as tf  # noqa: E402

REPORTS_CSV = ROOT / "data" / "scout_reports.csv"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "football26"))


def load_reports() -> pd.DataFrame:
    return pd.read_csv(REPORTS_CSV)


def _numn(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _agreement(scout_grade: float, ai_fit: float, recommendation: str) -> str:
    gap = scout_grade - ai_fit                       # + = 스카우트가 AI보다 후함
    if ai_fit >= scout_grade - 5:
        return "✅ AI 동의(동급 이상)"
    if gap <= 18:
        return "△ AI 다소 신중"
    return "⚠️ AI 회의적(재검토)"


def evaluate_reports() -> list[dict]:
    out = []
    for _, r in load_reports().iterrows():
        rep = tf.evaluate_fit(str(r["player"]), str(r["target_club"]),
                              str(r["target_role"]), source_league=str(r.get("source_league") or "") or None)
        if "error" in rep:
            out.append({"report_id": r["report_id"], "player": r["player"], "error": rep["error"]})
            continue
        sg = float(r["scout_grade"])
        comp = rep["components"]
        pos_comps = {k: comp[k] for k in ("RoleFit", "TeamNeed", "Translation", "Potential", "Value")}
        bneck_k = min(pos_comps, key=pos_comps.get)
        bottleneck = (f"Risk {comp['Risk']}" if comp["Risk"] >= 45 and comp["Risk"] >= (100 - pos_comps[bneck_k])
                      else f"{bneck_k} {pos_comps[bneck_k]}")
        out.append({
            "report_id": str(r["report_id"]), "scout": str(r["scout"]), "player": str(r["player"]),
            "target_club": str(r["target_club"]), "role": rep["role"],
            "scout_grade": sg, "recommendation": str(r["recommendation"]),
            "ai_fit": rep["fit_score"], "ai_type": rep["signing_type"], "ai_risk": rep["risk_level"],
            "agreement": _agreement(sg, rep["fit_score"], str(r["recommendation"])),
            "bottleneck": bottleneck,
            "components": rep["components"], "est_fee_eur": _numn(r.get("est_fee_eur")),
            "comment": str(r.get("comment") or ""),
        })
    return out


def sync_to_kg(rows: list[dict]) -> None:
    from neo4j import GraphDatabase
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    reports = load_reports().set_index("report_id")
    with d.session() as s:
        s.run("CREATE CONSTRAINT scout_report_id IF NOT EXISTS "
              "FOR (r:ScoutReport) REQUIRE r.id IS UNIQUE")
        s.run("CREATE CONSTRAINT scout_name IF NOT EXISTS FOR (x:Scout) REQUIRE x.name IS UNIQUE")
        n_link = 0
        for row in rows:
            if "error" in row:
                continue
            meta = reports.loc[row["report_id"]]
            src = str(meta.get("source_league") or "")
            res = s.run(
                "MERGE (sc:Scout {name:$scout}) "
                "MERGE (rep:ScoutReport {id:$id}) "
                "  SET rep.player=$player, rep.role=$role, rep.grade=$grade, "
                "      rep.recommendation=$rec, rep.date=$date, rep.est_fee=$fee, rep.comment=$comment, "
                "      rep.ai_fit=$ai_fit, rep.ai_type=$ai_type, rep.agreement=$agree "
                "MERGE (sc)-[:FILED]->(rep) "
                "MERGE (c:Club {name:$club}) MERGE (rep)-[:FOR_CLUB]->(c) "
                "WITH rep MATCH (p:Player {name:$player, league:$src}) "
                "MERGE (rep)-[:ON_PLAYER]->(p) RETURN count(p) AS linked",
                scout=row["scout"], id=row["report_id"], player=row["player"], role=row["role"],
                grade=row["scout_grade"], rec=row["recommendation"], date=str(meta.get("date") or ""),
                fee=row["est_fee_eur"], comment=row["comment"], ai_fit=row["ai_fit"],
                ai_type=row["ai_type"], agree=row["agreement"], club=row["target_club"], src=src).single()
            n_link += int(res["linked"]) if res else 0
    d.close()
    print(f"[scout-kg] ScoutReport {sum(1 for r in rows if 'error' not in r)}건 적재 · Player 연결 {n_link}")


def discover(club: str, role: str, k: int = 8) -> list[dict]:
    """AI Discover — 클럽·역할에 적합도 상위 후보 + 스카우트 리포트 커버 여부."""
    pool = tf._pool()
    role_n = tf._pos_detail(role) or role
    tgt = pool[pool["squad"].astype(str) == club]
    if tgt.empty:
        return []
    scouted = set(load_reports().query("target_club == @club")["player"].astype(str))
    cands = pool[(pool["_pos_detail"] == role_n) & (pool["squad"].astype(str) != club)
                 & (pool["_min"] >= 900)].sort_values("ss_rating", ascending=False).head(18)
    res = []
    for _, r in cands.iterrows():
        rep = tf.evaluate_fit(str(r["player"]), club, role, source_league=str(r["_league"]))
        if "error" in rep:
            continue
        res.append({"player": rep["candidate"], "league": rep["source_league"], "club": str(r["squad"]),
                    "fit": rep["fit_score"], "type": rep["signing_type"],
                    "scouted": str(r["player"]) in scouted})
    res.sort(key=lambda x: -x["fit"])
    return res[:k]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rows = evaluate_reports()
    print("=" * 78)
    print("휴먼 스카우트 ↔ AI Fit 비교")
    print("=" * 78)
    for r in rows:
        if "error" in r:
            print(f"  {r['report_id']} {r['player']:22} ❌ {r['error']}")
            continue
        print(f"  {r['player']:22} → {r['target_club']:16} {r['role']:18}")
        print(f"     스카우트 {int(r['scout_grade'])}({r['recommendation']}) vs AI {r['ai_fit']}"
              f"({r['ai_type']})  {r['agreement']} · 병목 {r['bottleneck']}")
    sync_to_kg(rows)

    print("\n" + "=" * 78)
    print("AI 발굴 데모 — Chelsea / Attacking Midfield 적합도 상위 (★=스카우트 미커버)")
    print("=" * 78)
    for c in discover("Chelsea", "Attacking Midfield", k=8):
        star = "  " if c["scouted"] else "★ "
        print(f"  {star}{c['player']:24} {c['club']:14} {c['league']:12} Fit {c['fit']} ({c['type']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
