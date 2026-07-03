"""
Common UI constants and low-level helpers.

Shared across all tabs (Overview, Analytics, Player, Pitch, Transfers, …).
Lowest layer of src/ui — depends only on stdlib/pandas/streamlit, never on the
other ui modules. Move shared HTML/format primitives here.
"""

import html

import pandas as pd
from unidecode import unidecode

# streamlit 은 레거시 Streamlit 앱(app.py) 렌더 헬퍼(_iframe·sec_title)에서만 필요.
# 데이터/뉴스 수집 체인(fetch_news_daily → ui.news → ui.common)은 team_color 만 쓰므로
# 여기서 top-level import 하지 않는다(그러면 GH Actions 러너에 streamlit 불필요).

ACCENT = "#e8344e"   # 레드 — 로고/액티브 네비/섹션 바

# 밴드 색상: 수비(파랑) → 중원(주황) → 공격(빨강)
BAND_DEF, BAND_MID, BAND_FWD = "#4d80e0", "#e0a23a", "#e0584c"

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

# 구단 풀네임 + 홈구장 수용인원 (사실 데이터)
TEAM_EXTRA: dict[str, tuple[str, int]] = {
    "Arsenal": ("Arsenal FC", 60704), "Aston Villa": ("Aston Villa FC", 42657),
    "Bournemouth": ("AFC Bournemouth", 11307), "Brentford": ("Brentford FC", 17250),
    "Brighton": ("Brighton & Hove Albion", 31800), "Burnley": ("Burnley FC", 21944),
    "Chelsea": ("Chelsea FC", 40343), "Crystal Palace": ("Crystal Palace FC", 25486),
    "Everton": ("Everton FC", 52888), "Fulham": ("Fulham FC", 29600),
    "Leeds United": ("Leeds United FC", 37792), "Liverpool": ("Liverpool FC", 61276),
    "Manchester City": ("Manchester City FC", 53400), "Manchester Utd": ("Manchester United FC", 74310),
    "Newcastle United": ("Newcastle United FC", 52305), "Nottingham Forest": ("Nottingham Forest FC", 30404),
    "Sunderland": ("Sunderland AFC", 49000), "Tottenham Hotspur": ("Tottenham Hotspur FC", 62850),
    "West Ham United": ("West Ham United FC", 62500), "Wolves": ("Wolverhampton Wanderers FC", 31750),
}


def team_color(team: str) -> str:
    return TEAM_COLOR.get(team, "#444a55")


def team_logo(team: str) -> str:
    """Transfermarkt 구단 크레스트 URL (verein id 기반). 없으면 빈 문자열."""
    info = {
        "Arsenal": 11, "Aston Villa": 405, "Bournemouth": 989, "Brentford": 1148,
        "Brighton": 1237, "Burnley": 1132, "Chelsea": 631, "Crystal Palace": 873,
        "Everton": 29, "Fulham": 931, "Leeds United": 399, "Liverpool": 31,
        "Manchester City": 281, "Manchester Utd": 985, "Newcastle United": 762,
        "Nottingham Forest": 703, "Sunderland": 289, "Tottenham Hotspur": 148,
        "West Ham United": 379, "Wolves": 543,
    }.get(team)
    return f"https://tmssl.akamaized.net/images/wappen/head/{info}.png" if info else ""


def _norm(s) -> str:
    return unidecode(str(s)).lower().strip()


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


def avatar(photo, tcol: str = "#444a55", size: int = 46,
           extra: str = "", border: str = "2px solid #e4e8f0") -> str:
    """원형 선수 아바타 — <img> 태그 기반(st.markdown·iframe 양쪽에서 사진 로드됨).
    CSS background-image는 Streamlit이 sanitize하므로 반드시 <img>를 쓴다."""
    has = isinstance(photo, str) and photo.startswith("http")
    img = (f"<img src=\"{photo}\" referrerpolicy=\"no-referrer\" "
           f"onerror=\"this.style.display='none'\" "
           f"style=\"width:100%;height:100%;object-fit:cover;display:block\"/>") if has else ""
    return (f"<div style=\"width:{size}px;height:{size}px;border-radius:50%;overflow:hidden;"
            f"background:{tcol};border:{border};{extra}\">{img}</div>")


