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

from similar_players import FEATURES, DATA_PATH, build_embeddings, find_similar, fine_group  # noqa: E402  # fine_group kept for fallback
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
    """선수 사진 URL. 값이 이미 http URL이면(API-Football photo) 그대로 통과,
    숫자면 Sofascore 헤드샷 URL로 변환. 없으면 빈 문자열."""
    s = str(sid).strip() if sid is not None else ""
    if s.startswith("http"):
        return s
    s = _num_str(sid)
    return f"https://img.sofascore.com/api/v1/player/{s}/image" if s else ""


def _photo(sid_val, tm_val=None) -> str:
    """Sofascore id 우선, 없으면 Transfermarkt 사진(tm_photo) 폴백."""
    s = sofa_photo(sid_val)
    if s:
        return s
    if tm_val is not None and pd.notna(tm_val) and str(tm_val).startswith("http"):
        return str(tm_val)
    return ""


# 시장가치(€) 표시 + 국적 코드 (Transfermarkt 데이터)
def fmt_value(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if v >= 1_000_000:
        return f"€{v / 1_000_000:.0f}M"
    if v >= 1_000:
        return f"€{v / 1_000:.0f}K"
    return "—"


NATION_CODE = {
    "England": "ENG", "Spain": "ESP", "France": "FRA", "Brazil": "BRA", "Germany": "GER",
    "Portugal": "POR", "Netherlands": "NED", "Italy": "ITA", "Argentina": "ARG",
    "Belgium": "BEL", "Norway": "NOR", "Egypt": "EGY", "Scotland": "SCO", "Wales": "WAL",
    "Ireland": "IRL", "Republic of Ireland": "IRL", "Uruguay": "URU", "Colombia": "COL",
    "Ecuador": "ECU", "Ivory Coast": "CIV", "Senegal": "SEN", "Ghana": "GHA",
    "Nigeria": "NGA", "Japan": "JPN", "South Korea": "KOR", "Korea, South": "KOR",
    "Denmark": "DEN", "Sweden": "SWE", "Switzerland": "SUI", "Croatia": "CRO",
    "Serbia": "SRB", "Poland": "POL", "Austria": "AUT", "Czech Republic": "CZE",
    "Ukraine": "UKR", "Turkey": "TUR", "Türkiye": "TUR", "Mexico": "MEX",
    "United States": "USA", "Cameroon": "CMR", "Mali": "MLI", "Morocco": "MAR",
    "Algeria": "ALG", "Greece": "GRE", "Hungary": "HUN", "Slovakia": "SVK",
    "Slovenia": "SVN", "Paraguay": "PAR", "Jamaica": "JAM", "Australia": "AUS",
    "Finland": "FIN", "Iceland": "ISL", "Albania": "ALB", "Montenegro": "MNE",
    "Guinea": "GUI", "Zimbabwe": "ZIM", "DR Congo": "COD", "Congo": "COG", "Gabon": "GAB",
}


def nation_code(nat) -> str:
    if nat is None or (isinstance(nat, float) and pd.isna(nat)):
        return ""
    nat = str(nat).strip()
    if not nat or nat == "nan":
        return ""
    return NATION_CODE.get(nat, nat[:3].upper())


# 국가명 → flagcdn ISO 코드 (홈네이션 gb-eng/sct/wls/nir 지원)
NATION_ISO = {
    "England": "gb-eng", "Scotland": "gb-sct", "Wales": "gb-wls",
    "Northern Ireland": "gb-nir", "Spain": "es", "France": "fr", "Brazil": "br",
    "Germany": "de", "Portugal": "pt", "Netherlands": "nl", "Italy": "it",
    "Argentina": "ar", "Belgium": "be", "Norway": "no", "Egypt": "eg",
    "Ireland": "ie", "Republic of Ireland": "ie", "Uruguay": "uy", "Colombia": "co",
    "Ecuador": "ec", "Ivory Coast": "ci", "Senegal": "sn", "Ghana": "gh",
    "Nigeria": "ng", "Japan": "jp", "South Korea": "kr", "Korea, South": "kr",
    "Denmark": "dk", "Sweden": "se", "Switzerland": "ch", "Croatia": "hr",
    "Serbia": "rs", "Poland": "pl", "Austria": "at", "Czech Republic": "cz",
    "Ukraine": "ua", "Turkey": "tr", "Türkiye": "tr", "Mexico": "mx",
    "United States": "us", "Cameroon": "cm", "Mali": "ml", "Morocco": "ma",
    "Algeria": "dz", "Greece": "gr", "Hungary": "hu", "Slovakia": "sk",
    "Slovenia": "si", "Paraguay": "py", "Jamaica": "jm", "Australia": "au",
    "Finland": "fi", "Iceland": "is", "Albania": "al", "Montenegro": "me",
    "Guinea": "gn", "Zimbabwe": "zw", "DR Congo": "cd", "Congo": "cg", "Gabon": "ga",
}


def flag_chip(nat, h: int = 13) -> str:
    """국가명 → 국기 <img>. 매핑 없으면 텍스트 코드 칩 폴백. 없으면 빈 문자열."""
    if nat is None or (isinstance(nat, float) and pd.isna(nat)):
        return ""
    nat = str(nat).strip()
    if not nat or nat == "nan":
        return ""
    iso = NATION_ISO.get(nat)
    if iso:
        return (f"<img src='https://flagcdn.com/h20/{iso}.png' alt='{nation_code(nat)}' "
                f"title='{nat}' loading='lazy' "
                f"style='height:{h}px;border-radius:2px;vertical-align:middle;"
                f"margin-left:6px;box-shadow:0 0 0 1px rgba(0,0,0,.08)'/>")
    code = nation_code(nat)
    if not code:
        return ""
    return (f"<span style='font-size:10px;font-weight:800;color:#8a93a5;background:#f1f3f7;"
            f"border-radius:4px;padding:1px 5px;margin-left:6px;vertical-align:middle'>{code}</span>")

st.set_page_config(
    page_title="SCOUT.AI — EPL 25/26",
    page_icon="⚽",
    layout="wide",
)


# ── 전역 셸 테마 (Figma Football AI SCOUT: 밝은 메인 + 다크 사이드바 + 레드 액센트) ──
# config.toml의 [theme]가 라이트 베이스를, 아래 CSS가 다크 사이드바·흰 카드·타이포를 담당.
# 기존 커스텀 HTML(피치·FM패널·배너 등)은 components.html(iframe) 안에서 자체
# 다크 스타일로 렌더되어 라이트 메인 위에 '다크 카드'처럼 보인다(레퍼런스 피치와 동일).
ACCENT = "#e8344e"   # 레드 — 로고/액티브 네비/섹션 바
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


def sec_title(title: str, sub: str = "") -> None:
    """레퍼런스의 '레드 세로 바 + 제목' 섹션 헤더. sub는 회색 보조설명."""
    sub_html = f"<div style='color:#8a93a5;font-size:13px;margin-top:2px'>{sub}</div>" if sub else ""
    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:flex-start;margin:6px 0 14px'>"
        f"<div style='width:4px;align-self:stretch;min-height:26px;background:{ACCENT};"
        f"border-radius:3px'></div>"
        f"<div><div style='font-size:22px;font-weight:800;color:#1a1f2e;"
        f"letter-spacing:-.4px'>{title}</div>{sub_html}</div></div>",
        unsafe_allow_html=True,
    )


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
    """메인 상단 팀 배지 헤더 — 팀 컬러 사각 이니셜 + 팀명 + 리그·시즌."""
    tcol = team_color(team)
    initial = team.strip()[0].upper() if team.strip() else "?"
    return f"""
    <div style="display:flex;align-items:center;gap:14px;margin:-6px 0 18px">
      <div style="width:46px;height:46px;border-radius:12px;flex:none;background:{tcol};
                  display:flex;align-items:center;justify-content:center;color:#fff;
                  font-weight:800;font-size:21px;box-shadow:0 4px 14px rgba(0,0,0,.18)">{initial}</div>
      <div>
        <div style="font-size:23px;font-weight:800;color:#1a1f2e;letter-spacing:-.5px">{team}</div>
        <div style="font-size:13px;color:#8a93a5">Premier League · 2025/26</div>
      </div>
    </div>"""


