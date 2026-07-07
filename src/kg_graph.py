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


def squad_graph(team: str, min_matches: int = 4, edge_limit: int = 60) -> dict:
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
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
