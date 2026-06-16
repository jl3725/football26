"""
Phase 2 — "비슷한 선수 추천" (포지션 가중 + 퍼포먼스 하이브리드)

개선 내역 (v1 → v2):
  - ALL_FEATURES 16개: dribble / goals_per90 / assists_per90 / big_chances 추가
  - ROLE_WEIGHTS: FW/MF/DF 포지션별로 피처 중요도를 달리해 가중 코사인 유사도 산출
  - 하이브리드 스코어: alpha×스타일유사도 + (1-alpha)×퍼포먼스(ss_rating + 실output)
    → 사카처럼 스타일은 같아도 폼이 떨어지면 세멘요가 상위로 올라옴

사용 예:
    python src/similar_players.py "Bukayo Saka"
    python src/similar_players.py "Bukayo Saka" --alpha 0.5   # 퍼포먼스 비중 상향
    python src/similar_players.py "Rodri" --top 5
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

# ── 피처 정의 ──────────────────────────────────────────────────────────────
ALL_FEATURES: list[str] = [
    # 공격 output
    "npxg_p90",                   # 비페널티 xG
    "xa_p90",                     # xA
    "shots_p90",                  # 슈팅 빈도
    "goals_per90",                # 실득점/90  ← 新
    "assists_per90",              # 실어시스트/90  ← 新
    # 찬스 창출
    "kp_p90",                     # 키패스/90 (FBref)
    "key_passes_per90",           # 키패스/90 (Sofascore — 보완)
    "big_chances_created_per90",  # 빅찬스 창출  ← 新
    # 드리블·운반
    "successful_dribbles_per90",  # 성공 드리블  ← 新 (세멘요 vs 사카 핵심 차이)
    "dribble_success_pct",        # 드리블 성공률  ← 新
    "crosses_per90",              # 크로스
    "fouled_per90",               # 피파울 (적극성 프록시)
    "offsides_per90",             # 오프사이드 (침투 프록시)
    # 수비 기여
    "interceptions_per90",        # 인터셉트
    "tackles_won_per90",          # 태클 성공
    "fouls_per90",                # 수비 파울
]

# 하위 호환: app.py 등에서 FEATURES 를 import 하는 경우 대비
FEATURES = ALL_FEATURES

# ── 포지션별 가중치 ────────────────────────────────────────────────────────
# 값이 높을수록 유사도 계산에서 더 중요하게 반영됨.
# FW: 득점·드리블 중심 / MF: 창의성·빌드업 중심 / DF: 수비액션 중심
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "FW": {
        "npxg_p90": 3.0, "xa_p90": 2.0, "shots_p90": 2.5,
        "goals_per90": 3.0, "assists_per90": 1.5,
        "kp_p90": 1.5, "key_passes_per90": 1.5, "big_chances_created_per90": 2.0,
        "successful_dribbles_per90": 3.0, "dribble_success_pct": 2.5,
        "crosses_per90": 1.5, "fouled_per90": 2.0, "offsides_per90": 2.0,
        "interceptions_per90": 0.3, "tackles_won_per90": 0.3, "fouls_per90": 0.5,
    },
    "MF": {
        "npxg_p90": 1.5, "xa_p90": 2.5, "shots_p90": 1.0,
        "goals_per90": 1.5, "assists_per90": 2.0,
        "kp_p90": 3.0, "key_passes_per90": 3.0, "big_chances_created_per90": 2.0,
        "successful_dribbles_per90": 1.5, "dribble_success_pct": 1.0,
        "crosses_per90": 1.0, "fouled_per90": 1.5, "offsides_per90": 0.5,
        "interceptions_per90": 2.0, "tackles_won_per90": 2.0, "fouls_per90": 1.5,
    },
    "DF": {
        "npxg_p90": 0.5, "xa_p90": 0.5, "shots_p90": 0.3,
        "goals_per90": 0.3, "assists_per90": 0.5,
        "kp_p90": 1.0, "key_passes_per90": 1.0, "big_chances_created_per90": 0.5,
        "successful_dribbles_per90": 1.5, "dribble_success_pct": 1.0,
        "crosses_per90": 1.5, "fouled_per90": 1.0, "offsides_per90": 0.2,
        "interceptions_per90": 3.0, "tackles_won_per90": 3.0, "fouls_per90": 2.0,
    },
}
_DEFAULT_WEIGHTS = {f: 1.0 for f in ALL_FEATURES}

# full > basic > sample 순으로 폴백
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
for _p in ["players_full_2025_2026.csv", "players_2025_2026.csv", "players_sample.csv"]:
    DATA_PATH = _DATA_DIR / _p
    if DATA_PATH.exists():
        break

DEFAULT_MIN_MINUTES = 900


# ── 전처리 유틸 ────────────────────────────────────────────────────────────

def position_group(pos: str) -> str:
    """FBref pos('FW,MF' 등)에서 그룹. FW가 포함되면 항상 FW 반환."""
    parts = [p.strip().upper() for p in str(pos).split(",")]
    if "FW" in parts: return "FW"
    if "MF" in parts: return "MF"
    if "DF" in parts: return "DF"
    if "GK" in parts: return "GK"
    return "OTH"


def _add_computed(df: pd.DataFrame) -> pd.DataFrame:
    """goals_per90 / assists_per90 파생 컬럼 추가 (없을 때만)."""
    m = df["minutes"].replace(0, np.nan)
    if "goals_per90" not in df.columns:
        df = df.copy()
        df["goals_per90"] = df["goals"] / m * 90
    if "assists_per90" not in df.columns:
        df = df.copy()
        df["assists_per90"] = df["assists"] / m * 90
    return df


_POS_PRIO = {"FW": 4, "MF": 3, "DF": 2, "GK": 1}


def fine_group(pos: str, row: "pd.Series | None" = None) -> str:
    """FBref pos 문자열 + 선수 통계 → 세부 포지션 그룹.

    FBref는 FW/MF/DF 3단계만 제공하므로 통계로 보정:
      WING_AM : 윙어·공격형미드 (FW+MF 혼합 or 드리블/크로스 높은 MF)
      ST      : 스트라이커 (순수 FW, 침투·슈팅 위주)
      CAM_CM  : 공격형·박스투박스 미드필더
      DM      : 수비형 미드필더
      CB      : 센터백
      FB      : 풀백·윙백
    """
    parts = frozenset(p.strip().upper() for p in str(pos).split(","))

    if "GK" in parts:
        return "GK"

    # FW+MF 혼합 = 윙어 or 공격형미드 (사카·트로사르 등 모두 해당)
    if "FW" in parts and "MF" in parts:
        return "WING_AM"

    # 순수 FW: 드리블/크로스 높으면 WING_AM, 아니면 ST
    if "FW" in parts:
        if row is not None:
            drib    = float(row.get("successful_dribbles_per90", 0) or 0)
            crosses = float(row.get("crosses_per90", 0) or 0)
            if drib > 1.0 or crosses > 1.0:
                return "WING_AM"
        return "ST"

    # MF (+ possibly DF)
    if "MF" in parts:
        if "DF" in parts:
            return "DM"  # DF,MF = 수비형 or 공격적 CB
        if row is not None:
            drib    = float(row.get("successful_dribbles_per90", 0) or 0)
            crosses = float(row.get("crosses_per90", 0) or 0)
            xa      = float(row.get("xa_p90", 0) or 0)
            tackles = float(row.get("tackles_won_per90", 0) or 0)
            itc     = float(row.get("interceptions_per90", 0) or 0)
            kp      = float(row.get("kp_p90", 0) or 0)
            # 윙어 판별: 드리블 높고 (크로스 많거나 xA 높은) 순수 MF
            if drib > 0.8 and (crosses > 0.7 or xa > 0.15):
                return "WING_AM"
            # DM: 수비 액션 > 공격 창출
            if (tackles + itc) > 1.5 and (tackles + itc) > (kp + xa) * 1.8:
                return "DM"
            # 공격적 중원
            if kp + xa > 0.6:
                return "CAM_CM"
        return "CM"

    # 순수 DF: 공중볼 높으면 CB, 크로스/드리블 높으면 FB
    if "DF" in parts:
        if row is not None:
            aerial  = float(row.get("aerial_won_per90", 0) or 0)
            crosses = float(row.get("crosses_per90", 0) or 0)
            drib    = float(row.get("successful_dribbles_per90", 0) or 0)
            if aerial > 1.5 and crosses < 0.8:
                return "CB"
            if crosses > 0.5 or drib > 0.3:
                return "FB"
        return "CB"

    return "OTH"


def _best_pos_group(pos_series: pd.Series) -> str:
    """선수의 복수 pos 행 전체에서 가장 공격적인 포지션 그룹 선택.
    예: ['MF', 'MF,FW'] → 'FW'  (세멘요 케이스 해결)
    """
    parts: set[str] = set()
    for p in pos_series:
        parts.update(x.strip().upper() for x in str(p).split(","))
    found = parts & {"FW", "MF", "DF", "GK"}
    return max(found, key=lambda x: _POS_PRIO.get(x, 0)) if found else "OTH"


def load_players(path: Path = DATA_PATH, min_minutes: int = DEFAULT_MIN_MINUTES,
                 include_gk: bool = False) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = _add_computed(df)

    # 중복 선수 제거: 포지션 그룹은 전 행을 통합해 가장 공격적 그룹 사용,
    # 통계는 minutes가 가장 많은 행(= 가장 완전한 데이터) 유지.
    pg_map = df.groupby("player")["pos"].apply(_best_pos_group).to_dict()
    df = (df.sort_values("minutes", ascending=False)
            .drop_duplicates(subset=["player"])
            .reset_index(drop=True))
    df["pos_group"] = df["player"].map(pg_map)
    # fl_group이 있으면 우선 사용, 없는 선수만 fine_group으로 폴백
    if "fl_group" in df.columns:
        missing = df["fl_group"].isna() | (df["fl_group"] == "")
        df.loc[missing, "fl_group"] = [
            fine_group(row["pos"], row) for _, row in df[missing].iterrows()
        ]
    else:
        df["fl_group"] = [fine_group(row["pos"], row) for _, row in df.iterrows()]

    df = df[df["minutes"] >= min_minutes].reset_index(drop=True)
    if not include_gk:
        df = df[df["pos_group"] != "GK"].reset_index(drop=True)
    return df


# ── 임베딩 & 유사도 ────────────────────────────────────────────────────────

def build_embeddings(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    z-score 표준화 임베딩.
    반환: (matrix, feat_list) — feat_list는 실제 사용된 피처 순서.
    가중치는 find_similar 내에서 포지션별로 적용됨.
    """
    df = _add_computed(df)
    feat_list = [c for c in ALL_FEATURES if c in df.columns]
    raw = df[feat_list].to_numpy(dtype=float)
    raw = np.nan_to_num(raw, nan=0.0)
    return StandardScaler().fit_transform(raw), feat_list