# ── Transfer Recommendations — 팀 적합 영입 후보 스코어링 ──────────────────────
# 풀: 선택 팀을 제외한 EPL 전 팀. 데이터: pct(백분위) + age/ss_rating(원본).
# 주의: market_value_eur 컬럼은 현재 전부 결측 → 시장가치 타일 대신 실측 지표 사용.
#   · Tactical Fit  = 팀 약점 컬럼에서의 후보 백분위(약점 심할수록 가중) → 보강 적합도
#   · Squad Match   = 팀 스타일 벡터(분 가중 평균 백분위)와의 근접도 → 시스템 적합도
FIT_FEATURES = [
    "npxg_p90", "xa_p90", "key_passes_per90", "crosses_per90",
    "successful_dribbles_per90", "pass_pct", "long_ball_pct",
    "aerial_won_pct", "tackles_won_per90", "interceptions_per90",
    "recoveries_per90", "big_chances_created_per90",
]

# 팀 약점 라벨(TEAM_TRAITS) → 그 약점을 메울 선수 백분위 컬럼
TRAIT_TO_COLS: dict[str, list[str]] = {
    "화력": ["npxg_p90", "shots_p90"],
    "수비 견고함": ["tackles_won_per90", "interceptions_per90", "clearances_per90"],
    "점유·빌드업": ["pass_pct"],
    "공중 장악": ["aerial_won_pct"],
    "측면 공격": ["crosses_per90"],
    "전방 압박": ["recoveries_per90"],
    "찬스 창출": ["key_passes_per90", "big_chances_created_per90"],
    "개인 돌파": ["successful_dribbles_per90"],
    "롱볼 활용": ["long_ball_pct"],
}

FIT_LABEL = {
    "npxg_p90": "득점위협", "shots_p90": "슈팅", "tackles_won_per90": "태클",
    "interceptions_per90": "인터셉트", "clearances_per90": "클리어링", "pass_pct": "패스정확도",
    "aerial_won_pct": "공중볼", "crosses_per90": "크로스", "recoveries_per90": "볼회수",
    "key_passes_per90": "키패스", "big_chances_created_per90": "빅찬스", "long_ball_pct": "롱볼",
    "successful_dribbles_per90": "드리블", "xa_p90": "패스위협",
}


def _team_style_vector(team: str, pctdf: pd.DataFrame) -> dict[str, float]:
    """팀 외야 선수들의 분 가중 평균 백분위 벡터(FIT_FEATURES)."""
    t = pctdf[(pctdf["squad"] == team) & (pctdf["minutes"] > 0)]
    vec: dict[str, float] = {}
    for f in FIT_FEATURES:
        if f not in t.columns:
            continue
        v = t[t[f].notna()]
        w = v["minutes"].sum()
        if w > 0:
            vec[f] = float((v[f] * v["minutes"]).sum() / w)
    return vec


