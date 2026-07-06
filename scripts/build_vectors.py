"""football26 선수 유사도 벡터 → Qdrant.

players_full 의 per90 스탯으로 스타일 피처 벡터를 만들어(정규화·코사인) Qdrant 에 적재.
"유사 선수" / 드림타깃·대체자 추천의 기반. (텍스트 임베딩은 GraphRAG 단계에서 별도)

접속(기본 로컬 docker): QDRANT_URL 환경변수.
사용:  pip install -r requirements-kg.txt && python scripts/build_vectors.py
"""
from __future__ import annotations

import hashlib
import os
import sys
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

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "players"
LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal"]
MIN_MINUTES = 270   # per90 스탯이 의미 있으려면 최소 출전

# 스타일 피처(공격 생산·창출·드리블·수비·경합) — players_full 에 존재하는 per90 컬럼
FEATURES = [
    "npg_per90", "ast_per90", "xg_p90", "npxg_p90", "xa_p90", "kp_p90", "shots_p90",
    "sot_per90", "xg_chain_p90", "big_chances_created_per90", "successful_dribbles_per90",
    "crosses_per90", "final_third_passes_per90", "tackles_won_per90", "interceptions_per90",
    "recoveries_per90", "clearances_per90", "blocked_shots_per90", "aerial_won_per90",
    "ground_duels_won_per90", "possession_won_att_per90", "fouled_per90", "offsides_per90",
]


def _pid(r) -> str:
    tm = r.get("tm_id")
    if pd.notna(tm):
        return f"tm:{int(tm)}"
    nk = r.get("norm_key")
    return f"nk:{r.get('_league')}:{nk}" if pd.notna(nk) else f"nm:{r.get('_league')}:{r.get('player')}"


def _point_id(pid: str) -> int:
    return int(hashlib.md5(pid.encode("utf-8")).hexdigest()[:15], 16)


def build_matrix():
    """반환: (point_ids, vectors[np.ndarray], payloads[list])."""
    frames = []
    for lg in LEAGUES:
        try:
            df = pd.read_csv(data_path("players_full", lg))
        except (OSError, ValueError):
            continue
        df["_league"] = lg
        frames.append(df)
    if not frames:
        return [], np.zeros((0, len(FEATURES))), [], FEATURES
    allp = pd.concat(frames, ignore_index=True)
    feats = [c for c in FEATURES if c in allp.columns]
    allp = allp[pd.to_numeric(allp.get("minutes"), errors="coerce").fillna(0) >= MIN_MINUTES].copy()

    X = allp[feats].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xn = (X - mu) / sd     # z-score 정규화(코사인 유사도용)

    ids, payloads = [], []
    for _, r in allp.iterrows():
        pid = _pid(r)
        ids.append(_point_id(pid))
        nat = r.get("nationality")
        nat = str(nat).split("/")[0].split(",")[0].strip() if pd.notna(nat) else None
        payloads.append({
            "pid": pid, "tm_id": None if pd.isna(r.get("tm_id")) else int(r.get("tm_id")),
            "name": str(r.get("player") or ""), "club": str(r.get("squad") or ""),
            "league": str(r.get("_league") or ""), "pos": str(r.get("pos") or ""),
            "nationality": nat,
            "age": None if pd.isna(r.get("age")) else int(r.get("age")),
            "market_value_eur": None if pd.isna(r.get("market_value_eur")) else float(r.get("market_value_eur")),
            "ss_rating": None if pd.isna(r.get("ss_rating")) else float(r.get("ss_rating")),
            "minutes": None if pd.isna(r.get("minutes")) else int(r.get("minutes")),
            "contract_until": (str(r.get("tm_contract_until"))[:10] if pd.notna(r.get("tm_contract_until")) else None),
        })
    return ids, Xn, payloads, feats


def main() -> int:
    from qdrant_client import QdrantClient, models

    ids, vecs, payloads, feats = build_matrix()
    if not ids:
        print("[vec] 선수 없음 — 중단", file=sys.stderr)
        return 1
    dim = len(feats)
    print(f"[vec] {len(ids)}명 · {dim}피처 (min {MIN_MINUTES}분)")

    client = QdrantClient(url=QDRANT_URL)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION,
                             vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))

    points = [models.PointStruct(id=i, vector=v.tolist(), payload=p)
              for i, v, p in zip(ids, vecs, payloads)]
    for j in range(0, len(points), 256):
        client.upsert(COLLECTION, points=points[j:j + 256])
    print(f"[vec] Qdrant '{COLLECTION}' 적재 완료 ({len(points)}점)")

    # 데모: 첫 유명선수 유사도 top5
    demo = next((k for k, p in enumerate(payloads) if p["name"] in
                 ("Vitinha", "Bruno Fernandes", "Florian Wirtz", "Bradley Barcola")), 0)
    hits = client.search(COLLECTION, query_vector=vecs[demo].tolist(), limit=6)
    print(f"  '{payloads[demo]['name']}' ({payloads[demo]['league']}) 유사 선수:")
    for h in hits[1:]:
        pl = h.payload
        print(f"    {pl['name']:22} {pl['club']:16} {pl['league']:12} sim={h.score:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
