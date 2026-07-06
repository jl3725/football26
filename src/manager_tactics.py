"""Manager Tactical Profile v1 — 감독/팀 전술 프로필 (조립: 기존 데이터, 스크랩 없음).

정량(team_unit_metrics 지표) + 역할 사용(스쿼드 pos_detail 출전분포) + 선호포메이션/스타일
(manager_profiles, 있으면). 감독이 바뀌면 이 프로필이 바뀌고 → 역할 니즈·영입 후보가 바뀐다.

주의(단일 시즌): 팀 지표는 '그 시즌 그 팀'이라 감독 고유성향 + 스쿼드 질이 섞임(=team-derived).
최근 부임 감독은 시즌 스탯이 이전 감독분일 수 있음 → 근사치로 사용.

사용: python src/manager_tactics.py  (프로필 데모 + KG 적재)
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
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
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "football26"))
LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal"]

# 전술 축 → team_unit_metrics 컬럼 (0-100)
AXES = {"pressing": "pressing_index", "ball_winning": "midfield_ball_winning_index",
        "creativity": "midfield_creativity_index", "control": "midfield_control_index",
        "attack_creation": "attack_creation_index", "attack_output": "attack_output_index",
        "disruption": "defense_disruption_index", "aerial": "defense_box_aerial_index"}

TM_POS_NORM = {"CB": "Centre-Back", "RB": "Right-Back", "LB": "Left-Back", "RWB": "Right-Back",
               "LWB": "Left-Back", "DM": "Defensive Midfield", "CM": "Central Midfield",
               "AM": "Attacking Midfield", "RM": "Right Midfield", "LM": "Left Midfield",
               "RW": "Right Winger", "LW": "Left Winger", "CF": "Centre-Forward",
               "SS": "Second Striker", "GK": "Goalkeeper"}


def _posd(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return TM_POS_NORM.get(s, s) or None


@lru_cache(maxsize=1)
def _load():
    """리그별 team_unit_metrics·manager_profiles·players_full 로드."""
    tum, mgr, squad = {}, {}, {}
    for lg in LEAGUES:
        try:
            tum[lg] = pd.read_csv(data_path("team_unit_metrics", lg)).set_index("squad")
        except (OSError, ValueError, KeyError):
            pass
        try:
            mgr[lg] = json.loads(data_path("manager_profiles", lg, ext="json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            mgr[lg] = {}
        try:
            pf = pd.read_csv(data_path("players_full", lg))
            pf["_posd"] = pf.get("tm_position").map(_posd)
            pf["_min"] = pd.to_numeric(pf.get("minutes"), errors="coerce").fillna(0)
            squad[lg] = pf
        except (OSError, ValueError):
            pass
    return tum, mgr, squad


def _league_of(club: str) -> str | None:
    tum, _, _ = _load()
    for lg, t in tum.items():
        if club in t.index:
            return lg
    return None


def _style_tags(v: dict) -> list[str]:
    tags = []
    if v.get("pressing", 0) >= 65:
        tags.append("high-press")
    if v.get("control", 0) >= 65 and v.get("creativity", 0) >= 65:
        tags.append("possession")
    if v.get("attack_creation", 0) >= 72:
        tags.append("chance-creation")
    if v.get("attack_output", 0) >= 72:
        tags.append("attacking")
    if v.get("aerial", 0) >= 72:
        tags.append("aerial-strong")
    if v.get("disruption", 0) >= 65:
        tags.append("disruptive-defense")
    if v.get("control", 0) < 45 and v.get("pressing", 0) < 50:
        tags.append("reactive/low-block")
    return tags or ["balanced"]


def tactical_profile(club: str) -> dict | None:
    tum, mgr, squad = _load()
    lg = _league_of(club)
    if not lg:
        return None
    row = tum[lg].loc[club]
    vec = {ax: round(float(row[col]), 1) for ax, col in AXES.items() if col in row.index and pd.notna(row[col])}
    prof = mgr.get(lg, {}).get(club, {})
    # 역할 사용(감독이 실제 기용하는 역할) — pos_detail 출전분(minutes) 비중 top
    role_usage = []
    if lg in squad:
        sq = squad[lg]
        cl = sq[sq["squad"].astype(str) == club]
        by = cl.groupby("_posd")["_min"].sum().sort_values(ascending=False)
        tot = by.sum() or 1
        role_usage = [{"role": r, "minutes_share": round(float(m) / tot, 3)}
                      for r, m in by.items() if r][:6]
    return {
        "club": club, "league": lg, "manager": prof.get("name") or "?",
        "formation": prof.get("formation") or None, "style_text": (prof.get("style") or "") or None,
        "tactical_vector": vec, "style_tags": _style_tags(vec), "role_usage": role_usage,
        "note": "team-derived(감독+스쿼드 혼합, 단일시즌 근사)",
    }


def sync_to_kg() -> int:
    """Manager 노드에 전술 속성 + (Manager)-[:EMPHASIZES {share}]->(Role) 적재."""
    from neo4j import GraphDatabase
    tum, _, _ = _load()
    clubs = [c for lg in tum for c in tum[lg].index]
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    n = 0
    with d.session() as s:
        s.run("CREATE CONSTRAINT role_name IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE")
        for club in clubs:
            p = tactical_profile(club)
            if not p or p["manager"] == "?":
                continue
            v = p["tactical_vector"]
            s.run(
                "MATCH (m:Manager {name:$mgr}) "
                "SET m.formation=$formation, m.style_tags=$tags, "
                "    m.tac_pressing=$pr, m.tac_control=$ct, m.tac_creativity=$cr, "
                "    m.tac_attack=$at, m.tac_aerial=$ae, m.tac_disruption=$di",
                mgr=p["manager"], formation=p["formation"], tags=p["style_tags"],
                pr=v.get("pressing"), ct=v.get("control"), cr=v.get("creativity"),
                at=v.get("attack_output"), ae=v.get("aerial"), di=v.get("disruption"))
            for ru in p["role_usage"][:4]:
                s.run("MATCH (m:Manager {name:$mgr}) MERGE (r:Role {name:$role}) "
                      "MERGE (m)-[e:EMPHASIZES]->(r) SET e.minutes_share=$sh",
                      mgr=p["manager"], role=ru["role"], sh=ru["minutes_share"])
            n += 1
    d.close()
    return n


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for club in ["Arsenal", "Barcelona", "Bayern Munich"]:
        p = tactical_profile(club)
        if not p:
            print(f"  {club}: 프로필 없음"); continue
        print(f"■ {club} ({p['manager']}, {p['formation'] or '?'}) — {', '.join(p['style_tags'])}")
        print(f"   전술벡터: {p['tactical_vector']}")
        print(f"   역할사용: {', '.join(f'{r['role']}({int(r['minutes_share']*100)}%)' for r in p['role_usage'][:5])}")
    n = sync_to_kg()
    print(f"\n[mgr-tactics] KG 적재: 감독 {n}명 전술속성 + EMPHASIZES 역할")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