def recommend_signings(team: str, pctdf: pd.DataFrame, weaknesses: list,
                       sid_map: dict, raw_rating: dict,
                       n: int = 6, min_minutes: int = 900) -> list[dict]:
    """팀 약점 보강 + 스타일 적합 기준 영입 후보 추천 (EPL 내 타팀 풀)."""
    style = _team_style_vector(team, pctdf)
    wcols: list[tuple[str, float]] = []   # (백분위 컬럼, 가중치=리그순위)
    for label, rank in weaknesses:
        for c in TRAIT_TO_COLS.get(label, []):
            if c in pctdf.columns:
                wcols.append((c, float(rank)))

    pool = pctdf[(pctdf["squad"] != team) & (pctdf["minutes"] >= min_minutes)].copy()
    pool = pool.sort_values("minutes", ascending=False).drop_duplicates("player")

    scored: list[tuple] = []
    for _, r in pool.iterrows():
        # Tactical Fit — 약점 컬럼 가중 평균 백분위
        num = den = 0.0
        for c, w in wcols:
            val = r.get(c)
            if pd.notna(val):
                num += w * float(val); den += w
        tac = num / den if den else float("nan")
        # Squad Match — 스타일 벡터 근접도
        diffs = [abs(float(r[f]) - style[f]) for f in style
                 if f in r.index and pd.notna(r.get(f))]
        match = 1 - sum(diffs) / len(diffs) if diffs else float("nan")
        if pd.isna(tac) or pd.isna(match):
            continue
        scored.append((0.6 * tac + 0.4 * match, tac, match, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict] = []
    for _, tac, match, r in scored[:n]:
        # AI 한줄평 — 가장 잘 메우는 약점 + 대표 강점
        best_lbl = best_col = ""
        best_v = -1.0
        for label, _rank in weaknesses:
            for c in TRAIT_TO_COLS.get(label, []):
                v = r.get(c)
                if pd.notna(v) and float(v) > best_v:
                    best_v, best_lbl, best_col = float(v), label, c
        note = f"{best_lbl} 보강 · {FIT_LABEL.get(best_col, best_col)} 상위 {round(best_v*100)}%" if best_lbl else ""
        rr = raw_rating.get(r["player"])
        # OVR — 시장가치(품질 추정) 기반 + 현재폼 미세 보정. 가치 없으면 평점 폴백.
        ovr = player_ovr(r.get("market_value_eur"), rr, r.get("minutes"),
                         r.get("goals"), r.get("assists"))
        out.append({
            "name": r["player"], "squad": r["squad"],
            "age": int(r["age"]) if pd.notna(r.get("age")) else None,
            "pos": str(r.get("fl_group") or r.get("fl_pos") or r.get("pos") or ""),
            "fit": round(tac * 100), "match": round(match * 100),
            "ovr": ovr,
            "value": fmt_value(r.get("market_value_eur")),
            "nat": r.get("nationality"),
            "note": note,
            "sid": _photo(sid_map.get(r["player"], ""), r.get("tm_photo")),
            "tcol": team_color(r["squad"]),
        })
    return out


def signing_card_html(r: dict) -> str:
    """영입 후보 1장 — 흰 카드(사진/OVR/포지션칩/Fit·Match·평점 타일/AI 한줄평)."""
    ovr = r["ovr"]
    oc = ("#2563eb" if ovr >= 85 else "#16a34a" if ovr >= 75
          else "#d97706" if ovr >= 65 else "#6b7280")
    sub = r["squad"] + (f" · {r['age']}세" if r["age"] else "")
    disc = (f"background-image:url('{r['sid']}'),linear-gradient(135deg,{r['tcol']},#0b0f17);"
            if r["sid"] else f"background:{r['tcol']};")
    fit_c = "#16a34a" if r["fit"] >= 70 else "#d97706" if r["fit"] >= 50 else "#ef4444"
    mat_c = "#16a34a" if r["match"] >= 70 else "#d97706" if r["match"] >= 50 else "#ef4444"

    def tile(label, val, color, bar=None):
        barhtml = (f"<div style='height:4px;border-radius:3px;background:#eef1f6;margin-top:6px'>"
                   f"<div style='height:100%;width:{bar}%;background:{color};border-radius:3px'></div></div>"
                   if bar is not None else
                   "<div style='height:4px;margin-top:6px'></div>")
        return (f"<div style='flex:1;text-align:center'>"
                f"<div style='font-size:18px;font-weight:800;color:{color};line-height:1.1'>{val}</div>"
                f"<div style='font-size:10px;color:#8a93a5;text-transform:uppercase;"
                f"letter-spacing:.4px;margin-top:3px'>{label}</div>{barhtml}</div>")

    note = (f"<div style='margin-top:12px;padding:8px 11px;background:#fbeaec;"
            f"border-left:3px solid {ACCENT};border-radius:6px;font-size:12px;color:#7a2230'>"
            f"<b style='color:{ACCENT}'>AI</b> {r['note']}</div>") if r["note"] else ""
    nat_chip = flag_chip(r.get("nat"))

    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:16px;padding:16px 18px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05);
                margin-bottom:16px">
      <div style="display:flex;align-items:center;gap:12px">
        <div style="width:52px;height:52px;border-radius:50%;flex:none;{disc}
                    background-size:cover;background-position:center;border:2px solid #e4e8f0"></div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:800;font-size:15px;color:#1a1f2e;white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis">{r['name']}{nat_chip}</div>
          <div style="font-size:12px;color:#8a93a5">{sub}</div>
        </div>
        <div style="text-align:center;flex:none">
          <div style="font-size:24px;font-weight:800;color:{oc};line-height:1">{ovr}</div>
          <div style="font-size:9px;color:#8a93a5;letter-spacing:1px">OVR</div>
        </div>
      </div>
      <div style="margin-top:11px">
        <span style="display:inline-block;padding:2px 9px;background:#f1f3f7;border-radius:6px;
                     font-size:11px;font-weight:700;color:#5a6478">{r['pos']}</span>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px">
        {tile('Value', r['value'], '#16a34a')}
        {tile('Tactical Fit', str(r['fit']) + '%', fit_c, r['fit'])}
        {tile('Squad Match', str(r['match']) + '%', mat_c, r['match'])}
      </div>
      {note}
    </div>"""


# ── Team Overview — 4 레이팅 도넛 + 6 스탯 카드 ────────────────────────────────
def rating_color(v: int) -> str:
    if v >= 85: return "#2563eb"   # 엘리트(파랑)
    if v >= 70: return "#16a34a"   # 강함(초록)
    if v >= 55: return "#d97706"   # 평균(주황)
    return "#ef4444"               # 약함(빨강)


def team_ratings(team: str, traits: pd.DataFrame, standings) -> list[tuple]:
    """팀 → [(라벨, 1~99 레이팅, 보조설명)] 4개. 20팀 랭크-백분위를 1~99로 환산."""
    def pct_rank(col: str, asc: bool = True):
        if col not in traits.columns or team not in traits.index:
            return None
        s = traits[col].dropna()
        if team not in s.index:
            return None
        return float(s.rank(ascending=asc, pct=True)[team])

    def tval(col):
        if col in traits.columns and team in traits.index and pd.notna(traits.loc[team, col]):
            return traits.loc[team, col]
        return None

    rank = None
    ovrp = None
    if standings is not None and (standings["squad"] == team).any():
        srow = standings[standings["squad"] == team].iloc[0]
        rank = int(srow["rank"])
        ps = standings.set_index("squad")["points"]
        ovrp = float(ps.rank(ascending=True, pct=True)[team])

    att = pct_rank("gf", asc=True)          # 득점 많을수록 강함
    deff = pct_rank("ga", asc=False)        # 실점 적을수록 강함
    mids = [pct_rank(c, asc=True) for c in ("pass_pct", "key_passes_per90", "recoveries_per90")]
    mids = [m for m in mids if m is not None]
    midp = sum(mids) / len(mids) if mids else None

    gf_v, ga_v, pass_v = tval("gf"), tval("ga"), tval("pass_pct")

    def rt(p):
        return fm_rating(p) if p is not None else 1

    return [
        ("Overall Rating", rt(ovrp), f"리그 {rank}위" if rank else ""),
        ("Attack Rating", rt(att), f"{int(gf_v)}골 득점" if gf_v is not None else ""),
        ("Midfield Rating", rt(midp), f"패스 정확도 {pass_v:.0f}%" if pass_v is not None else ""),
        ("Defense Rating", rt(deff), f"{int(ga_v)}골 실점" if ga_v is not None else ""),
    ]


def donut_card_html(label: str, value: int, sub: str) -> str:
    """레이팅 도넛 카드 — SVG 링 + 중앙 숫자 + 라벨/보조설명."""
    import math
    value = int(value) if value else 1
    color = rating_color(value)
    R, C = 30, 2 * math.pi * 30
    dash = C * max(0.0, min(1.0, value / 99))
    sub_html = f"<div style='font-size:12px;color:#8a93a5;margin-top:3px'>{sub}</div>" if sub else ""
    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 18px;
                display:flex;align-items:center;gap:14px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 4px 16px rgba(16,24,40,.04)">
      <svg width="74" height="74" viewBox="0 0 74 74" style="flex:none">
        <circle cx="37" cy="37" r="{R}" fill="none" stroke="#eef1f6" stroke-width="6"/>
        <circle cx="37" cy="37" r="{R}" fill="none" stroke="{color}" stroke-width="6"
                stroke-linecap="round" stroke-dasharray="{dash:.1f} {C-dash:.1f}"
                transform="rotate(-90 37 37)"/>
        <text x="37" y="37" text-anchor="middle" dominant-baseline="central"
              font-size="20" font-weight="800" fill="#1a1f2e">{value}</text>
      </svg>
      <div><div style="font-weight:800;font-size:14px;color:#1a1f2e">{label}</div>{sub_html}</div>
    </div>"""


