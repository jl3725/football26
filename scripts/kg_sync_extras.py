"""그래프 보강 적재 — 이적 루머(RUMORED_WITH)·클럽 영입 성향·감독 전술(EMPHASIZES) (kg_reload.yml 주간).

각 모듈의 main() 은 예시 출력과 함께 적재하므로, 여기선 적재 함수만 부른다. 루머는 매번 지금 목록으로 다시 싣는다
(지난주 루머가 남지 않게 RUMORED_WITH 를 먼저 지움).

    python scripts/kg_sync_extras.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from neo4j import GraphDatabase

    import club_profile
    import manager_tactics
    import rumor_eval

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    auth = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j", os.getenv("NEO4J_PASSWORD", "football26"))
    with GraphDatabase.driver(uri, auth=auth) as d, d.session() as s:
        n = s.run("MATCH ()-[r:RUMORED_WITH]->() DELETE r RETURN count(r) AS n").single()["n"]
        print(f"[kg-extras] 지난 루머 관계 정리 {n}")
    failed = 0
    for name, fn in (("루머 RUMORED_WITH", rumor_eval.sync_to_kg), ("클럽 영입 성향·예산", club_profile.sync_to_kg),
                     ("감독 전술·EMPHASIZES", manager_tactics.sync_to_kg)):
        try:
            print(f"[kg-extras] {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[kg-extras] {name} 실패 {type(e).__name__}: {str(e)[:160]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
