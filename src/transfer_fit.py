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
from manager_tactics import tactical_profile, tendency_clubs  # noqa: E402
from club_profile import price_realism, recruit_fit  # noqa: E402

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6335")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j", os.getenv("NEO4J_PASSWORD", "football26"))
LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie"]
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
    # uvicorn 안에서는 이미 로드된 api.main 재사용(중복 로드 방지). 단독 실행 시 main 로드.
    if "api.main" in sys.modules:
        return sys.modules["api.main"]
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


def _num0(v):
    try:
        f = float(v)
        return 0.0 if pd.isna(f) else f
    except (TypeError, ValueError):
        return 0.0


# ── Qdrant: Role Fit + 유사선수 ────────────────────────────────────────────
def _qdrant():
    from qdrant_client import QdrantClient
    # QDRANT_API_KEY 있으면 사용(Qdrant Cloud 등 호스팅). 로컬 docker는 키 없음.
    return QdrantClient(url=QDRANT_URL, api_key=os.getenv("QDRANT_API_KEY") or None)


def _cos(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def _role_centroid_for(qc, role, clubs):
    """주어진 클럽 표본에서 해당 역할 선수들의 스타일 centroid."""
    from qdrant_client import models
    if not clubs:
        return None
    f = models.Filter(must=[models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role)),
                            models.FieldCondition(key="club", match=models.MatchAny(any=list(clubs)))])
    pts = qc.scroll(QCOLLECTION, scroll_filter=f, with_vectors=True, limit=2000)[0]
    return np.mean([p.vector for p in pts], axis=0) if pts else None


def _elite_archetype(qc, role):
    """리그 엘리트(해당 pos_detail) 스타일 원형 centroid."""
    from qdrant_client import models
    f = models.Filter(must=[models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role))])
    pts = qc.scroll(QCOLLECTION, scroll_filter=f, with_vectors=True, with_payload=True, limit=2000)[0]
    elite = [p for p in pts if (p.payload.get("ss_rating") or 0) >= 7.0 and (p.payload.get("minutes") or 0) >= 900]
    ref = elite or pts
    return np.mean([p.vector for p in ref], axis=0) if ref else None


def _weak_roles(team, pool, k=3):
    """팀 스쿼드에서 세부 역할 뎁스가 얇은(<=2명) 주요 역할 top-k."""
    sq = pool[pool["squad"].astype(str) == team]
    played = sq[sq["_min"] > 300]
    cnt = played["_pos_detail"].value_counts().to_dict()
    MAIN = ["Centre-Back", "Right-Back", "Left-Back", "Defensive Midfield", "Central Midfield",
            "Attacking Midfield", "Right Winger", "Left Winger", "Centre-Forward"]
    thin = sorted([r for r in MAIN if cnt.get(r, 0) <= 2], key=lambda r: cnt.get(r, 0))
    return thin[:k] or ["Central Midfield"]


def _kg_enrich(team, recs, tgt_league):
    """KG(Neo4j) 신호로 후보 보강(best-effort, Neo4j 없으면 그대로).

    RUMORED_WITH: 후보가 이미 이 클럽과 루머로 연결(그래프 엣지) → 부스트+배지.
    precedent: 후보 리그→타깃 리그 이적 선례 수(TransferEvent) → 신뢰 컨텍스트.
    """
    if not recs:
        return recs
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    except Exception:  # noqa: BLE001
        return recs   # Neo4j 미가동 → KG 신호 없이 degrade
    names = [r["player"] for r in recs]
    rumored, prec = {}, {}
    try:
        with d.session() as s:
            for row in s.run(
                    "MATCH (p:Player)-[x:RUMORED_WITH]->(c:Club {name:$club}) "
                    "WHERE p.name IN $names RETURN p.name AS n, x.probability AS prob",
                    club=team, names=names).data():
                rumored[row["n"]] = row.get("prob")
            for lg in {r["source_league"] for r in recs if r["cross_league"]}:
                prec[lg] = s.run(
                    "MATCH (fr:Club)-[:COMPETES_IN]->(:League {key:$src}) "
                    "MATCH (fr)<-[:FROM]-(t:TransferEvent)-[:TO]->(to:Club)-[:COMPETES_IN]->(:League {key:$tgt}) "
                    "RETURN count(t) AS n", src=lg, tgt=tgt_league).single()["n"]
    except Exception:  # noqa: BLE001
        pass
    finally:
        d.close()
    for r in recs:
        pr = rumored.get(r["player"])
        if pr is not None:
            r["kg_rumored"] = True
            r["kg_rumor_prob"] = pr
            r["why_fit"].append(f"🔗 이 클럽과 루머 연결{f' ({int(pr)}%)' if pr else ''}")
            r["_score"] += 6
        pc = prec.get(r["source_league"])
        if pc:
            r["kg_precedent"] = int(pc)
    recs.sort(key=lambda x: -x["_score"])
    return recs