def stat_card_html(value: str, label: str, color: str = "#1a1f2e", size: int = 26) -> str:
    """단순 스탯 카드 — 큰 숫자 + 대문자 라벨."""
    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 12px;
                text-align:center;box-shadow:0 1px 3px rgba(16,24,40,.04),0 4px 16px rgba(16,24,40,.04)">
      <div style="font-size:{size}px;font-weight:800;color:{color};line-height:1.1">{value}</div>
      <div style="font-size:10px;color:#8a93a5;text-transform:uppercase;letter-spacing:.6px;
                  margin-top:7px">{label}</div>
    </div>"""


# ── Team Analytics — 팀 퍼포먼스 레이더 (리그 백분위) ─────────────────────────
def team_trait_pcts(team: str, traits: pd.DataFrame) -> list[tuple[str, float]]:
    """팀의 TEAM_TRAITS 각 항목 리그 백분위(0~1, 1=리그 최고)."""
    out = []
    for label, col, direction, _ in TEAM_TRAITS:
        if col not in traits.columns or team not in traits.index:
            continue
        s = traits[col].dropna()
        if team not in s.index:
            continue
        asc = (direction == "low")
        rank = int(s.rank(ascending=asc, method="min")[team])
        nt = len(s)
        out.append((label, 1 - (rank - 1) / (nt - 1) if nt > 1 else 1.0))
    return out


def team_radar_html(team: str, traits: pd.DataFrame, color: str = ACCENT) -> str:
    """팀 특성 레이더 — 흰 카드 + SVG(라이트 테마). 각 축=리그 백분위."""
    import math
    cats = team_trait_pcts(team, traits)
    n = len(cats)
    if n < 3:
        return ""
    W = H = 430
    cx, cy, R = W / 2, H / 2, 125

    def pt(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang))

    grid = "".join(
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, g) for i in range(n)))}" '
        f'fill="none" stroke="#e4e8f0" stroke-width="1"/>'
        for g in (0.25, 0.5, 0.75, 1.0)
    )
    axes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#eef1f6" stroke-width="1"/>'
        for ex, ey in (pt(i, 1.0) for i in range(n))
    )
    data_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, (_, v) in enumerate(cats)))
    verts = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>'
                    for x, y in (pt(i, v) for i, (_, v) in enumerate(cats)))
    labels = []
    for i, (lbl, v) in enumerate(cats):
        lx, ly = pt(i, 1.18)
        anchor = "middle" if abs(lx - cx) <= 8 else ("end" if lx < cx else "start")
        labels.append(
            f'<text x="{lx:.1f}" y="{ly-5:.1f}" fill="#1a1f2e" font-size="12.5" font-weight="700" '
            f'text-anchor="{anchor}" dominant-baseline="central">{lbl}</text>'
            f'<text x="{lx:.1f}" y="{ly+9:.1f}" fill="#8a93a5" font-size="11" '
            f'text-anchor="{anchor}" dominant-baseline="central">{round(v*100)}</text>'
        )
    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:16px;padding:14px 10px 8px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05);text-align:center">
      <svg viewBox="0 0 {W} {H}" width="100%" style="max-width:380px">
        {grid}{axes}
        <polygon points="{data_pts}" fill="{color}22" stroke="{color}" stroke-width="2.5"
                 stroke-linejoin="round"/>
        {verts}{''.join(labels)}
      </svg>
    </div>"""


# AI Scout Report — 강점/약점 + 전술 스타일 + 개선 제안 (강·약점 기반 규칙)
TRAIT_STYLE = {
    "점유·빌드업": "점유 기반 (Possession)", "측면 공격": "측면 공격 (Wing-play)",
    "전방 압박": "전방 압박 (High press)", "롱볼 활용": "다이렉트 (Direct)",
    "개인 돌파": "개인 돌파 (Dribble)", "공중 장악": "제공권 장악 (Aerial)",
    "화력": "공격적 (Attacking)", "수비 견고함": "견고한 수비 (Solid)",
    "찬스 창출": "창의적 (Creative)",
}
IMPROVE_MAP = {
    "화력": "전방 득점력 보강 — 클리니컬한 9번",
    "수비 견고함": "수비 안정성 강화 — CB/수비형 미드필더",
    "점유·빌드업": "빌드업 강화 — 패스 좋은 미드필더",
    "공중 장악": "제공권 보강 — 높은 수비수/타깃맨",
    "측면 공격": "측면 침투 강화 — 윙어/크로서",
    "전방 압박": "압박 강도 보강 — 활동량 많은 미드필더",
    "찬스 창출": "창의성 보강 — 키패스/플레이메이커",
    "개인 돌파": "돌파 자원 보강 — 1대1 윙어",
    "롱볼 활용": "전개 다양화 — 롱패스 옵션",
}


def team_tactical_styles(team: str, traits: pd.DataFrame, formation: str,
                         thresh: float = 0.60, top: int = 4) -> list[str]:
    """리그 백분위 thresh 이상 강점 트레잇 → 전술 스타일 칩 (+포메이션 베이스)."""
    pcts = sorted(team_trait_pcts(team, traits), key=lambda x: x[1], reverse=True)
    styles = [TRAIT_STYLE[l] for l, v in pcts if v >= thresh and l in TRAIT_STYLE][:top]
    return [f"{formation} 베이스"] + styles