def _weight_vec(pos: str, feat_list: list[str]) -> np.ndarray:
    wdict = ROLE_WEIGHTS.get(pos, _DEFAULT_WEIGHTS)
    return np.array([wdict.get(f, 1.0) for f in feat_list])


def _perf_score(df: pd.DataFrame, pos: str) -> np.ndarray:
    """포지션별 퍼포먼스 점수 0~1: ss_rating(60%) + 실 output 지표(40%)."""
    df = _add_computed(df)
    rating = df["ss_rating"].fillna(6.5) / 10.0

    zero = pd.Series(0.0, index=df.index)
    g90  = df["goals_per90"].fillna(0)
    a90  = df["assists_per90"].fillna(0)

    if pos == "FW":
        output = g90 * 0.6 + a90 * 0.4
    elif pos == "MF":
        kp = df.get("key_passes_per90", zero).fillna(0)
        output = a90 * 0.5 + g90 * 0.3 + kp * 0.2
    else:  # DF
        itc = df["interceptions_per90"].fillna(0)
        tkl = df["tackles_won_per90"].fillna(0)
        aer = df.get("aerial_won_per90", zero).fillna(0)
        output = itc * 0.4 + tkl * 0.4 + aer * 0.2

    out_norm = (output - output.min()) / (output.max() - output.min() + 1e-9)
    perf = 0.6 * rating + 0.4 * out_norm
    return ((perf - perf.min()) / (perf.max() - perf.min() + 1e-9)).to_numpy()


