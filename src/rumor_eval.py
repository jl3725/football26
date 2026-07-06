"""Transfermarkt 루머 ↔ AI 1차 분석 (Transfer Fit Evaluator, 루머 소스).

data/transfer_rumors_<리그>.csv (fetch_transfer_rumors.py 수집)의 클럽 링크 선수에
AI evaluate_fit 을 돌려: 루머를 AI 적합도순 랭킹 + TM 확률 vs AI Fit 비교.
우리 7리그 밖 선수는 '데이터 없음(수집 대상)' 표시. KG 에 RUMORED_WITH 적재 옵션.

로컬 전용. 사용: python src/rumor_eval.py   (기본 데모: Arsenal)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import transfer_fit as tf  # noqa: E402
from leagues import data_path  # noqa: E402

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "football26"))
RUMOR_LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal"]


def load_rumors() -> pd.DataFrame:
    frames = []
    for lg in RUMOR_LEAGUES:
        try:
            df = pd.read_csv(data_path("transfer_rumors", lg))
            df["_rumor_league"] = lg
            frames.append(df)
        except (OSError, ValueError):
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def analyze_club(club: str) -> list[dict]:
    df = load_rumors()
    sub = df[df["target_club"].astype(str) == club]
    out = []
    for _, r in sub.iterrows():
        player, role = str(r["player"]), str(r.get("pos_detail") or "")
        tm_prob = None if pd.isna(r.get("probability")) else int(r["probability"])
        rep = tf.evaluate_fit(player, club, role)
        if "error" in rep:
            out.append({"player": player, "current_club": str(r.get("current_club") or ""),
                        "tm_prob": tm_prob, "ai_fit": None, "note": "데이터 없음(우리 7리그 밖 — 수집 대상)"})
            continue
        out.append({"player": player, "current_club": str(r.get("current_club") or ""),
                    "role": rep["role"], "tm_prob": tm_prob, "ai_fit": rep["fit_score"],
                    "ai_type": rep["signing_type"], "team_need": rep["components"]["TeamNeed"],
                    "role_fit": rep["components"]["RoleFit"],
                    "verdict": _verdict(tm_prob, rep["fit_score"], rep["components"])})
    # AI Fit 순(없으면 뒤로)
    out.sort(key=lambda x: (x["ai_fit"] is not None, x["ai_fit"] or 0), reverse=True)
    return out


def _verdict(tm_prob, ai_fit, comp) -> str:
    if ai_fit >= 62:
        return "👍 AI도 좋게 봄"
    if tm_prob is not None and tm_prob >= 60 and ai_fit < 50:
        low = min(("RoleFit", "TeamNeed", "Translation"), key=lambda k: comp[k])
        return f"⚠️ TM확률 높은데 AI 회의적 (병목 {low} {comp[low]})"
    if ai_fit < 45:
        return "🔻 AI 적합도 낮음"
    return "△ 보통"


def sync_to_kg() -> int:
    """RUMORED_WITH 엣지 적재(우리 풀 매칭 선수만). (Player)-[:RUMORED_WITH {prob}]->(Club)."""
    from neo4j import GraphDatabase
    df = load_rumors()
    if df.empty:
        return 0
    rows = [{"player": str(r["player"]), "club": str(r["target_club"]),
             "prob": None if pd.isna(r.get("probability")) else int(r["probability"]),
             "cur": str(r.get("current_club") or "")}
            for _, r in df.iterrows()]
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    linked = 0
    with d.session() as s:
        for i in range(0, len(rows), 300):
            res = s.run(
                "UNWIND $rows AS r MATCH (p:Player {name:r.player}) "
                "MERGE (c:Club {name:r.club}) "
                "MERGE (p)-[x:RUMORED_WITH]->(c) SET x.probability=r.prob, x.source='transfermarkt' "
                "RETURN count(x) AS n", rows=rows[i:i + 300]).single()
            linked += int(res["n"]) if res else 0
    d.close()
    return linked


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    club = sys.argv[1] if len(sys.argv) > 1 else "Arsenal"
    res = analyze_club(club)
    print("=" * 82)
    print(f"{club} — Transfermarkt 루머 AI 1차 분석 (AI 적합도순)")
    print("=" * 82)
    for r in res:
        if r["ai_fit"] is None:
            print(f"  {r['player']:22} ({r['current_club'][:16]:16}) TM {r['tm_prob']}  · {r['note']}")
            continue
        print(f"  {r['player']:22} ({r['current_club'][:16]:16}) {r['role']:16} "
              f"TM {str(r['tm_prob'])+'%' if r['tm_prob'] is not None else '-':>4} · AI Fit {r['ai_fit']}"
              f"({r['ai_type']}) · {r['verdict']}")
    n = sync_to_kg()
    print(f"\n[rumor-kg] RUMORED_WITH 적재: {n}건 (풀 매칭 선수)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
