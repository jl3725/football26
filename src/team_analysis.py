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

import numpy as np
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
MID_TRIANGLE_DY = 9  # 단일 피벗 3미들 삼각형의 깊이 오프셋(%)

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
            y = band_y(bi, n_bands)
            # 단일 미드필드 라인(4-3-3의 RCM/CM/LCM)은 평평한 일렬이 아니라
            # 단일 피벗 삼각형(4-1-2-3 느낌)으로 그린다: 중앙 CM(=수비형 피벗)은
            # 한 칸 내려앉고, 양옆 8번(RCM/LCM)은 한 칸 전진. 현대 4-3-3의
            # 중앙 미드는 거의 항상 가장 깊은 6번이므로 일반적으로 성립.
            if kind == "M" and size == 3 and not is_high_mid:
                if slot == "CM":
                    y += MID_TRIANGLE_DY      # 피벗 — 더 깊게
                elif slot in ("RCM", "LCM"):
                    y -= MID_TRIANGLE_DY      # 8번 — 더 높게
            return (x, y)
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


def display_slot(slot: str, formation: str) -> str:
    """토큰에 보여줄 슬롯 라벨. 단일 피벗 3미들의 중앙 CM은 'DM'으로 표기한다.

    (기하학적 배치는 slot_xy가 원래 슬롯명 'CM'으로 계산하므로 여기선 텍스트만 바꾼다.)
    """
    if slot != "CM":
        return slot
    try:
        parts = [int(x) for x in formation.split("-")]
    except ValueError:
        return slot
    n_bands = len(parts)
    for bi, size in enumerate(parts):
        if 0 < bi < n_bands - 1 and size == 3:        # 중간 M 밴드
            is_high_mid = bi == n_bands - 2 and n_bands >= 4
            if not is_high_mid:
                return "DM"
    return slot


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

# 배지 산정 최소 출전(분) ≈ 10경기. '리그 #1 머신/마스터' 류 배지는 충분한
# 표본을 요구해야 한다. 이보다 낮으면 5경기 소표본 선수가 per-90 비율로 실제
# 시즌 1위(예: 득점왕 Haaland)를 제치고 '리그 #1'을 가로채는 왜곡이 생긴다.
# 900분 이상으로 한정하면 비율 1위와 시즌 총량 1위가 일치한다.
BADGE_MIN_MINUTES = 900


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
    # GK — 선방 빈도(saves/90)는 강팀 키퍼 역지표라 배지에서 제외.
    ("gk_save_pct", "🧤", "선방왕(세이브율)"),
    ("gk_clean_sheets", "🔒", "무실점왕"),
    ("gk_high_claims_per90", "🪂", "공중볼 캐치 (GK)"),
]
_TIER = ["🥇", "🥈", "🥉"]
_MVP_TIER = ["🏆", "🥈", "🥉", "🎖️", "🎖️"]

# GK 전용 지표 — 외야수 풀에서는 평가 스킵, GK 풀에서만 의미.
GK_ONLY_METRICS = {
    "gk_saves_per90", "gk_high_claims_per90", "gk_runs_out_per90",
    "gk_punches_per90", "gk_save_pct", "gk_clean_sheets",
}

# Percentage 메트릭의 sample size 가드. 동반 raw 카운트 메트릭의 풀 내 백분위가
# 임계 이상인 선수만 leader 평가 대상. 시도 1회로 100% 인플레이션 차단.
SAMPLE_SIZE_GUARDS = {
    "aerial_won_pct": ("aerial_won_per90", 0.40),
    "tackles_won_pct": ("tackles_won_per90_ss", 0.40),
    "long_ball_pct": ("accurateLongBalls", 0.40),
    "cross_acc_pct": ("accurateCrosses", 0.30),
    "dribble_success_pct": ("successful_dribbles_per90", 0.30),
    "ground_duels_won_pct": ("ground_duels_won_per90", 0.30),
}

# DF 를 CB(센터백) vs FB(풀백/윙백) 로 가르는 임계.
# crosses_per90 의 outfield 풀 내 백분위 — 풀백은 보통 0.6+ 이지만,
# inverted FB(Calafiori 등) 같은 미드필드형 풀백은 cross 적어 0.45 정도.
FB_CROSS_PCT = 0.45


