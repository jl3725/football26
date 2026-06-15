"""
Streamlit 프론트엔드 — 팀 포메이션 보드 + 선수 역할/프로필 + 비슷한 선수.

실행:
    streamlit run app.py

좌측에서 팀/포메이션을 고르면 피치 위에 주전 XI 가 배치되고,
각 선수 토큰에 호버하면 강점 지표가 '라벨'과 함께 보인다(숫자만 X).
아래에서 선수를 고르면 10개 지표 백분위 막대 + 스타일 유사 선수를 보여준다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from similar_players import FEATURES, DATA_PATH, build_embeddings, find_similar, fine_group  # noqa: E402
from team_analysis import (  # noqa: E402
    league_percentiles, assign_role, position_group,
    pick_bands, team_formations, team_goalkeeper, load_formations,
    load_slots, team_xi_from_slots, slot_xy, slot_kind, display_slot,
    compute_player_badges,
    GK_Y, BAND_Y_TOP, BAND_Y_BOTTOM,
)

# 피처 → 한글 라벨 (숫자만 보이는 문제 해결의 핵심)
LABELS = {
    # 원래 10개
    "npxg_p90": "npxG/90", "xa_p90": "xA/90", "kp_p90": "키패스/90", "shots_p90": "슈팅/90",
    "crosses_per90": "크로스/90", "fouled_per90": "피파울/90", "offsides_per90": "침투/90",
    "interceptions_per90": "인터셉트/90", "tackles_won_per90": "태클성공/90", "fouls_per90": "수비파울/90",
    # v2 추가 6개
    "goals_per90": "득점/90", "assists_per90": "어시스트/90",
    "key_passes_per90": "키패스(SS)/90", "big_chances_created_per90": "빅찬스/90",
    "successful_dribbles_per90": "드리블/90", "dribble_success_pct": "드리블성공률",
}
# 밴드 색상: 수비(파랑) → 중원(주황) → 공격(빨강)
BAND_DEF, BAND_MID, BAND_FWD = "#4d80e0", "#e0a23a", "#e0584c"

# EPL 25/26 팀 대표 컬러 (유니폼 폴백 토큰 + 사진 배경 디스크용)
TEAM_COLOR = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Bournemouth": "#DA291C",
    "Brentford": "#E30613", "Brighton": "#0057B8", "Burnley": "#6C1D45",
    "Chelsea": "#034694", "Crystal Palace": "#1B458F", "Everton": "#003399",
    "Fulham": "#1d1d1f", "Leeds United": "#1D428A", "Liverpool": "#C8102E",
    "Manchester City": "#6CABDD", "Manchester Utd": "#DA291C",
    "Newcastle United": "#241F20", "Nottingham Forest": "#DD0000",
    "Sunderland": "#EB172B", "Tottenham Hotspur": "#132257",
    "West Ham United": "#7A263A", "Wolves": "#FDB913",
}


def team_color(team: str) -> str:
    return TEAM_COLOR.get(team, "#444a55")


def sofa_photo(sid) -> str:
    """Sofascore 선수 id → 헤드샷 이미지 URL. id 없으면 빈 문자열."""
    s = _num_str(sid)
    return f"https://img.sofascore.com/api/v1/player/{s}/image" if s else ""

st.set_page_config(page_title="FC Analytics — 포메이션·역할", layout="wide")


STANDINGS_PATH = Path(__file__).resolve().parent / "data" / "standings_2025_2026.csv"


@st.cache_data
def load(_mtime: float = 0.0) -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


@st.cache_data
def load_standings() -> pd.DataFrame | None:
    if not STANDINGS_PATH.exists():
        return None
    return pd.read_csv(STANDINGS_PATH)


# 팀 특성 지표: (라벨, 컬럼, 방향) — 방향 high=높을수록 강점, low=낮을수록 강점.
# gf/ga 는 standings(팀 절대값), 나머지는 선수 분(minutes) 가중평균.
TEAM_TRAITS = [
    ("화력",        "gf",                         "high", "standings"),
    ("수비 견고함",  "ga",                         "low",  "standings"),
    ("점유·빌드업",  "pass_pct",                   "high", "wmean"),
    ("공중 장악",    "aerial_won_pct",             "high", "wmean"),
    ("측면 공격",    "crosses_per90",              "high", "wmean"),
    ("전방 압박",    "recoveries_per90",           "high", "wmean"),
    ("찬스 창출",    "key_passes_per90",           "high", "wmean"),
    ("개인 돌파",    "successful_dribbles_per90",   "high", "wmean"),
    ("롱볼 활용",    "long_ball_pct",              "high", "wmean"),
]


@st.cache_data
def team_traits_table(_mtime: float = 0.0) -> pd.DataFrame:
    """전 팀 × 특성지표 표 — 강점/약점 백분위 산정용."""
    fulldf = pd.read_csv(DATA_PATH)
    out = fulldf[~fulldf["pos"].fillna("").str.contains("GK")].copy()  # 외야만
    stnd = load_standings()
    teams = sorted(fulldf["squad"].unique())
    rows: dict[str, dict] = {}
    for t in teams:
        td = out[out["squad"] == t]
        rec: dict[str, float] = {}
        # standings 절대값
        if stnd is not None:
            srow = stnd[stnd["squad"] == t]
            if not srow.empty:
                rec["gf"] = float(srow["gf"].iloc[0])
                rec["ga"] = float(srow["ga"].iloc[0])
        # 분 가중평균
        for _, col, _, mode in TEAM_TRAITS:
            if mode != "wmean":
                continue
            v = td[td[col].notna() & (td["minutes"] > 0)]
            w = v["minutes"].sum()
            if w > 0:
                rec[col] = float((v[col] * v["minutes"]).sum() / w)
        rows[t] = rec
    return pd.DataFrame(rows).T


def team_characteristics(team: str, traits: pd.DataFrame):
    """팀의 강점 3 / 약점 3 → 각각 [(라벨, 리그순위), ...] (순위 1=리그 최고)."""
    n = len(traits)
    scored = []
    for label, col, direction, _ in TEAM_TRAITS:
        if col not in traits.columns or team not in traits.index:
            continue
        s = traits[col]
        if pd.isna(s.get(team)):
            continue
        asc = (direction == "low")          # low면 작은 값이 1위
        rank = int(s.rank(ascending=asc, method="min")[team])
        pctile = 1 - (rank - 1) / (n - 1) if n > 1 else 1.0   # 1=최고
        scored.append((label, rank, pctile))
    scored.sort(key=lambda x: x[2], reverse=True)
    strengths = [(lbl, r) for lbl, r, _ in scored[:3]]
    weaknesses = [(lbl, r) for lbl, r, _ in sorted(scored, key=lambda x: x[2])[:3]]
    return strengths, weaknesses


def team_traits_html(strengths, weaknesses) -> str:
    def chips(items, color):
        return "".join(
            f"<span style='display:inline-block; padding:4px 11px; margin:3px 5px 3px 0; "
            f"background:{color}22; color:{color}; border:1px solid {color}66; "
            f"border-radius:14px; font-size:12.5px; font-weight:600; white-space:nowrap;'>"
            f"{lbl} <b style='opacity:.8;'>{r}위</b></span>"
            for lbl, r in items
        )
    return f"""
    <div style="margin:-4px 0 14px; font-family:sans-serif;">
      <div style="margin-bottom:5px;">
        <span style="color:#4caf50; font-weight:800; font-size:13px; margin-right:6px;">💪 강점</span>
        {chips(strengths, '#4caf50')}
      </div>
      <div>
        <span style="color:#ef5350; font-weight:800; font-size:13px; margin-right:6px;">⚠️ 약점</span>
        {chips(weaknesses, '#ef5350')}
      </div>
    </div>
    """


def standings_banner_html(row: pd.Series) -> str:
    rank = int(row["rank"])
    pts  = int(row["points"])
    w, d, l = int(row["won"]), int(row["drawn"]), int(row["lost"])
    gf, ga, gd = int(row["gf"]), int(row["ga"]), int(row["gd"])
    gd_str = f"+{gd}" if gd > 0 else str(gd)

    if rank == 1:
        medal = "🥇"
    elif rank == 2:
        medal = "🥈"
    elif rank == 3:
        medal = "🥉"
    elif rank <= 4:
        medal = "🏆"   # UCL
    elif rank <= 6:
        medal = "🟢"   # UEL / UECL 권
    elif rank >= 18:
        medal = "🔴"   # 강등권
    else:
        medal = "⚪"

    return f"""
    <div style="
        display:flex; align-items:center; gap:18px; flex-wrap:wrap;
        background:linear-gradient(90deg,#1a2a3a,#0f1f2f);
        border:1px solid rgba(255,255,255,.12); border-radius:10px;
        padding:12px 20px; margin-bottom:14px; font-family:sans-serif; color:#fff;">
      <div style="font-size:28px; line-height:1;">{medal}</div>
      <div>
        <div style="font-size:22px; font-weight:800; letter-spacing:.5px;">리그 {rank}위</div>
        <div style="font-size:12px; color:#aaa;">Premier League 2025/26</div>
      </div>
      <div style="width:1px; height:40px; background:rgba(255,255,255,.2);"></div>
      <div style="text-align:center;">
        <div style="font-size:26px; font-weight:800; color:#f0c040;">{pts}</div>
        <div style="font-size:11px; color:#aaa;">승점</div>
      </div>
      <div style="width:1px; height:40px; background:rgba(255,255,255,.2);"></div>
      <div style="text-align:center;">
        <div style="font-size:16px; font-weight:700;">
          <span style="color:#4caf50;">{w}승</span>
          <span style="color:#999; margin:0 4px;">{d}무</span>
          <span style="color:#f44336;">{l}패</span>
        </div>
        <div style="font-size:11px; color:#aaa;">{w+d+l}경기</div>
      </div>
      <div style="width:1px; height:40px; background:rgba(255,255,255,.2);"></div>
      <div style="display:flex; gap:16px;">
        <div style="text-align:center;">
          <div style="font-size:18px; font-weight:700; color:#64b5f6;">{gf}</div>
          <div style="font-size:11px; color:#aaa;">득점</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:18px; font-weight:700; color:#ef9a9a;">{ga}</div>
          <div style="font-size:11px; color:#aaa;">실점</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:18px; font-weight:700; color:{'#4caf50' if gd > 0 else '#ef9a9a' if gd < 0 else '#aaa'};">{gd_str}</div>
          <div style="font-size:11px; color:#aaa;">득실차</div>
        </div>
      </div>
    </div>
    """


def top_strengths(prow: pd.Series, n: int = 3) -> list[tuple[str, int]]:
    # LABELS에 있고 prow에도 존재하는 피처만 사용 — 새 피처 추가 시 KeyError 방지
    avail = [f for f in FEATURES if f in LABELS and f in prow.index and pd.notna(prow.get(f))]
    s = prow[avail].sort_values(ascending=False)
    return [(LABELS[f], round(prow[f] * 100)) for f in s.index[:n]]


# ── FM 선수 능력치 화면 스타일 ─────────────────────────────────────────────
# 대분류(6개) 아래 세부 능력치(총 19개)를 숫자+색상으로 표시. FM 능력치 화면 느낌.
# 각 세부 능력치 = (라벨, [기여 컬럼들]) — 컬럼 평균 백분위 → 1~20.
FM_DETAIL: dict[str, list[tuple[str, list[str]]]] = {
    "공격": [
        ("결정력",   ["npxg_p90"]),
        ("슈팅 빈도", ["shots_p90", "sot_per90"]),
        ("침투",     ["offsides_per90"]),
    ],
    "창조": [
        ("패스 위협", ["xa_p90"]),
        ("키패스",    ["kp_p90", "key_passes_per90"]),
        ("빅찬스",    ["big_chances_created_per90"]),
    ],
    "배급": [
        ("패스 정확도", ["pass_pct"]),
        ("롱패스",      ["long_ball_pct"]),
        ("전진 패스",   ["final_third_passes_per90"]),
    ],
    "볼 운반": [
        ("드리블", ["successful_dribbles_per90", "dribble_success_pct"]),
        ("돌파력", ["fouled_per90"]),
        ("크로스", ["cross_acc_pct"]),
    ],
    "수비": [
        ("태클",       ["tackles_won_per90", "tackles_won_pct"]),
        ("가로채기",   ["interceptions_per90"]),
        ("블록·클리어", ["blocked_shots_per90", "clearances_per90"]),
        ("볼 회수",    ["recoveries_per90", "possession_won_att_per90"]),
    ],
    "피지컬·듀얼": [
        ("공중볼",    ["aerial_won_pct", "aerial_won_per90"]),
        ("지상 경합", ["ground_duels_won_pct"]),
        ("종합 듀얼", ["total_duels_won_pct"]),
    ],
}

# GK 세부 능력치.
# 주의: gk_saves_per90(선방 빈도)는 키퍼 실력이 아니라 '팀이 슛을 얼마나 내주는가'
# 를 측정한다(강팀 키퍼일수록 낮음 — 라야가 리그 꼴찌급). 역지표라 평가에서 제외하고,
# 실력 지표인 세이브율 + 결과 지표인 클린시트 + 빌드업/박스 커맨딩으로 평가한다.
GK_DETAIL: dict[str, list[tuple[str, list[str]]]] = {
    "선방": [
        ("세이브율", ["gk_save_pct"]),   # 빈도 제외 — 실력 지표만
    ],
    "무실점": [
        ("클린시트", ["gk_clean_sheets"]),
    ],
    "박스 지배": [
        ("하이볼 처리", ["gk_high_claims_per90"]),
        ("펀칭",        ["gk_punches_per90"]),
        ("스위핑",      ["gk_runs_out_per90"]),
    ],
    "빌드업": [
        ("패스 정확도", ["pass_pct"]),
        ("롱볼 정확도", ["long_ball_pct"]),
    ],
}


def fm_rating(pct: float) -> int:
    """0~1 리그 백분위 → 1~99 능력치."""
    if pct is None or pd.isna(pct):
        return 1
    return max(1, min(99, round(1 + float(pct) * 98)))


def fm_color(r: int) -> str:
    """1~99 능력치 → 색상."""
    if r >= 85: return "#4d9aff"   # 파랑 — 압도적
    if r >= 70: return "#5cd66c"   # 초록 — 강점
    if r >= 50: return "#ffd048"   # 노랑 — 평균
    if r >= 35: return "#ff9c4a"   # 주황 — 평균 이하
    return "#ff6961"                # 빨강 — 약점


def _attr_rating(prow: pd.Series, cols: list[str]) -> int | None:
    """기여 컬럼들의 평균 백분위 → 1~99. 모두 결측이면 None."""
    vals = [float(prow[c]) for c in cols
            if c in prow.index and pd.notna(prow.get(c))]
    if not vals:
        return None
    return fm_rating(sum(vals) / len(vals))


def _fm_detail_html(prow: pd.Series, detail: dict) -> str:
    """FM 선수 화면 스타일 — 대분류 카드 그리드, 각 세부 능력치는 색상 숫자칩."""
    blocks = []
    for cat, attrs in detail.items():
        rows = []
        for label, cols in attrs:
            r = _attr_rating(prow, cols)
            if r is not None:
                rows.append((label, r))
        if not rows:
            continue
        cat_avg = round(sum(r for _, r in rows) / len(rows))
        attr_html = "".join(
            f'<div class="fa-row"><span class="fa-lbl">{lbl}</span>'
            f'<span class="fa-num" style="background:{fm_color(r)};">{r}</span></div>'
            for lbl, r in rows
        )
        blocks.append(f"""
        <div class="fa-cat">
          <div class="fa-head"><span>{cat}</span>
            <span class="fa-avg" style="color:{fm_color(cat_avg)};">{cat_avg}</span></div>
          {attr_html}
        </div>""")
    return f"""
    <style>
      .fa-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
      .fa-cat {{ background:rgba(16,21,28,.55); border:1px solid rgba(255,255,255,.08);
                 border-radius:9px; padding:8px 10px; }}
      .fa-head {{ display:flex; justify-content:space-between; align-items:center;
                  color:#cfe; font-weight:700; font-size:12.5px;
                  border-bottom:1px solid rgba(255,255,255,.1);
                  padding-bottom:5px; margin-bottom:5px; }}
      .fa-avg {{ font-size:14px; font-weight:800; }}
      .fa-row {{ display:flex; justify-content:space-between; align-items:center;
                 padding:2px 0; }}
      .fa-lbl {{ color:#bcd; font-size:12px; }}
      .fa-num {{ min-width:24px; text-align:center; color:#10151c;
                 font-weight:800; font-size:12px; border-radius:5px;
                 padding:1px 5px; }}
    </style>
    <div class="fa-grid">{''.join(blocks)}</div>"""


def fm_panel_html(prow: pd.Series) -> str:
    """외야 선수 FM 세부 능력치 패널."""
    return _fm_detail_html(prow, FM_DETAIL)


def fm_gk_panel_html(prow: pd.Series) -> str:
    """GK 세부 능력치 패널."""
    return _fm_detail_html(prow, GK_DETAIL)


def category_avgs(prow: pd.Series, detail: dict) -> list[tuple[str, int]]:
    """대분류별 평균 능력치 → [(카테고리, 1~99), ...]."""
    out = []
    for cat, attrs in detail.items():
        rs = [r for _, cols in attrs if (r := _attr_rating(prow, cols)) is not None]
        if rs:
            out.append((cat, round(sum(rs) / len(rs))))
    return out


# 카테고리별 대표 raw 컬럼(괄호로 실제 수치 병기용) — 가장 상징적인 단일 지표.
CAT_RAW_COL: dict[str, str] = {
    # 외야
    "공격": "npxg_p90", "창조": "xa_p90", "배급": "pass_pct",
    "볼 운반": "successful_dribbles_per90", "수비": "tackles_won_per90",
    "피지컬·듀얼": "aerial_won_pct",
    # GK
    "선방": "gk_save_pct", "무실점": "gk_clean_sheets",
    "박스 지배": "gk_high_claims_per90", "빌드업": "pass_pct",
}


def _fmt_raw(col: str, v) -> str:
    """원본 수치를 컬럼 종류에 맞춰 표시 문자열로."""
    if v is None or pd.isna(v):
        return ""
    c = str(col)
    if "pct" in c:                       # 비율 (%)
        return f"{v:.0f}%"
    if "clean_sheets" in c:              # 클린시트 횟수
        return f"{int(round(v))}회"
    if c.endswith("_p90"):               # xG류 작은 값
        return f"{v:.2f}"
    if c.endswith("_per90"):             # per-90 카운트
        return f"{v:.1f}"
    return f"{v:.1f}"


def radar_html(prow: pd.Series, detail: dict, color: str = "#4d9aff",
               raw_row: pd.Series | None = None) -> str:
    """대분류 평균을 꼭짓점으로 하는 레이더(육각형) 차트 SVG.
    라벨 + 점수 배지가 잘리지 않도록 viewBox 여백을 충분히 둔다.
    raw_row(원본 수치)가 주어지면 카테고리 대표 지표의 실제 값을 괄호로 병기.
    """
    import math
    cats = category_avgs(prow, detail)
    n = len(cats)
    if n < 3:
        return ""
    W, H = 400, 380
    cx, cy, R = W / 2, H / 2, 92      # 중심 / 그리드 반지름
    RING = R + 16                     # 외곽 원(배지가 이 선 위에 얹힘)
    badge_frac = RING / R             # 배지 반지름 비율
    label_frac = badge_frac + 0.36    # 라벨은 배지보다 더 바깥(방사형) → 겹침 없음

    def pt(i: int, frac: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang))

    # 외곽 검은 원 (차트를 감싸는 테두리)
    disk = (f'<circle cx="{cx}" cy="{cy}" r="{RING}" fill="none" '
            f'stroke="#111" stroke-width="2"/>')

    # 배경 그리드(4단계 동심 다각형)
    grid = []
    for g in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, g) for i in range(n)))
        op = ".30" if g == 1.0 else ".14"
        grid.append(f'<polygon points="{pts}" fill="none" '
                    f'stroke="rgba(0,0,0,{op})" stroke-width="1"/>')

    # 축선
    axes = []
    for i in range(n):
        ex, ey = pt(i, 1.0)
        axes.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
                    f'stroke="rgba(0,0,0,.12)" stroke-width="1"/>')

    # 데이터 다각형
    data_pts = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (pt(i, val / 99) for i, (_, val) in enumerate(cats))
    )
    # 데이터 꼭짓점 점
    verts = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" '
        f'stroke="#fff" stroke-width="1"/>'
        for x, y in (pt(i, val / 99) for i, (_, val) in enumerate(cats))
    )

    # 라벨 + 배지 (배지는 외곽 원 위, 라벨은 배지 바깥)
    nodes = []
    for i, (cat, val) in enumerate(cats):
        bx, by = pt(i, badge_frac)         # 배지 중심 = 외곽 원 위
        lx, ly = pt(i, label_frac)         # 라벨 = 더 바깥
        anchor = "middle"
        if lx < cx - 8: anchor = "end"
        elif lx > cx + 8: anchor = "start"
        col = fm_color(val)
        nodes.append(
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="14" fill="{col}" '
            f'stroke="#0d1117" stroke-width="1.5"/>'
            f'<text x="{bx:.1f}" y="{by:.1f}" fill="#0d1117" font-size="13" '
            f'font-weight="800" text-anchor="middle" dominant-baseline="central">{val}</text>'
        )
        # 카테고리 대표 raw 수치 (있으면)
        raw_txt = ""
        if raw_row is not None:
            rc = CAT_RAW_COL.get(cat)
            if rc is not None and rc in raw_row.index:
                raw_txt = _fmt_raw(rc, raw_row.get(rc))
        if raw_txt:
            nodes.append(
                f'<text x="{lx:.1f}" y="{ly-6:.1f}" fill="#111" font-size="12.5" '
                f'font-weight="700" text-anchor="{anchor}" '
                f'dominant-baseline="central">{cat}</text>'
                f'<text x="{lx:.1f}" y="{ly+8:.1f}" fill="#667" font-size="11" '
                f'font-weight="600" text-anchor="{anchor}" '
                f'dominant-baseline="central">{raw_txt}</text>'
            )
        else:
            nodes.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#111" font-size="12.5" '
                f'font-weight="700" text-anchor="{anchor}" '
                f'dominant-baseline="central">{cat}</text>'
            )

    return f"""
    <div style="display:flex; justify-content:center; padding:4px 0 2px;">
      <svg viewBox="0 0 {W} {H}" width="100%" style="max-width:360px;">
        {disk}
        {''.join(grid)}
        {''.join(axes)}
        <polygon points="{data_pts}" fill="{color}38"
                 stroke="{color}" stroke-width="2.5"
                 stroke-linejoin="round"/>
        {verts}
        {''.join(nodes)}
      </svg>
    </div>"""


def line_x(n: int) -> list[float]:
    if n == 1:
        return [50.0]
    return [16 + 68 * i / (n - 1) for i in range(n)]


KIND_COLOR = {"DEF": BAND_DEF, "MID": BAND_MID, "FWD": BAND_FWD, "GK": "#3aa99a"}


def band_color(bi: int, n_bands: int) -> str:
    if bi == 0:
        return "DEF"
    if bi == n_bands - 1:
        return "FWD"
    return "MID"


def _num_str(v) -> str:
    """등번호 값을 표시용 문자열로. 없으면 빈 문자열. '7.0' → '7'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if s in ("", "nan"):
        return ""
    return s[:-2] if s.endswith(".0") else s


def _ga_str(row) -> str:
    """선수 행(Series)에서 '· 2골 1도움' 형태 문자열. 골·도움 0이면 빈 문자열."""
    if row is None:
        return ""
    g = int(row["goals"]) if "goals" in row and pd.notna(row["goals"]) else 0
    a = int(row["assists"]) if "assists" in row and pd.notna(row["assists"]) else 0
    return f" · {g}골 {a}도움" if (g or a) else ""


def mark_team_aces(placements: list[dict], full: pd.DataFrame, top: int = 3) -> None:
    """XI 11명 중 ss_rating 상위 N명에게 ace_rank(1=최고) 부여 — in-place."""
    rated: list[tuple[float, dict]] = []
    for p in placements:
        prow = full[full["player"] == p["full"]]
        if prow.empty:
            continue
        r = prow.iloc[0]
        rating = r.get("ss_rating")
        mins = r.get("minutes", 0)
        # 최소 출전 필터 — 표본 작은 평점은 신뢰 낮음
        if pd.notna(rating) and pd.notna(mins) and mins >= 900:
            rated.append((float(rating), p))
    rated.sort(key=lambda x: x[0], reverse=True)
    for i, (_, p) in enumerate(rated[:top]):
        p["ace_rank"] = i + 1


def placements_from_slots(team: str, slots_df: pd.DataFrame, full: pd.DataFrame,
                          pct: pd.DataFrame, formation: str) -> list[dict] | None:
    """실측 슬롯 → 배치 리스트. 슬롯 데이터 없으면 None."""
    xi = team_xi_from_slots(team, slots_df, formation)
    if xi is None:
        return None
    out = []
    for _, r in xi.iterrows():
        slot = r["slot"]
        x, y = slot_xy(slot, formation)
        disp = display_slot(slot, formation)   # 단일 피벗 3미들의 중앙 CM → DM 표기
        kind = slot_kind(slot)
        norm = r["norm_key"]
        prow = pct[pct["norm_key"] == norm]
        drow = full[full["norm_key"] == norm]
        minutes = int(drow.iloc[0]["minutes"]) if not drow.empty else 0
        if kind == "GK":
            save = drow.iloc[0].get("gk_save_pct") if not drow.empty else None
            chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
            out.append({"name": r["player"].split()[-1], "x": x, "y": y, "kind": "GK",
                        "abbr": "GK", "num": _num_str(r.get("number")),
                        "sid": sofa_photo(r.get("sofa_id")), "tcol": team_color(team),
                        "role": slot, "chip": chip, "minutes": minutes,
                        "full": r["player"], "tip": f"{slot} · {minutes}분 · {chip}"})
        elif not prow.empty:
            prow = prow.iloc[0]
            role, _ = assign_role(prow, position_group(prow["pos"]))
            strengths = top_strengths(prow)
            ga = _ga_str(drow.iloc[0] if not drow.empty else None)
            tip = f"{disp} · {minutes}분{ga}<br>" + "<br>".join(f"{lab} {v}%" for lab, v in strengths)
            out.append({"name": r["player"].split()[-1], "x": x, "y": y, "kind": kind,
                        "abbr": disp, "num": _num_str(r.get("number")),
                        "sid": sofa_photo(r.get("sofa_id")), "tcol": team_color(team),
                        "role": f"{disp} · {role.split(' (')[0]}",
                        "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": minutes, "full": r["player"], "tip": tip})
    return out


def placements_from_bands(bands: list[pd.DataFrame], pct: pd.DataFrame,
                          gk: pd.Series | None, team: str = "") -> list[dict]:
    """휴리스틱 밴드 → 배치 리스트(슬롯 데이터 없는 팀용)."""
    tcol = team_color(team)
    out, n_bands = [], len(bands)
    for bi, band in enumerate(bands):
        band = band.reset_index(drop=True)
        if n_bands <= 1:
            y = 50.0
        else:
            y = BAND_Y_BOTTOM - (BAND_Y_BOTTOM - BAND_Y_TOP) * (bi / (n_bands - 1))
        kind = band_color(bi, n_bands)
        xs = line_x(len(band))
        for i, (_, r) in enumerate(band.iterrows()):
            prow = pct[pct["player"] == r["player"]].iloc[0]
            role, _ = assign_role(prow, position_group(r["pos"]))
            strengths = top_strengths(prow)
            ga = _ga_str(r)
            tip = f"{int(r['minutes'])}분{ga}<br>" + "<br>".join(f"{lab} {v}%" for lab, v in strengths)
            out.append({"name": r["player"].split()[-1], "x": xs[i], "y": y, "kind": kind,
                        "abbr": {"DEF": "DF", "MID": "MF", "FWD": "FW"}.get(kind, ""),
                        "num": "", "sid": "", "tcol": tcol,
                        "role": role.split(" (")[0], "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": int(r["minutes"]), "full": r["player"], "tip": tip})
    if gk is not None:
        save = gk.get("gk_save_pct")
        chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
        out.append({"name": gk["player"].split()[-1], "x": 50, "y": GK_Y, "kind": "GK",
                    "abbr": "GK", "num": "", "sid": "", "tcol": tcol,
                    "role": "골키퍼", "chip": chip, "minutes": int(gk["minutes"]),
                    "full": gk["player"], "tip": f"{int(gk['minutes'])}분 · {chip}"})
    return out


# 라인별 토큰 그라데이션 (밝은→어두운) + 링 색
TOK_GRAD = {
    "GK":  ("#37d6c0", "#1f8e80"),
    "DEF": ("#6fa8ff", "#2e63d6"),
    "MID": ("#ffc24d", "#e08a1e"),
    "FWD": ("#ff7a6e", "#d8362a"),
}


def _pitch_svg() -> str:
    """세로 피치 SVG 배경 — 잔디 줄무늬 + 정규 마킹(viewBox 0 0 100 130)."""
    stripes = "".join(
        f'<rect x="0" y="{i*13}" width="100" height="13" '
        f'fill="{"#2f8a52" if i % 2 == 0 else "#2b8049"}"/>'
        for i in range(10)
    )
    L = 'stroke="rgba(255,255,255,.6)" stroke-width="0.5" fill="none"'
    return f"""
    <svg class="pitch-bg" viewBox="0 0 100 130" preserveAspectRatio="none">
      {stripes}
      <rect x="1.5" y="1.5" width="97" height="127" {L}/>
      <line x1="1.5" y1="65" x2="98.5" y2="65" {L}/>
      <circle cx="50" cy="65" r="9" {L}/>
      <circle cx="50" cy="65" r="0.8" fill="rgba(255,255,255,.6)"/>
      <!-- 상단 골(공격 방향) -->
      <rect x="21" y="1.5" width="58" height="15" {L}/>
      <rect x="37" y="1.5" width="26" height="6" {L}/>
      <rect x="43" y="0" width="14" height="1.5" fill="rgba(255,255,255,.6)"/>
      <circle cx="50" cy="11" r="0.7" fill="rgba(255,255,255,.6)"/>
      <path d="M 39 16.5 A 11 11 0 0 0 61 16.5" {L}/>
      <!-- 하단 골(수비 방향) -->
      <rect x="21" y="113.5" width="58" height="15" {L}/>
      <rect x="37" y="124" width="26" height="6" {L}/>
      <rect x="43" y="128.5" width="14" height="1.5" fill="rgba(255,255,255,.6)"/>
      <circle cx="50" cy="119" r="0.7" fill="rgba(255,255,255,.6)"/>
      <path d="M 39 113.5 A 11 11 0 0 1 61 113.5" {L}/>
      <!-- 코너 아크 -->
      <path d="M 1.5 4 A 2.5 2.5 0 0 0 4 1.5" {L}/>
      <path d="M 96 1.5 A 2.5 2.5 0 0 0 98.5 4" {L}/>
      <path d="M 1.5 126 A 2.5 2.5 0 0 1 4 128.5" {L}/>
      <path d="M 96 128.5 A 2.5 2.5 0 0 1 98.5 126" {L}/>
    </svg>"""


def pitch_html(placements: list[dict]) -> str:
    cards = []
    for p in placements:
        abbr = p.get("abbr", "")
        num = p.get("num", "")
        sid = p.get("sid", "")
        tcol = p.get("tcol", "#444a55")
        ace_rank = int(p.get("ace_rank", 0) or 0)
        num_badge = f'<div class="num">{num}</div>' if num else ""
        # 사진이 있으면 헤드샷(로드 실패 시 onerror로 제거 → 뒤의 유니폼 폴백 노출)
        photo = (f'<img class="photo" src="{sid}" loading="lazy" '
                 f'referrerpolicy="no-referrer" onerror="this.remove()"/>') if sid else ""
        # 에이스 표시 — 토큰 좌상단 코너 배지(등번호와 같은 패턴, layout 영향 없음).
        # 1위=🌟(금색 글로우), 2-3위=⭐
        ace_badge = ""
        ace_cls = ""
        if ace_rank == 1:
            ace_badge = '<div class="ace-mark ace-top">🌟</div>'
            ace_cls = " ace ace-top"
        elif ace_rank in (2, 3):
            ace_badge = '<div class="ace-mark">⭐</div>'
            ace_cls = " ace"
        cards.append(f"""
        <div class="pl{ace_cls}" style="left:{p['x']}%;top:{p['y']}%">
          <div class="tok" style="--tc:{tcol};">
            <span class="abbr">{abbr}</span>{photo}{num_badge}{ace_badge}
          </div>
          <div class="nm">{p['name']}</div>
          <div class="rl">{p['role']}</div>
          <div class="tip"><b>{p['full']}</b><br>{p['tip']}</div>
        </div>""")
    return f"""
    <style>
      .wrap {{ max-width:540px; margin:0 auto; }}
      .pitch {{ position:relative; width:100%; padding-top:130%;
                border-radius:14px; overflow:visible;
                box-shadow:0 8px 24px rgba(0,0,0,.35);
                border:1px solid rgba(255,255,255,.15); }}
      .pitch-bg {{ position:absolute; inset:0; width:100%; height:100%;
                   border-radius:14px; }}
      .pl {{ position:absolute; transform:translate(-50%,-50%); text-align:center;
             width:120px; z-index:2; transition:transform .15s ease; }}
      .pl:hover {{ z-index:9; }}
      .tok {{ position:relative; width:44px; height:44px; margin:0 auto;
              border-radius:50%; border:2.5px solid rgba(255,255,255,.92);
              background:radial-gradient(circle at 35% 28%,rgba(255,255,255,.30),rgba(255,255,255,0) 55%),var(--tc);
              box-shadow:0 3px 8px rgba(0,0,0,.45);
              display:flex; align-items:center; justify-content:center;
              overflow:visible; transition:transform .15s ease; }}
      .abbr {{ color:#fff; font-weight:800; font-size:13px; letter-spacing:.3px;
               text-shadow:0 1px 2px rgba(0,0,0,.55); }}
      .photo {{ position:absolute; inset:0; width:100%; height:100%;
                object-fit:cover; border-radius:50%; background:var(--tc); }}
      .num {{ position:absolute; top:-6px; right:-8px; min-width:18px; height:18px;
              padding:0 3px; background:#10151c; color:#fff; font-size:10px;
              font-weight:800; line-height:18px; border-radius:9px; z-index:3;
              border:1px solid rgba(255,255,255,.35); box-shadow:0 1px 3px rgba(0,0,0,.5); }}
      .nm {{ color:#fff; font-weight:700; font-size:13.5px; margin-top:5px;
             text-shadow:0 1px 3px rgba(0,0,0,.8); }}
      .rl {{ color:#eafff4; font-size:10.5px; opacity:.92; margin-top:1px;
             text-shadow:0 1px 2px rgba(0,0,0,.7); }}
      .tip {{ display:none; position:absolute; left:50%; bottom:112%; transform:translateX(-50%);
              background:rgba(16,21,28,.97); color:#fff; padding:9px 12px; border-radius:10px;
              font-size:12px; white-space:nowrap; z-index:20;
              border:1px solid rgba(255,255,255,.12);
              box-shadow:0 6px 18px rgba(0,0,0,.5); }}
      .pl:hover .tip {{ display:block; }}
      .pl:hover .tok {{ transform:scale(1.15); }}
      /* 팀 에이스 — 토큰 좌상단 코너 배지(등번호와 동일한 패턴). 토큰 layout 영향 없음. */
      .ace .tok {{ border-color:rgba(255,210,74,.95); }}
      .ace-top .tok {{ border-color:#ffd24a;
                       box-shadow:0 0 0 2px rgba(255,210,74,.35),
                                  0 3px 10px rgba(255,180,40,.5),
                                  0 3px 8px rgba(0,0,0,.45); }}
      .ace-mark {{ position:absolute; top:-6px; left:-8px;
                   font-size:13px; line-height:1; z-index:3;
                   filter:drop-shadow(0 1px 2px rgba(0,0,0,.7)); }}
      .ace-mark.ace-top {{ font-size:15px;
                           filter:drop-shadow(0 0 5px rgba(255,210,74,.85))
                                  drop-shadow(0 1px 2px rgba(0,0,0,.7)); }}
    </style>
    <div class="wrap"><div class="pitch">{_pitch_svg()}{''.join(cards)}</div></div>
    """


def _norm(s) -> str:
    return unidecode(str(s)).lower().strip()


# ---------------- UI ----------------
full = load(DATA_PATH.stat().st_mtime).copy()   # mtime 캐시 키 — CSV 교체 시 자동 무효화
full["norm_key"] = full["player"].map(_norm)
df = full[~full["pos"].fillna("").str.contains("GK")]  # 필드플레이어
slots_df = load_slots()
slot_teams = set(slots_df["squad"].unique()) if slots_df is not None else set()
st.title("⚽ Analytics Bot — 포메이션 & 역할 (EPL 2025/26)")

formations_cfg = load_formations()
FORM_OPTIONS = ["4-3-3", "4-2-3-1", "4-4-2", "3-4-3", "3-4-2-1", "3-5-2", "4-1-4-1"]

with st.sidebar:
    st.header("필터")
    teams = sorted(df["squad"].unique())
    default = teams.index("Arsenal") if "Arsenal" in teams else 0
    team = st.selectbox("팀", teams, index=default)

    has_real = team in slot_teams
    forms = team_formations(team, formations_cfg)
    main_form, sub_form = forms["main"], forms["sub"]

    if sub_form:
        # 메인/서브 라디오 토글
        choice = st.radio(
            "포메이션",
            options=["main", "sub"],
            format_func=lambda k: f"메인 ({main_form})" if k == "main" else f"서브 ({sub_form})",
            horizontal=True,
        )
        formation = main_form if choice == "main" else sub_form
        if has_real:
            st.success(f"✅ 실측 라인업 — {formation} ({'메인' if choice == 'main' else '서브'})")
        else:
            st.info(f"ℹ️ 휴리스틱 배치 ({formation})")
    else:
        if has_real:
            st.success(f"✅ 실측 라인업 사용 ({main_form}) — RB/CB/LB 정확")
            formation = main_form
        else:
            st.info(f"ℹ️ 휴리스틱 배치 ({main_form}) — 실측 미수집")
            use_auto = st.checkbox(f"팀 포메이션 사용 ({main_form})", value=True)
            if use_auto:
                formation = main_form
            else:
                idx = FORM_OPTIONS.index(main_form) if main_form in FORM_OPTIONS else 0
                formation = st.selectbox("포메이션 수동 선택", FORM_OPTIONS, index=idx)

    st.caption("실측 슬롯: fetch_lineups.py로 수집 · 포메이션: team_formations.json")

# 백분위 baseline 하한(분). 저출전 선수의 per-90 과대값이 분포를 오염시키지
# 않도록 이 출전시간 이상 선수로만 분포를 만든다(모든 선수는 그 분포에 매겨짐).
# 사용자 조정 슬라이더를 두지 않는 이유: 값을 올리면 실측 XI 선수가 백분위 표에서
# 빠져 보드에서 통째로 사라지는 혼란이 있었음.
BASELINE_MIN = 450

dff = df.reset_index(drop=True)
# goals_per90 / assists_per90 — 유사도 v2 필요 컬럼
_m = dff["minutes"].replace(0, float("nan"))
dff["goals_per90"]   = dff["goals"]   / _m * 90
dff["assists_per90"] = dff["assists"]  / _m * 90
# pos_group: 동일 선수 복수 행에서 가장 공격적 그룹 채택 (MF,FW → FW)
from similar_players import _best_pos_group  # noqa: E402
_pg_map = dff.groupby("player")["pos"].apply(_best_pos_group).to_dict()
dff["pos_group"] = dff["player"].map(_pg_map)
# fine_group: 통계 기반 세부 포지션 (WING_AM / ST / CAM_CM / DM / CB / FB)
dff["fine_group"] = [fine_group(row["pos"], row) for _, row in dff.iterrows()]
pct = league_percentiles(dff, min_minutes=BASELINE_MIN)
pct["norm_key"] = pct["player"].map(_norm)
team_df = dff[dff["squad"] == team]

# GK 별도 풀 — 외야와 percentile 분리(GK끼리 비교)
gk_pool_df = full[full["pos"].fillna("").str.contains("GK")].reset_index(drop=True)
pct_gk = league_percentiles(gk_pool_df, min_minutes=300)
pct_gk["norm_key"] = pct_gk["player"].map(_norm)

# 실측 슬롯이 있으면 정확 배치, 없으면 휴리스틱 밴드
placements = None
if has_real:
    placements = placements_from_slots(team, slots_df, full, pct, formation)
if not placements:
    bands = pick_bands(team_df, formation)
    gk = team_goalkeeper(full, team)
    placements = placements_from_bands(bands, pct, gk, team)

# XI 11명 중 Sofascore 평점 상위 3명에게 ace_rank 부여
mark_team_aces(placements, full)

xi_players = [p["full"] for p in placements if p["kind"] != "GK"]
xi_gk = [p["full"] for p in placements if p["kind"] == "GK"]
xi_all = {p["full"] for p in placements}  # GK 포함 — 벤치 필터링용


def bench_placements(team: str, xi_all: set[str]) -> list[dict]:
    """XI에 없는 선수들 → 벤치 토큰 배치 리스트 (사진 포함)."""
    t = full[full["squad"] == team].copy()
    bench = t[~t["player"].isin(xi_all)].sort_values("minutes", ascending=False)
    if bench.empty:
        return []

    sid_map: dict[str, str] = {}
    num_map: dict[str, str] = {}
    if slots_df is not None:
        sf = slots_df[slots_df["squad"] == team]
        for _, r in sf.iterrows():
            pname = r["player"]
            sid_map[pname] = str(r.get("sofa_id", "") or "")
            num_map[pname] = _num_str(r.get("number", ""))

    tcol = team_color(team)
    out = []
    for _, p in bench.iterrows():
        name = p["player"]
        pos = str(p.get("pos", ""))
        minutes = int(p["minutes"])
        sid = sofa_photo(sid_map.get(name, ""))
        num = num_map.get(name, "")
        g = int(p["goals"]) if "goals" in p and pd.notna(p["goals"]) else 0
        a = int(p["assists"]) if "assists" in p and pd.notna(p["assists"]) else 0
        ga = f"{g}골 {a}도움" if (g or a) else ""

        if "GK" in pos:
            kind, abbr, role = "GK", "GK", "골키퍼"
        else:
            pg = position_group(pos)
            kind = {"FW": "FWD", "MF": "MID", "DF": "DEF"}.get(pg, "MID")
            abbr = pos.split(",")[0].strip()[:3]
            prow_b = pct[pct["norm_key"] == p.get("norm_key", _norm(name))]
            if not prow_b.empty and minutes > 0:
                role_full, _ = assign_role(prow_b.iloc[0], pg)
                role = role_full.split(" (")[0]
            else:
                role = abbr

        tip_parts = [f"{minutes}분"]
        if ga:
            tip_parts.append(ga)
        out.append({
            "name": name.split()[-1], "full": name,
            "kind": kind, "abbr": abbr, "num": num,
            "sid": sid, "tcol": tcol, "role": role,
            "tip": " · ".join(tip_parts), "minutes": minutes,
        })
    return out


def bench_strip_html(subs: list[dict]) -> str:
    """벤치 선수들을 가로 토큰 스트립으로 렌더링."""
    if not subs:
        return "<div style='color:#888;font-size:12px;padding:8px'>벤치 데이터 없음</div>"
    cards = []
    for p in subs:
        abbr = p.get("abbr", "")
        num = p.get("num", "")
        sid = p.get("sid", "")
        tcol = p.get("tcol", "#444a55")
        num_badge = f'<div class="snum">{num}</div>' if num else ""
        photo = (f'<img class="sphoto" src="{sid}" loading="lazy" '
                 f'referrerpolicy="no-referrer" onerror="this.remove()"/>') if sid else ""
        cards.append(f"""
        <div class="sub-pl">
          <div class="stok" style="--tc:{tcol};">
            <span class="sabbr">{abbr}</span>{photo}{num_badge}
          </div>
          <div class="snm">{p['name']}</div>
          <div class="srl">{p['role']}</div>
          <div class="smins">{p['minutes']}분</div>
          <div class="stip"><b>{p['full']}</b><br>{p['tip']}</div>
        </div>""")

    return f"""
    <style>
      .bench-wrap {{ background:rgba(10,20,35,.75); border:1px solid rgba(255,255,255,.1);
                    border-radius:10px; padding:10px 14px 12px; }}
      .bench-title {{ color:#7a8fa6; font-size:10.5px; font-weight:700; margin-bottom:10px;
                      text-transform:uppercase; letter-spacing:1px; }}
      .bench-row {{ display:flex; flex-wrap:wrap; gap:12px 16px; }}
      .sub-pl {{ position:relative; text-align:center; width:68px; cursor:default; }}
      .sub-pl:hover .stip {{ display:block; }}
      .stok {{ position:relative; width:44px; height:44px; margin:0 auto;
               border-radius:50%; border:2.5px solid rgba(255,255,255,.75);
               background:radial-gradient(circle at 35% 28%,rgba(255,255,255,.22),rgba(255,255,255,0) 55%),var(--tc);
               box-shadow:0 2px 8px rgba(0,0,0,.45);
               display:flex; align-items:center; justify-content:center;
               overflow:visible; transition:transform .12s ease; }}
      .sub-pl:hover .stok {{ transform:scale(1.12); }}
      .sabbr {{ color:#fff; font-weight:800; font-size:12px;
                text-shadow:0 1px 2px rgba(0,0,0,.55); }}
      .sphoto {{ position:absolute; inset:0; width:100%; height:100%;
                 object-fit:cover; border-radius:50%; background:var(--tc); }}
      .snum {{ position:absolute; top:-6px; right:-8px; min-width:17px; height:17px;
               padding:0 2px; background:#10151c; color:#fff; font-size:9.5px;
               font-weight:800; line-height:17px; border-radius:9px; z-index:3;
               border:1px solid rgba(255,255,255,.3); }}
      .snm {{ color:#dde; font-weight:600; font-size:11.5px; margin-top:5px;
              white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .srl {{ color:#8ab; font-size:10px; margin-top:2px; }}
      .smins {{ color:#556; font-size:9.5px; margin-top:1px; }}
      .stip {{ display:none; position:absolute; left:50%; bottom:110%; transform:translateX(-50%);
               background:rgba(16,21,28,.97); color:#fff; padding:8px 10px; border-radius:8px;
               font-size:11px; white-space:nowrap; z-index:20;
               border:1px solid rgba(255,255,255,.12); box-shadow:0 4px 12px rgba(0,0,0,.5); }}
    </style>
    <div class="bench-wrap">
      <div class="bench-title">벤치 &amp; 백업 ({len(subs)}명)</div>
      <div class="bench-row">{''.join(cards)}</div>
    </div>
    """


bench_pls = bench_placements(team, xi_all)

# ── 팀 순위 배너 + 강점/약점 ─────────────────────────────────────────────────
_standings = load_standings()
if _standings is not None:
    _srow = _standings[_standings["squad"] == team]
    if not _srow.empty:
        st.components.v1.html(standings_banner_html(_srow.iloc[0]), height=90)

# 팀 특성(리그 20팀 대비 강점 3 / 약점 3)
_traits = team_traits_table(DATA_PATH.stat().st_mtime)
_str, _weak = team_characteristics(team, _traits)
if _str or _weak:
    st.markdown(team_traits_html(_str, _weak), unsafe_allow_html=True)

left, right = st.columns([1.1, 1])
with left:
    src = "실측 라인업" if has_real else "휴리스틱"
    tag = ""
    if sub_form:
        tag = " · 메인" if formation == main_form else " · 서브"
    st.subheader(f"{team} · 주전 XI ({formation}){tag} · {src}")
    st.caption("토큰에 호버하면 강점 지표가 라벨과 함께 표시 · 색=라인(🔴공격 🟠중원 🔵수비 🟢GK)")
    st.components.v1.html(pitch_html(placements), height=720)

    if bench_pls:
        n_rows = max(1, (len(bench_pls) + 5) // 6)
        st.components.v1.html(bench_strip_html(bench_pls), height=62 + n_rows * 112, scrolling=False)

with right:
    st.subheader("선수 상세")
    # 팀 전원 풀 — XI(GK·외야) + 벤치 전원. 중복 제거하고 등장 순서 유지.
    bench_all = [p["full"] for p in bench_pls]
    pool = list(dict.fromkeys(xi_gk + xi_players + bench_all))
    pick = st.selectbox("선수 선택", pool)

    raw_match = full[full["player"] == pick]
    is_gk = (not raw_match.empty) and "GK" in str(raw_match.iloc[0]["pos"])

    # ── GK 분기 — 별도 풀 percentile + GK 카테고리 패널 ──────────────────────
    if is_gk:
        prow_gk = pct_gk[pct_gk["player"] == pick]
        raw = raw_match.iloc[0]
        st.markdown(f"**{pick}** · GK · {int(raw['minutes'])}분")
        if prow_gk.empty:
            st.info("⚠️ GK 지표 데이터 부족 — 300분 미만이면 백분위 분석에서 빠집니다.")
        else:
            badges = compute_player_badges(prow_gk.iloc[0]["norm_key"], pct_gk)
            if badges:
                chips = "".join(
                    f"<span style='display:inline-block; padding:4px 10px; margin:3px 4px 3px 0; "
                    f"background:linear-gradient(135deg,#3a3a3a,#222); color:#fff; "
                    f"border:1px solid rgba(255,255,255,.15); border-radius:14px; "
                    f"font-size:12px; white-space:nowrap;'>"
                    f"{b['tier']} {b['emoji']} {b['label']}</span>"
                    for b in badges
                )
                st.markdown(f"<div style='margin:6px 0 10px;'>{chips}</div>",
                            unsafe_allow_html=True)
            st.markdown("**🧤 GK 능력치 (GK 풀 내 백분위 → 1~99)**")
            st.markdown(fm_gk_panel_html(prow_gk.iloc[0]), unsafe_allow_html=True)
            st.caption("색상: 🟦 85+ 압도적 · 🟩 70+ 강점 · 🟨 50+ 평균 · 🟧 35+ 부족 · 🟥 ~34 약점")
            st.markdown(radar_html(prow_gk.iloc[0], GK_DETAIL, color=team_color(team),
                                   raw_row=raw_match.iloc[0]),
                        unsafe_allow_html=True)
    elif (prow_match := pct[pct["player"] == pick]).empty:
        # 외야 선수인데 데이터 없음 (이름 불일치 등) — 안전 가드
        if not raw_match.empty:
            raw = raw_match.iloc[0]
            st.markdown(f"**{pick}** · {raw['pos']} · {int(raw['minutes'])}분")
        st.info("⚠️ 이 선수의 지표 데이터를 찾을 수 없습니다.")
    else:
        prow = prow_match.iloc[0]
        grp = position_group(prow["pos"])
        role, _ = assign_role(prow, grp)
        raw = dff[dff["player"] == pick].iloc[0]
        st.markdown(f"**{pick}** · {raw['pos']} · {int(raw['minutes'])}분 → **{role}**")

        # 시즌 누적 — 골/어시/출전경기 (Understat 기준, goals=페널티 포함)
        g = int(raw["goals"]) if "goals" in raw and pd.notna(raw["goals"]) else 0
        a = int(raw["assists"]) if "assists" in raw and pd.notna(raw["assists"]) else 0
        cg, ca = st.columns(2)
        cg.metric("⚽ 골", g)
        ca.metric("🅰️ 도움", a)

        badges = compute_player_badges(prow["norm_key"], pct)
        if badges:
            chips = "".join(
                f"<span style='display:inline-block; padding:4px 10px; margin:3px 4px 3px 0; "
                f"background:linear-gradient(135deg,#3a3a3a,#222); color:#fff; "
                f"border:1px solid rgba(255,255,255,.15); border-radius:14px; "
                f"font-size:12px; white-space:nowrap;'>"
                f"{b['tier']} {b['emoji']} {b['label']}</span>"
                for b in badges
            )
            st.markdown(f"<div style='margin:6px 0 10px;'>{chips}</div>",
                        unsafe_allow_html=True)

        st.markdown("**🎯 능력치 (리그 내 백분위 → 1~99)**")
        st.markdown(fm_panel_html(prow), unsafe_allow_html=True)
        st.caption("색상: 🟦 85+ 압도적 · 🟩 70+ 강점 · 🟨 50+ 평균 · 🟧 35+ 부족 · 🟥 ~34 약점")
        st.markdown(radar_html(prow, FM_DETAIL, color=team_color(team), raw_row=raw),
                    unsafe_allow_html=True)

        # 기준 선수 fine_group 표시
        _pick_row = dff[dff["player"].str.lower() == pick.lower()]
        if _pick_row.empty:
            _pick_row = dff[dff["player"].str.lower().str.contains(pick.lower())]
        _fine = _pick_row.iloc[0]["fine_group"] if not _pick_row.empty else grp
        same_pos = st.checkbox(
            f"같은 세부 포지션 비교 (현재: **{_fine}**)", value=True,
            help="WING_AM=윙어·공격형미드 / ST=스트라이커 / CAM_CM=공격형MF / DM=수비형MF / CB / FB"
        )
        alpha = st.slider("스타일 ↔ 퍼포먼스 비중", 0.3, 0.9, 0.65, 0.05,
                          help="높을수록 스타일 우선 · 낮을수록 이번 시즌 퍼포먼스 우선")
        st.markdown("**비슷한 선수 (리그 전체)**")
        emb = build_embeddings(dff)
        sim = find_similar(dff, emb, pick, top=5, same_position=same_pos, alpha=alpha)
        sim_show = sim[["player", "squad", "pos", "fine_group", "style_sim", "perf_score", "score"]].copy()
        sim_show.columns = ["선수", "팀", "포지션", "역할", "스타일", "퍼포먼스", "종합"]
        for col in ["스타일", "퍼포먼스", "종합"]:
            sim_show[col] = (sim_show[col] * 100).round(1).astype(str) + "%"
        st.dataframe(sim_show, hide_index=True, use_container_width=True)

# ── 시즌 전적 테이블 ────────────────────────────────────────────────────────
SCHEDULE_PATH = Path(__file__).resolve().parent / "data" / "schedule_2025_2026.csv"


@st.cache_data
def load_schedule() -> pd.DataFrame | None:
    if not SCHEDULE_PATH.exists():
        return None
    return pd.read_csv(SCHEDULE_PATH)


_schedule = load_schedule()
if _schedule is not None:
    team_sched = _schedule[_schedule["squad"] == team].sort_values("gw").copy()
    if not team_sched.empty:
        st.markdown("---")
        st.subheader(f"{team} — 2025/26 시즌 전적 ({len(team_sched)}경기)")

        def _result_badge(res: str) -> str:
            color = {"W": "#2e7d32", "D": "#888", "L": "#b71c1c"}.get(res, "#555")
            label = {"W": "승", "D": "무", "L": "패"}.get(res, res)
            return (f"<span style='display:inline-block;width:28px;text-align:center;"
                    f"background:{color};color:#fff;border-radius:4px;"
                    f"font-size:12px;font-weight:700;padding:1px 0'>{label}</span>")

        def _ha_badge(ha: str) -> str:
            color = "#1565c0" if ha == "H" else "#4a148c"
            label = "홈" if ha == "H" else "원정"
            return (f"<span style='display:inline-block;width:36px;text-align:center;"
                    f"background:{color};color:#fff;border-radius:4px;"
                    f"font-size:11px;padding:1px 0'>{label}</span>")

        rows_html = ""
        for _, r in team_sched.iterrows():
            result_badge = _result_badge(r["result"])
            ha_badge = _ha_badge(r["home_away"])
            score_color = ("#4caf50" if r["result"] == "W"
                           else "#ef9a9a" if r["result"] == "L" else "#aaa")
            rows_html += (
                f"<tr>"
                f"<td style='text-align:center;color:#aaa'>{int(r['gw'])}</td>"
                f"<td style='color:#111'>{r['date']}</td>"
                f"<td>{ha_badge}</td>"
                f"<td style='font-weight:600;color:#111'>{r['opponent']}</td>"
                f"<td style='text-align:center;font-weight:700;font-size:15px;"
                f"color:{score_color}'>{r['score']}</td>"
                f"<td style='text-align:center'>{result_badge}</td>"
                f"</tr>"
            )

        table_html = f"""
        <style>
          .match-table {{ width:100%; border-collapse:collapse; font-family:sans-serif;
                         font-size:13px; color:#eee; }}
          .match-table th {{ background:#1e2a38; color:#aaa; font-weight:600;
                             padding:7px 10px; text-align:left; border-bottom:1px solid #333; }}
          .match-table td {{ padding:6px 10px; border-bottom:1px solid #1e1e1e; }}
          .match-table tr:hover td {{ background:rgba(255,255,255,.04); }}
        </style>
        <table class="match-table">
          <thead><tr>
            <th style="text-align:center">GW</th>
            <th>날짜</th>
            <th>H/A</th>
            <th>상대팀</th>
            <th style="text-align:center">스코어</th>
            <th style="text-align:center">결과</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
        """
        st.components.v1.html(table_html, height=min(38 * 34 + 60, 900), scrolling=True)

st.caption(
    "데이터: FBref + Understat(xG·골·도움) + Sofascore(라인업·고급지표) 2025/26 · "
    "역할=리그 백분위 기반 아키타입 매칭 · 골/도움=시즌 누적 · 시뮬레이션 아님"
)
