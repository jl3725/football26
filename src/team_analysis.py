"""
팀 분석 — 주전 XI(출전시간 기준) + 데이터 기반 '역할(role)' 자동 부여.

각 선수의 90분당 지표를 리그 전체 대비 백분위로 변환한 뒤,
포지션 그룹별 아키타입 템플릿과 매칭해 가장 잘 맞는 역할을 고른다.
(시뮬레이션이 아니라 '관측된 플레이 스타일'의 해석)

실행:
    python src/team_analysis.py Arsenal
    python src/team_analysis.py "Manchester City" --formation 4-3-3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from similar_players import DATA_PATH, FEATURES, position_group

FORMATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "team_formations.json"
SLOTS_PATH = Path(__file__).resolve().parent.parent / "data" / "player_slots_2025_2026.csv"

# 슬롯별 가로(x%) 위치 — 포메이션과 무관하게 일관 유지.
# y는 포메이션의 어느 밴드에 속하는지에 따라 slot_xy()가 동적으로 계산한다.
SLOT_X = {
    "GK": 50,
    "RB": 84, "LB": 16,
    "RWB": 88, "LWB": 12,
    "RCB": 63, "CB": 50, "LCB": 37,
    "RDM": 62, "LDM": 38,
    "CM": 50,
    "RCM": 66, "LCM": 34,
    "RM": 82, "LM": 18,
    "RW": 80, "LW": 20,
    "ST": 50, "RST": 60, "LST": 40,
}

# 공격형 미드 밴드(=마지막 M 밴드, n_bands>=4)에서만 쓰는 가로 위치.
# 같은 슬롯 이름이라도 4-2-3-1의 "3"은 사실상 RW-CAM-LW, 3-4-2-1의 "2"는
# CAM pair. 4-3-3 같은 단일 M 밴드의 RCM/CM/LCM과 구분하기 위해 별도 테이블.
HIGH_MID_X = {
    1: {"CM": 50},
    2: {"RDM": 64, "LDM": 36},
    3: {"RCM": 78, "CM": 50, "LCM": 22},
}

# y 범위: 0=상단(공격) ~ 100=하단(자기 골). 라벨이 토큰 아래에 그려지므로
# 양 끝에 ~14% 여백을 두어 라벨이 피치 안에 들어오게 한다.
GK_Y = 87           # 골키퍼 — 페널티 박스 내, 라벨이 잘리지 않을 정도로 올림
BAND_Y_TOP = 22     # 최전방(FW) 밴드
BAND_Y_BOTTOM = 74  # 최후방(DF) 밴드

_DEF = {"RB", "RWB", "RCB", "CB", "LCB", "LB", "LWB"}
_FWD = {"RW", "LW", "ST", "RST", "LST"}


def slot_kind(slot: str) -> str:
    if slot == "GK":
        return "GK"
    if slot in _DEF:
        return "DEF"
    if slot in _FWD:
        return "FWD"
    return "MID"


def band_y(band_idx: int, n_bands: int) -> float:
    """필드플레이어 밴드 인덱스(0=수비, n_bands-1=공격) → y%."""
    if n_bands <= 1:
        return 50.0
    return BAND_Y_BOTTOM - (BAND_Y_BOTTOM - BAND_Y_TOP) * (band_idx / (n_bands - 1))


def slot_xy(slot: str, formation: str) -> tuple[float, float]:
    """슬롯과 포메이션을 받아 (x%, y%) 반환.

    같은 슬롯 이름이라도 포메이션에 따라 의미하는 라인이 다르다(예: 4-3-3의
    RCM/CM/LCM은 중원, 4-2-3-1의 RCM/CM/LCM은 공격형 미드 라인). y는 항상
    '이 포메이션에서 몇 번째 밴드인가'로 계산한다.
    """
    if slot == "GK":
        return (SLOT_X["GK"], GK_Y)
    try:
        parts = [int(x) for x in formation.split("-")]
    except ValueError:
        return (SLOT_X.get(slot, 50.0), 50.0)
    n_bands = len(parts)
    for bi, size in enumerate(parts):
        kind = "D" if bi == 0 else ("F" if bi == n_bands - 1 else "M")
        if slot in slot_labels(size, kind):
            # 공격형 M 밴드면 다른 X 테이블 사용 (4-2-3-1의 "3" = RW/CAM/LW 등)
            is_high_mid = kind == "M" and bi == n_bands - 2 and n_bands >= 4
            if is_high_mid:
                table = HIGH_MID_X.get(size, {})
                x = table.get(slot, SLOT_X.get(slot, 50.0))
            else:
                x = SLOT_X.get(slot, 50.0)
            return (x, band_y(bi, n_bands))
    # 폴백: 슬롯 종류로 밴드 추정
    kind = slot_kind(slot)
    if kind == "DEF":
        bi = 0
    elif kind == "FWD":
        bi = n_bands - 1
    else:
        bi = max(1, n_bands // 2)
    return (SLOT_X.get(slot, 50.0), band_y(bi, n_bands))


def load_formations() -> dict:
    try:
        return json.loads(FORMATIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"_default": "4-3-3"}


def team_formations(team: str, formations: dict | None = None) -> dict:
    """팀의 메인/서브 포메이션 반환. {'main': '4-3-3', 'sub': '4-2-3-1' or None}.

    JSON 값은 문자열(legacy) 또는 {'main': ..., 'sub': ...} 객체 둘 다 허용.
    """
    formations = formations or load_formations()
    default = formations.get("_default", "4-3-3")
    entry = formations.get(team, default)
    if isinstance(entry, dict):
        return {"main": entry.get("main", default), "sub": entry.get("sub")}
    return {"main": entry, "sub": None}


def slot_labels(size: int, kind: str) -> list[str]:
    """라인 인원수+종류(D/M/F)에 맞는 슬롯 라벨을 우→좌 순으로. (fetch_lineups와 동일)"""
    D = {2: ["RCB", "LCB"], 3: ["RCB", "CB", "LCB"], 4: ["RB", "RCB", "LCB", "LB"],
         5: ["RWB", "RCB", "CB", "LCB", "LWB"]}
    M = {1: ["CM"], 2: ["RDM", "LDM"], 3: ["RCM", "CM", "LCM"],
         4: ["RM", "RCM", "LCM", "LM"], 5: ["RM", "RCM", "CM", "LCM", "LM"]}
    F = {1: ["ST"], 2: ["RST", "LST"], 3: ["RW", "ST", "LW"]}
    table = {"D": D, "M": M, "F": F}[kind]
    return table.get(size, [f"{kind}{i+1}" for i in range(size)])


def formation_slots(formation: str) -> list[str]:
    """포메이션 문자열 → 기대 슬롯 목록(GK 포함, 정확히 11개)."""
    parts = [int(x) for x in formation.split("-")]
    slots = ["GK"]
    for bi, size in enumerate(parts):
        kind = "D" if bi == 0 else ("F" if bi == len(parts) - 1 else "M")
        slots += slot_labels(size, kind)
    return slots


def load_slots() -> pd.DataFrame | None:
    if SLOTS_PATH.exists():
        return pd.read_csv(SLOTS_PATH)
    return None


def team_xi_from_slots(team: str, slots_df: pd.DataFrame,
                       formation: str) -> pd.DataFrame | None:
    """포메이션의 슬롯마다 최다출전 선수 1명을 배정 → 정확히 11명.

    CSV에 'formation' 컬럼이 있으면 해당 포메이션 행만 사용(메인/서브 분리).
    없으면 전체 행을 사용(legacy 데이터 호환).
    """
    t = slots_df[slots_df["squad"] == team]
    if "formation" in t.columns:
        t_f = t[t["formation"] == formation]
        if not t_f.empty:
            t = t_f
        # 해당 포메이션 데이터가 없으면 팀 전체 행으로 폴백
    if t.empty:
        return None
    expected = formation_slots(formation)
    picked, used = [], set()
    for slot in expected:
        cand = t[(t["slot"] == slot) & (~t["player"].isin(used))]
        if cand.empty:
            continue
        row = cand.nlargest(1, "apps").iloc[0]
        used.add(row["player"])
        picked.append(row)
    return pd.DataFrame(picked) if picked else None


def team_formation(team: str, formations: dict | None = None) -> str:
    """하위호환: 메인 포메이션만 반환."""
    return team_formations(team, formations)["main"]

# 포지션 그룹별 아키타입: {역할명: {피처: 가중치(+선호/-비선호)}}
# 가중치는 '리그 백분위'에 곱해져 점수화된다.
ARCHETYPES = {
    "FW": {
        "최전방 스트라이커 (Centre Forward)":
            {"npxg_p90": 2.5, "shots_p90": 2, "offsides_per90": 1.5, "kp_p90": -0.5, "crosses_per90": -2},
        "인사이드 윙어 (Inverted Winger)":
            {"kp_p90": 1.5, "fouled_per90": 2, "shots_p90": 1.5, "xa_p90": 1, "crosses_per90": -1},
        "측면 크리에이터 (Wide Winger)":
            {"crosses_per90": 2.5, "xa_p90": 1.5, "fouled_per90": 1, "npxg_p90": -0.5},
    },
    "MF": {
        "수비형 앵커 (Defensive Anchor)":
            {"tackles_won_per90": 2.5, "interceptions_per90": 2.5, "kp_p90": -1, "npxg_p90": -1},
        "박스투박스 (Box-to-Box)":
            {"tackles_won_per90": 1.5, "shots_p90": 1.5, "npxg_p90": 1.5, "fouled_per90": 1},
        "딥 크리에이터 (Deep Playmaker)":
            {"crosses_per90": 2, "kp_p90": 2, "xa_p90": 1.5, "tackles_won_per90": -0.5},
        "공격형 미드 (Advanced Playmaker)":
            {"kp_p90": 2.5, "xa_p90": 2, "npxg_p90": 1.5, "fouled_per90": 1.5, "interceptions_per90": -0.5},
    },
    # DF는 crosses 게이트로 풀백/CB 먼저 분리(assign_role 참조)
    "DF": {},
}

# 풀백 식별 임계값: 크로스 90분당 리그 백분위가 이 값 이상이면 풀백으로 본다.
FULLBACK_CROSS_PCT = 0.5


# 스탯 기반 배지 — 리그 단일 지표 Top N 리더 라벨.
# 새 지표(Sofascore)는 pct_df 에 컬럼이 있을 때만 자동 평가된다.
LEADER_METRICS = [
    # 기존 (FBref/Understat)
    ("npxg_p90", "⚽", "득점 머신"),
    ("xa_p90", "🎁", "어시스트 마스터"),
    ("kp_p90", "🔑", "키패스 장인"),
    ("shots_p90", "💥", "슈팅 폭격기"),
    ("crosses_per90", "✈️", "크로스 스페셜리스트"),
    ("fouled_per90", "🏃", "드리블 침투형"),
    ("offsides_per90", "🦘", "오프-라인 침투"),
    ("interceptions_per90", "👁️", "수비 예측가"),
    ("tackles_won_per90", "🛡️", "태클 머신"),
    # Sofascore — 고급 지표
    ("aerial_won_pct", "🦅", "공중볼 지배자"),
    ("pass_pct", "🎯", "패스 정확도"),
    ("long_ball_pct", "📡", "롱볼 마스터"),
    ("tackles_won_pct", "🪝", "태클 성공률"),
    ("clearances_per90", "🧹", "클리어 머신"),
    ("blocked_shots_per90", "🛡️", "슛 블록"),
    ("big_chances_created_per90", "💎", "빅찬스 메이커"),
    ("key_passes_per90", "🗝️", "키패스(SS) 마스터"),
    ("possession_won_att_per90", "🔥", "전방 압박왕"),
    ("ss_rating", "⭐", "Sofascore 평점왕"),
    # GK
    ("gk_saves_per90", "🧤", "슛스토퍼"),
    ("gk_high_claims_per90", "🪂", "공중볼 캐치 (GK)"),
]
_TIER = ["🥇", "🥈", "🥉"]
_MVP_TIER = ["🏆", "🥈", "🥉"]

# 포지션 그룹별 MVP 종합 점수에 쓰는 지표(나머지는 무시 → 그룹 특성에 맞는 평가).
# Sofascore 컬럼이 없으면 자동 무시되므로 안전하게 추가 가능.
GROUP_MVP_METRICS = {
    "FW": ["npxg_p90", "xa_p90", "kp_p90", "shots_p90",
           "fouled_per90", "offsides_per90",
           "ss_rating", "big_chances_created_per90", "successful_dribbles_per90"],
    "MF": ["xa_p90", "kp_p90", "tackles_won_per90", "interceptions_per90",
           "npxg_p90", "fouled_per90",
           "ss_rating", "pass_pct", "key_passes_per90",
           "ground_duels_won_per90", "recoveries_per90"],
    "DF": ["tackles_won_per90", "interceptions_per90",
           "aerial_won_pct", "aerial_won_per90",
           "pass_pct", "long_ball_pct",
           "clearances_per90", "blocked_shots_per90",
           "ss_rating"],
    "GK": ["ss_rating", "gk_save_pct", "gk_saves_per90",
           "gk_high_claims_per90", "gk_clean_sheets"],
}


def compute_player_badges(norm_key: str, pct_df: pd.DataFrame,
                          top_n: int = 3) -> list[dict]:
    """선수의 스탯 기반 배지 리스트 반환.

    pct_df: league_percentiles() 결과 + 'norm_key', 'pos' 컬럼 포함.
    Sofascore 확장 컬럼이 pct_df 에 있으면 자동으로 평가에 반영.
    배지 종류: (1) 단일 지표 리그 Top N, (2) 포지션 그룹 MVP Top 3, (3) 올라운더.
    """
    if pct_df.empty or "norm_key" not in pct_df.columns:
        return []
    me_match = pct_df[pct_df["norm_key"] == norm_key]
    if me_match.empty:
        return []
    me = me_match.iloc[0]
    badges: list[dict] = []

    # (1) 단일 지표 리그 Top N — 컬럼이 존재하고 값이 충분히 있을 때만
    for col, emoji, label in LEADER_METRICS:
        if col not in pct_df.columns:
            continue
        valid = pct_df[pct_df[col].notna()]
        if len(valid) < top_n:
            continue
        ranked = valid.nlargest(top_n, col)["norm_key"].tolist()
        if norm_key in ranked:
            rank = ranked.index(norm_key) + 1
            badges.append({
                "tier": _TIER[rank - 1],
                "emoji": emoji,
                "label": f"{label} 리그 #{rank}",
                "kind": "leader",
            })

    # (2) 포지션 그룹 MVP — 그룹 특성 지표 평균 백분위 Top 3
    my_grp = position_group(me["pos"])
    grp_metrics = GROUP_MVP_METRICS.get(my_grp, FEATURES)
    # pct_df 에 실제 존재하는 컬럼만 사용
    grp_metrics = [c for c in grp_metrics if c in pct_df.columns]
    if not grp_metrics:
        return badges
    df_g = pct_df.copy()
    df_g["__grp"] = df_g["pos"].map(position_group)
    df_g["__avg"] = df_g[grp_metrics].mean(axis=1, skipna=True)
    grp_top = (df_g[(df_g["__grp"] == my_grp) & df_g["__avg"].notna()]
               .sort_values("__avg", ascending=False)
               .head(3)["norm_key"].tolist())
    if norm_key in grp_top:
        rank = grp_top.index(norm_key) + 1
        badges.append({
            "tier": _MVP_TIER[rank - 1],
            "emoji": "⭐",
            "label": f"{my_grp} MVP #{rank}",
            "kind": "mvp",
        })

    # (3) 올라운더 — 5개 이상 지표가 90+ 백분위 (FEATURES 10개 기준)
    feats_available = [c for c in FEATURES if c in pct_df.columns]
    top_count = sum(1 for c in feats_available if pd.notna(me[c]) and me[c] >= 0.90)
    if top_count >= 5:
        badges.append({
            "tier": "🎩",
            "emoji": "",
            "label": f"올라운더 ({top_count}개 지표 90+%)",
            "kind": "complete",
        })

    return badges


# Sofascore 확장 지표 — 있으면 percentile 변환 대상에 추가.
# 키는 fetch_understat.py 에서 머지될 때의 컬럼명과 일치해야 함.
EXTENDED_FEATURES = [
    "ss_rating", "pass_pct", "long_ball_pct", "cross_acc_pct",
    "tackles_won_pct", "aerial_won_pct", "ground_duels_won_pct",
    "dribble_success_pct", "total_duels_won_pct",
    "key_passes_per90", "big_chances_created_per90",
    "clearances_per90", "blocked_shots_per90", "outfielder_blocks_per90",
    "interceptions_per90_ss", "recoveries_per90",
    "aerial_won_per90", "tackles_won_per90_ss", "ground_duels_won_per90",
    "errors_per90", "possession_won_att_per90",
    "successful_dribbles_per90", "final_third_passes_per90",
    # GK
    "gk_save_pct", "gk_saves_per90", "gk_clean_sheets",
    "gk_high_claims_per90", "gk_runs_out_per90", "gk_punches_per90",
]


def league_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """각 피처를 리그 전체 백분위(0~1)로 변환.

    FEATURES + EXTENDED_FEATURES 중 df 에 존재하는 컬럼을 모두 변환.
    errors_per90 은 낮을수록 좋으므로 부호 반전(1 - rank).
    """
    pct = df.copy()
    for f in FEATURES:
        if f in df.columns:
            pct[f] = df[f].rank(pct=True)
    for f in EXTENDED_FEATURES:
        if f in df.columns:
            r = df[f].rank(pct=True)
            if f == "errors_per90":
                r = 1.0 - r  # 실수가 적을수록 높은 백분위
            pct[f] = r
    return pct


def assign_role(pct_row: pd.Series, group: str) -> tuple[str, float]:
    if group == "DF":
        # 크로스 백분위로 풀백 vs 센터백을 먼저 가른다.
        if pct_row["crosses_per90"] >= FULLBACK_CROSS_PCT:
            return ("공격형 풀백 (Attacking Full-back)", pct_row["crosses_per90"])
        # 센터백: 도움/피파울이 있으면 빌드업형, 아니면 스토퍼.
        if pct_row["ast_per90"] >= 0.5 or pct_row["fouled_per90"] >= 0.5:
            return ("빌드업 CB (Ball-playing)", pct_row["ast_per90"])
        return ("스토퍼 CB (Stopper)", pct_row["interceptions_per90"])

    table = ARCHETYPES.get(group)
    if not table:
        return ("기타", 0.0)
    best, best_score = "기타", -1e9
    for role, weights in table.items():
        score = sum(w * pct_row[f] for f, w in weights.items())
        if score > best_score:
            best, best_score = role, score
    return best, best_score


def top_features(pct_row: pd.Series, n: int = 3) -> str:
    """이 선수의 리그 상위 강점 지표 n개를 라벨로."""
    labels = {
        "npxg_p90": "npxG", "xa_p90": "xA", "kp_p90": "키패스", "shots_p90": "슈팅",
        "crosses_per90": "크로스", "fouled_per90": "피파울(전진)", "offsides_per90": "침투",
        "interceptions_per90": "인터셉트", "tackles_won_per90": "태클", "fouls_per90": "수비파울",
        # 혹시 old 컬럼이 남아있을 경우 폴백
        "npg_per90": "골", "ast_per90": "도움", "sh_per90": "슈팅(raw)",
    }
    s = pct_row[FEATURES].sort_values(ascending=False)
    return ", ".join(f"{labels[f]}({pct_row[f]*100:.0f}%)" for f in s.index[:n])


def _sort_band(band: pd.DataFrame) -> pd.DataFrame:
    """밴드 내 좌→중→우 정렬: 크로스 높은 선수를 바깥쪽(터치라인)으로."""
    n = len(band)
    if n <= 1:
        return band
    s = band.sort_values("crosses_per90")  # 낮을수록 중앙
    order = [None] * n
    left, right = 0, n - 1
    # 크로스 높은 선수부터 바깥(양끝)→안쪽으로 채운다
    for i, (_, row) in enumerate(s.iloc[::-1].iterrows()):
        if i % 2 == 0:
            order[left] = row; left += 1
        else:
            order[right] = row; right -= 1
    return pd.DataFrame(order)


def pick_bands(team_df: pd.DataFrame, formation: str) -> list[pd.DataFrame]:
    """
    포메이션 문자열(예: '4-3-3', '3-4-2-1')에 맞춰 밴드별 선수를 배정한다.
    반환: [수비밴드, 미드밴드, ..., 공격밴드] (각 밴드는 좌→중→우 정렬).
    """
    parts = [int(x) for x in formation.split("-")]
    team_df = team_df.copy()
    team_df["grp"] = team_df["pos"].map(position_group)

    n_def, n_fwd = parts[0], parts[-1]
    n_mid_total = sum(parts[1:-1]) if len(parts) > 2 else 0

    used = set()

    def take(pool_groups, n):
        pool = team_df[team_df["grp"].isin(pool_groups) & ~team_df.index.isin(used)]
        sel = pool.nlargest(n, "minutes")
        used.update(sel.index)
        return sel

    def_band = take(["DF"], n_def)
    # 부족하면 MF에서 보충
    if len(def_band) < n_def:
        def_band = pd.concat([def_band, take(["MF"], n_def - len(def_band))])

    fwd_band = take(["FW"], n_fwd)
    if len(fwd_band) < n_fwd:
        fwd_band = pd.concat([fwd_band, take(["MF", "FW"], n_fwd - len(fwd_band))])

    # 중간 밴드들: MF 우선, 모자라면 FW/DF로 보충
    mid_pool = take(["MF", "FW", "DF"], n_mid_total)
    mid_pool = mid_pool.sort_values("minutes", ascending=False)

    bands = [_sort_band(def_band)]
    if len(parts) > 2:
        # 중간 밴드 크기대로 분할 (앞쪽=수비적 밴드부터)
        rows = list(mid_pool.iterrows())
        idx = 0
        for size in parts[1:-1]:
            chunk = pd.DataFrame([r for _, r in rows[idx:idx + size]])
            bands.append(_sort_band(chunk))
            idx += size
    bands.append(_sort_band(fwd_band))
    return bands


def pick_xi(team_df: pd.DataFrame, n_def=4, n_mid=3, n_fwd=3) -> pd.DataFrame:
    """하위호환: 4-3-3류 3밴드 XI를 단일 DataFrame으로 반환."""
    bands = pick_bands(team_df, f"{n_def}-{n_mid}-{n_fwd}")
    return pd.concat(bands)


def team_goalkeeper(full_df: pd.DataFrame, team: str) -> pd.Series | None:
    """팀의 최다 출전 GK 1명 반환 (없으면 None)."""
    gks = full_df[(full_df["squad"] == team) &
                  (full_df["pos"].fillna("").str.contains("GK"))]
    if gks.empty:
        return None
    return gks.nlargest(1, "minutes").iloc[0]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="팀 포메이션 + 역할 분석")
    p.add_argument("team", help="팀 이름 (부분 일치)")
    p.add_argument("--formation", default=None, help="라인 구성 강제, 예: 4-3-3 (생략시 팀 설정 사용)")
    p.add_argument("--min-minutes", type=int, default=600)
    args = p.parse_args(argv)

    full = pd.read_csv(DATA_PATH)
    df = full[full["minutes"] >= args.min_minutes].reset_index(drop=True)
    # 백분위/역할은 필드플레이어 기준 (GK 제외)
    outfield = df[~df["pos"].fillna("").str.contains("GK")].reset_index(drop=True)
    pct = league_percentiles(outfield)

    team = outfield[outfield["squad"].str.contains(args.team, case=False, na=False)]
    if team.empty:
        print(f"팀을 찾을 수 없음: {args.team}")
        return 1
    squad = team.iloc[0]["squad"]

    formation = args.formation or team_formation(squad)
    bands = pick_bands(team, formation)

    print(f"\n■ {squad}  —  주전 XI 추정 ({formation}, 출전시간 기준)\n")
    band_names = (["수비"] +
                  [f"중원{i+1}" for i in range(len(bands) - 2)] +
                  ["공격"]) if len(bands) > 2 else ["수비", "공격"]
    # 공격→수비 순으로 출력(피치 위→아래)
    for bi in range(len(bands) - 1, -1, -1):
        band = bands[bi]
        if band.empty:
            continue
        print(f"  [{band_names[bi]}]")
        for _, r in band.iterrows():
            grp = position_group(r["pos"])
            prow = pct[pct["player"] == r["player"]].iloc[0]
            role, _ = assign_role(prow, grp)
            print(f"    {r['player']:<20} {r['pos']:<7} {int(r['minutes']):>4}분  →  {role}")
            print(f"      강점: {top_features(prow)}")
        print()

    gk = team_goalkeeper(full, squad)
    if gk is not None:
        save = gk.get("gk_save_pct")
        save_s = f"세이브% {save:.0f}" if pd.notna(save) else ""
        print(f"  [GK]\n    {gk['player']:<20} {int(gk['minutes']):>4}분  {save_s}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