@lru_cache(maxsize=1)
def _departed_keys() -> set:
    """이번 창 이적한 선수(transfers direction=out) norm_key — 추천에서 제외(이미 떠남)."""
    try:
        import club_profile as cp
        t = cp._transfers()
        if t.empty or "norm_key" not in t.columns:
            return set()
        out = t[t.get("direction") == "out"]
        return {str(x).lower() for x in out["norm_key"].dropna().tolist() if str(x).strip()}
    except Exception:  # noqa: BLE001
        return set()


def discover_fits(team: str, role: str | None = None, top: int = 24,
                  leagues: list | None = None, min_age: int | None = None,
                  max_age: int | None = None, max_value: float | None = None) -> dict:
    """Qdrant 기반 교차리그 스타일-핏 발굴(리그 중립) — 스카우트 추천의 핵심.

    팀의 해당 역할 사용 스타일 centroid(없으면 리그 엘리트 원형)로 전 리그 벡터 검색 →
    스타일적합(코사인) + 리그변환(_project_ovr) + 유럽검증으로 랭크. EPL 편향 없음.
    필터: leagues(소스리그 화이트리스트)·min_age/max_age·max_value(시장가 상한).
    """
    api, pool = _api(), _pool()
    tgt = pool[pool["squad"].astype(str) == team]
    if tgt.empty:
        return {"available": True, "error": f"클럽 '{team}' 없음", "recommendations": []}
    tgt_league = tgt.iloc[0]["_league"]
    try:
        qc = _qdrant()
        qc.get_collections()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Qdrant 미가동: {str(e)[:60]}", "recommendations": []}

    lgset = set(leagues) if leagues else None
    departed = _departed_keys()                    # 이번 창 이적 완료 선수 제외
    roles = [(_pos_detail(role) or role)] if role else _weak_roles(team, pool)
    recs, seen = [], set()
    for rl in roles:
        target = _role_centroid_for(qc, rl, [team])
        if target is None:
            target = _elite_archetype(qc, rl)
        if target is None:
            continue
        hits = qc.search(QCOLLECTION, query_vector=target.tolist(), limit=120)
        for h in hits:
            pay = h.payload or {}
            nm, clb, lg = pay.get("name"), pay.get("club"), pay.get("league")
            if not nm or clb == team or pay.get("pos_detail") != rl or nm in seen:
                continue
            if lgset and lg not in lgset:
                continue
            prow = pool[(pool["player"].astype(str) == nm) & (pool["_league"] == lg)]
            if prow.empty:
                continue
            r = prow.iloc[0]
            if str(r.get("norm_key") or "").lower() in departed:   # 이번 창 이적 완료 → 제외
                continue
            base = int(api._player_ovr(r))
            age = None if pd.isna(r.get("_age")) else int(r["_age"])
            mv = None if pd.isna(r.get("_mv")) else int(r["_mv"])
            if min_age and age is not None and age < min_age:
                continue
            if max_age and age is not None and age > max_age:
                continue
            if max_value and mv is not None and mv > max_value:
                continue
            euro = bool((r.get("_euro") or 0) > 0)
            bucket = api._pos_bucket(r)
            proj = base if lg == tgt_league else int(api._project_ovr(base, lg, tgt_league, euro, age, bucket)[0])
            style_fit = int(round(max(0.0, h.score) * 100))
            proj_norm = _clamp((proj - 55) / 37 * 100)
            likely_fee = float(mv) * 1.2 if mv else None      # 시장가 대비 이적료 근사
            pr = price_realism(team, likely_fee)              # 가격 현실성(구단 상한 대비)
            rf = recruit_fit(team, age)                       # 영입 나이기조 부합
            contract = str(r.get("contract_until") or "")
            score = (0.42 * style_fit + 0.22 * proj_norm + 0.14 * pr["score"]
                     + 0.10 * float(rf["score"]) + (6 if euro else 0))
            cross = bool(lg != tgt_league)
            why = [f"스타일 적합 {style_fit}"]
            if cross:
                why.append(f"{lg} OVR {base}→예상 {proj}")
            if euro:
                why.append("유럽 검증")
            if age is not None and age <= 22:
                why.append(f"{age}세 성장형")
            if pr["verdict"] == "over-budget":
                why.append("예산 초과 우려")
            elif pr["verdict"] == "stretch":
                why.append("가격 다소 무리")
            if contract[:4] in ("2026", "2027"):
                why.append(f"계약 {contract[:4]} 만료")
            seen.add(nm)
            recs.append({
                "player": nm, "squad": clb or "", "pos": rl, "role_bucket": rl,
                "ovr": proj, "current_ovr": base, "projected_ovr": proj,
                "cross_league": cross, "source_league": lg, "value_eur": mv,
                "goals": int(_num0(r.get("goals"))), "assists": int(_num0(r.get("assists"))),
                "rating": round(float(_num0(r.get("ss_rating"))), 2),
                "style_fit": style_fit, "euro": euro, "age": age,
                "price_verdict": pr["verdict"], "likely_fee_eur": pr.get("likely_fee_eur"),
                "recruit_fit": int(rf["score"]), "contract_until": contract,
                "photo": str(r.get("photo") or ""), "why_fit": why, "_score": round(score, 1),
            })
    recs.sort(key=lambda x: -x["_score"])
    recs = _kg_enrich(team, recs[:max(top * 2, 24)], tgt_league)[:top]   # KG 신호 보강·재정렬
    ages = [x["age"] for x in recs if x["age"] is not None]
    vals = [x["value_eur"] for x in recs if x["value_eur"]]
    kpi = {"count": len(recs),
           "avg_age": round(sum(ages) / len(ages), 1) if ages else None,
           "avg_value": round(sum(vals) / len(vals)) if vals else None,
           "leagues": sorted({x["source_league"] for x in recs})}
    return {"available": True, "team": team, "target_league": tgt_league,
            "target_roles": roles, "weakest": {"label": " · ".join(roles)},
            "kpi": kpi, "recommendations": recs}


