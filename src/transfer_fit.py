"""Transfer Fit Evaluator (Phase 1) — 영입 적합도 평가.

기존 신호(관계형 rating·_project_ovr) + Qdrant(스타일 유사도) + KG(선례)를 조립해
(후보, 대상클럽, 대상역할) → Fit Score + 리포트. 로컬 전용(KG/Qdrant 로컬 docker).

구성요소(0-100): RoleFit(Qdrant) · TeamNeed(스쿼드갭) · Translation(_project_ovr)
 · Potential · Value · Risk(감점) · Euro보너스.  (Similar-Success 는 이력데이터 확보 후)

사용:
    python src/transfer_fit.py                       # 데모
    from transfer_fit import evaluate_fit
    evaluate_fit("Vitinha", "Manchester Utd", "Central Midfield")
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "src"))
from leagues import data_path  # noqa: E402
from manager_tactics import tactical_profile  # noqa: E402

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6335")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "football26"))
LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal"]
QCOLLECTION = "players"
TM_POS_NORM = {"CB": "Centre-Back", "RB": "Right-Back", "LB": "Left-Back", "RWB": "Right-Back",
               "LWB": "Left-Back", "DM": "Defensive Midfield", "CM": "Central Midfield",
               "AM": "Attacking Midfield", "RM": "Right Midfield", "LM": "Left Midfield",
               "RW": "Right Winger", "LW": "Left Winger", "CF": "Centre-Forward",
               "SS": "Second Striker", "GK": "Goalkeeper"}


def _pos_detail(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return TM_POS_NORM.get(s, s) or None


@lru_cache(maxsize=1)
def _api():
    import main as api  # api/main.py — _player_ovr·_pos_bucket·_project_ovr·_LEAGUE_LEVEL 재사용
    return api


@lru_cache(maxsize=1)
def _pool() -> pd.DataFrame:
    """전 리그 players_full 통합(+ _league, _pos_detail, euro, career_gm)."""
    frames = []
    for lg in LEAGUES:
        try:
            df = pd.read_csv(data_path("players_full", lg))
        except (OSError, ValueError):
            continue
        df["_league"] = lg
        frames.append(df)
    pool = pd.concat(frames, ignore_index=True)
    pool["_pos_detail"] = pool.get("tm_position").map(_pos_detail)
    pool["_mv"] = pd.to_numeric(pool.get("market_value_eur"), errors="coerce")
    pool["_min"] = pd.to_numeric(pool.get("minutes"), errors="coerce").fillna(0)
    pool["_age"] = pd.to_numeric(pool.get("age"), errors="coerce")
    # 유럽대항전 출전(euro_starts) + 통산 결장 병합
    euro, gm = {}, {}
    for lg in LEAGUES:
        try:
            cu = pd.read_csv(data_path("player_comp_usage", lg))
            for _, r in cu.iterrows():
                euro[(lg, str(r.get("norm_key") or "").lower())] = float(r.get("euro_starts") or 0)
        except (OSError, ValueError):
            pass
        try:
            ih = pd.read_csv(data_path("tm_injury_history", lg))
            for tid, g in ih.groupby("tm_player_id"):
                gm[float(tid)] = int(pd.to_numeric(g.get("games_missed"), errors="coerce").fillna(0).sum())
        except (OSError, ValueError, KeyError):
            pass
    pool["_euro"] = [euro.get((lg, str(nk).lower()), 0.0)
                     for lg, nk in zip(pool["_league"], pool.get("norm_key", ""))]
    pool["_career_gm"] = [gm.get(float(t)) if pd.notna(t) else None for t in pool.get("tm_id", pd.Series())]
    return pool


def _pct(series: pd.Series, val) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty or val is None or pd.isna(val):
        return 0.5
    return float((s < val).mean())


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ── Qdrant: Role Fit + 유사선수 ────────────────────────────────────────────
def _qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL)


def _cos(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def _style_fits(qc, cand_name, role, target_club):
    """(RoleFit=리그 엘리트 역할 원형, TacticalFit=대상 클럽 해당역할 스타일=감독 기용방식, 유사선수)."""
    from qdrant_client import models
    f_name = models.Filter(must=[models.FieldCondition(key="name", match=models.MatchValue(value=cand_name))])
    got = qc.scroll(QCOLLECTION, scroll_filter=f_name, with_vectors=True, limit=1)[0]
    if not got:
        return None, None, []
    cand_vec = got[0].vector
    # RoleFit — 리그 엘리트(해당 pos_detail) 원형
    f_role = models.Filter(must=[models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role))])
    pts = qc.scroll(QCOLLECTION, scroll_filter=f_role, with_vectors=True, with_payload=True, limit=2000)[0]
    elite = [p for p in pts if (p.payload.get("ss_rating") or 0) >= 7.0 and (p.payload.get("minutes") or 0) >= 900]
    ref = elite or pts
    role_vec = np.mean([p.vector for p in ref], axis=0) if ref else None
    rolefit = _clamp(max(0.0, _cos(cand_vec, role_vec)) * 100) if role_vec is not None else None
    # TacticalFit — 대상 클럽의 해당 역할 선수 스타일 centroid(감독이 실제 그 역할을 쓰는 방식)
    f_club = models.Filter(must=[models.FieldCondition(key="club", match=models.MatchValue(value=target_club)),
                                 models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role))])
    tpts = qc.scroll(QCOLLECTION, scroll_filter=f_club, with_vectors=True, limit=50)[0]
    tvec = np.mean([p.vector for p in tpts], axis=0) if tpts else None
    tacticalfit = _clamp(max(0.0, _cos(cand_vec, tvec)) * 100) if tvec is not None else None
    sim = qc.search(QCOLLECTION, query_vector=cand_vec, limit=6)
    similar = [f"{h.payload['name']} ({h.payload['league']})" for h in sim[1:]]
    return rolefit, tacticalfit, similar


# ── KG(Neo4j): 선례(유사 리그점프) — best-effort ────────────────────────────
def _precedent(source_league, target_league):
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with d.session() as s:
            n = s.run(
                "MATCH (fr:Club)-[:COMPETES_IN]->(:League {key:$src}) "
                "MATCH (fr)<-[:FROM]-(t:TransferEvent)-[:TO]->(to:Club)-[:COMPETES_IN]->(:League {key:$tgt}) "
                "RETURN count(t) AS n", src=source_league, tgt=target_league).single()["n"]
        d.close()
        return int(n)
    except Exception:  # noqa: BLE001
        return None


def evaluate_fit(candidate: str, target_club: str, target_role: str,
                 source_league: str | None = None) -> dict:
    api, pool = _api(), _pool()
    role = _pos_detail(target_role) or target_role

    cand = pool[pool["player"].astype(str) == candidate]
    if source_league:
        cand = cand[cand["_league"] == source_league]
    if cand.empty:
        return {"error": f"후보 '{candidate}' 를 찾을 수 없음"}
    row = cand.iloc[0]
    src = row["_league"]
    tgt_rows = pool[pool["squad"].astype(str) == target_club]
    if tgt_rows.empty:
        return {"error": f"대상 클럽 '{target_club}' 없음"}
    tgt = tgt_rows.iloc[0]["_league"]

    base = api._player_ovr(row)
    age = None if pd.isna(row.get("_age")) else int(row["_age"])
    bucket = api._pos_bucket(row)
    euro = (row.get("_euro") or 0) > 0
    proj, proof, risknote = api._project_ovr(base, src, tgt, euro, age, bucket)

    # RoleFit(리그원형) + TacticalFit(감독 기용방식) + 유사선수 (Qdrant)
    try:
        rolefit, tacticalfit, similar = _style_fits(_qdrant(), candidate, role, target_club)
    except Exception as e:  # noqa: BLE001
        rolefit, tacticalfit, similar = None, None, []
        proof = (proof + f" [qdrant 오류: {str(e)[:40]}]").strip()
    rolefit = 60.0 if rolefit is None else rolefit
    tacticalfit = rolefit if tacticalfit is None else tacticalfit   # 클럽 역할표본 없으면 RoleFit 대체
    mp = tactical_profile(target_club) or {}

    # TeamNeed — 대상 클럽 해당 역할 뎁스·나이·품질·계약
    rp = tgt_rows[tgt_rows["_pos_detail"] == role]
    rp_played = rp[rp["_min"] > 0]
    depth = len(rp_played)
    best_ss = pd.to_numeric(rp_played.get("ss_rating"), errors="coerce").max() if depth else None
    avg_age = pd.to_numeric(rp_played.get("_age"), errors="coerce").mean() if depth else None
    need = 0.0
    need += 45 if depth <= 1 else (22 if depth == 2 else 5)
    pool_ss_med = pd.to_numeric(pool.get("ss_rating"), errors="coerce").median()
    if best_ss is not None and best_ss < pool_ss_med:
        need += 20
    if avg_age is not None and avg_age >= 29:
        need += 20
    elif avg_age is not None and avg_age >= 27:
        need += 10
    team_need = _clamp(need)

    # Translation(리그 이식 매끄러움) · Potential · Value · Risk
    translation = _clamp(100.0 * proj / base) if base else 60.0
    potential = _clamp(proj + max(0, 24 - (age or 24)) * 2.0)
    proj_pct = _pct(pool.get("ss_rating"), row.get("ss_rating"))
    mv_pct = _pct(pool["_mv"], row.get("_mv"))
    value = _clamp((proj_pct - mv_pct + 1) / 2 * 100)
    risk = 0.0
    mn = row.get("_min") or 0
    risk += 25 if mn < 600 else (10 if mn < 1200 else 0)
    cg = row.get("_career_gm")
    if cg is not None:
        risk += 25 if cg > 30 else (10 if cg > 15 else 0)
    if age is not None and (age <= 18 or age >= 31):
        risk += 15
    gap = api._LEAGUE_LEVEL.get(tgt, 90) - api._LEAGUE_LEVEL.get(src, 90)
    risk += 25 if gap >= 5 else (10 if gap >= 2 else 0)
    risk = _clamp(risk)

    euro_bonus = 5.0 if euro else 0.0
    fit = _clamp(0.18 * rolefit + 0.16 * tacticalfit + 0.18 * team_need + 0.16 * translation
                 + 0.12 * potential + 0.10 * value - 0.12 * risk + euro_bonus)

    if proj >= 80 and translation >= 90:
        kind = "Ready-now"
    elif (age or 30) <= 21 and potential >= 80:
        kind = "High-upside development"
    elif value >= 65 and proj >= 68:
        kind = "Value-bet"
    else:
        kind = "Rotation"
    risk_lv = "High" if risk >= 55 else ("Medium" if risk >= 30 else "Low")

    return {
        "candidate": candidate, "source_league": src, "target_club": target_club,
        "target_league": tgt, "role": role, "base_ovr": base, "proj_ovr": proj,
        "components": {"RoleFit": round(rolefit), "TacticalFit": round(tacticalfit),
                       "TeamNeed": round(team_need), "Translation": round(translation),
                       "Potential": round(potential), "Value": round(value),
                       "Risk": round(risk), "Euro": int(euro_bonus)},
        "fit_score": round(fit), "signing_type": kind, "risk_level": risk_lv,
        "manager": {"name": mp.get("manager"), "formation": mp.get("formation"),
                    "style_tags": mp.get("style_tags")},
        "team_need_detail": {"depth": depth, "best_ss": None if best_ss is None else round(float(best_ss), 2),
                             "avg_age": None if avg_age is None else round(float(avg_age), 1)},
        "similar_players": similar, "euro_experience": bool(euro),
        "precedent_transfers": _precedent(src, tgt), "notes": (proof + " " + risknote).strip(),
    }


def format_report(r: dict) -> str:
    if "error" in r:
        return "❌ " + r["error"]
    c = r["components"]
    lines = [
        f"후보: {r['candidate']} ({r['source_league']}) → {r['target_club']} / {r['role']}",
        f"  base OVR {r['base_ovr']} → proj OVR {r['proj_ovr']} ({r['target_league']})",
        f"  RoleFit {c['RoleFit']} · TacticalFit {c['TacticalFit']} · TeamNeed {c['TeamNeed']} · "
        f"Translation {c['Translation']} · Potential {c['Potential']} · Value {c['Value']} · "
        f"Risk {c['Risk']} · Euro +{c['Euro']}",
        f"  감독: {(r.get('manager') or {}).get('name') or '?'} "
        f"({(r.get('manager') or {}).get('formation') or '?'}) "
        f"{', '.join((r.get('manager') or {}).get('style_tags') or [])}",
        f"  ▶ Fit Score {r['fit_score']}/100 · 유형 {r['signing_type']} · Risk {r['risk_level']}",
        f"  팀니즈: {r['role']} 뎁스 {r['team_need_detail']['depth']}명 "
        f"(최고 ss {r['team_need_detail']['best_ss']}, 평균나이 {r['team_need_detail']['avg_age']})",
        f"  유사선수: {', '.join(r['similar_players'][:5]) or '-'}",
        f"  선례(같은 리그점프 이적): {r['precedent_transfers']}건 · 유럽경험 {'O' if r['euro_experience'] else 'X'}",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    demos = [("Ousmane Diomande", "Manchester Utd", "Centre-Back", "LigaPortugal"),
             ("Victor Froholdt", "Arsenal", "Central Midfield", "LigaPortugal")]
    for cand, club, role, src in demos:
        print("=" * 70)
        print(format_report(evaluate_fit(cand, club, role, source_league=src)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