def team_improvements(weaknesses: list) -> list[str]:
    """팀 약점 → 개선 제안 텍스트."""
    return [IMPROVE_MAP.get(lbl, f"{lbl} 보강") for lbl, _ in weaknesses]


def ai_scout_report_html(strengths, weaknesses, styles, improvements) -> str:
    """AI Scout Report 카드 — 강점·약점·전술스타일 칩 + 개선 제안 리스트."""
    def chips(items, color):
        return "".join(
            f"<span style='display:inline-block;padding:4px 11px;margin:3px 5px 3px 0;"
            f"background:{color}14;color:{color};border:1px solid {color}40;border-radius:14px;"
            f"font-size:12.5px;font-weight:700;white-space:nowrap'>{t}</span>" for t in items
        )

    def block(icon, label, color, body):
        return (f"<div style='margin-bottom:13px'>"
                f"<div style='font-size:11px;font-weight:800;letter-spacing:.5px;color:{color};"
                f"margin-bottom:6px'>{icon} {label}</div>{body}</div>")

    improv = "".join(
        f"<div style='display:flex;gap:8px;align-items:flex-start;margin:5px 0;"
        f"font-size:13px;color:#3a4253'><span style='color:{ACCENT};font-weight:800'>→</span>"
        f"<span>{t}</span></div>" for t in improvements
    )
    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:16px;padding:18px 20px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)">
      <div style="font-size:15px;font-weight:800;color:#1a1f2e;margin-bottom:14px">⚡ AI Scout Report
        <span style="font-size:11px;font-weight:600;color:#8a93a5;margin-left:6px">리그 데이터 기반</span>
      </div>
      {block("✓", "STRENGTHS", "#16a34a", chips([l for l, _ in strengths], "#16a34a"))}
      {block("✕", "WEAKNESSES", "#ef4444", chips([l for l, _ in weaknesses], "#ef4444"))}
      {block("⚡", "TACTICAL STYLE", "#2563eb", chips(styles, "#2563eb"))}
      <div style="border-top:1px solid #eef1f6;padding-top:11px">
        <div style="font-size:11px;font-weight:800;letter-spacing:.5px;color:#d97706;
                    margin-bottom:6px">💡 RECOMMENDED IMPROVEMENTS</div>{improv}
      </div>
    </div>"""


# ── Star Players — 팀 내 ss_rating 상위 N명 ───────────────────────────────────
def pos_chip_color(pos: str) -> str:
    p = str(pos).upper()
    if p in ("ST", "RW", "LW", "W", "AM", "WING_AM") or "FW" in p: return "#ef4444"
    if p in ("CM", "DM", "CAM_CM") or "MF" in p: return "#16a34a"
    if p in ("CB", "RB", "LB", "FB") or "DF" in p: return "#2563eb"
    if "GK" in p: return "#d97706"
    return "#6b7280"


def team_star_players(team: str, full: pd.DataFrame, fine_map: dict, sid_map: dict,
                      n: int = 5, min_minutes: int = 450) -> list[dict]:
    """팀 내 ss_rating 상위 N명. OVR = 리그 전체 ss_rating 백분위 → 1~99."""
    pool = full[(full["minutes"] >= min_minutes) & full["ss_rating"].notna()]
    pool = pool.sort_values("minutes", ascending=False).drop_duplicates("player")
    if pool.empty:
        return []
    t = pool[pool["squad"] == team].sort_values("ss_rating", ascending=False).head(n)
    out = []
    for i, (_, r) in enumerate(t.iterrows()):
        name = r["player"]
        pos = fine_map.get(name)
        if not pos or (isinstance(pos, float) and pd.isna(pos)):
            pos = "GK" if "GK" in str(r.get("pos", "")) else str(r.get("pos", "")).split(",")[0].strip()
        out.append({
            "rank": i + 1, "name": name, "pos": str(pos),
            "ovr": player_ovr(r.get("market_value_eur"), r.get("ss_rating"),
                              r.get("minutes"), r.get("goals"), r.get("assists")),
            "rating": f"{float(r['ss_rating']):.2f}",
            "sid": _photo(sid_map.get(name, ""), r.get("tm_photo")),
            "tcol": team_color(team),
            "nat": r.get("nationality"),
            "value": fmt_value(r.get("market_value_eur")),
            "age": int(r["age"]) if pd.notna(r.get("age")) else None,
        })
    return out


def star_card_html(s: dict) -> str:
    """스타 플레이어 1장 — 랭크#·사진·이름·포지션칩·OVR (세로 카드)."""
    oc = rating_color(s["ovr"])
    pc = pos_chip_color(s["pos"])
    disc = (f"background-image:url('{s['sid']}'),linear-gradient(135deg,{s['tcol']},#0b0f17);"
            if s["sid"] else f"background:{s['tcol']};")
    star = ("<div style='position:absolute;top:12px;right:14px;font-size:15px;"
            "color:#f5b301'>★</div>") if s["rank"] == 1 else ""
    name = s["name"].split()[-1] if len(s["name"]) > 14 else s["name"]
    nat_chip = flag_chip(s.get("nat"))
    val = s.get("value", "—")
    return f"""
    <div style="position:relative;background:#fff;border:1px solid #e4e8f0;border-radius:16px;
                padding:18px 14px 16px;text-align:center;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)">
      <div style="position:absolute;top:12px;left:14px;font-size:12px;font-weight:800;
                  color:#c2c8d4">#{s['rank']}</div>{star}
      <div style="width:64px;height:64px;border-radius:50%;margin:6px auto 0;{disc}
                  background-size:cover;background-position:center;border:2px solid #e4e8f0"></div>
      <div style="font-weight:800;font-size:14px;color:#1a1f2e;margin-top:10px;
                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
      <div style="margin-top:6px">
        <span style="display:inline-block;padding:2px 9px;background:{pc}1a;color:{pc};
                     border-radius:6px;font-size:11px;font-weight:800">{s['pos']}</span>{nat_chip}
      </div>
      <div style="font-size:30px;font-weight:800;color:{oc};margin-top:10px;line-height:1">{s['ovr']}</div>
      <div style="font-size:9px;color:#8a93a5;letter-spacing:1px">OVR · 평점 {s['rating']}</div>
      <div style="font-size:12px;font-weight:800;color:#16a34a;margin-top:6px">{val}</div>
    </div>"""