def find_similar(
    df: pd.DataFrame,
    embeddings: tuple[np.ndarray, list[str]] | np.ndarray,
    name: str,
    top: int = 10,
    same_position: bool = True,
    max_value: float | None = None,
    alpha: float = 0.65,
) -> pd.DataFrame:
    """
    스타일 유사도 + 퍼포먼스 하이브리드 탐색.

    alpha: 스타일 유사도 비중 (0~1).
      - 0.65 (기본): 스타일 우선, 퍼포먼스 보조
      - 0.50: 스타일 = 퍼포먼스 동등 (이적 추천 모드)
      - 0.80+: 순수 스타일 클론 탐색
    """
    # 하위 호환: 구버전 np.ndarray도 수용
    if isinstance(embeddings, tuple):
        emb_mat, feat_list = embeddings
    else:
        emb_mat = embeddings
        feat_list = [c for c in ALL_FEATURES if c in df.columns]

    matches = df.index[df["player"].str.lower() == name.lower()].tolist()
    if not matches:
        matches = df.index[df["player"].str.lower().str.contains(name.lower())].tolist()
    if not matches:
        raise KeyError(f"선수를 찾을 수 없습니다: '{name}'. --list 로 목록 확인.")
    idx = matches[0]
    pos = df.loc[idx, "pos_group"]

    # 포지션 가중 코사인 유사도
    w = _weight_vec(pos, feat_list)
    weighted = emb_mat * w
    style_sims = cosine_similarity(weighted[idx : idx + 1], weighted)[0]

    # 퍼포먼스 점수 (전체 pool 기준 정규화)
    perf = _perf_score(df, pos)

    result = df.copy()
    result["style_sim"]  = style_sims
    result["perf_score"] = perf
    result["score"]      = alpha * style_sims + (1 - alpha) * perf
    # 하위 호환: similarity 컬럼 유지
    result["similarity"] = result["score"]
    result = result.drop(index=idx)

    if same_position:
        if "fl_group" not in result.columns:
            result["fl_group"] = [fine_group(r["pos"], r) for _, r in result.iterrows()]
        ref_grp = df.loc[idx, "fl_group"] if "fl_group" in df.columns else fine_group(df.loc[idx, "pos"], df.loc[idx])

        if ref_grp in ("OTH", "GK", ""):
            result = result[result["pos_group"] == pos]
        elif ref_grp == "W":
            # 방향 미정 WF → RW·LW·W·AM 전체와 비교
            result = result[result["fl_group"].isin(("W", "RW", "LW", "AM"))]
        elif ref_grp == "AM":
            # 중앙 AM → 인접 wide(RW/LW)·W도 포함해 풀 확장
            result = result[result["fl_group"].isin(("AM", "RW", "LW", "W"))]
        else:
            result = result[result["fl_group"] == ref_grp]
    if max_value is not None:
        result = result[~(result.get("market_value_eur", pd.Series(dtype=float)) > max_value)]

    want = ["player", "squad", "pos", "fl_group", "age", "market_value_eur",
            "style_sim", "perf_score", "score"]
    cols = [c for c in want if c in result.columns]
    return result.sort_values("score", ascending=False).head(top)[cols].reset_index(drop=True)