def _df_subgroup(pct_row: pd.Series) -> str:
    """DF 선수의 sub-group 결정. crosses_per90 백분위 기준 — 풀백이면 'FB',
    아니면 'CB'. 임계는 0.55 (outfield 풀 내 평균 이상 = 풀백류).
    """
    val = pct_row.get("crosses_per90")
    if val is not None and pd.notna(val) and val >= FB_CROSS_PCT:
        return "FB"
    return "CB"


# MF 를 DM(앵커·레지스타) / CM(박투박) / AM(공격형) 으로 가르는 임계.
# 절대 백분위 기준 — 한쪽 점수가 매우 높을 때만 한쪽으로 분류, 둘 다 어중간하면 CM.
MF_AM_THRESHOLD = 0.65   # 공격 백분위 평균 0.65+ 이고 수비보다 충분히 높을 때 AM
MF_DM_THRESHOLD = 0.65   # 수비 백분위 평균 0.65+ 이고 공격보다 충분히 높을 때 DM
MF_SUBGROUP_MARGIN = 0.10  # 양 끝 분류 시 반대 측보다 최소 이만큼 우세해야 함


def _mf_subgroup(pct_row: pd.Series) -> str:
    """MF 선수의 sub-group 결정. 공격/수비 기여 평균 백분위 절대값 기준.

    분류 규칙:
    - 양쪽 모두 평균 이상(0.55+) → CM (박투박 — Rice, Bellingham 류)
    - 공격만 강함 → AM (Bruno, Eze, Palmer)
    - 수비만 강함 → DM (Caicedo, Zubimendi)
    - 그 외(둘 다 약함) → CM 폴백
    """
    att_keys = ["kp_p90", "xa_p90", "npxg_p90"]
    def_keys = ["tackles_won_per90", "interceptions_per90"]
    att_vals = [pct_row.get(k) for k in att_keys
                if pct_row.get(k) is not None and pd.notna(pct_row.get(k))]
    def_vals = [pct_row.get(k) for k in def_keys
                if pct_row.get(k) is not None and pd.notna(pct_row.get(k))]
    if not att_vals or not def_vals:
        return "CM"
    att = sum(att_vals) / len(att_vals)
    dfn = sum(def_vals) / len(def_vals)
    # 양쪽 모두 평균 이상이면 박투박 (CM)
    if att >= 0.55 and dfn >= 0.55:
        return "CM"
    # 한쪽만 강하면 그쪽으로 분류
    if att >= MF_AM_THRESHOLD and att > dfn:
        return "AM"
    if dfn >= MF_DM_THRESHOLD and dfn > att:
        return "DM"
    return "CM"

