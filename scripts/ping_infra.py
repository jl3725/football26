"""선택 인프라(Qdrant Cloud · Neo4j AuraDB) 깨우기 — 무료 티어 미사용 정지 방지. GH daily_data 에서 매일 실행.

환경변수가 없으면 해당 서비스는 건너뛴다(exit 0). 연결 실패는 exit 1 — ci_try 가 실패 목록에 올린다.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    bad = 0
    if os.getenv("QDRANT_URL"):
        try:
            from qdrant_client import QdrantClient
            qc = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.getenv("QDRANT_API_KEY") or None, timeout=20)
            cols = [c.name for c in qc.get_collections().collections]
            print(f"[ping] qdrant OK · collections {cols}")
        except Exception as e:  # noqa: BLE001
            print(f"[ping] qdrant FAIL: {type(e).__name__}: {str(e)[:120]}")
            bad += 1
    else:
        print("[ping] qdrant: QDRANT_URL 없음 — 건너뜀")
    if os.getenv("NEO4J_URI"):
        try:
            from neo4j import GraphDatabase
            d = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                     auth=(os.getenv("NEO4J_USERNAME") or "neo4j", os.getenv("NEO4J_PASSWORD") or ""),
                                     connection_timeout=15)
            with d.session() as s:
                n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            d.close()
            print(f"[ping] neo4j OK · nodes {n}")
        except Exception as e:  # noqa: BLE001
            print(f"[ping] neo4j FAIL: {type(e).__name__}: {str(e)[:120]}")
            bad += 1
    else:
        print("[ping] neo4j: NEO4J_URI 없음 — 건너뜀")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