# ── Squad Depth Chart — 포지션별 주전/백업 + 깊이 점수 ────────────────────────
# 주전=실제 XI(placements), 백업=벤치(bench_pls). fine_group 버킷으로 묶고,
# 깊이 점수 = 0.7·백업 최고 OVR + 0.3·스쿼드 규모(최대 100). 백업 없으면 얕음.
def squad_depth_html(placements: list, bench_pls: list,
                     ovr_map: dict, fine_map: dict) -> str:
    BUCKETS = [("GK", "GK"), ("CB", "CB"), ("RB", "RB"), ("LB", "LB"),
               ("DM", "DM"), ("CM", "CM"), ("AM", "AM"),
               ("RW", "RW"), ("LW", "LW"), ("W", "WF"),
               ("ST", "ST")]
    valid = {b for b, _ in BUCKETS}

    def bucket_of(name, kind):
        if kind == "GK":
            return "GK"
        b = fine_map.get(name)
        return b if b in valid else None

    def ovr(n):
        return ovr_map.get(n)

    data = {b: {"s": [], "k": []} for b, _ in BUCKETS}
    for p in placements:
        b = bucket_of(p["full"], p.get("kind"))
        if b:
            data[b]["s"].append(p["full"])
    for p in bench_pls:
        b = bucket_of(p["full"], p.get("kind"))
        if b:
            data[b]["k"].append(p["full"])

    def name_tag(n):
        o = ovr(n)
        c = rating_color(o) if o else "#9aa3b2"
        ostr = f"<b style='color:{c}'>{o}</b>" if o else ""
        return (f"<span style='display:inline-block;margin:2px 12px 2px 0;font-size:13px;color:#1a1f2e'>"
                f"<span style='color:{c}'>●</span> {n.split()[-1]} {ostr}</span>")

    rows = ""
    for code, _label in BUCKETS:
        s = sorted(data[code]["s"], key=lambda n: (ovr(n) or 0), reverse=True)
        k = sorted(data[code]["k"], key=lambda n: (ovr(n) or 0), reverse=True)
        if not s and not k:
            continue
        b_ovr = ovr(k[0]) if k else None
        count = len(s) + len(k)
        depth = round(0.7 * (b_ovr if b_ovr else 38) + 0.3 * min(100, count * 22))
        dcol = "#16a34a" if depth >= 70 else "#d97706" if depth >= 55 else "#ef4444"
        pc = pos_chip_color(code)
        s_html = "".join(name_tag(n) for n in s) or "<span style='color:#b6bdc9'>—</span>"
        k_html = "".join(name_tag(n) for n in k) or "<span style='color:#b6bdc9'>—</span>"
        rows += (
            f"<tr>"
            f"<td><span style='display:inline-block;padding:3px 9px;background:{pc}1a;color:{pc};"
            f"border-radius:6px;font-size:11px;font-weight:800'>{code}</span></td>"
            f"<td>{s_html}</td><td>{k_html}</td>"
            f"<td style='min-width:140px'><div style='display:flex;align-items:center;gap:8px'>"
            f"<div style='flex:1;height:6px;background:#eef1f6;border-radius:4px'>"
            f"<div style='height:100%;width:{depth}%;background:{dcol};border-radius:4px'></div></div>"
            f"<b style='color:{dcol};font-size:13px'>{depth}</b></div></td></tr>"
        )
    return f"""
    <style>
      .depthtbl{{width:100%;border-collapse:collapse;font-family:sans-serif}}
      .depthtbl th{{padding:10px;font-size:11px;color:#8a93a5;letter-spacing:.5px;text-align:left;
                    border-bottom:1px solid #e4e8f0}}
      .depthtbl td{{padding:11px 10px;border-bottom:1px solid #eef1f6;vertical-align:middle}}
      .depthtbl tr:last-child td{{border-bottom:none}}
    </style>
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:16px;padding:6px 12px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)">
      <table class="depthtbl">
        <thead><tr><th>POS</th><th>STARTER</th><th>ROTATION / BACKUP</th><th>DEPTH</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


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


# 선수 OVR — Sofascore 평점(객관적 절대 지표)을 고정 스케일로 1~99 변환.
# 백분위(상대 순위)와 달리, 동일 평점이면 팀·시즌 무관 동일 OVR → 객관적·비교가능.
# 앵커: ss 6.3 → OVR 60, ss 7.7 → OVR 92 (선형, 40~99 clamp).
#   ≈6.8(중앙값)→72 · 7.0→76 · 7.2→81 · 7.46(Rice)→87 · 7.61(리그1위)→90
_OVR_LO_R, _OVR_LO_O = 6.3, 60
_OVR_HI_R, _OVR_HI_O = 7.7, 92
_OVR_SLOPE = (_OVR_HI_O - _OVR_LO_O) / (_OVR_HI_R - _OVR_LO_R)


def ovr_from_rating(ss) -> int | None:
    """Sofascore 평점(≈6.3~7.7) → OVR 1~99. 결측이면 None."""
    if ss is None or pd.isna(ss):
        return None
    ovr = _OVR_LO_O + _OVR_SLOPE * (float(ss) - _OVR_LO_R)
    return int(max(40, min(99, round(ovr))))


def ovr_from_value(v):
    """시장가치(EUR) → OVR(로그 스케일, 미clamp float). 결측이면 None.
    앵커: €1M→62 · €10M→75 · €30M→81 · €75M→86 · €100M→88 · €200M→92."""
    if v is None or pd.isna(v) or float(v) <= 0:
        return None
    import math
    return 13.04 * math.log10(float(v)) - 16.24


def perf_ovr(ss_rating, goals=0, assists=0):
    """시즌 퍼포먼스 OVR — 평점 기반(60~92) + 골·도움 기여 보너스(최대 +8).
    기여 보너스는 가산만(수비수가 골 없다고 깎이지 않음). 평점 없으면 None."""
    base = ovr_from_rating(ss_rating)
    if base is None:
        return None
    g = float(goals) if (goals is not None and not pd.isna(goals)) else 0.0
    a = float(assists) if (assists is not None and not pd.isna(assists)) else 0.0
    return base + min(8.0, (g + a) * 0.4)


def player_ovr(value, ss_rating=None, minutes=0, goals=0, assists=0) -> int:
    """OVR = 시장가치(품질) 50% + 시즌 퍼포먼스(평점+골·도움) 50% 블렌드.
    단, 출전 적은 선수는 폼 신뢰도가 낮아 퍼포먼스 비중을 출전시간에 비례 축소
    (min/1200, 1500분↑이면 완전 50/50). 한쪽 데이터만 있으면 그쪽만 사용."""
    vov = ovr_from_value(value)               # 가치 OVR (float) 또는 None
    pov = perf_ovr(ss_rating, goals, assists)  # 퍼포먼스 OVR (float) 또는 None
    if vov is None and pov is None:
        return 60
    if vov is None:
        return int(max(48, min(95, round(pov))))
    if pov is None:
        return int(max(48, min(95, round(vov))))
    rel = min(1.0, (float(minutes) if (minutes and not pd.isna(minutes)) else 0) / 1200)
    w = 0.5 * rel                              # 퍼포먼스 가중치(최대 0.5)
    return int(max(48, min(95, round((1 - w) * vov + w * pov))))


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
                        "sid": _photo(r.get("sofa_id"), drow.iloc[0].get("tm_photo") if not drow.empty else None), "tcol": team_color(team),
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
                        "sid": _photo(r.get("sofa_id"), drow.iloc[0].get("tm_photo") if not drow.empty else None), "tcol": team_color(team),
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
                        "num": "", "sid": _photo("", prow.get("tm_photo")), "tcol": tcol,
                        "role": role.split(" (")[0], "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": int(r["minutes"]), "full": r["player"], "tip": tip})
    if gk is not None:
        save = gk.get("gk_save_pct")
        chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
        out.append({"name": gk["player"].split()[-1], "x": 50, "y": GK_Y, "kind": "GK",
                    "abbr": "GK", "num": "", "sid": _photo("", gk.get("tm_photo")), "tcol": tcol,
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

formations_cfg = load_formations()
FORM_OPTIONS = ["4-3-3", "4-2-3-1", "4-4-2", "3-4-3", "3-4-2-1", "3-5-2", "4-1-4-1"]

# 사이드바 네비 메뉴 (레퍼런스 좌측 네비) — 라디오를 nav 항목 스타일로 CSS 변환.
# Formation은 Team Overview에 통합(레퍼런스 Team Overview 구성).
NAV = ["⚡ Team Overview", "📊 Analytics", "👤 Player Detail",
       "📋 Squad Depth", "🔁 Transfer", "📅 Schedule"]
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

    # ── 메뉴 (필터 아래에 배치) ──────────────────────────────────────────────
    st.markdown("<div style='border-bottom:1px solid rgba(255,255,255,.08);margin:16px 0 12px'></div>",
                unsafe_allow_html=True)
    st.markdown("<div class='side-label'>MENU</div>", unsafe_allow_html=True)
    _nav = st.radio("nav", NAV, label_visibility="collapsed", key="nav_menu")

# 메인 상단 팀 배지 헤더 (사이드바에서 team 확정 후 렌더)
st.markdown(team_header_html(team), unsafe_allow_html=True)

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

# 실측 슬롯이 있으면 정확 배치, 없으면 휴리스틱 밴드
placements = None
if has_real:
    placements = placements_from_slots(team, slots_df, full, pct, formation)
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


def bench_placements(team: str, xi_all: set[str]) -> list[dict]:
    """XI에 없는 선수들 → 벤치 토큰 배치 리스트 (사진 포함).
    시즌 중 이적해 떠난 선수(left_out)는 제외 — 별도 '이적' 섹션에서 표기."""
    t = full[full["squad"] == team].copy()
    bench = t[~t["player"].isin(xi_all) & ~t["player"].isin(left_out)] \
        .sort_values("minutes", ascending=False)
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
        sid = _photo(sid_map.get(name, ""), p.get("tm_photo"))
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


def departed_placements(team: str) -> list[dict]:
    """시즌 중 이 팀을 떠난 선수 토큰 (→ 현 소속 표기). bench_strip_html로 렌더."""
    if not left_out:
        return []
    t = full[full["squad"] == team]
    dep = t[t["player"].isin(left_out)].sort_values("minutes", ascending=False)
    tcol = team_color(team)
    out = []
    for _, p in dep.iterrows():
        name = p["player"]
        dest = left_out.get(name, "")
        pos = str(p.get("pos", ""))
        if "GK" in pos:
            kind, abbr = "GK", "GK"
        else:
            kind = {"FW": "FWD", "MF": "MID", "DF": "DEF"}.get(position_group(pos), "MID")
            abbr = pos.split(",")[0].strip()[:3]
        out.append({
            "name": name.split()[-1], "full": name,
            "kind": kind, "abbr": abbr, "num": "",
            "sid": _photo("", p.get("tm_photo")), "tcol": tcol,
            "role": f"→ {dest}",
            "tip": f"{int(p['minutes'])}분 · {dest}(으)로 이적",
            "minutes": int(p["minutes"]),
        })
    return out


def bench_strip_html(subs: list[dict], title: str = "벤치 &amp; 백업") -> str:
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
      <div class="bench-title">{title} ({len(subs)}명)</div>
      <div class="bench-row">{''.join(cards)}</div>
    </div>
    """


