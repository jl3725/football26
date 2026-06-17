"""
Streamlit 프론트엔드 — 팀 포메이션 보드 + 선수 역할/프로필 + 비슷한 선수.

실행:
    streamlit run app.py

좌측에서 팀/포메이션을 고르면 피치 위에 주전 XI 가 배치되고,
각 선수 토큰에 호버하면 강점 지표가 '라벨'과 함께 보인다(숫자만 X).
아래에서 선수를 고르면 10개 지표 백분위 막대 + 스타일 유사 선수를 보여준다.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from similar_players import FEATURES, DATA_PATH, build_embeddings, find_similar, fine_group  # noqa: E402  # fine_group kept for fallback
from team_analysis import (  # noqa: E402
    league_percentiles, assign_role, position_group,
    pick_bands, team_formations, team_goalkeeper, load_formations,
    load_slots, team_xi_from_slots, slot_xy, slot_kind, display_slot,
    formation_slots, espn_assign_slots,
    compute_player_badges,
    GK_Y, BAND_Y_TOP, BAND_Y_BOTTOM,
)

# UI modules — split so agents can target specific tabs clearly
from src.ui.analytics import analytics_dashboard_html  # Analytics tab only lives here
from src.ui.common import (  # noqa: E402
    ACCENT, LABELS, BAND_DEF, BAND_MID, BAND_FWD,
    TEAM_COLOR, TEAM_EXTRA, team_color, team_logo,
    sofa_photo, _photo, avatar, portrait_photo, fmt_value,
    nation_code, flag_chip, fee_label, _num_str, _ga_str, _norm,
    _grid, _iframe, sec_title, _form_dots_html, _progress_bar_html,
    rating_color, pos_chip_color,
)
from src.ui.metrics import (  # noqa: E402
    fm_rating, fm_color, ovr_from_rating, ovr_from_value, perf_ovr, player_ovr,
    _series_pct, goalkeeper_ovr, season_achievement_bonus, top_strengths,
    _rank_pct, _blend_pcts, _blend_scores, _pct_to_rating,
    _power_from_pct, _power_from_index,
)
from src.ui.overview import (  # noqa: E402
    TEAM_INFO, TEAM_TRAITS, _competition_label, _cup_stage,
    competition_results_html, team_info_html, team_logo_box,
    overview_scout_dossier_html, team_ratings,
    donut_card_html, stat_card_html, manager_profile_html,
    team_snapshot_html, set_piece_discipline_html,
    team_radar_html, ai_scout_report_html, team_tactical_styles, team_improvements,
    form_block_html, xg_block_html, squad_profile_html, team_leaders, leader_card_html,
    team_characteristics, team_traits_html, standings_banner_html,
)
from src.ui.player import (  # noqa: E402
    db_player_card_html, player_picker_card_html, selected_player_spotlight_html,
    fm_panel_html, fm_gk_panel_html, radar_html, category_avgs,
    FM_DETAIL, GK_DETAIL, CAT_RAW_COL,
)
from src.ui.pitch import (  # noqa: E402
    team_star_players, star_card_html, squad_depth_html, mark_team_aces,
    placements_from_slots, placements_from_espn, placements_from_bands, espn_main_xi,
    pitch_html, bench_placements, departed_placements, bench_strip_html,
)
from src.ui.transfers import (  # noqa: E402
    transfer_side_html, recommend_signings, signing_card_html,
)

# LABELS, BAND_*, TEAM_COLOR/EXTRA, 저수준 헬퍼는 src/ui/common.py로 이동(상단 import)

MANAGER_PROFILES = {
    "Arsenal": {
        "name": "Mikel Arteta", "nationality": "Spain", "appointed": "Dec 2019",
        "style": "Control + high press", "formation": "4-3-3",
        "focus": "possession dominance, positional rotations, set-piece edge",
    },
    "Aston Villa": {
        "name": "Unai Emery", "nationality": "Spain", "appointed": "Nov 2022",
        "style": "Structured transition", "formation": "4-2-3-1",
        "focus": "compact block, wide overloads, knockout-game detail",
    },
    "Bournemouth": {
        "name": "Andoni Iraola", "nationality": "Spain", "appointed": "Jun 2023",
        "style": "Aggressive press", "formation": "4-2-3-1",
        "focus": "front-foot defending, vertical attacks, second balls",
    },
    "Brentford": {
        "name": "Keith Andrews", "nationality": "Ireland", "appointed": "Jun 2025",
        "style": "Direct + set plays", "formation": "4-2-3-1",
        "focus": "compact spacing, restarts, fast wide service",
    },
    "Brighton": {
        "name": "Fabian Hurzeler", "nationality": "Germany", "appointed": "Jun 2024",
        "style": "Build-up control", "formation": "4-2-3-1",
        "focus": "press resistance, rotations, young-player development",
    },
    "Burnley": {
        "name": "Scott Parker", "nationality": "England", "appointed": "Jul 2024",
        "style": "Organised possession", "formation": "4-2-3-1",
        "focus": "defensive structure, controlled build-up, wide progression",
    },
    "Chelsea": {
        "name": "Enzo Maresca", "nationality": "Italy", "appointed": "Jun 2024",
        "style": "Positional play", "formation": "4-2-3-1",
        "focus": "inverted full-back build-up, central overloads, ball security",
    },
    "Crystal Palace": {
        "name": "Oliver Glasner", "nationality": "Austria", "appointed": "Feb 2024",
        "style": "Back-three transition", "formation": "3-4-2-1",
        "focus": "mid-block traps, wing-back thrust, fast attacks",
    },
    "Everton": {
        "name": "David Moyes", "nationality": "Scotland", "appointed": "Jan 2025",
        "style": "Compact + pragmatic", "formation": "4-2-3-1",
        "focus": "box defence, set pieces, direct chance creation",
    },
    "Fulham": {
        "name": "Marco Silva", "nationality": "Portugal", "appointed": "Jul 2021",
        "style": "Balanced possession", "formation": "4-2-3-1",
        "focus": "wide combinations, quick switches, disciplined rest defence",
    },
    "Leeds United": {
        "name": "Daniel Farke", "nationality": "Germany", "appointed": "Jul 2023",
        "style": "Possession build-up", "formation": "4-2-3-1",
        "focus": "patient circulation, full-back width, central runners",
    },
    "Liverpool": {
        "name": "Arne Slot", "nationality": "Netherlands", "appointed": "Jun 2024",
        "style": "High-tempo control", "formation": "4-2-3-1",
        "focus": "counter-pressing, rotations, quick central combinations",
    },
    "Manchester City": {
        "name": "Pep Guardiola", "nationality": "Spain", "appointed": "Jul 2016",
        "style": "Positional dominance", "formation": "4-3-3",
        "focus": "territorial control, chance suppression, overload creation",
    },
    "Manchester Utd": {
        "name": "Ruben Amorim", "nationality": "Portugal", "appointed": "Nov 2024",
        "style": "Back-three press", "formation": "3-4-2-1",
        "focus": "high pressing, wing-back width, vertical combinations",
    },
    "Newcastle United": {
        "name": "Eddie Howe", "nationality": "England", "appointed": "Nov 2021",
        "style": "Intensity football", "formation": "4-3-3",
        "focus": "pressing volume, wide attacks, aggressive midfield duels",
    },
    "Nottingham Forest": {
        "name": "Sean Dyche", "nationality": "England", "appointed": "Oct 2025",
        "style": "Compact directness", "formation": "4-4-2",
        "focus": "defensive distances, aerial pressure, early forward play",
    },
    "Sunderland": {
        "name": "Regis Le Bris", "nationality": "France", "appointed": "Jun 2024",
        "style": "Young + energetic", "formation": "4-2-3-1",
        "focus": "player development, pressing triggers, quick wide attacks",
    },
    "Tottenham Hotspur": {
        "name": "Thomas Frank", "nationality": "Denmark", "appointed": "Jun 2025",
        "style": "Flexible pressing", "formation": "4-3-3",
        "focus": "set plays, direct attacks, adaptable defensive blocks",
    },
    "West Ham United": {
        "name": "Nuno Espirito Santo", "nationality": "Portugal", "appointed": "Sep 2025",
        "style": "Transition block", "formation": "3-4-2-1",
        "focus": "compact defending, fast counters, wing-back outlets",
    },
    "Wolves": {
        "name": "Rob Edwards", "nationality": "England", "appointed": "Nov 2025",
        "style": "Back-three intensity", "formation": "3-4-2-1",
        "focus": "defensive organisation, wing-back runs, transition attacks",
    },
}

MANAGER_PROFILES_PATH = Path(__file__).resolve().parent / "data" / "manager_profiles_2025_2026.json"
TEAM_UNIT_METRICS_PATH = Path(__file__).resolve().parent / "data" / "team_unit_metrics_2025_2026.csv"
STATBUNKER_TEAM_STATS_PATH = Path(__file__).resolve().parent / "data" / "statbunker_team_stats_2025_2026.csv"


@st.cache_data
def load_manager_profiles(_mtime: float = 0.0) -> dict:
    profiles = dict(MANAGER_PROFILES)
    if not MANAGER_PROFILES_PATH.exists():
        return profiles
    try:
        with MANAGER_PROFILES_PATH.open("r", encoding="utf-8") as f:
            file_profiles = json.load(f)
    except (OSError, json.JSONDecodeError):
        return profiles
    for team, profile in file_profiles.items():
        base = profiles.get(team, {}).copy()
        base.update(profile)
        profiles[team] = base
    return profiles


@st.cache_data
def load_team_unit_metrics(_file_key: tuple[int, int] = (0, 0)) -> pd.DataFrame | None:
    if not TEAM_UNIT_METRICS_PATH.exists():
        return None
    return pd.read_csv(TEAM_UNIT_METRICS_PATH).set_index("squad")


@st.cache_data
def load_statbunker_team_stats(_file_key: tuple[int, int] = (0, 0)) -> pd.DataFrame | None:
    if not STATBUNKER_TEAM_STATS_PATH.exists():
        return None
    return pd.read_csv(STATBUNKER_TEAM_STATS_PATH).set_index("squad")


def file_cache_key(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


# team_color / team_logo now from src/ui/common.py


# 구단 정보 — verein id(로고용) + 연고지/홈구장/창단/별명/한줄 설명 (EPL 25/26)
# moved to src/ui/overview.py: TEAM_INFO, team_logo_box, competition_results_html, team_info_html, _competition_label, _cup_stage
# (+ NATION_CODE/NATION_ISO) → src/ui/common.py 로 이동(상단 import)


# moved to src/ui/transfers.py: transfer_side_html


st.set_page_config(
    page_title="SCOUT.AI — EPL 25/26",
    page_icon="⚽",
    layout="wide",
)


# ── 전역 셸 테마 (Figma Football AI SCOUT: 밝은 메인 + 다크 사이드바 + 레드 액센트) ──
# config.toml의 [theme]가 라이트 베이스를, 아래 CSS가 다크 사이드바·흰 카드·타이포를 담당.
# 기존 커스텀 HTML(피치·FM패널·배너 등)은 components.html(iframe) 안에서 자체
# 다크 스타일로 렌더되어 라이트 메인 위에 '다크 카드'처럼 보인다(레퍼런스 피치와 동일).
SHELL_CSS = f"""
<style>
  :root {{
    --bg:#eef1f6; --card:#ffffff; --card-br:#e4e8f0;
    --accent:{ACCENT}; --txt:#1a1f2e; --muted:#8a93a5;
    --side:#0c1322; --side-2:#0f1830; --side-txt:#cfd6e4; --side-muted:#6b7689;
  }}
  /* 메인 배경 — 아주 옅은 그레이 */
  .stApp {{ background:var(--bg); }}
  [data-testid="stHeader"] {{ background:transparent; }}
  .block-container {{ padding-top:2rem; padding-bottom:3rem; max-width:1480px; }}

  /* 타이틀/서브헤더 — 좌측 레드 바 악센트는 .sec-title 헬퍼로 별도 제공 */
  h1, h2, h3 {{ color:var(--txt) !important; font-weight:800 !important; letter-spacing:-.4px; }}
  [data-testid="stCaptionContainer"] {{ color:var(--muted) !important; }}

  /* ── 다크 사이드바 ─────────────────────────────────────────── */
  section[data-testid="stSidebar"] {{
    background:var(--side);
    border-right:1px solid rgba(255,255,255,.06);
  }}
  section[data-testid="stSidebar"] * {{ color:var(--side-txt); }}
  section[data-testid="stSidebar"] [data-testid="stHeading"] h2,
  section[data-testid="stSidebar"] h2 {{
    font-size:11px !important; font-weight:800 !important;
    text-transform:uppercase; letter-spacing:1.5px; color:var(--side-muted) !important;
  }}
  section[data-testid="stSidebar"] label {{ color:var(--side-muted) !important; }}
  /* 사이드바 입력 필드 — 다크 */
  section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
    background:var(--side-2) !important; border:1px solid rgba(255,255,255,.1) !important;
    border-radius:9px !important; color:var(--side-txt) !important;
  }}

  /* ── 메인 위젯 (라이트) ─────────────────────────────────────── */
  /* selectbox 등 입력 — 흰 필드 */
  div[data-baseweb="select"] > div {{
    background:#fff !important; border:1px solid var(--card-br) !important;
    border-radius:9px !important;
  }}
  [data-testid="stSlider"] [role="slider"] {{ background:var(--accent) !important; }}

  /* st.metric → 흰 카드 + 소프트 섀도 */
  [data-testid="stMetric"] {{
    background:var(--card); border:1px solid var(--card-br);
    border-radius:14px; padding:16px 18px;
    box-shadow:0 1px 3px rgba(16,24,40,.04), 0 4px 16px rgba(16,24,40,.04);
  }}
  [data-testid="stMetricLabel"] {{ color:var(--muted) !important;
    text-transform:uppercase; letter-spacing:.5px; font-size:11px !important; }}
  [data-testid="stMetricValue"] {{ color:var(--txt) !important; font-weight:800; }}

  /* 탭 — 언더라인형, 액티브=레드 */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap:8px; border-bottom:1px solid var(--card-br); }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{ font-weight:700; color:var(--muted); }}
  [data-testid="stTabs"] [aria-selected="true"] {{ color:var(--accent) !important; }}
  [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background:var(--accent) !important; }}

  [data-testid="stDataFrame"] {{ border-radius:12px; overflow:hidden;
    border:1px solid var(--card-br); }}
  hr {{ border-color:var(--card-br) !important; }}