# ── CLI ────────────────────────────────────────────────────────────────────

def fmt_value(v: float) -> str:
    if pd.isna(v):
        return "-"
    return f"€{v / 1_000_000:.0f}M"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="비슷한 선수 추천 (v2 — 포지션 가중 + 퍼포먼스)")
    p.add_argument("player", nargs="?", help="기준 선수 이름 (부분 일치 가능)")
    p.add_argument("--top",          type=int,   default=10)
    p.add_argument("--alpha",        type=float, default=0.65,
                   help="스타일 유사도 비중 0~1 (기본 0.65). 0.5=이적추천모드")
    p.add_argument("--same-position", action="store_true")
    p.add_argument("--max-value",    type=float, default=None, help="이적가치 상한 (유로)")
    p.add_argument("--min-minutes",  type=int,   default=DEFAULT_MIN_MINUTES)
    p.add_argument("--data",         type=Path,  default=DATA_PATH)
    p.add_argument("--list",         action="store_true")
    args = p.parse_args(argv)

    df = load_players(args.data, args.min_minutes)

    if args.list:
        for _, r in df.sort_values("player").iterrows():
            print(f"  {r['player']:<28} {r['pos_group']:<4} {r['squad']}")
        return 0

    if not args.player:
        p.error("선수 이름을 입력하거나 --list 를 사용하세요.")

    emb = build_embeddings(df)
    try:
        res = find_similar(df, emb, args.player,
                           top=args.top, same_position=args.same_position,
                           max_value=args.max_value, alpha=args.alpha)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1

    pos_q = df.loc[df["player"].str.lower().str.contains(args.player.lower())].iloc[0]["pos_group"]
    print(f"\n'{args.player}' ({pos_q}) 와 비슷한 선수 [alpha={args.alpha}]:\n")
    print(f"  {'선수':<26} {'팀':<20} {'포지션':<8} {'나이':>3} {'가치':>8}  "
          f"{'스타일':>7}  {'퍼폼':>6}  {'종합':>6}")
    print("  " + "-" * 95)
    for _, r in res.iterrows():
        print(
            f"  {r['player']:<26} {r['squad']:<20} {r['pos']:<8} "
            f"{r['age']:>3} {fmt_value(r.get('market_value_eur', float('nan'))):>8}  "
            f"{r['style_sim']:>6.3f}  {r['perf_score']:>6.3f}  {r['score']:>6.3f}"
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