bench_pls = bench_placements(team, xi_all)
departed_pls = departed_placements(team)

# ── 공통 계산 (탭 렌더 전) ────────────────────────────────────────────────────
_standings = load_standings()
_traits = team_traits_table(DATA_PATH.stat().st_mtime)
_str, _weak = team_characteristics(team, _traits)     # _weak: Transfer 탭에서 재사용
_fine_map = dict(zip(dff["player"], dff["fl_group"]))
_sid_all = {}
if slots_df is not None:
    for _, _r in slots_df.iterrows():
        _sid_all[_r["player"]] = str(_r.get("sofa_id", "") or "")
_raw_rating = dict(zip(full["player"], full["ss_rating"]))
# 통합 OVR(시장가치 기반 + 폼 보정) — 전 섹션 공통 사용.
# 시즌 중 이적 선수는 행이 여러 개 → 시장가치 있는 행 + 출전 많은 행을 대표로 선택
# (예: Eze는 Arsenal €65m 행을 써야 함, Crystal Palace 무가치 행 아님).
_rep = (full.assign(_mv=full["market_value_eur"].notna())
        .sort_values(["_mv", "minutes"], ascending=[False, False])
        .drop_duplicates("player"))
_ovr_map = {r.player: player_ovr(r.market_value_eur, r.ss_rating, r.minutes,
                                 r.goals, r.assists)
            for r in _rep.itertuples(index=False)}

SCHEDULE_PATH = Path(__file__).resolve().parent / "data" / "schedule_2025_2026.csv"


@st.cache_data
def load_schedule() -> pd.DataFrame | None:
    if not SCHEDULE_PATH.exists():
        return None
    return pd.read_csv(SCHEDULE_PATH)


