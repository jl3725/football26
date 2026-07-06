"""football26 지식그래프(KG) 적재 — CSV → Neo4j (멱등 MERGE, 증분).

노드:  League, Country, Club, Player(id=tm_id), Manager, TransferEvent
관계:  (League)-[:IN_COUNTRY]->(Country)
       (Club)-[:COMPETES_IN]->(League)
       (Player)-[:PLAYS_FOR]->(Club)
       (Manager)-[:MANAGES]->(Club)
       (TransferEvent)-[:OF]->(Player) / -[:FROM]->(Club) / -[:TO]->(Club)

접속(기본: 로컬 docker-compose): NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 환경변수.
사용:  pip install -r requirements-kg.txt && python scripts/build_kg.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from leagues import data_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "football26")

# 리그 → (표시명, 국가, UEFA계수 기반 리그레벨)  ※ api._LEAGUE_LEVEL 와 정합
LEAGUE_META = {
    "EPL": ("Premier League", "England", 100.0),
    "LaLiga": ("La Liga", "Spain", 95.5),
    "SerieA": ("Serie A", "Italy", 96.1),
    "Bundesliga": ("Bundesliga", "Germany", 94.7),
    "Ligue1": ("Ligue 1", "France", 92.8),
    "LigaPortugal": ("Liga Portugal", "Portugal", 90.7),
}

CONSTRAINTS = [
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT club_name IF NOT EXISTS FOR (c:Club) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT league_key IF NOT EXISTS FOR (l:League) REQUIRE l.key IS UNIQUE",
    "CREATE CONSTRAINT country_name IF NOT EXISTS FOR (n:Country) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT manager_name IF NOT EXISTS FOR (m:Manager) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT transfer_id IF NOT EXISTS FOR (t:TransferEvent) REQUIRE t.id IS UNIQUE",
]


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _load_players(league: str) -> list[dict]:
    try:
        df = pd.read_csv(data_path("players_full", league))
    except (OSError, ValueError):
        return []
    rows = []
    for _, r in df.iterrows():
        tm = _clean(r.get("tm_id"))
        nk = _clean(r.get("norm_key"))
        pid = f"tm:{int(tm)}" if tm is not None else (f"nk:{league}:{nk}" if nk else None)
        if not pid or not _clean(r.get("player")):
            continue
        rows.append({
            "id": pid, "name": str(r.get("player")), "club": str(r.get("squad") or ""),
            "pos": _clean(r.get("pos")), "age": _num(r.get("age")),
            "nat": _clean(r.get("nationality")), "mv": _num(r.get("market_value_eur")),
            "ss": _num(r.get("ss_rating")), "goals": _num(r.get("goals")),
            "assists": _num(r.get("assists")), "minutes": _num(r.get("minutes")),
        })
    return rows


def _load_managers(league: str) -> list[dict]:
    try:
        d = json.loads(data_path("manager_profiles", league, ext="json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for club, prof in d.items():
        name = (prof or {}).get("name")
        if name and str(name).strip():
            out.append({"name": str(name).strip(), "club": club,
                        "nationality": _clean((prof or {}).get("nationality")),
                        "formation": _clean((prof or {}).get("formation"))})
    return out


def _load_transfers(league: str) -> list[dict]:
    try:
        df = pd.read_csv(data_path("transfers", league))
    except (OSError, ValueError):
        return []
    rows = []
    for _, r in df.iterrows():
        if str(r.get("direction")) != "in":
            continue
        player, to, frm = str(r.get("player") or ""), str(r.get("squad") or ""), str(r.get("club") or "")
        if not player or not to:
            continue
        season = str(r.get("season") or "")
        rows.append({
            "id": f"{league}:{season}:{player}:{frm}->{to}", "player": player,
            "to": to, "from": frm, "fee_eur": _num(r.get("fee_eur")),
            "fee_text": _clean(r.get("fee_text")), "window": _clean(r.get("window")), "season": season,
        })
    return rows


def _batched(session, cypher, rows, batch=200, **params):
    for i in range(0, len(rows), batch):
        session.run(cypher, rows=rows[i:i + batch], **params)


def main() -> int:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[kg] connected {NEO4J_URI}")

    with driver.session() as s:
        for c in CONSTRAINTS:
            s.run(c)

        for lg, (name, country, level) in LEAGUE_META.items():
            s.run("MERGE (l:League {key:$k}) SET l.name=$n, l.level=$lv "
                  "MERGE (co:Country {name:$c}) MERGE (l)-[:IN_COUNTRY]->(co)",
                  k=lg, n=name, c=country, lv=level)

            players = _load_players(lg)
            _batched(s,
                     "UNWIND $rows AS r "
                     "MERGE (c:Club {name:r.club}) "
                     "MERGE (l:League {key:$key}) MERGE (c)-[:COMPETES_IN]->(l) "
                     "MERGE (p:Player {id:r.id}) "
                     "  SET p.name=r.name, p.pos=r.pos, p.age=r.age, p.nationality=r.nat, "
                     "      p.market_value_eur=r.mv, p.ss_rating=r.ss, p.goals=r.goals, "
                     "      p.assists=r.assists, p.minutes=r.minutes, p.league=$key "
                     "MERGE (p)-[:PLAYS_FOR]->(c)", players, key=lg)

            managers = _load_managers(lg)
            _batched(s,
                     "UNWIND $rows AS r MERGE (m:Manager {name:r.name}) "
                     "SET m.nationality=r.nationality, m.formation=r.formation "
                     "MERGE (c:Club {name:r.club}) MERGE (m)-[:MANAGES]->(c)", managers)

            transfers = _load_transfers(lg)
            _batched(s,
                     "UNWIND $rows AS r MERGE (t:TransferEvent {id:r.id}) "
                     "  SET t.player=r.player, t.fee_eur=r.fee_eur, t.fee_text=r.fee_text, "
                     "      t.window=r.window, t.season=r.season "
                     "MERGE (to:Club {name:r.to}) MERGE (t)-[:TO]->(to) "
                     "FOREACH (_ IN CASE WHEN r.from <> '' THEN [1] ELSE [] END | "
                     "  MERGE (fr:Club {name:r.from}) MERGE (t)-[:FROM]->(fr)) "
                     "WITH t, r MATCH (p:Player {name:r.player})-[:PLAYS_FOR]->(:Club {name:r.to}) "
                     "MERGE (t)-[:OF]->(p)", transfers)

            print(f"  {lg:14} players={len(players)} managers={len(managers)} transfers={len(transfers)}")

        counts = s.run(
            "MATCH (p:Player) WITH count(p) AS players "
            "MATCH (c:Club) WITH players, count(c) AS clubs "
            "MATCH (t:TransferEvent) RETURN players, clubs, count(t) AS transfers").single()
        print(f"[kg] 총 Player={counts['players']} Club={counts['clubs']} TransferEvent={counts['transfers']}")
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