def _style_fits(qc, cand_name, role, target_club, tendency_cl):
    """RoleFit(리그 엘리트 원형) + CurrentFit(대상 클럽 현재 스냅샷) + TendencyFit(감독 성향 표본) + 유사선수.

    CurrentFit = 지금 그 팀이 그 역할을 쓰는 방식(빠르게 변함).
    TendencyFit = 감독 장기성향과 스타일 겹치는 클럽들의 그 역할(느리게 변함, 새 감독 대비).
    """
    from qdrant_client import models
    f_name = models.Filter(must=[models.FieldCondition(key="name", match=models.MatchValue(value=cand_name))])
    got = qc.scroll(QCOLLECTION, scroll_filter=f_name, with_vectors=True, limit=1)[0]
    if not got:
        return None, None, None, []
    cand_vec = got[0].vector
    # RoleFit — 리그 엘리트(해당 pos_detail) 원형
    f_role = models.Filter(must=[models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role))])
    pts = qc.scroll(QCOLLECTION, scroll_filter=f_role, with_vectors=True, with_payload=True, limit=2000)[0]
    elite = [p for p in pts if (p.payload.get("ss_rating") or 0) >= 7.0 and (p.payload.get("minutes") or 0) >= 900]
    ref = elite or pts
    role_vec = np.mean([p.vector for p in ref], axis=0) if ref else None
    rolefit = _clamp(max(0.0, _cos(cand_vec, role_vec)) * 100) if role_vec is not None else None
    # CurrentFit — 대상 클럽의 해당 역할 선수 스타일 centroid(현재 시즌 스냅샷)
    cvec = _role_centroid_for(qc, role, [target_club])
    current_fit = _clamp(max(0.0, _cos(cand_vec, cvec)) * 100) if cvec is not None else None
    # TendencyFit — 감독 성향과 스타일 겹치는 클럽 표본의 해당 역할
    tvec = _role_centroid_for(qc, role, tendency_cl)
    tendency_fit = _clamp(max(0.0, _cos(cand_vec, tvec)) * 100) if tvec is not None else None
    sim = qc.search(QCOLLECTION, query_vector=cand_vec, limit=6)
    similar = [f"{h.payload['name']} ({h.payload['league']})" for h in sim[1:]]
    return rolefit, current_fit, tendency_fit, similar


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

    # RoleFit(리그원형) + CurrentFit(현재 스냅샷) + TendencyFit(감독 성향) + 유사선수 (Qdrant)
    mp = tactical_profile(target_club) or {}
    ten = mp.get("tenure") or {"w_current": 0.65, "w_tendency": 0.35, "is_new": False}
    try:
        rolefit, current_fit, tendency_fit, similar = _style_fits(
            _qdrant(), candidate, role, target_club, tendency_clubs(target_club))
    except Exception as e:  # noqa: BLE001
        rolefit, current_fit, tendency_fit, similar = None, None, None, []
        proof = (proof + f" [qdrant 오류: {str(e)[:40]}]").strip()
    rolefit = 60.0 if rolefit is None else rolefit
    current_fit = rolefit if current_fit is None else current_fit    # 클럽 역할표본 없으면 RoleFit 대체
    tendency_fit = current_fit if tendency_fit is None else tendency_fit
    # TacticalFit = 재임 기반 블렌드(안정=현재 중심 / 새 부임=감독 성향 중심)
    wc, wt = ten["w_current"], ten["w_tendency"]
    tacticalfit = _clamp(wc * current_fit + wt * tendency_fit)

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

    # RecruitFit(구단 영입 나이성향 매칭) + PriceRealism(예상이적료 vs 구단 가격상한)
    rf = recruit_fit(target_club, age)
    mv = row.get("_mv")
    likely_fee = float(mv) * 1.2 if pd.notna(mv) else None   # 시장가치 대비 이적료 프리미엄 근사
    pr = price_realism(target_club, likely_fee)
    recruitfit, pricerealism = float(rf["score"]), float(pr["score"])

    euro_bonus = 5.0 if euro else 0.0
    fit = _clamp(0.16 * rolefit + 0.14 * tacticalfit + 0.16 * team_need + 0.14 * translation
                 + 0.10 * potential + 0.08 * value + 0.07 * recruitfit + 0.07 * pricerealism
                 - 0.12 * risk + euro_bonus)

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
                       "RecruitFit": round(recruitfit), "PriceRealism": round(pricerealism),
                       "Risk": round(risk), "Euro": int(euro_bonus)},
        "fit_score": round(fit), "signing_type": kind, "risk_level": risk_lv,
        "tactical_detail": {"current_fit": round(current_fit), "tendency_fit": round(tendency_fit),
                            "blended": round(tacticalfit), "w_current": wc, "w_tendency": wt,
                            "is_new_manager": ten.get("is_new"), "appointed": ten.get("appointed"),
                            "descriptor_tags": mp.get("descriptor_tags") or []},
        "affordability": {"verdict": pr["verdict"], "likely_fee_eur": pr.get("likely_fee_eur"),
                          "ceiling_eur": pr.get("ceiling_eur"), "spend_tier": pr.get("spend_tier"),
                          "club_recruit_profile": rf.get("age_profile"),
                          "club_avg_signing_age": rf.get("club_avg_age")},
        "manager": {"name": mp.get("manager"), "formation": mp.get("formation"),
                    "style_tags": mp.get("style_tags")},
        "team_need_detail": {"depth": depth, "best_ss": None if best_ss is None else round(float(best_ss), 2),
                             "avg_age": None if avg_age is None else round(float(avg_age), 1)},
        "similar_players": similar, "euro_experience": bool(euro),
        "precedent_transfers": _precedent(src, tgt), "notes": (proof + " " + risknote).strip(),
    }