def portrait_photo(photo, tcol: str = "#444a55", width: int = 62, height: int = 74,
                   extra: str = "", radius: int = 14,
                   border: str = "3px solid #fff", label: str = "") -> str:
    """Portrait-safe photo block for report cards. Uses contain so faces are not cropped."""
    has = isinstance(photo, str) and photo.startswith("http")
    bg = f"linear-gradient(135deg,{tcol}22,#f8fafc)"
    if has:
        content = (
            f"<img src=\"{photo}\" alt=\"{html.escape(label)}\" loading=\"lazy\" "
            f"referrerpolicy=\"no-referrer\" onerror=\"this.style.display='none'\" "
            f"style=\"width:100%;height:100%;object-fit:contain;object-position:center top;"
            f"display:block\"/>"
        )
    else:
        initials = html.escape(str(label or "")[:2].upper())
        content = f"<span style=\"font-size:18px;font-weight:950;color:#fff\">{initials}</span>"
        bg = f"radial-gradient(circle at 35% 25%,rgba(255,255,255,.34),rgba(255,255,255,0) 54%),{tcol}"
    return (
        f"<div style=\"width:{width}px;height:{height}px;border-radius:{radius}px;overflow:hidden;"
        f"background:{bg};border:{border};display:flex;align-items:center;justify-content:center;"
        f"flex:none;{extra}\">{content}</div>"
    )


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


def fee_label(fee_eur, fee_text) -> str:
    """이적료 표시 — 금액 있으면 €표기, 없으면 임대/자유/임대복귀 등 텍스트화."""
    if fee_eur is not None and not pd.isna(fee_eur) and float(fee_eur) > 0:
        return fmt_value(fee_eur)
    t = str(fee_text or "").lower()
    if "end of loan" in t:
        return "임대복귀"
    if "loan" in t:
        return "임대"
    if "free" in t:
        return "자유이적"
    return "—"


def _grid(cards: list, ncols: int) -> str:
    return (f"<div style='display:grid;grid-template-columns:repeat({ncols},1fr);gap:14px'>"
            + "".join(cards) + "</div>")


def rating_color(v: int) -> str:
    if v >= 85: return "#2563eb"   # 엘리트(파랑)
    if v >= 70: return "#16a34a"   # 강함(초록)
    if v >= 55: return "#d97706"   # 평균(주황)
    return "#ef4444"               # 약함(빨강)


def pos_chip_color(pos: str) -> str:
    p = str(pos).upper().split("/")[0]
    if p in ("ST", "RW", "LW", "W", "AM", "WING_AM") or "FW" in p: return "#ef4444"
    if p in ("CM", "DM", "CAM_CM") or "MF" in p: return "#16a34a"
    if p in ("CB", "RB", "LB", "FB") or "DF" in p: return "#2563eb"
    if "GK" in p: return "#d97706"
    return "#6b7280"


def _iframe(inner_html: str, height: int, scrolling: bool = False) -> None:
    """카드 HTML을 components.html(iframe)로 렌더 — st.markdown과 달리 외부 이미지
    (background-image)가 sanitize되지 않아 선수 사진이 정상 표시된다."""
    import streamlit as st  # 레거시 앱 전용 — 지연 import
    st.components.v1.html(
        "<style>body{margin:0;background:#eef1f6;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}</style>" + inner_html,
        height=height, scrolling=scrolling,
    )


def sec_title(title: str, sub: str = "") -> None:
    """레퍼런스의 '레드 세로 바 + 제목' 섹션 헤더. sub는 회색 보조설명."""
    import streamlit as st  # 레거시 앱 전용 — 지연 import
    sub_html = f"<div style='color:#8a93a5;font-size:13px;margin-top:2px'>{sub}</div>" if sub else ""
    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:flex-start;margin:6px 0 14px'>"
        f"<div style='width:4px;align-self:stretch;min-height:26px;background:{ACCENT};"
        f"border-radius:3px'></div>"
        f"<div><div style='font-size:22px;font-weight:800;color:#1a1f2e;"
        f"letter-spacing:-.4px'>{title}</div>{sub_html}</div></div>",
        unsafe_allow_html=True,
    )


def _form_dots_html(results: list[str]) -> str:
    col = {"W": "#16a34a", "D": "#9aa3b2", "L": "#ef4444"}
    return "".join(
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:26px;'
        f'height:26px;border-radius:7px;background:{col.get(r, "#9aa3b2")};color:#fff;font-size:12px;'
        f'font-weight:800;margin-right:5px">{r}</span>'
        for r in results
    )


def _progress_bar_html(score: int, color: str, width_pct: int | None = None) -> str:
    w = width_pct if width_pct is not None else max(8, min(100, score))
    return (
        f'<div style="height:8px;background:#eef1f6;border-radius:999px;overflow:hidden;margin-top:7px">'
        f'<div style="width:{w}%;height:100%;background:{color};border-radius:999px"></div></div>'
    )
