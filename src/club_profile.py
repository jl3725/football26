"""Club Recruitment DNA + Affordability (조립: 기존 데이터, 스크랩 없음).

영입 성향 · 예산(프록시) — 감독 전술([[manager_tactics]])과 짝을 이루는 '구단 성향' 레이어.

  recruitment_dna(club): 최근 영입의 나이/이적료 패턴 → 유망주형 vs 즉전형, 큰손 vs 가성비
     재료: transfers_<league>.csv (direction=='in', squad==club). age 100% · fee_eur 부분.

  affordability(club): 지출 여력 '프록시'(실제 예산/급여 아님) →
     스쿼드 총 시장가치(players_full market_value_eur) + 드러난 순영입비/최고이적료(transfers).

  spend_pressure(club): net spend vs 스쿼드가치 근사 지표. ⚠ FFP/PSR 아님
     (진짜 FFP는 매출·급여·3년 손실·상각이 필요 — 우리 데이터에 없음. 흉내 금지).

로컬/CI 어디서나 동작(순수 CSV). KG 적재는 sync_to_kg().
사용: python src/club_profile.py   (데모 + KG 적재)
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
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


@lru_cache(maxsize=1)
def _transfers() -> pd.DataFrame:
    """전 리그 transfers 통합(+ _league)."""
    frames = []
    for lg in LEAGUES:
        try:
            df = pd.read_csv(data_path("transfers", lg))
        except (OSError, ValueError):
            continue
        df["_league"] = lg
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    t = pd.concat(frames, ignore_index=True)
    t["_age"] = pd.to_numeric(t.get("age"), errors="coerce")
    t["_fee"] = pd.to_numeric(t.get("fee_eur"), errors="coerce")
    return t


@lru_cache(maxsize=1)
def _squad_value() -> pd.DataFrame:
    """클럽별 스쿼드 총 시장가치(players_full market_value_eur 합) + 리그 내 백분위 tier."""
    frames = []
    for lg in LEAGUES:
        try:
            df = pd.read_csv(data_path("players_full", lg))
        except (OSError, ValueError):
            continue
        df["_mv"] = pd.to_numeric(df.get("market_value_eur"), errors="coerce")
        g = df.groupby(df["squad"].astype(str))["_mv"].agg(["sum", "count"]).reset_index()
        g.columns = ["club", "squad_value", "n_players"]
        g["_league"] = lg
        frames.append(g)
    if not frames:
        return pd.DataFrame()
    sv = pd.concat(frames, ignore_index=True)
    # 전 리그 통합 백분위(리그레벨 무보정 — 절대 지출여력 관점)
    sv["value_pct"] = sv["squad_value"].rank(pct=True)
    return sv


def _tier(pct: float) -> str:
    if pct >= 0.80:
        return "elite"
    if pct >= 0.55:
        return "big"
    if pct >= 0.30:
        return "mid"
    return "modest"


def recruitment_dna(club: str) -> dict | None:
    """구단 영입 성향(최근 창) — 나이 패턴 + 이적료 패턴 + 라벨."""
    t = _transfers()
    if t.empty:
        return None
    inn = t[(t.get("direction") == "in") & (t["squad"].astype(str) == club)]
    if inn.empty:
        return None
    ages = inn["_age"].dropna()
    fees = inn["_fee"].dropna()
    n = len(inn)
    avg_age = float(ages.mean()) if len(ages) else None
    u21 = float((ages <= 21).mean()) if len(ages) else None
    u23 = float((ages <= 23).mean()) if len(ages) else None
    prime = float(((ages >= 24) & (ages <= 29)).mean()) if len(ages) else None
    vet = float((ages >= 30).mean()) if len(ages) else None
    avg_fee = float(fees.mean()) if len(fees) else None
    max_fee = float(fees.max()) if len(fees) else None
    med_fee = float(fees.median()) if len(fees) else None
    paid_ratio = float(len(fees) / n) if n else None   # 유료(이적료) 비율(무료·임대 제외)

    # 나이 라벨
    if avg_age is None:
        age_tag = "unknown"
    elif avg_age <= 22.5:
        age_tag = "prospect-oriented"      # 유망주 지향
    elif avg_age >= 25.5:
        age_tag = "experience-oriented"    # 즉전/경험 지향
    else:
        age_tag = "balanced-age"
    # 지출 라벨(전 리그 유료영입 평균이적료 대비)
    all_fees = t[(t.get("direction") == "in")]["_fee"].dropna()
    fee_med_all = float(all_fees.median()) if len(all_fees) else 0.0
    if avg_fee is None:
        spend_tag = "free/loan-heavy"
    elif avg_fee >= fee_med_all * 2.2:
        spend_tag = "big-spender"
    elif avg_fee <= fee_med_all * 0.6:
        spend_tag = "bargain/value"
    else:
        spend_tag = "moderate-spender"
    return {
        "club": club, "n_signings": n, "avg_age": None if avg_age is None else round(avg_age, 1),
        "u21_ratio": None if u21 is None else round(u21, 2),
        "u23_ratio": None if u23 is None else round(u23, 2),
        "prime_ratio": None if prime is None else round(prime, 2),
        "veteran_ratio": None if vet is None else round(vet, 2),
        "avg_fee_eur": None if avg_fee is None else round(avg_fee),
        "max_fee_eur": None if max_fee is None else round(max_fee),
        "median_fee_eur": None if med_fee is None else round(med_fee),
        "paid_ratio": None if paid_ratio is None else round(paid_ratio, 2),
        "age_profile": age_tag, "spend_profile": spend_tag,
        "profile": f"{age_tag} · {spend_tag}",
        "note": "최근 이적창 실제 영입 기준(단일 시즌)",
    }


def affordability(club: str) -> dict | None:
    """지출 여력 '프록시'(실제 예산/급여 아님) — 스쿼드가치 + 드러난 지출 + 가격상한 추정."""
    sv = _squad_value()
    row = sv[sv["club"] == club]
    if row.empty:
        return None
    r = row.iloc[0]
    squad_value = float(r["squad_value"]) if pd.notna(r["squad_value"]) else 0.0
    pct = float(r["value_pct"])
    t = _transfers()
    mine = t[t["squad"].astype(str) == club]
    gross_in = float(mine[mine.get("direction") == "in"]["_fee"].dropna().sum())
    gross_out = float(mine[mine.get("direction") == "out"]["_fee"].dropna().sum())
    max_paid = mine[mine.get("direction") == "in"]["_fee"].dropna()
    max_fee_paid = float(max_paid.max()) if len(max_paid) else 0.0
    typical_fee = float(max_paid.median()) if len(max_paid) else 0.0
    # 가격 상한 추정: 드러난 최고이적료 vs 스쿼드가치의 일정비율 중 큰 값(마퀴 영입 여력)
    ceiling = max(max_fee_paid, squad_value * 0.12)
    return {
        "club": club, "league": r["_league"], "spend_tier": _tier(pct),
        "squad_value_eur": round(squad_value), "value_pct": round(pct, 2),
        "gross_spend_eur": round(gross_in), "player_sales_eur": round(gross_out),
        "net_spend_eur": round(gross_in - gross_out),
        "max_fee_paid_eur": round(max_fee_paid), "typical_fee_eur": round(typical_fee),
        "price_ceiling_eur": round(ceiling),
        "note": "프록시(시장가치+드러난지출). 실제 예산·급여·매출 아님",
    }


def spend_pressure(club: str) -> dict | None:
    """⚠ FFP/PSR 아님. net spend / 스쿼드가치 근사 '지출 강도'만."""
    a = affordability(club)
    if not a:
        return None
    sv = a["squad_value_eur"] or 1
    ratio = a["net_spend_eur"] / sv
    if ratio >= 0.30:
        level = "aggressive"
    elif ratio >= 0.12:
        level = "active"
    elif ratio <= -0.05:
        level = "net-seller"
    else:
        level = "balanced"
    return {"club": club, "net_spend_eur": a["net_spend_eur"], "squad_value_eur": a["squad_value_eur"],
            "net_to_value": round(ratio, 3), "intensity": level,
            "disclaimer": "근사 지표 — FFP/PSR 컴플라이언스 아님(재무제표 필요)"}


def price_realism(club: str, likely_fee_eur: float | None) -> dict:
    """후보 예상이적료 vs 구단 가격상한 → 현실성 0-100 + 판정."""
    a = affordability(club)
    if not a or not likely_fee_eur:
        return {"score": 70, "verdict": "unknown", "ceiling_eur": None, "likely_fee_eur": likely_fee_eur}
    ceiling = a["price_ceiling_eur"] or 1
    ratio = likely_fee_eur / ceiling
    if ratio <= 1.0:
        score, verdict = 100, "within"
    elif ratio >= 2.5:
        score, verdict = 20, "over-budget"
    else:
        score = 100 - (ratio - 1.0) / 1.5 * 80
        verdict = "stretch"
    return {"score": round(score), "verdict": verdict, "ceiling_eur": ceiling,
            "likely_fee_eur": round(likely_fee_eur), "spend_tier": a["spend_tier"]}


def recruit_fit(club: str, cand_age: int | None) -> dict:
    """후보 나이가 구단 영입 성향에 맞나 → 0-100."""
    dna = recruitment_dna(club)
    if not dna or cand_age is None or dna["avg_age"] is None:
        return {"score": 60, "club_avg_age": None if not dna else dna.get("avg_age"),
                "age_profile": None if not dna else dna.get("age_profile")}
    # 구단 평균영입나이에 가까울수록 높음(±1.5세 만점, 이후 감쇠)
    diff = abs(cand_age - dna["avg_age"])
    score = max(25.0, 100.0 - max(0.0, diff - 1.5) * 12.0)
    return {"score": round(score), "club_avg_age": dna["avg_age"], "age_profile": dna["age_profile"],
            "cand_age": cand_age}


def sync_to_kg() -> int:
    """Club 노드에 영입성향 + 예산프록시 속성 적재."""
    from neo4j import GraphDatabase
    sv = _squad_value()
    clubs = sorted(sv["club"].unique())
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    n = 0
    with d.session() as s:
        for club in clubs:
            dna, aff = recruitment_dna(club), affordability(club)
            if not aff:
                continue
            s.run(
                "MATCH (c:Club {name:$club}) "
                "SET c.squad_value_eur=$sv, c.spend_tier=$tier, c.net_spend_eur=$net, "
                "    c.max_fee_paid_eur=$maxfee, c.price_ceiling_eur=$ceil, "
                "    c.recruit_avg_age=$age, c.recruit_profile=$prof, c.recruit_u23_ratio=$u23",
                club=club, sv=aff["squad_value_eur"], tier=aff["spend_tier"],
                net=aff["net_spend_eur"], maxfee=aff["max_fee_paid_eur"], ceil=aff["price_ceiling_eur"],
                age=(dna or {}).get("avg_age"), prof=(dna or {}).get("profile"),
                u23=(dna or {}).get("u23_ratio"))
            n += 1
    d.close()
    return n


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for club in ["Brighton", "Chelsea", "Burnley", "Arsenal", "Barcelona", "Real Madrid"]:
        dna, aff, sp = recruitment_dna(club), affordability(club), spend_pressure(club)
        print("=" * 74)
        if dna:
            print(f"■ {club} 영입성향: {dna['profile']}  (n={dna['n_signings']}, "
                  f"평균나이 {dna['avg_age']}, U23 {int((dna['u23_ratio'] or 0)*100)}%, "
                  f"평균이적료 {(dna['avg_fee_eur'] or 0)/1e6:.1f}M)")
        else:
            print(f"■ {club}: 영입 기록 없음")
        if aff:
            print(f"   예산프록시: {aff['spend_tier']} tier · 스쿼드가치 {aff['squad_value_eur']/1e6:.0f}M · "
                  f"순지출 {aff['net_spend_eur']/1e6:+.0f}M · 최고이적료 {aff['max_fee_paid_eur']/1e6:.0f}M · "
                  f"가격상한(추정) {aff['price_ceiling_eur']/1e6:.0f}M")
        if sp:
            print(f"   지출강도(⚠FFP아님): {sp['intensity']} (net/value {sp['net_to_value']})")
    try:
        n = sync_to_kg()
        print(f"\n[club-profile] KG 적재: 클럽 {n}개 영입성향+예산프록시")
    except Exception as e:  # noqa: BLE001
        print(f"\n[club-profile] KG 적재 skip: {str(e)[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