# 포지션 그룹별 MVP 종합 점수에 쓰는 지표. 같은 지표를 여러 번 적어
# 가중치(반복 횟수만큼)를 부여한다. Sofascore 컬럼이 없으면 자동 무시.
# 핵심 시그널(ss_rating, 포지션 특화 지표)을 2~3배 가중.
GROUP_MVP_METRICS = {
    # 공격수 — 팀 공격 보정 약하게(어시 인플레이션 보정 정도). 약팀 진짜 잘하는 ST 페널티 최소화.
    "FW": [
        "team_attack_score", "team_attack_score",     # 2x ≈ 12%
        "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        "npxg_p90", "npxg_p90",
        "xa_p90", "kp_p90", "shots_p90",
        "fouled_per90", "offsides_per90",
        "big_chances_created_per90", "successful_dribbles_per90",
    ],
    # MF 폴백 — _mf_subgroup() 으로 분류 못 할 때
    "MF": [
        "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        "xa_p90", "kp_p90",
        "pass_pct", "pass_pct",
        "key_passes_per90",
        "tackles_won_per90", "interceptions_per90",
        "ground_duels_won_per90", "recoveries_per90",
    ],
    # 수비형 미드 (앵커·레지스타) — 팀 수비 + 차단·인터셉트·딥 패싱
    "DM": [
        # 팀 수비 컨텍스트 (~25%) — DM은 수비 골격의 일부
        "team_defense_score", "team_defense_score", "team_defense_score",
        "team_defense_score",
        # 개인 종합 (~30%)
        "ss_rating", "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        # 수비 액션 (~25%)
        "tackles_won_per90", "tackles_won_per90",
        "interceptions_per90", "interceptions_per90",
        "tackles_won_pct",
        # 빌드업 (~20%) — 레지스타 평가
        "pass_pct", "pass_pct",
        "long_ball_pct",
        "recoveries_per90",
    ],
    # 박투박 (Rice, Bellingham 류) — 균형, 팀 수비+공격 양쪽 약하게 보정
    "CM": [
        "team_defense_score", "team_defense_score",          # 수비 일부 기여
        "team_attack_score", "team_attack_score",            # 공격 일부 기여
        "ss_rating", "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        "pass_pct", "pass_pct",
        "kp_p90", "xa_p90",                                  # 창의성도 일부
        "tackles_won_per90", "interceptions_per90",          # 수비도 일부
        "npxg_p90",                                          # 박투박 골 기여
        "fouled_per90",                                      # 드리블 침투
        "ground_duels_won_per90", "recoveries_per90",
    ],
    # 공격형 미드 (Bruno, Eze, Bellingham 식 10번) — 팀 공격 보정 약하게
    "AM": [
        # 팀 공격 컨텍스트 — 어시 인플레이션 보정 정도(~10%), 약팀 잘하는 10번 페널티 최소화
        "team_attack_score", "team_attack_score",
        # 개인 종합
        "ss_rating", "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        # 창의성 핵심
        "kp_p90", "kp_p90",
        "xa_p90", "xa_p90",
        "key_passes_per90", "key_passes_per90",
        "big_chances_created_per90", "big_chances_created_per90",
        # 마무리 기여
        "npxg_p90",
        # 드리블·침투
        "fouled_per90",
        "successful_dribbles_per90",
    ],
    # CB와 FB는 _df_subgroup() 으로 분리되어 각각 별도 평가.
    # "DF"는 폴백 — crosses 데이터가 없거나 sub-group 판단 못할 때 사용.
    "DF": [
        "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        "aerial_won_pct", "pass_pct", "long_ball_pct",
        "tackles_won_per90", "interceptions_per90",
    ],
    # 센터백 — 팀 수비 + 빌드업 + 공중볼 + set piece 마무리
    "CB": [
        # 팀 수비 컨텍스트 (~30%) — 리그 최소실점 팀의 CB 보정
        "team_defense_score", "team_defense_score", "team_defense_score",
        "team_defense_score", "team_defense_score",
        # 개인 종합 평가 (~30%)
        "ss_rating", "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        # CB 효율 메트릭 (~30%)
        "aerial_won_pct", "aerial_won_pct",      # 공중볼 효율
        "pass_pct", "pass_pct",                  # 빌드업 정확도
        "long_ball_pct",                          # 롱볼 정확도
        # 공격 기여 (~10%) — 코너 헤더 골
        "npxg_p90",
        "xa_p90",
    ],
    # 풀백/윙백 — 팀 수비 + 크로스·드리블·어시스트·진영 진입
    "FB": [
        # 팀 수비 컨텍스트
        "team_defense_score", "team_defense_score", "team_defense_score",
        "team_defense_score", "team_defense_score",
        # 개인 종합
        "ss_rating", "ss_rating", "ss_rating", "ss_rating", "ss_rating",
        # 공격 기여
        "cross_acc_pct", "cross_acc_pct",
        "successful_dribbles_per90", "successful_dribbles_per90",
        "key_passes_per90", "key_passes_per90",
        "xa_p90", "xa_p90",
        # 수비 효율
        "tackles_won_pct",
        "interceptions_per90",
    ],
    "GK": [
        # 팀 수비 컨텍스트 — 키퍼는 팀 결과의 산물
        "team_defense_score", "team_defense_score", "team_defense_score",
        "team_defense_score",
        "ss_rating", "ss_rating", "ss_rating",
        "gk_clean_sheets", "gk_clean_sheets",    # 시즌 클린시트 비중
        "gk_save_pct", "gk_save_pct",            # 세이브율(실력 지표) — 빈도 대신 가중
        "gk_high_claims_per90",                  # 박스 커맨딩
        # gk_saves_per90(선방 빈도) 제외 — 강팀 키퍼 역지표
    ],
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
    # 저출전 선수는 per-90 과대값으로 백분위가 부풀려질 수 있으므로 배지 미부여.
    if "minutes" in me and pd.notna(me["minutes"]) and me["minutes"] < BADGE_MIN_MINUTES:
        return []
    my_grp = position_group(me["pos"])
    badges: list[dict] = []

    # DF/MF 는 세부 sub-group 으로 분리 (다른 역할은 다른 풀로 비교)
    mvp_grp = my_grp
    if my_grp == "DF":
        mvp_grp = _df_subgroup(me)
    elif my_grp == "MF":
        mvp_grp = _mf_subgroup(me)

    # 그룹 비교 풀 분리 — GK는 GK 끼리, 외야는 외야 끼리
    pct_df = pct_df.copy()
    pct_df["__grp"] = pct_df["pos"].map(position_group)
    if my_grp == "GK":
        pool = pct_df[pct_df["__grp"] == "GK"]
    else:
        pool = pct_df[pct_df["__grp"] != "GK"]
    # 시즌 중 이적한 선수가 양 팀에 두 번 잡히는 경우 — 출전 많은 행만 유지
    if "minutes" in pool.columns:
        pool = (pool.sort_values("minutes", ascending=False)
                    .drop_duplicates("norm_key", keep="first"))
        # 저출전 선수(소표본 per-90 인플레이션) 제외 — 배지 산정 전체에 적용
        pool = pool[pool["minutes"] >= BADGE_MIN_MINUTES]
    # Leader 는 외야 전체(또는 GK 전체) 풀에서 비교 — "리그 #N" 라벨이 의미 있게.
    leader_pool = pool
    # MVP 풀 — DF/MF 의 경우 sub-group 으로 좁혀 같은 역할끼리 비교
    mvp_pool = pool
    if my_grp == "DF":
        mvp_pool = mvp_pool[mvp_pool["__grp"] == "DF"]
        mvp_pool = mvp_pool[mvp_pool.apply(_df_subgroup, axis=1) == mvp_grp]
    elif my_grp == "MF":
        mvp_pool = mvp_pool[mvp_pool["__grp"] == "MF"]
        mvp_pool = mvp_pool[mvp_pool.apply(_mf_subgroup, axis=1) == mvp_grp]

    # (1) 단일 지표 리그 Top N — leader_pool 에서 평가
    # 외야 전체에서 잡힌 메트릭은 sub-group leader 평가에서 스킵 (중복 방지)
    outfield_leader_cols: set[str] = set()
    pool = leader_pool  # 아래 변수명 호환
    for col, emoji, label in LEADER_METRICS:
        # GK 전용 메트릭은 GK 풀에서만, 그 외는 외야 풀에서만
        if col in GK_ONLY_METRICS and my_grp != "GK":
            continue
        if col not in GK_ONLY_METRICS and my_grp == "GK":
            continue
        if col not in pool.columns:
            continue
        # 값이 의미있게 분산되는지: 0이거나 NaN을 제외
        valid = pool[pool[col].notna() & (pool[col] > 0)]
        # Sample size 가드 — % 메트릭은 동반 raw 카운트 백분위가 임계 이상이어야 함
        guard = SAMPLE_SIZE_GUARDS.get(col)
        if guard:
            guard_col, guard_threshold = guard
            if guard_col in pool.columns:
                valid = valid[valid[guard_col].notna()
                              & (valid[guard_col] >= guard_threshold)]
            # 본인도 동반 카운트 임계 통과해야 함
            my_guard = me.get(guard_col)
            if my_guard is None or pd.isna(my_guard) or my_guard < guard_threshold:
                continue
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
            outfield_leader_cols.add(col)

    # (1b) Sub-group leader — DF/MF 에 한해, 외야 전체 leader 에서 못 잡힌 메트릭만
    # 같은 sub-group(CB/FB/DM/CM/AM) 내에서 Top 3 평가 → "CB #N" 같은 라벨
    if my_grp in {"DF", "MF"} and not mvp_pool.empty:
        for col, emoji, label in LEADER_METRICS:
            if col in GK_ONLY_METRICS:
                continue
            if col in outfield_leader_cols:
                continue  # 이미 외야 전체에서 받은 배지
            if col not in mvp_pool.columns:
                continue
            valid = mvp_pool[mvp_pool[col].notna() & (mvp_pool[col] > 0)]
            guard = SAMPLE_SIZE_GUARDS.get(col)
            if guard:
                gc, gt = guard
                if gc in mvp_pool.columns:
                    valid = valid[valid[gc].notna() & (valid[gc] >= gt)]
                my_g = me.get(gc)
                if my_g is None or pd.isna(my_g) or my_g < gt:
                    continue
            if len(valid) < top_n:
                continue
            ranked = valid.nlargest(top_n, col)["norm_key"].tolist()
            if norm_key in ranked:
                rank = ranked.index(norm_key) + 1
                badges.append({
                    "tier": _TIER[rank - 1],
                    "emoji": emoji,
                    "label": f"{label} {mvp_grp} #{rank}",
                    "kind": "subgroup_leader",
                })

    # (2) 포지션 그룹 MVP — mvp_pool(sub-group) 내에서 평균 백분위 Top 5
    grp_metrics = GROUP_MVP_METRICS.get(mvp_grp, FEATURES)
    grp_metrics = [c for c in grp_metrics if c in mvp_pool.columns]
    if not grp_metrics:
        return badges
    mvp_pool = mvp_pool.copy()
    mvp_pool["__avg"] = mvp_pool[grp_metrics].mean(axis=1, skipna=True)
    grp_top = (mvp_pool[mvp_pool["__avg"].notna()]
               .sort_values("__avg", ascending=False)
               .head(5)["norm_key"].tolist())
    if norm_key in grp_top:
        rank = grp_top.index(norm_key) + 1
        badges.append({
            "tier": _MVP_TIER[rank - 1],
            "emoji": "⭐",
            "label": f"{mvp_grp} MVP #{rank}",
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
    # 팀 컨텍스트 — 수비/공격 평가 보정
    "team_defense_score", "team_attack_score",
]


def league_percentiles(df: pd.DataFrame, min_minutes: int = 0) -> pd.DataFrame:
    """각 피처를 리그 백분위(0~1)로 변환.

    FEATURES + EXTENDED_FEATURES 중 df 에 존재하는 컬럼을 모두 변환.
    errors_per90 은 낮을수록 좋으므로 부호 반전(1 - rank).

    min_minutes > 0 이면 그 출전시간 이상 선수들로만 분포(baseline)를 만들고,
    df 의 '모든' 선수(미달 선수 포함)를 그 분포에 대한 백분위로 매긴다.
    → 소수 저출전 선수의 per-90 과대값이 분포를 오염시키지 않으면서도,
      보드의 실측 XI 선수가 백분위 표에서 누락돼 사라지는 일이 없다.
    """
    pct = df.copy()
    if min_minutes > 0 and "minutes" in df.columns:
        base_mask = df["minutes"] >= min_minutes
        if int(base_mask.sum()) < 10:        # baseline 표본이 너무 적으면 전체 사용
            base_mask = pd.Series(True, index=df.index)
    else:
        base_mask = pd.Series(True, index=df.index)

    def pctl(col: pd.Series) -> pd.Series:
        base = np.sort(col[base_mask].dropna().to_numpy())
        if base.size == 0:
            return col.rank(pct=True)
        vals = col.to_numpy(dtype=float)
        ranks = np.searchsorted(base, vals, side="right") / base.size
        out = np.clip(ranks, 0.0, 1.0)
        out[np.isnan(vals)] = np.nan       # 결측은 백분위도 결측
        return pd.Series(out, index=col.index)

    for f in FEATURES:
        if f in df.columns:
            pct[f] = pctl(df[f])
    for f in EXTENDED_FEATURES:
        if f in df.columns:
            r = pctl(df[f])
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