def _tactical_line(t: dict) -> str:
    if not t:
        return "  전술적합: -"
    stab = "새 부임" if t.get("is_new_manager") else "안정"
    return (f"  전술적합: 현재 {t.get('current_fit')} · 감독성향 {t.get('tendency_fit')} "
            f"→ 블렌드 {t.get('blended')} "
            f"(재임 {t.get('appointed') or '?'}, {stab}: 현재{int((t.get('w_current') or 0)*100)}%"
            f"/성향{int((t.get('w_tendency') or 0)*100)}%)")


def _afford_line(a: dict) -> str:
    if not a:
        return "  구단성향/예산: -"
    lf = a.get("likely_fee_eur")
    cl = a.get("ceiling_eur")
    fee_s = f"{lf/1e6:.0f}M" if lf else "?"
    cl_s = f"{cl/1e6:.0f}M" if cl else "?"
    v = {"within": "적정", "stretch": "무리", "over-budget": "예산초과", "unknown": "?"}.get(a.get("verdict"), a.get("verdict"))
    return (f"  구단성향/예산: {a.get('club_recruit_profile') or '?'} "
            f"(평균영입나이 {a.get('club_avg_signing_age') or '?'}) · "
            f"{a.get('spend_tier') or '?'} tier · 가격 {fee_s}/상한 {cl_s} → {v}")


def format_report(r: dict) -> str:
    if "error" in r:
        return "❌ " + r["error"]
    c = r["components"]
    lines = [
        f"후보: {r['candidate']} ({r['source_league']}) → {r['target_club']} / {r['role']}",
        f"  base OVR {r['base_ovr']} → proj OVR {r['proj_ovr']} ({r['target_league']})",
        f"  RoleFit {c['RoleFit']} · TacticalFit {c['TacticalFit']} · TeamNeed {c['TeamNeed']} · "
        f"Translation {c['Translation']} · Potential {c['Potential']} · Value {c['Value']} · "
        f"RecruitFit {c['RecruitFit']} · PriceRealism {c['PriceRealism']} · "
        f"Risk {c['Risk']} · Euro +{c['Euro']}",
        f"  감독: {(r.get('manager') or {}).get('name') or '?'} "
        f"({(r.get('manager') or {}).get('formation') or '?'}) "
        f"{', '.join((r.get('manager') or {}).get('style_tags') or [])}",
        _tactical_line(r.get("tactical_detail") or {}),
        _afford_line(r.get("affordability") or {}),
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
