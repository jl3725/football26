"""스쿼드 네트워크 — KG(Neo4j)의 TEAMMATE_OF 로 '같이 뛴' 관계 그래프.

squad_graph(team): 그 팀 선수 노드 + 강한 teammate 엣지(matches>=임계) → 프론트 force
그래프용. 연결 없는 선수(거의 안 뛴)는 제외해 깔끔하게. Neo4j 없으면 available=False.
"""
from __future__ import annotations

import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j",
             os.getenv("NEO4J_PASSWORD", "football26"))

# pos_detail → 라인(색상 그룹)
_LINE = {
    "Goalkeeper": "GK",
    "Centre-Back": "DEF", "Right-Back": "DEF", "Left-Back": "DEF", "Defender": "DEF",
    "Defensive Midfield": "MID", "Central Midfield": "MID", "Attacking Midfield": "MID",
    "Left Midfield": "MID", "Right Midfield": "MID",
    "Left Winger": "ATT", "Right Winger": "ATT", "Centre-Forward": "ATT", "Second Striker": "ATT",
}


class _SharedDriver:
    """프로세스 공유 드라이버 — 호출부의 close() 는 무시한다(기존 호출부 수정 없이 재사용)."""

    def __init__(self, d):
        self._d = d

    def close(self) -> None:
        pass

    def __getattr__(self, name):
        return getattr(self._d, name)


_DRIVER = None
_DRIVER_AT = 0.0
_REVERIFY_S = 600


def connect():
    """연결 확인된 Neo4j 드라이버. 꺼져 있으면 차단기(infra_health)가 10분간 즉시 실패시킨다.

    GraphDatabase.driver() 는 지연 연결이라 생성은 성공하고 첫 쿼리에서 DNS·타임아웃으로 수 초를
    쓴다 — verify_connectivity 로 여기서 확정하고, 실패는 차단기에 기록한다.
    드라이버는 프로세스에서 공유하고 10분마다만 재확인한다(예전엔 호출마다 생성·TLS 확인·종료로
    API 한 번에 1~2초를 썼다, 2026-10)."""
    global _DRIVER, _DRIVER_AT
    import time
    import infra_health as ih
    if ih.is_down("neo4j"):
        raise RuntimeError("Neo4j 차단 중(최근 연결 실패) " + ih.reason("neo4j"))
    if _DRIVER is not None and time.monotonic() - _DRIVER_AT < _REVERIFY_S:
        return _SharedDriver(_DRIVER)
    from neo4j import GraphDatabase
    with ih.guard("neo4j"):
        if _DRIVER is None:
            _DRIVER = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH, connection_timeout=5,
                                           max_connection_lifetime=300)
        try:
            _DRIVER.verify_connectivity()
        except Exception:
            d, _DRIVER = _DRIVER, None
            d.close()
            raise
    _DRIVER_AT = time.monotonic()
    return _SharedDriver(_DRIVER)


def squad_graph(team: str, min_matches: int = 4, edge_limit: int = 60) -> dict:
    try:
        d = connect()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Neo4j 미가동: {str(e)[:60]}", "nodes": [], "edges": []}
    try:
        with d.session() as s:
            nrows = s.run(
                "MATCH (p:Player)-[:PLAYS_FOR]->(:Club {name:$t}) "
                "RETURN p.name AS name, p.pos_detail AS pos, p.ss_rating AS ss", t=team).data()
            erows = s.run(
                "MATCH (p:Player)-[:PLAYS_FOR]->(c:Club {name:$t}) "
                "MATCH (p)-[x:TEAMMATE_OF]-(q:Player)-[:PLAYS_FOR]->(c) "
                "WHERE id(p) < id(q) AND x.matches >= $m "
                "RETURN p.name AS a, q.name AS b, x.matches AS m ORDER BY x.matches DESC LIMIT $lim",
                t=team, m=min_matches, lim=edge_limit).data()
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": str(e)[:120], "nodes": [], "edges": []}
    finally:
        d.close()

    edges, connected = [], set()
    for r in erows:
        edges.append({"a": r["a"], "b": r["b"], "matches": int(r["m"])})
        connected.add(r["a"]); connected.add(r["b"])
    nodes = []
    for r in nrows:
        nm = r["name"]
        if nm not in connected:            # 연결 없는 선수(거의 함께 안 뛴) 제외 → 깔끔
            continue
        try:
            ss = round(float(r["ss"]), 2) if r["ss"] is not None else None
        except (TypeError, ValueError):
            ss = None
        nodes.append({"id": nm, "name": nm, "pos": r.get("pos") or "",
                      "line": _LINE.get(r.get("pos") or "", "MID"), "rating": ss})
    return {"available": True, "team": team, "nodes": nodes, "edges": edges}


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    team = sys.argv[1] if len(sys.argv) > 1 else "Arsenal"
    g = squad_graph(team)
    print(f"{team}: nodes {len(g['nodes'])} · edges {len(g['edges'])} · available {g.get('available')}")
    for e in g["edges"][:6]:
        print(f"  {e['a']} — {e['b']} ({e['matches']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
