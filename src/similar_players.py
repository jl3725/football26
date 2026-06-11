"""
Phase 1 PoC — "비슷한 선수 추천" (Vector RAG의 핵심: 의미적 유사도)

선수의 90분당 플레이 지표를 벡터로 표현하고, 코사인 유사도로
스타일이 닮은 선수를 찾는다. Postgres/pgvector 없이 메모리에서 동작하며
(numpy + scikit-learn), 추후 pgvector로 그대로 이식 가능하다.

사용 예:
    python src/similar_players.py "Mohamed Salah"
    python src/similar_players.py "Rodri" --top 5 --same-position
    python src/similar_players.py "Cole Palmer" --max-value 80000000
    python src/similar_players.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

# 플레이 스타일을 규정하는 90분당 피처(임베딩 차원).
# FBref 'Standard / Shooting / Misc' basic 테이블에서 실제로 받을 수 있는 지표.
FEATURES = [
    # 공격 기여
    "npxg_p90",          # 비페널티 xG — 실제 득점 기대(관측 골보다 안정적)
    "xa_p90",            # xA — 어시스트 기대치
    "kp_p90",            # 키패스/90 — 마지막 패스 창의성
    "shots_p90",         # 슈팅/90 — 공격 참여도
    # 볼 운반·측면
    "crosses_per90",     # 크로스 — 측면/배급 성향
    "fouled_per90",      # 피파울 — 드리블 적극성(프록시)
    "offsides_per90",    # 오프사이드 — 침투 성향(프록시)
    # 수비 기여
    "interceptions_per90",  # 인터셉트 — 위치 수비
    "tackles_won_per90",    # 태클 성공 — 수비 강도
    # 기타
    "fouls_per90",       # 파울 — 수비 압박(프록시)
]

# 코사인 유사도 신뢰성을 위한 최소 출전 시간(분). 표본이 적으면 90분당 지표가 튄다.
DEFAULT_MIN_MINUTES = 900

# full(xG 보강) > basic > sample 순으로 폴백
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
for _p in ["players_full_2025_2026.csv", "players_2025_2026.csv", "players_sample.csv"]:
    DATA_PATH = _DATA_DIR / _p
    if DATA_PATH.exists():
        break


def position_group(pos: str) -> str:
    """FBref pos 문자열('FW', 'MF', 'DF,MF' 등)을 대표 그룹으로 축약."""
    first = str(pos).split(",")[0].strip().upper()
    return first if first in {"FW", "MF", "DF", "GK"} else "OTH"


def load_players(path: Path = DATA_PATH, min_minutes: int = DEFAULT_MIN_MINUTES,
                 include_gk: bool = False) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"CSV에 필요한 피처 컬럼이 없습니다: {missing}")
    df = df[df["minutes"] >= min_minutes].reset_index(drop=True)
    df["pos_group"] = df["pos"].map(position_group)
    if not include_gk:
        # GK는 필드 지표가 0이라 유사도/백분위를 왜곡 → 기본 제외
        df = df[df["pos_group"] != "GK"].reset_index(drop=True)
    return df


def build_embeddings(df: pd.DataFrame) -> np.ndarray:
    """피처를 z-score 표준화 → 각 선수의 스타일 벡터(임베딩)."""
    raw = df[FEATURES].to_numpy(dtype=float)
    raw = np.nan_to_num(raw, nan=0.0)  # 안전장치: 남은 NaN은 0으로
    return StandardScaler().fit_transform(raw)


def find_similar(
    df: pd.DataFrame,
    embeddings: np.ndarray,
    name: str,
    top: int = 10,
    same_position: bool = False,
    max_value: float | None = None,
) -> pd.DataFrame:
    matches = df.index[df["player"].str.lower() == name.lower()].tolist()
    if not matches:
        # 부분 일치로 한 번 더 시도
        matches = df.index[df["player"].str.lower().str.contains(name.lower())].tolist()
    if not matches:
        raise KeyError(f"선수를 찾을 수 없습니다: '{name}'. --list 로 목록 확인.")
    idx = matches[0]

    sims = cosine_similarity(embeddings[idx : idx + 1], embeddings)[0]
    result = df.copy()
    result["similarity"] = sims
    result = result.drop(index=idx)  # 자기 자신 제외

    if same_position:
        result = result[result["pos_group"] == df.loc[idx, "pos_group"]]
    if max_value is not None:
        # 시장가치가 비어있는(NaN) 선수는 상한 필터에서 제외하지 않고 남긴다.
        result = result[~(result["market_value_eur"] > max_value)]

    cols = ["player", "squad", "pos", "age", "market_value_eur", "similarity"]
    return result.sort_values("similarity", ascending=False).head(top)[cols].reset_index(drop=True)


def fmt_value(v: float) -> str:
    if pd.isna(v):
        return "-"
    return f"€{v/1_000_000:.0f}M"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="비슷한 선수 추천 (Phase 1 PoC)")
    p.add_argument("player", nargs="?", help="기준 선수 이름 (부분 일치 가능)")
    p.add_argument("--top", type=int, default=10, help="추천 인원 수 (기본 10)")
    p.add_argument("--same-position", action="store_true", help="같은 포지션 그룹으로 제한")
    p.add_argument("--max-value", type=float, default=None, help="시장가치 상한 (유로)")
    p.add_argument("--min-minutes", type=int, default=DEFAULT_MIN_MINUTES, help="최소 출전 시간(분)")
    p.add_argument("--data", type=Path, default=DATA_PATH, help="선수 CSV 경로")
    p.add_argument("--list", action="store_true", help="선수 목록만 출력")
    args = p.parse_args(argv)

    df = load_players(args.data, args.min_minutes)

    if args.list:
        for _, r in df.sort_values("player").iterrows():
            print(f"  {r['player']:<26} {r['pos_group']:<4} {r['squad']}")
        return 0

    if not args.player:
        p.error("선수 이름을 입력하거나 --list 를 사용하세요.")

    embeddings = build_embeddings(df)
    try:
        res = find_similar(
            df, embeddings, args.player,
            top=args.top, same_position=args.same_position, max_value=args.max_value,
        )
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"\n'{args.player}' 와(과) 스타일이 비슷한 선수:\n")
    print(f"  {'선수':<24} {'팀':<18} {'포지션':<8} {'나이':>3} {'가치':>7}  유사도")
    print("  " + "-" * 74)
    for _, r in res.iterrows():
        print(
            f"  {r['player']:<24} {r['squad']:<18} {r['pos']:<8} "
            f"{r['age']:>3} {fmt_value(r['market_value_eur']):>7}  {r['similarity']:.3f}"
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
