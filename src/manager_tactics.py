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
import re
import sys
from datetime import date
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
NEO4J_AUTH = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j", os.getenv("NEO4J_PASSWORD", "football26"))
LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague"]

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

SEASON = os.getenv("FB_SEASON", "2025_2026")   # 현재 스냅샷 시즌(시즌 쌓이면 append)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

# 감독 '장기 성향'(descriptor 텍스트) ↔ 표준 전술 태그. 현재 팀 스냅샷과 별개(느리게 변함).
_TEXT_TAGS = {
    "press": ["press", "gegen", "high line", "high-press", "aggress", "front-foot"],
    "possession": ["possess", "control", "positional", "tiki", "build-up", "buildup",
                   "patient", "dominance", "rotation"],
    "direct": ["counter", "direct", "vertical", "transition", "quick", "fast break"],
    "low_block": ["low block", "low-block", "compact", "defensive", "deep", "reactive", "pragmat"],
    "wing": ["wing", "width", "cross", "flank", "overlap", "wide"],
    "aerial": ["aerial", "set-piece", "set piece", "physical", "long ball", "duel"],
    "attacking": ["attack", "goal", "front", "offensiv", "expansive"],
}


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


def _parse_appointed(s: str):
    """'Dec 2019' / '1 June 2026' / '2020' → date. 실패 시 None."""
    s = (s or "").strip().lower()
    if not s:
        return None
    m = re.match(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", s)      # '30 april 2026'
    if m and _MONTHS.get(m.group(2)[:3]):
        return date(int(m.group(3)), _MONTHS[m.group(2)[:3]], min(int(m.group(1)), 28))
    m = re.match(r"([a-z]+)\s+(\d{4})", s)                    # 'dec 2019'
    if m and _MONTHS.get(m.group(1)[:3]):
        return date(int(m.group(2)), _MONTHS[m.group(1)[:3]], 1)
    m = re.match(r"(\d{4})$", s)                              # '2020'
    if m:
        return date(int(m.group(1)), 1, 1)
    return None


@lru_cache(maxsize=1)
def _recent_changes() -> set:
    """감독 교체 감지된 클럽(전 리그) — 새 부임 보강 신호."""
    from leagues import data_path as _dp
    out = set()
    for lg in LEAGUES:
        try:
            mc = pd.read_csv(_dp("manager_changes", lg))
        except (OSError, ValueError):
            continue
        for _, r in mc.iterrows():
            if str(r.get("accepted")).lower() in ("true", "1") and r.get("team"):
                out.add(str(r["team"]))
    return out


def tenure_context(club: str) -> dict:
    """재임 기간 → 현재 스냅샷 vs 감독 장기성향 블렌드 가중치.

    안정 감독(재임 김) → 현재 팀 전술 신뢰(current-heavy).
    새 부임(스냅샷=전임자 것) → 감독 성향 쪽으로 flip(tendency-heavy).
    """
    _, mgr, _ = _load()
    lg = _league_of(club)
    prof = mgr.get(lg, {}).get(club, {}) if lg else {}
    d = _parse_appointed(prof.get("appointed", ""))
    months = None
    if d:
        today = date.today()
        months = (today.year - d.year) * 12 + (today.month - d.month)
    changed = club in _recent_changes()
    m_eff = months if months is not None else (2 if changed else 18)
    is_new = m_eff <= 6 or (changed and m_eff <= 10)
    m = max(0, min(24, m_eff))
    w_current = round(min(0.75, max(0.30, 0.30 + 0.45 * min(1.0, max(0.0, (m - 3) / 9)))), 2)
    return {"appointed": prof.get("appointed") or None, "months": months, "is_new": is_new,
            "recent_change": changed, "w_current": w_current, "w_tendency": round(1 - w_current, 2)}


def _canon_from_vec(v: dict) -> set:
    """현재 팀 전술벡터 → 표준 태그(현 스냅샷의 실제 성향)."""
    t = set()
    if v.get("pressing", 0) >= 62:
        t.add("press")
    if v.get("control", 0) >= 60 and v.get("creativity", 0) >= 60:
        t.add("possession")
    if v.get("attack_output", 0) >= 68:
        t.add("attacking")
    if v.get("attack_creation", 0) >= 70:
        t.add("wing")
    if v.get("aerial", 0) >= 70:
        t.add("aerial")
    if v.get("control", 100) < 48 and v.get("pressing", 100) < 52:
        t.add("low_block")
    return t


def _canon_from_text(text: str) -> set:
    """감독 descriptor(style+focus+formation) 텍스트 → 표준 태그(장기 성향)."""
    tl = (text or "").lower()
    return {tag for tag, kws in _TEXT_TAGS.items() if any(k in tl for k in kws)}


def descriptor_tags(club: str) -> list:
    _, mgr, _ = _load()
    lg = _league_of(club)
    prof = mgr.get(lg, {}).get(club, {}) if lg else {}
    txt = " ".join(str(prof.get(k) or "") for k in ("style", "focus", "formation"))
    return sorted(_canon_from_text(txt))


def tendency_clubs(club: str) -> list:
    """감독 장기성향(descriptor)과 스타일이 겹치는 클럽들 — '성향 원형' 표본.

    안정 감독이면 자기 클럽 포함(성향≈현재). 새 감독이면 descriptor 기반이라
    현재(전임자) 스냅샷 대신 성향에 맞는 클럽 표본을 씀. 겹침 없으면 자기 클럽 폴백.
    """
    tum, _, _ = _load()
    mtags = set(descriptor_tags(club))
    if not mtags:
        return [club]
    out = []
    for _lg, t in tum.items():
        for c in t.index:
            row = t.loc[c]
            vec = {ax: float(row[col]) for ax, col in AXES.items()
                   if col in row.index and pd.notna(row[col])}
            if mtags & _canon_from_vec(vec):
                out.append(c)
    return out or [club]


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
    ten = tenure_context(club)
    return {
        "club": club, "league": lg, "manager": prof.get("name") or "?",
        "formation": prof.get("formation") or None, "style_text": (prof.get("style") or "") or None,
        # 현재 시즌 스냅샷(빠르게 변함) — 시즌/기간 키로 두어 다시즌 확장 대비
        "season": SEASON, "period": "full-season",
        "tactical_vector": vec, "style_tags": _style_tags(vec), "role_usage": role_usage,
        # 감독 장기 성향(느리게 변함) + 재임 기반 블렌드 가중치
        "descriptor_tags": descriptor_tags(club), "tenure": ten,
        "note": "current=팀스냅샷(단일시즌) / tendency=감독 descriptor. 재임으로 블렌드.",
    }


def sync_to_kg() -> int:
    """시즌별 TacticalSnapshot(append) + Manager 장기성향/재임 속성 + EMPHASIZES 적재.

    전술은 감독 '고정값'이 아니라 (club, season, period) 스냅샷 → 시즌 쌓이면 누적.
    Manager 노드엔 느리게 변하는 것만(descriptor 성향·재임·formation).
    """
    from neo4j import GraphDatabase
    tum, _, _ = _load()
    clubs = [c for lg in tum for c in tum[lg].index]
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    n = 0
    with d.session() as s:
        s.run("CREATE CONSTRAINT role_name IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE")
        s.run("CREATE CONSTRAINT tacsnap_id IF NOT EXISTS "
              "FOR (t:TacticalSnapshot) REQUIRE t.id IS UNIQUE")
        for club in clubs:
            p = tactical_profile(club)
            if not p or p["manager"] == "?":
                continue
            v, ten = p["tactical_vector"], p["tenure"]
            snap_id = f"{club}|{p['season']}|{p['period']}"
            # 시즌 스냅샷(append) — 클럽·감독에 연결
            s.run(
                "MERGE (t:TacticalSnapshot {id:$id}) "
                "SET t.club=$club, t.season=$season, t.period=$period, t.manager=$mgr, "
                "    t.style_tags=$tags, t.pressing=$pr, t.control=$ct, t.creativity=$cr, "
                "    t.attack=$at, t.aerial=$ae, t.disruption=$di "
                "WITH t MATCH (c:Club {name:$club}) MERGE (c)-[:HAS_SNAPSHOT]->(t) "
                "WITH t MATCH (m:Manager {name:$mgr}) MERGE (m)-[:HAD_SNAPSHOT]->(t)",
                id=snap_id, club=club, season=p["season"], period=p["period"], mgr=p["manager"],
                tags=p["style_tags"], pr=v.get("pressing"), ct=v.get("control"),
                cr=v.get("creativity"), at=v.get("attack_output"), ae=v.get("aerial"),
                di=v.get("disruption"))
            # 감독 장기 성향(느림) — descriptor 태그·재임·formation
            s.run(
                "MATCH (m:Manager {name:$mgr}) "
                "SET m.formation=$formation, m.tendency_tags=$dtags, m.appointed=$appt, "
                "    m.months_tenure=$months, m.is_new=$isnew",
                mgr=p["manager"], formation=p["formation"], dtags=p["descriptor_tags"],
                appt=ten["appointed"], months=ten["months"], isnew=ten["is_new"])
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
    for club in ["Arsenal", "Barcelona", "Bayern Munich", "Manchester Utd", "Bournemouth"]:
        p = tactical_profile(club)
        if not p:
            print(f"  {club}: 프로필 없음"); continue
        t = p["tenure"]
        stab = "새 부임" if t["is_new"] else "안정"
        print(f"■ {club} ({p['manager']}, {p['formation'] or '?'}) — 현재:{', '.join(p['style_tags'])}")
        print(f"   감독성향(descriptor): {', '.join(p['descriptor_tags']) or '-'}")
        print(f"   재임: {t['appointed'] or '?'} ({t['months']}개월, {stab}) "
              f"→ 블렌드 현재 {int(t['w_current']*100)}% / 성향 {int(t['w_tendency']*100)}%")
        print(f"   역할사용: {', '.join(f'{r['role']}({int(r['minutes_share']*100)}%)' for r in p['role_usage'][:5])}")
    n = sync_to_kg()
    print(f"\n[mgr-tactics] KG 적재: 감독 {n}명 전술속성 + EMPHASIZES 역할")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