# ── 섹션 렌더 — 사이드바 _nav 선택에 따라 한 섹션만 표시 ──────────────────────
# 1: Team Overview — 레이팅 도넛 + 스탯 카드 + Star Players
if _nav == NAV[0]:
    sec_title("Team Overview", f"{team} · Premier League · 2025/26")

    _rcols = st.columns(4)
    for _c, (_lbl, _val, _sub) in zip(_rcols, team_ratings(team, _traits, _standings)):
        with _c:
            st.markdown(donut_card_html(_lbl, _val, _sub), unsafe_allow_html=True)

    if _standings is not None and (_standings["squad"] == team).any():
        _s = _standings[_standings["squad"] == team].iloc[0]
        _gd = int(_s["gd"]); _gd_str = f"+{_gd}" if _gd > 0 else str(_gd)
        _stats = [
            (f"{int(_s['rank'])}위", "League Position", "#d97706", 26),
            (f"{int(_s['points'])}", "Points", "#1a1f2e", 26),
            (f"{int(_s['won'])}-{int(_s['drawn'])}-{int(_s['lost'])}", "W-D-L", "#1a1f2e", 22),
            (f"{int(_s['gf'])}", "Goals For", "#16a34a", 26),
            (f"{int(_s['ga'])}", "Goals Against", "#ef4444", 26),
            (_gd_str, "Goal Diff", "#2563eb", 26),
        ]
        for _c, (_v, _l, _col, _sz) in zip(st.columns(6), _stats):
            with _c:
                st.markdown(stat_card_html(_v, _l, _col, _sz), unsafe_allow_html=True)

    _stars = team_star_players(team, full, _fine_map, _sid_all, n=5)
    if _stars:
        st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
        sec_title("Star Players", "AI 종합 평점(ss_rating) 상위 5명 · OVR=객관 평점 환산")
        for _c, _sp in zip(st.columns(5), _stars):
            with _c:
                st.markdown(star_card_html(_sp), unsafe_allow_html=True)

    # Formation & Tactical Shape — 주전 XI 보드 + 벤치 (레퍼런스 Team Overview 구성)
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    _tag = (" · 메인" if formation == main_form else " · 서브") if sub_form else ""
    _src = "실측 라인업" if has_real else "휴리스틱"
    sec_title("Formation & Tactical Shape",
              f"주전 XI ({formation}){_tag} · {_src} · 색=라인(🔴공격 🟠중원 🔵수비 🟢GK)")
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

# 2: Analytics — 팀 퍼포먼스 레이더 + AI 스카우트 리포트
elif _nav == NAV[1]:
    sec_title("Team Analytics", "리그 20팀 대비 팀 퍼포먼스 · 강점·약점·전술 스타일·개선점")
    _aL, _aR = st.columns([1, 1])
    with _aL:
        st.markdown("**Performance Radar** · 각 축 = 리그 백분위(100=리그 최고)")
        st.markdown(team_radar_html(team, _traits), unsafe_allow_html=True)
    with _aR:
        if _str or _weak:
            _styles = team_tactical_styles(team, _traits, formation)
            _improv = team_improvements(_weak)
            st.markdown(ai_scout_report_html(_str, _weak, _styles, _improv), unsafe_allow_html=True)
        else:
            st.info("강점/약점 데이터를 계산할 수 없습니다.")

# 3: Player Detail — 선수 능력치/레이더/유사선수
elif _nav == NAV[2]:
    sec_title("Player Detail", "선수별 능력치 · 레이더 · 스타일 유사 선수")
    bench_all = [p["full"] for p in bench_pls]
    pool = list(dict.fromkeys(xi_gk + xi_players + bench_all))
    pick = st.selectbox("선수 선택", pool)

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
        emb = build_embeddings(dff)
        sim = find_similar(dff, emb, pick, top=5, same_position=same_pos, alpha=alpha)
        sim_show = sim[["player", "squad", "pos", "fl_group", "style_sim", "perf_score", "score"]].copy()
        sim_show.columns = ["선수", "팀", "포지션", "역할", "스타일", "퍼포먼스", "종합"]
        for col in ["스타일", "퍼포먼스", "종합"]:
            sim_show[col] = (sim_show[col] * 100).round(1).astype(str) + "%"
        st.dataframe(sim_show, hide_index=True, use_container_width=True)

# 4: Squad Depth Chart — 포지션별 주전/백업 + 깊이 점수
elif _nav == NAV[3]:
    sec_title("Squad Depth Chart", "포지션별 주전/백업 + 깊이 점수 · OVR=객관 평점 환산")
    st.markdown(squad_depth_html(placements, bench_pls, _ovr_map, _fine_map),
                unsafe_allow_html=True)

# 5: Transfer Recommendations — 팀 적합 영입 후보
elif _nav == NAV[4]:
    sec_title("Transfer Recommendations",
              f"{team} 약점 보강 + 스타일 적합 · EPL 내 후보 · AI 추정 (시뮬레이션 아님)")
    _recs = recommend_signings(team, pct, _weak, _sid_all, _raw_rating, n=6)
    if not _recs:
        st.info("추천 후보를 계산할 수 없습니다 — 팀 약점 또는 후보 데이터가 부족합니다.")
    else:
        for _i in range(0, len(_recs), 3):
            _cols = st.columns(3)
            for _col, _rec in zip(_cols, _recs[_i:_i + 3]):
                with _col:
                    st.markdown(signing_card_html(_rec), unsafe_allow_html=True)

# 6: Schedule — 시즌 전적 테이블
elif _nav == NAV[5]:
    _schedule = load_schedule()
    team_sched = (_schedule[_schedule["squad"] == team].sort_values("gw").copy()
                  if _schedule is not None else None)
    if team_sched is None or team_sched.empty:
        st.info("시즌 전적 데이터가 없습니다.")
    else:
        sec_title(f"{team} — 2025/26 시즌 전적", f"{len(team_sched)}경기")

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
                f"<td style='text-align:center;color:#888'>{int(r['gw'])}</td>"
                f"<td style='color:#1a1f2e'>{r['date']}</td>"
                f"<td>{ha_badge}</td>"
                f"<td style='font-weight:600;color:#1a1f2e'>{r['opponent']}</td>"
                f"<td style='text-align:center;font-weight:700;font-size:15px;"
                f"color:{score_color}'>{r['score']}</td>"
                f"<td style='text-align:center'>{result_badge}</td>"
                f"</tr>"
            )

        table_html = f"""
        <style>
          .match-table {{ width:100%; border-collapse:collapse; font-family:sans-serif;
                         font-size:13px; color:#1a1f2e; }}
          .match-table th {{ background:#f1f3f7; color:#8a93a5; font-weight:700;
                             padding:8px 10px; text-align:left; border-bottom:1px solid #e4e8f0; }}
          .match-table td {{ padding:7px 10px; border-bottom:1px solid #eef1f6; }}
          .match-table tr:hover td {{ background:#f7f9fc; }}
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