</style>
"""
st.markdown(SHELL_CSS, unsafe_allow_html=True)


# sec_title → src/ui/common.py (상단 import)


# ── 브랜딩 — 사이드바 로고 + 메인 팀 배지 헤더 (Figma 상단바 느낌) ─────────────
BRAND_HTML = """
<div style="display:flex;align-items:center;gap:11px;padding:2px 2px 14px;
            border-bottom:1px solid rgba(255,255,255,.08);margin-bottom:8px">
  <div style="width:38px;height:38px;border-radius:10px;flex:none;
              background:linear-gradient(135deg,#ff5b6b,#e8344e);
              display:flex;align-items:center;justify-content:center;
              box-shadow:0 4px 12px rgba(232,52,78,.45)">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2">
      <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/>
      <circle cx="12" cy="12" r="1.3" fill="#fff" stroke="none"/>
    </svg>
  </div>
  <div style="line-height:1.15">
    <div style="font-size:17px;font-weight:800;color:#fff;letter-spacing:-.3px">Football</div>
    <div style="font-size:10px;font-weight:800;color:#ff5b6b;letter-spacing:2px">AI SCOUT</div>
  </div>
</div>
"""


def team_header_html(team: str) -> str:
    """메인 상단 팀 배지 헤더 — 구단 크레스트 로고 + 팀명 + 리그·시즌."""
    return f"""
    <div style="display:flex;align-items:center;gap:14px;margin:-6px 0 18px">
      {team_logo_box(team, 44, 52)}
      <div>
        <div style="font-size:23px;font-weight:800;color:#1a1f2e;letter-spacing:-.5px">{team}</div>
        <div style="font-size:13px;color:#8a93a5">Premier League · 2025/26</div>
      </div>
    </div>"""


# moved to src/ui/transfers.py: FIT_FEATURES, TRAIT_TO_COLS, FIT_LABEL, _team_style_vector, recommend_signings, signing_card_html

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
# TEAM_TRAITS moved to src/ui/overview.py (imported below for team_traits_table)


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


# moved to src/ui/overview.py: team_characteristics, team_traits_html, standings_banner_html
# top_strengths → src/ui/metrics.py (상단 import)


# moved to src/ui/player.py: FM_DETAIL, GK_DETAIL, _attr_rating, _fm_detail_html, fm_panel_html, fm_gk_panel_html, category_avgs, CAT_RAW_COL, _fmt_raw, radar_html
# moved to src/ui/pitch.py: line_x, band_color(+KIND_COLOR), mark_team_aces, placements_from_slots/espn/bands, _match_db_row, espn_main_xi, _pitch_svg, pitch_html(+TOK_GRAD)
# _norm → src/ui/common.py (상단 import)


# ---------------- UI ----------------
full = load(DATA_PATH.stat().st_mtime).copy()   # mtime 캐시 키 — CSV 교체 시 자동 무효화
full["norm_key"] = full["player"].map(_norm)
df = full[~full["pos"].fillna("").str.contains("GK")]  # 필드플레이어
slots_df = load_slots()
slot_teams = set(slots_df["squad"].unique()) if slots_df is not None else set()

formations_cfg = load_formations()
FORM_OPTIONS = ["4-3-3", "4-2-3-1", "4-4-2", "3-4-3", "3-4-2-1", "3-5-2", "4-1-4-1"]

# 사이드바 네비 메뉴 (레퍼런스 좌측 네비) — 라디오를 nav 항목 스타일로 CSS 변환.
# Formation은 Team Overview에 통합(레퍼런스 Team Overview 구성).
NAV = ["⚡ Team Overview", "📊 Analytics", "👤 Player Detail",
       "📋 Squad Depth", "🔁 Transfer", "📅 Schedule", "🔎 Player Database"]
# nav 라디오에만 적용되도록 key("nav_menu") 컨테이너로 스코프 한정
# → 포메이션 main/sub 라디오는 영향받지 않음.
NAV_CSS = """
<style>
  .st-key-nav_menu [role="radiogroup"]{gap:2px;}
  .st-key-nav_menu [role="radiogroup"] label{
    display:flex;align-items:center;width:100%;padding:9px 12px;margin:0;
    border-radius:9px;cursor:pointer;transition:background .12s;}
  .st-key-nav_menu [role="radiogroup"] label:hover{background:rgba(255,255,255,.06);}
  /* 라디오 동그라미 숨김 → 순수 nav 항목처럼 */
  .st-key-nav_menu [role="radiogroup"] label > div:first-child{display:none;}
  .st-key-nav_menu [role="radiogroup"] label p{
    color:#cfd6e4 !important;font-size:14px;font-weight:600;}
  .st-key-nav_menu [role="radiogroup"] label:has(input:checked){
    background:rgba(232,52,78,.16);}
  .st-key-nav_menu [role="radiogroup"] label:has(input:checked) p{
    color:#ff5b6b !important;font-weight:800;}
  .side-label{font-size:11px;font-weight:800;color:#6b7689;letter-spacing:1.5px;margin:4px 0 4px;}
</style>
"""

with st.sidebar:
    st.markdown(BRAND_HTML, unsafe_allow_html=True)
    st.markdown(NAV_CSS, unsafe_allow_html=True)
    st.header("필터")
    teams = sorted(df["squad"].unique())
    default = teams.index("Arsenal") if "Arsenal" in teams else 0
    team = st.selectbox("팀", teams, index=default)

    # 포메이션은 ESPN 실측 라인업에서 자동 도출 (사이드바 수동 선택 제거)
    has_real = team in slot_teams
    forms = team_formations(team, formations_cfg)
    main_form, sub_form = forms["main"], forms["sub"]

    # ── 메뉴 (필터 아래에 배치) ──────────────────────────────────────────────
    st.markdown("<div style='border-bottom:1px solid rgba(255,255,255,.08);margin:16px 0 12px'></div>",
                unsafe_allow_html=True)
    st.markdown("<div class='side-label'>MENU</div>", unsafe_allow_html=True)
    _nav = st.radio("nav", NAV, label_visibility="collapsed", key="nav_menu")

# 메인 상단 팀 배지 헤더 (사이드바에서 team 확정 후 렌더) — 로고 <img> 확실히 뜨도록 iframe
_iframe(team_header_html(team), height=72)

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
# fl_group: FL 실측 포지션 그룹 (W / ST / CM / DM / CB / FB / GK)
# fl_group이 없는 선수(미출전·신규)는 fine_group 통계 추정으로 폴백
if "fl_group" not in dff.columns or dff["fl_group"].isna().all():
    dff["fl_group"] = [fine_group(row["pos"], row) for _, row in dff.iterrows()]
else:
    missing = dff["fl_group"].isna() | (dff["fl_group"] == "")
    dff.loc[missing, "fl_group"] = [fine_group(r["pos"], r) for _, r in dff[missing].iterrows()]
pct = league_percentiles(dff, min_minutes=BASELINE_MIN)
pct["norm_key"] = pct["player"].map(_norm)
team_df = dff[dff["squad"] == team]

# 시즌 중 이적해 이 팀을 떠난 선수(left_for 기록) → XI·벤치에서 제외하고 별도 표기.
# 해당 선수는 새 소속 팀(left_for="")에서 정상적으로 노출됨.
left_out: dict[str, str] = {}
if "left_for" in full.columns:
    for _, _r in full[full["squad"] == team].iterrows():
        _lf = _r.get("left_for")
        if pd.notna(_lf) and str(_lf).strip():
            left_out[_r["player"]] = str(_lf).strip()
if left_out:
    team_df = team_df[~team_df["player"].isin(left_out)]

# GK 별도 풀 — 외야와 percentile 분리(GK끼리 비교)
gk_pool_df = full[full["pos"].fillna("").str.contains("GK")].reset_index(drop=True)
pct_gk = league_percentiles(gk_pool_df, min_minutes=300)
pct_gk["norm_key"] = pct_gk["player"].map(_norm)

# 포메이션 & XI 배치 — ESPN 실측(주 포메이션의 최근 경기 XI) 우선, 없으면 슬롯/휴리스틱
formation = main_form   # 기본값 (ESPN 있으면 덮어씀)
_espn_lu_path = Path(__file__).resolve().parent / "data" / "espn_lineups_2025_2026.csv"
try:
    _espn_all = pd.read_csv(_espn_lu_path) if _espn_lu_path.exists() else None
    if _espn_all is not None:
        _espn_all["event_id"] = _espn_all["event_id"].astype(str)
        _espn_all["date"] = _espn_all["date"].astype(str)
except Exception:
    _espn_all = None

placements = None
_espn_form, _espn_rows = espn_main_xi(team, _espn_all)
if _espn_form and _espn_rows:
    formation = _espn_form
    placements = placements_from_espn(team, _espn_rows, formation, full, pct)
    _form_source = "ESPN 실측"
elif has_real:
    placements = placements_from_slots(team, slots_df, full, pct, formation)
    _form_source = "실측 슬롯"
else:
    _form_source = "휴리스틱"
if not placements:
    bands = pick_bands(team_df, formation)
    gk = team_goalkeeper(full, team)
    placements = placements_from_bands(bands, pct, gk, team)

# 떠난 선수가 실측 슬롯 XI에 남아 있으면 제거(전술판에서 빠짐)
if left_out and placements:
    placements = [p for p in placements if p["full"] not in left_out]

# XI 11명 중 Sofascore 평점 상위 3명에게 ace_rank 부여
mark_team_aces(placements, full)

xi_players = [p["full"] for p in placements if p["kind"] != "GK"]
xi_gk = [p["full"] for p in placements if p["kind"] == "GK"]
xi_all = {p["full"] for p in placements}  # GK 포함 — 벤치 필터링용


# moved to src/ui/pitch.py: bench_placements, departed_placements, bench_strip_html

bench_pls = bench_placements(team, xi_all, full, slots_df, pct, left_out)
departed_pls = departed_placements(team, full, left_out)

# ── 공통 계산 (탭 렌더 전) ────────────────────────────────────────────────────
_standings = load_standings()
_traits = team_traits_table(DATA_PATH.stat().st_mtime)
_statbunker_team_stats = load_statbunker_team_stats(file_cache_key(STATBUNKER_TEAM_STATS_PATH))
_unit_metrics = load_team_unit_metrics(file_cache_key(TEAM_UNIT_METRICS_PATH))
_str, _weak = team_characteristics(team, _traits)     # _weak: Transfer 탭에서 재사용
_fine_map = dict(zip(dff["player"], dff["fl_group"]))


def _norm_slot_pos(slot: str) -> str:
    s = str(slot or "").strip().upper()
    return {
        "LCM": "CM", "RCM": "CM",
        "LDM": "DM", "RDM": "DM",
        "CAM": "AM",
        "LCB": "CB", "RCB": "CB",
        "RWB": "RB", "LWB": "LB",
    }.get(s, s)


def _build_display_pos_map(slots: pd.DataFrame | None, roster: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    if slots is not None and not slots.empty:
        for player, rows in slots.groupby("player"):
            counts: dict[str, float] = {}
            for _, r in rows.iterrows():
                pos = _norm_slot_pos(r.get("slot", ""))
                if not pos or pos == "NAN":
                    continue
                counts[pos] = counts.get(pos, 0.0) + float(r.get("apps") or 0)
            if counts:
                ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
                total = sum(v for _, v in ranked) or 1.0
                if ranked[0][1] / total >= 0.55 or len(ranked) == 1:
                    out[player] = ranked[0][0]
                else:
                    out[player] = "/".join(pos for pos, _ in ranked[:2])

    for _, row in roster.iterrows():
        player = row.get("player")
        if not player or player in out:
            continue
        vals = []
        for col in ["fl_pos", "fl_pos2"]:
            v = row.get(col)
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan":
                vals.append(_norm_slot_pos(str(v)))
        if not vals:
            b = str(row.get("fl_group") or "").strip().upper()
            if b and b != "NAN":
                vals.append(_norm_slot_pos(b))
        if not vals:
            pos = str(row.get("pos") or "").strip().upper()
            if "GK" in pos:
                vals.append("GK")
            elif "FW" in pos:
                vals.append("FW")
            elif "MF" in pos:
                vals.append("MF")
            elif "DF" in pos:
                vals.append("DF")
        clean = []
        for v in vals:
            if v and v != "NAN" and v not in clean:
                clean.append(v)
        if clean:
            out[player] = "/".join(clean[:2])
    return out


_display_pos_map = _build_display_pos_map(slots_df, dff)
_sid_all = {}
if slots_df is not None:
    for _, _r in slots_df.iterrows():
        _sid_all[_r["player"]] = str(_r.get("sofa_id", "") or "")
_raw_rating = dict(zip(full["player"], full["ss_rating"]))
# 통합 OVR(시장가치 기반 + 폼 보정) — 전 섹션 공통 사용.
# 시즌 중 이적 선수는 행이 여러 개다. left_for가 비어있는 현재 소속 행을 먼저
# 대표로 쓰고, 그다음 시장가치/출전시간으로 정렬한다.
_rep = (full.assign(
            _current=full.get("left_for", pd.Series(index=full.index, dtype=object)).isna(),
            _mv=full["market_value_eur"].notna(),
        )
        .sort_values(["_current", "_mv", "minutes"], ascending=[False, False, False])
        .drop_duplicates("player"))
_gk_ovr_pool = _rep[_rep["pos"].fillna("").str.contains("GK", na=False)].copy()
_ovr_map = {}
for _r in _rep.itertuples(index=False):
    _row = pd.Series(_r._asdict())
    if "GK" in str(_row.get("pos", "")):
        _ovr_map[_row["player"]] = goalkeeper_ovr(_row, _gk_ovr_pool)
    else:
        _base_ovr = player_ovr(
            _row.get("market_value_eur"), _row.get("ss_rating"),
            _row.get("minutes"), _row.get("goals"), _row.get("assists")
        )
        _bonus = season_achievement_bonus(_row, _rep)
        _ovr_map[_row["player"]] = int(max(48, min(95, round(_base_ovr + _bonus))))

SCHEDULE_PATH = Path(__file__).resolve().parent / "data" / "schedule_2025_2026.csv"
TRANSFERS_PATH = Path(__file__).resolve().parent / "data" / "transfers_2025_2026.csv"
FL_MATCHES_PATH = Path(__file__).resolve().parent / "data" / "fl_matches_2025_2026.csv"


@st.cache_data
def load_schedule() -> pd.DataFrame | None:
    if not SCHEDULE_PATH.exists():
        return None
    return pd.read_csv(SCHEDULE_PATH)


@st.cache_data
def load_fl_matches() -> pd.DataFrame | None:
    """football-lineups 경기별 (날짜·대회·포메이션·match_id). schedule와 date로 조인."""
    if not FL_MATCHES_PATH.exists():
        return None
    df = pd.read_csv(FL_MATCHES_PATH)
    df["match_id"] = df["match_id"].astype(str)
    return df


ESPN_LINEUPS_PATH = Path(__file__).resolve().parent / "data" / "espn_lineups_2025_2026.csv"


ESPN_SUBS_PATH = Path(__file__).resolve().parent / "data" / "espn_subs_2025_2026.csv"


@st.cache_data
def load_espn_lineups(_mtime: float = 0.0) -> pd.DataFrame | None:
    """ESPN 경기별 라인업(선발+교체 · 포메이션 · 포지션). 스케줄 탭 피치용."""
    if not ESPN_LINEUPS_PATH.exists():
        return None
    df = pd.read_csv(ESPN_LINEUPS_PATH)
    df["event_id"] = df["event_id"].astype(str)
    df["date"] = df["date"].astype(str)
    return df


@st.cache_data
def load_espn_subs(_mtime: float = 0.0) -> pd.DataFrame | None:
    """ESPN 경기별 교체 이벤트(분·IN·OUT). 스케줄 탭 교체 타임라인용."""
    if not ESPN_SUBS_PATH.exists():
        return None
    df = pd.read_csv(ESPN_SUBS_PATH)
    df["event_id"] = df["event_id"].astype(str)
    return df


@st.cache_data
def load_transfers(_mtime: float = 0.0) -> pd.DataFrame | None:
    if not TRANSFERS_PATH.exists():
        return None
    return pd.read_csv(TRANSFERS_PATH)


# ── 섹션 렌더 — 사이드바 _nav 선택에 따라 한 섹션만 표시 ──────────────────────
# 1: 팀 개요 — 레이팅 도넛 + 스탯 카드 + 핵심 선수
if _nav == NAV[0]:
    _manager_profiles = load_manager_profiles(
        MANAGER_PROFILES_PATH.stat().st_mtime if MANAGER_PROFILES_PATH.exists() else 0.0
    )
    _manager_profile = _manager_profiles.get(team)
    _ratings = team_ratings(team, _traits, _standings, full, _unit_metrics)

    # 구단 정보 (FM 스타일) — 감독·구장·리그순위·스쿼드가치 등 실데이터
    _ti_srow = _standings[_standings["squad"] == team] if _standings is not None else None
    _ti_rank = int(_ti_srow.iloc[0]["rank"]) if _ti_srow is not None and not _ti_srow.empty else None
    _ti_pts = int(_ti_srow.iloc[0]["points"]) if _ti_srow is not None and not _ti_srow.empty else None
    _ti_tv = _rep.groupby("squad")["market_value_eur"].sum()
    _ti_vrank = int(_ti_tv.rank(ascending=False)[team]) if team in _ti_tv.index else None
    _fl_matches_top = load_fl_matches()
    _iframe(
        team_info_html(team, _manager_profile, _ti_rank, _ti_pts, _ti_vrank, _fl_matches_top),
        height=322,
    )

    _iframe(
        overview_scout_dossier_html(
            team, _standings, _ratings, _manager_profile,
            _statbunker_team_stats, _unit_metrics
        ),
        height=318,
    )

    _snapshot_html = team_snapshot_html(team, _statbunker_team_stats, _unit_metrics)
    _set_piece_html = set_piece_discipline_html(team, _statbunker_team_stats, _unit_metrics)
    if _snapshot_html or _set_piece_html:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        _overview_cards = (
            "<div style='display:grid;grid-template-columns:1.05fr .95fr;gap:14px;align-items:stretch'>"
            f"<div style='height:100%'>{_snapshot_html}</div>"
            f"<div style='height:100%'>{_set_piece_html}</div></div>"
        )
        _iframe(_overview_cards, height=410)

    if _manager_profile:
        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
        _iframe(manager_profile_html(team, _manager_profile, _standings), height=396)

    _stars = team_star_players(team, full, _display_pos_map, _sid_all, _ovr_map, n=5)
    if _stars:
        st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
        #sec_title("핵심 선수", "AI 종합 평점(ss_rating) 상위 5명 · OVR=객관 평점 환산")
        _iframe(_grid([star_card_html(_sp) for _sp in _stars], 5), height=276)

    # 포메이션 & 전술 구조 — 주전 XI 보드 + 벤치 (ESPN 실측 주 포메이션의 최근 XI)
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    sec_title(f"포메이션 & 전술 구조 · {formation}",
              f"{_form_source} · 주 포메이션의 최근 선발 XI · 색=라인(🔴공격 🟠중원 🔵수비 🟢GK)")
    st.caption("토큰에 호버하면 강점 지표가 라벨과 함께 표시됩니다.")
    st.components.v1.html(pitch_html(placements), height=720)
    if bench_pls:
        n_rows = max(1, (len(bench_pls) + 5) // 6)
        st.components.v1.html(bench_strip_html(bench_pls), height=62 + n_rows * 112, scrolling=False)
    if departed_pls:
        st.caption("↪ 시즌 중 이적으로 팀을 떠난 선수 — 전술판·벤치에서 제외됨 (현 소속 표기)")
        n_dep = max(1, (len(departed_pls) + 5) // 6)
        st.components.v1.html(bench_strip_html(departed_pls, title="↪ 시즌 중 이적"),
                              height=62 + n_dep * 112, scrolling=False)

# 2: Analytics — 한국어 대시보드 (analytics_1–4)
elif _nav == NAV[1]:
    _sched_a = load_schedule()
    _ts = (_sched_a[_sched_a["squad"] == team] if _sched_a is not None else None)
    _mgr_a = load_manager_profiles(
        MANAGER_PROFILES_PATH.stat().st_mtime if MANAGER_PROFILES_PATH.exists() else 0.0
    ).get(team) or MANAGER_PROFILES.get(team)
    _iframe(
        analytics_dashboard_html(
            team, formation, _unit_metrics, _standings, _mgr_a, _ts, full, _rep, _weak,
        ),
        height=920,
        scrolling=True,
    )
    if st.button("🔍 선수 숏리스트 생성 →", type="primary", key="analytics_shortlist"):
        st.session_state["nav_menu"] = NAV[4]
        st.rerun()

# 3: Player Detail — 선수 능력치/레이더/유사선수
elif _nav == NAV[2]:
    sec_title("선수 상세", "선수별 능력치 · 레이더 · 스타일 유사 선수")
    bench_all = [p["full"] for p in bench_pls]
    pool = list(dict.fromkeys(xi_gk + xi_players + bench_all))

    state_key = f"player_detail_pick_{team}"
    if state_key not in st.session_state or st.session_state[state_key] not in pool:
        st.session_state[state_key] = pool[0] if pool else None

    def picker_bucket(pos: str) -> str:
        p = str(pos or "").upper()
        if "GK" in p:
            return "GK"
        if p in {"CB", "FB", "RB", "LB", "DF"} or "DF" in p:
            return "수비"
        if p in {"DM", "CM", "AM", "MF"} or "MF" in p:
            return "중원"
        return "공격"

    card_rows = []
    for pname in pool:
        raw_rows = full[full["player"] == pname]
        raw = raw_rows.iloc[0] if not raw_rows.empty else pd.Series(dtype=object)
        drow = dff[dff["player"] == pname]
        drow = drow.iloc[0] if not drow.empty else raw
        pos = _display_pos_map.get(pname) or _fine_map.get(pname)
        if not pos or (isinstance(pos, float) and pd.isna(pos)):
            pos = "GK" if "GK" in str(raw.get("pos", "")) else str(raw.get("pos", "")).split(",")[0].strip()
        short_name = pname.split()[-1] if len(pname) > 16 else pname
        card_ovr = _ovr_map.get(pname)
        if card_ovr is None:
            card_ovr = player_ovr(raw.get("market_value_eur"), raw.get("ss_rating"),
                                  raw.get("minutes"), raw.get("goals"), raw.get("assists"))
        card_rows.append({
            "name": pname,
            "short_name": short_name,
            "pos": pos,
            "minutes": raw.get("minutes"),
            "goals": raw.get("goals", 0),
            "assists": raw.get("assists", 0),
            "value": fmt_value(raw.get("market_value_eur")),
            "ovr": card_ovr,
            "sid": _photo(_sid_all.get(pname, ""), drow.get("tm_photo") if "tm_photo" in drow.index else None),
            "tcol": team_color(team),
        })
        card_rows[-1]["bucket"] = picker_bucket(pos)

    selected_card = next((p for p in card_rows if p["name"] == st.session_state[state_key]), None)
    if selected_card:
        st.markdown(selected_player_spotlight_html(selected_card), unsafe_allow_html=True)

    filter_col, sort_col = st.columns([1.4, 1])
    with filter_col:
        pos_filter = st.pills(
            "포지션 필터",
            ["전체", "공격", "중원", "수비", "GK"],
            default="전체",
            label_visibility="collapsed",
            key=f"player_filter_{team}",
        )
    with sort_col:
        sort_mode = st.segmented_control(
            "정렬",
            ["OVR", "출전", "이름"],
            default="OVR",
            label_visibility="collapsed",
            key=f"player_sort_{team}",
        )

    visible_cards = [p for p in card_rows if pos_filter in (None, "전체") or p["bucket"] == pos_filter]
    if sort_mode == "출전":
        visible_cards.sort(key=lambda x: float(x.get("minutes") or 0), reverse=True)
    elif sort_mode == "이름":
        visible_cards.sort(key=lambda x: str(x.get("name", "")))
    else:
        visible_cards.sort(key=lambda x: int(x.get("ovr") or 0), reverse=True)

    st.markdown(
        f"<div style='font-size:12px;color:#8a93a5;font-weight:800;margin:8px 0 10px'>"
        f"스쿼드 브라우저 · {len(visible_cards)}명</div>",
        unsafe_allow_html=True,
    )
    for start in range(0, len(visible_cards), 4):
        cols = st.columns(4)
        for col, pdata in zip(cols, visible_cards[start:start + 4]):
            with col:
                selected = pdata["name"] == st.session_state[state_key]
                st.markdown(player_picker_card_html(pdata, selected=selected), unsafe_allow_html=True)
                if st.button("리포트 보기" if not selected else "현재 분석 중",
                             key=f"pick_{team}_{pdata['name']}", use_container_width=True,
                             type="primary" if selected else "secondary",
                             disabled=selected):
                    st.session_state[state_key] = pdata["name"]
                    st.rerun()

    pick = st.session_state[state_key]
    st.markdown("<div style='margin-top:14px'></div>", unsafe_allow_html=True)

    raw_match = full[full["player"] == pick]
    is_gk = (not raw_match.empty) and "GK" in str(raw_match.iloc[0]["pos"])

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

        _pick_row = dff[dff["player"].str.lower() == pick.lower()]
        if _pick_row.empty:
            _pick_row = dff[dff["player"].str.lower().str.contains(pick.lower())]
        _fine = _pick_row.iloc[0]["fl_group"] if not _pick_row.empty else grp
        same_pos = st.checkbox(
            f"같은 세부 포지션 비교 (현재: **{_fine}**)", value=True,
            help="W=윙어·공격형미드 / ST=스트라이커 / CM=박스투박스 / DM=수비형MF / CB / FB"
        )
        alpha = st.slider("스타일 ↔ 퍼포먼스 비중", 0.3, 0.9, 0.65, 0.05,
                          help="높을수록 스타일 우선 · 낮을수록 이번 시즌 퍼포먼스 우선")
        st.markdown("**비슷한 선수 (리그 전체)**")
        # 임베딩: 리그 백분위(0.5 센터링) — raw per90 z-score 대비 이상치에 강건.
        emb = build_embeddings(dff, method="percentile")
        sim = find_similar(dff, emb, pick, top=5, same_position=same_pos, alpha=alpha)
        sim_show = sim[["player", "squad", "pos", "fl_group", "style_sim", "perf_score", "score"]].copy()
        sim_show.columns = ["선수", "팀", "포지션", "역할", "스타일", "퍼포먼스", "종합"]
        for col in ["스타일", "퍼포먼스", "종합"]:
            sim_show[col] = (sim_show[col] * 100).round(1).astype(str) + "%"
        st.dataframe(sim_show, hide_index=True, use_container_width=True)
        st.caption("스타일은 같은 포지션 풀의 백분위 기반이라 절대값이 높게 나옵니다 — "
                   "값보다 **순위(종합 정렬)**로 보세요. 종합 = 스타일·퍼포먼스 가중 결합.")

# 4: Squad Depth Chart — 포지션별 주전/백업 + 깊이 점수
elif _nav == NAV[3]:
    sec_title("Squad Depth Chart", "포지션별 주전/백업 + 깊이 점수 · OVR=객관 평점 환산")
    st.markdown(squad_depth_html(placements, bench_pls, _ovr_map, _fine_map),
                unsafe_allow_html=True)

# 5: Transfer Recommendations — 팀 적합 영입 후보
elif _nav == NAV[4]:
    # ── 이적시장 IN/OUT (실제 이적, Transfermarkt) — 여름/겨울 분리 ───────────
    _tdf = load_transfers(TRANSFERS_PATH.stat().st_mtime if TRANSFERS_PATH.exists() else 0.0)
    if _tdf is not None and (_tdf["squad"] == team).any():
        _tt = _tdf[_tdf["squad"] == team].copy()
        _tt["_fee"] = _tt["fee_eur"].fillna(-1)
        for _wval, _wlabel in [("summer", "Summer Transfers · 25/26"),
                               ("winter", "Winter Transfers · 25/26 (1월)")]:
            _w = _tt[_tt["window"] == _wval] if "window" in _tt.columns else _tt
            _ins = _w[_w["direction"] == "in"].sort_values("_fee", ascending=False).to_dict("records")
            _outs = _w[_w["direction"] == "out"].sort_values("_fee", ascending=False).to_dict("records")
            if not _ins and not _outs:
                continue
            sec_title(_wlabel, f"{team} · 영입/방출 · Transfermarkt")
            def _side_h(rows):
                return 56 + min(14, len(rows)) * 44 + (28 if len(rows) > 14 else 0) + 12
            _h = max(_side_h(_ins), _side_h(_outs))
            _ci, _co = st.columns(2)
            with _ci:
                _iframe(transfer_side_html("in", _ins), height=_h)
            with _co:
                _iframe(transfer_side_html("out", _outs), height=_h)
            st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    # ── AI 영입 추천 (팀 적합 후보) ──────────────────────────────────────────
    sec_title("AI Transfer Recommendations",
              f"{team} 약점 보강 + 스타일 적합 · EPL 내 후보 · AI 추정 (시뮬레이션 아님)")
    _recs = recommend_signings(team, pct, _weak, _sid_all, _raw_rating, _ovr_map, n=6)
    if not _recs:
        st.info("추천 후보를 계산할 수 없습니다 — 팀 약점 또는 후보 데이터가 부족합니다.")
    else:
        _rec_rows = (len(_recs) + 2) // 3
        _iframe(_grid([signing_card_html(_rec) for _rec in _recs], 3),
                height=_rec_rows * 290 + 8)

# 6: Schedule — 시즌 전적 테이블
elif _nav == NAV[5]:
    _schedule = load_schedule()
    _fl_matches = load_fl_matches()
    team_sched = (_schedule[_schedule["squad"] == team].sort_values("gw").copy()
                  if _schedule is not None else None)
    if team_sched is None or team_sched.empty:
        st.info("시즌 전적 데이터가 없습니다.")
    else:
        sec_title(f"{team} — 2025/26 시즌 전적", f"{len(team_sched)}경기")

        # ── football-lineups 경기별 포메이션 조인 (EPL, date 기준) ──────────
        _form_map: dict[str, str] = {}
        if _fl_matches is not None:
            _flm = _fl_matches[(_fl_matches["squad"] == team)
                               & (_fl_matches["comp"] == "EPL")]
            _form_map = dict(zip(_flm["date"].astype(str), _flm["formation"]))

        # 최근 N경기 주 포메이션 vs 시즌 누적 — 전술 변화 감지
        _recent_n = 10
        _recent_forms = [_form_map.get(str(d), "") for d in team_sched["date"].tail(_recent_n)]
        _recent_forms = [f for f in _recent_forms if f]
        _season_form = team_formations(team, formations_cfg)["main"]
        if _recent_forms:
            from collections import Counter as _Counter
            _rc = _Counter(_recent_forms).most_common(1)[0]
            _recent_main, _recent_cnt = _rc[0], _rc[1]
            _changed = _recent_main != _season_form
            _accent = "#e8344e" if _changed else "#16a34a"
            st.markdown(
                f"<div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap;"
                f"margin:2px 0 14px'>"
                f"<span style='font-size:12px;color:#8a93a5;font-weight:800'>포메이션</span>"
                f"<span style='background:#eef1f6;color:#555;border-radius:7px;"
                f"padding:4px 11px;font-size:13px;font-weight:800'>시즌 누적 {_season_form}</span>"
                f"<span style='color:#c2c8d4'>→</span>"
                f"<span style='background:{_accent}1a;color:{_accent};border-radius:7px;"
                f"padding:4px 11px;font-size:13px;font-weight:800'>"
                f"최근 {len(_recent_forms)}경기 {_recent_main} ({_recent_cnt}회)</span>"
                + (f"<span style='color:{_accent};font-size:12px;font-weight:700'>"
                   f"⚠️ 최근 전술 변화</span>" if _changed else "")
                + "</div>",
                unsafe_allow_html=True,
            )

        # ── 마스터-디테일: 좌측 전체 일정(클릭) → 우측 라인업 ──────────────────
        _result_kr = {"W": "승", "D": "무", "L": "패"}
        _espn_lineups = load_espn_lineups(
            ESPN_LINEUPS_PATH.stat().st_mtime if ESPN_LINEUPS_PATH.exists() else 0.0)
        _et = (_espn_lineups[_espn_lineups["squad"] == team]
               if _espn_lineups is not None else None)
        _avail = (set(zip(_et["date"].astype(str), _et["opponent"]))
                  if (_et is not None and not _et.empty) else set())

        _games = team_sched.to_dict("records")
        _default = len(_games) - 1
        for _i in range(len(_games) - 1, -1, -1):   # 라인업 있는 최근 경기를 기본 선택
            if (str(_games[_i]["date"]), _games[_i]["opponent"]) in _avail:
                _default = _i
                break

        _ac = team_color(team)
        st.markdown(
            f"""<style>
            .st-key-sched_pick [role=radiogroup]{{gap:0;border:1px solid #eef1f6;
                border-radius:10px;background:#fff;overflow:hidden}}
            .st-key-sched_pick [role=radiogroup] label{{width:100%;padding:9px 12px;margin:0;
                border-left:3px solid transparent;border-bottom:1px solid #f4f6f9;
                cursor:pointer;transition:background .12s}}
            .st-key-sched_pick [role=radiogroup] label:hover{{background:#f7f9fc}}
            .st-key-sched_pick [role=radiogroup] label>div:first-child{{display:none}}
            .st-key-sched_pick [role=radiogroup] label p{{font-size:13px;color:#3a4253;font-weight:600;
                white-space:nowrap}}
            .st-key-sched_pick [role=radiogroup] label:has(input:checked){{background:{_ac}12;
                border-left:3px solid {_ac}}}
            .st-key-sched_pick [role=radiogroup] label:has(input:checked) p{{color:{_ac};font-weight:800}}
            </style>""",
            unsafe_allow_html=True)

        _left, _right = st.columns([1, 1.6])
        with _left:
            st.markdown(f"<div style='font-size:11px;font-weight:800;color:#8a93a5;"
                        f"letter-spacing:1px;margin-bottom:7px'>전체 일정 {len(_games)}경기 · 클릭하면 라인업"
                        f" <span style='color:#c2c8d4;font-weight:600'>(GW=라운드)</span></div>",
                        unsafe_allow_html=True)
            _res_emoji = {"W": "🟢", "D": "⚪", "L": "🔴"}

            def _glabel(i):
                r = _games[i]
                return (f"{_res_emoji.get(r['result'], '·')} GW{int(r['gw'])} "
                        f"{r['opponent']} · {r['score']}")
            _pick = st.radio("sched", list(range(len(_games))), index=_default,
                             format_func=_glabel, key="sched_pick", label_visibility="collapsed")

        with _right:
            _gr = _games[_pick]
            _ha_full = "홈" if _gr["home_away"] == "H" else "원정"
            _mrows = (_et[(_et["date"].astype(str) == str(_gr["date"]))
                          & (_et["opponent"] == _gr["opponent"])].to_dict("records")
                      if _et is not None else [])
            _formation = str(_mrows[0]["formation"] or "") if _mrows else ""
            _res_c = {"W": "#bbf7d0", "D": "#e5e7eb", "L": "#fecaca"}.get(_gr["result"], "#fff")
            st.markdown(
                f"<div style='font-family:sans-serif;background:linear-gradient(135deg,{_ac},#10151c);"
                f"color:#fff;border-radius:12px;padding:14px 18px;margin-bottom:12px'>"
                f"<div style='font-size:12px;opacity:.85;font-weight:700'>"
                f"GW{int(_gr['gw'])} · {_gr['date']} · {_ha_full}</div>"
                f"<div style='font-size:19px;font-weight:800;margin-top:3px'>"
                f"vs {html.escape(str(_gr['opponent']))}</div>"
                f"<div style='font-size:27px;font-weight:800;margin-top:6px'>"
                f"{html.escape(str(_gr['score']))} "
                f"<span style='font-size:14px;color:{_res_c}'>{_result_kr.get(_gr['result'],'')}</span></div>"
                + (f"<div style='font-size:13px;opacity:.9;margin-top:5px;font-weight:700'>"
                   f"포메이션 {_formation}</div>" if _formation else "")
                + "</div>",
                unsafe_allow_html=True)

            _pl = (placements_from_espn(team, _mrows, _formation, full, pct)
                   if (_formation and _mrows) else None)
            if _pl:
                _iframe(pitch_html(_pl), height=760)

                # 선수 이름 → 사진 매핑 (정규화)
                _ft = full[full["squad"] == team]
                _tmcol = _ft["tm_photo"] if "tm_photo" in _ft.columns else [None] * len(_ft)
                _pm = {_norm(p): _photo(_sid_all.get(p, ""), tm)
                       for p, tm in zip(_ft["player"], _tmcol)}

                # ── 교체 in/out 타임라인 (ESPN 이벤트) ──────────────────────
                _subs_df = load_espn_subs(
                    ESPN_SUBS_PATH.stat().st_mtime if ESPN_SUBS_PATH.exists() else 0.0)
                _evid = str(_mrows[0].get("event_id", "")) if _mrows else ""
                _ha2 = "home" if _gr["home_away"] == "H" else "away"
                _tl = []
                if _subs_df is not None and _evid:
                    _tl = _subs_df[(_subs_df["event_id"] == _evid)
                                   & (_subs_df["home_away"] == _ha2)].sort_values("minute_sec").to_dict("records")

                if _tl:
                    def _side(name, arrow, ac):
                        return (f"<div style='flex:1;display:flex;align-items:center;gap:7px;min-width:0'>"
                                f"<span style='color:{ac};font-weight:900;font-size:13px'>{arrow}</span>"
                                f"{avatar(_pm.get(_norm(name), ''), '#cdd5e0', 26)}"
                                f"<span style='font-size:12.5px;font-weight:700;color:#1a1f2e;white-space:nowrap;"
                                f"overflow:hidden;text-overflow:ellipsis'>{html.escape(name)}</span></div>")
                    _rows_html = "".join(
                        f"<div style='display:flex;align-items:center;gap:10px;padding:7px 4px;"
                        f"border-bottom:1px solid #f4f6f9'>"
                        f"<span style='min-width:44px;text-align:center;font-size:12px;font-weight:800;"
                        f"color:#1a1f2e;background:#eef1f6;border-radius:6px;padding:3px 0'>{html.escape(str(e['minute']))}</span>"
                        f"{_side(str(e['player_in']), '▲', '#16a34a')}"
                        f"{_side(str(e['player_out']), '▼', '#ef4444')}</div>"
                        for e in _tl)
                    _iframe(
                        "<div style='font-family:sans-serif'>"
                        f"<div style='font-size:11px;font-weight:800;color:#8a93a5;margin-bottom:8px'>"
                        f"교체 타임라인 ({len(_tl)}건) · <span style='color:#16a34a'>▲ IN</span> "
                        f"<span style='color:#ef4444'>▼ OUT</span></div>" + _rows_html + "</div>",
                        height=len(_tl) * 44 + 44)
                else:
                    # 폴백: 교체 이벤트 미수집 → 벤치 명단(사진)
                    _subs = [r for r in _mrows if not r.get("starter")]
                    if _subs:
                        _sub_cards = "".join(
                            f"<div style='display:flex;align-items:center;gap:9px;padding:6px 9px;"
                            f"background:#f8fafc;border:1px solid #eef1f6;border-radius:9px'>"
                            f"{avatar(_pm.get(_norm(str(s.get('player') or '')), ''), '#cdd5e0', 30)}"
                            f"<div style='min-width:0'>"
                            f"<div style='font-size:12.5px;font-weight:700;color:#1a1f2e;white-space:nowrap;"
                            f"overflow:hidden;text-overflow:ellipsis'>{html.escape(str(s.get('player') or ''))}</div>"
                            f"<div style='font-size:10px;color:#9aa3b2'>#{_num_str(s.get('jersey'))}</div></div></div>"
                            for s in _subs[:12])
                        _srows = (min(len(_subs), 12) + 1) // 2
                        _iframe(
                            "<div style='font-family:sans-serif'>"
                            f"<div style='font-size:11px;font-weight:800;color:#8a93a5;margin-bottom:8px'>"
                            f"벤치 명단 ({len(_subs)}명)</div>"
                            "<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:7px'>"
                            + _sub_cards + "</div></div>",
                            height=_srows * 48 + 40)
            else:
                st.info("이 경기의 실측 라인업 데이터가 없습니다 (ESPN 미수집 경기).")

# 7: Player Database — EPL 전 선수 검색/필터
elif _nav == NAV[6]:
    sec_title("Player Database", "EPL 전 선수 검색 · 포지션/나이/시장가치/국적 필터 · OVR 순")

    _DB_BUCKETS = ["GK", "CB", "FB", "DM", "CAM_CM", "WING_AM", "ST"]
    _BLAB = {"GK": "GK 골키퍼", "CB": "CB 센터백", "FB": "FB 풀백", "DM": "DM 수비형MF",
             "CAM_CM": "CM 중앙MF", "WING_AM": "WG 윙/공미", "ST": "ST 스트라이커"}
    _DB_FINE_TO_BUCKET = {
        "GK": "GK",
        "CB": "CB",
        "FB": "FB", "RB": "FB", "LB": "FB",
        "DM": "DM",
        "CM": "CAM_CM", "AM": "CAM_CM",
        "W": "WING_AM", "RW": "WING_AM", "LW": "WING_AM",
        "ST": "ST", "FW": "ST",
    }

    def _db_bucket(row):
        if "GK" in str(row.get("pos", "")):
            return "GK"
        b = str(_fine_map.get(row["player"]) or row.get("fl_group") or row.get("fl_pos") or "").strip().upper()
        if b in _DB_FINE_TO_BUCKET:
            return _DB_FINE_TO_BUCKET[b]
        return _DB_FINE_TO_BUCKET.get(fine_group(row.get("pos", ""), row))

    def _db_display_pos(row):
        mapped = _display_pos_map.get(row.get("player"))
        if mapped:
            return mapped
        vals = []
        for col in ["fl_pos", "fl_pos2"]:
            v = row.get(col)
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan":
                vals.append(str(v).strip().upper())
        if not vals:
            b = str(row.get("fl_group") or "").strip().upper()
            if b:
                vals.append(b)
        if not vals:
            pos = str(row.get("pos") or "").strip().upper()
            if "GK" in pos:
                vals.append("GK")
            elif "FW" in pos:
                vals.append("FW")
            elif "MF" in pos:
                vals.append("MF")
            elif "DF" in pos:
                vals.append("DF")
        out = []
        for v in vals:
            if v and v not in out:
                out.append(v)
        return "/".join(out[:2]) if out else None

    _pdb = _rep.copy()
    _pdb["ovr"] = _pdb["player"].map(_ovr_map)
    _pdb["bucket"] = _pdb.apply(_db_bucket, axis=1)
    _pdb["display_pos"] = _pdb.apply(_db_display_pos, axis=1)
    _pdb = _pdb[_pdb["minutes"] > 0]

    # 필터 위젯
    _q = st.text_input("선수 검색", placeholder="선수 이름 입력…")
    _f1, _f2, _f3 = st.columns([1.4, 1, 1])
    _posf = _f1.multiselect("포지션", _DB_BUCKETS, format_func=lambda b: _BLAB.get(b, b))
    _age_rng = _f2.slider("나이", 15, 40, (15, 40))
    _val_max = _f3.slider("시장가치 상한 (€M)", 0, 200, 200, step=5)
    _nats = sorted([n for n in _pdb["nationality"].dropna().unique()])
    _natf = st.multiselect("국적", _nats)

    # 필터 적용
    _d = _pdb
    if _q:
        _d = _d[_d["player"].str.contains(_q, case=False, na=False)]
    if _posf:
        _d = _d[_d["bucket"].isin(_posf)]
    if _natf:
        _d = _d[_d["nationality"].isin(_natf)]
    _d = _d[_d["age"].between(_age_rng[0], _age_rng[1]) | _d["age"].isna()]
    if _val_max < 200:
        _d = _d[_d["market_value_eur"].notna() & (_d["market_value_eur"] <= _val_max * 1_000_000)]
    _d = _d.sort_values("ovr", ascending=False)

    st.caption(f"{len(_d)}명 매칭 · OVR 높은 순")
    _LIMIT = 24
    _rows = _d.head(_LIMIT).to_dict("records")
    if not _rows:
        st.info("조건에 맞는 선수가 없습니다 — 필터를 완화해보세요.")
    else:
        # iframe(components.html)로 렌더 → 사진(외부 이미지)이 sanitize 없이 로드됨
        _cards = "".join(db_player_card_html(
            _p["player"], _p["squad"], _p.get("age"), _p.get("market_value_eur"),
            _p.get("nationality"), _p.get("tm_photo"),
            int(_p["ovr"]) if pd.notna(_p.get("ovr")) else 0, _p.get("display_pos"))
            for _p in _rows)
        _nrows = (len(_rows) + 3) // 4
        st.components.v1.html(
            "<style>body{margin:0;background:#eef1f6;font-family:sans-serif}</style>"
            "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:14px'>"
            + _cards + "</div>",
            height=_nrows * 158 + 8, scrolling=False)
    if len(_d) > _LIMIT:
        st.caption(f"… 외 {len(_d) - _LIMIT}명 — 필터를 좁히면 더 정확히 찾을 수 있어요.")

