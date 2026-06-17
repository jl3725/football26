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
from src.ui.common import team_color, team_logo, TEAM_EXTRA, _form_dots_html, _progress_bar_html


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

# TEAM_COLOR, TEAM_EXTRA, team_color, team_logo etc. moved to src/ui/common.py
# (imported at top of file)

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
TEAM_INFO: dict[str, dict] = {
    "Arsenal": {"vid": 11, "city": "런던 (북부·홀로웨이)", "stadium": "에미레이츠 스타디움",
                "founded": 1886, "nick": "The Gunners",
                "desc": "북런던 명문. 아르테타 체제의 점유·고강도 전방압박으로 우승에 도전한다."},
    "Aston Villa": {"vid": 405, "city": "버밍엄", "stadium": "빌라 파크", "founded": 1874,
                    "nick": "The Villans", "desc": "잉글랜드 축구 창립 멤버. 에메리 부임 후 유럽대항전 단골로 부활."},
    "Bournemouth": {"vid": 989, "city": "본머스", "stadium": "비탈리티 스타디움", "founded": 1899,
                    "nick": "The Cherries", "desc": "남부 해안 소도시 클럽. 이라올라의 강한 압박·전환 축구."},
    "Brentford": {"vid": 1148, "city": "런던 (서부)", "stadium": "지테크 커뮤니티 스타디움",
                  "founded": 1889, "nick": "The Bees", "desc": "데이터·셋피스 강점의 스마트 운영 클럽."},
    "Brighton": {"vid": 1237, "city": "브라이턴 앤 호브", "stadium": "아메리칸 익스프레스 스타디움",
                 "founded": 1901, "nick": "The Seagulls", "desc": "영입·육성 모델의 모범. 공격적 점유 축구."},
    "Burnley": {"vid": 1132, "city": "번리 (랭커셔)", "stadium": "터프 무어", "founded": 1882,
                "nick": "The Clarets", "desc": "전통의 랭커셔 클럽. 25/26 시즌 승격."},
    "Chelsea": {"vid": 631, "city": "런던 (풀럼)", "stadium": "스탬퍼드 브리지", "founded": 1905,
                "nick": "The Blues", "desc": "대규모 영입으로 젊은 스쿼드를 리빌딩 중인 서런던 명문."},
    "Crystal Palace": {"vid": 873, "city": "런던 (남부)", "stadium": "셀허스트 파크", "founded": 1905,
                       "nick": "The Eagles", "desc": "열성 팬덤의 남런던 클럽. 24/25 FA컵 우승으로 첫 메이저 트로피."},
    "Everton": {"vid": 29, "city": "리버풀", "stadium": "힐 디킨슨 스타디움 (25/26 신축 이전)",
                "founded": 1878, "nick": "The Toffees", "desc": "리버풀 연고 전통 명문. 25/26 브램리무어 독 신구장으로 이전."},
    "Fulham": {"vid": 931, "city": "런던 (풀럼)", "stadium": "크레이븐 코티지", "founded": 1879,
               "nick": "The Cottagers", "desc": "템스강변 크레이븐 코티지를 쓰는 서런던 클럽."},
    "Leeds United": {"vid": 399, "city": "리즈 (요크셔)", "stadium": "엘런드 로드", "founded": 1919,
                     "nick": "The Whites", "desc": "요크셔 명문. 25/26 시즌 승격."},
    "Liverpool": {"vid": 31, "city": "리버풀", "stadium": "안필드", "founded": 1892,
                  "nick": "The Reds", "desc": "유럽 최고 명문 중 하나. 강한 압박과 빠른 측면 전개."},
    "Manchester City": {"vid": 281, "city": "맨체스터", "stadium": "에티하드 스타디움", "founded": 1880,
                        "nick": "The Citizens", "desc": "과르디올라의 점유 지배 축구. 최근 잉글랜드 최강 클럽."},
    "Manchester Utd": {"vid": 985, "city": "맨체스터", "stadium": "올드 트래퍼드", "founded": 1878,
                       "nick": "The Red Devils", "desc": "세계적 명문. 영광 재건을 위한 리빌딩 진행 중."},
    "Newcastle United": {"vid": 762, "city": "뉴캐슬어폰타인", "stadium": "세인트 제임스 파크",
                         "founded": 1892, "nick": "The Magpies", "desc": "북동부 열성 클럽. 대규모 투자 이후 상위권 도약."},
    "Nottingham Forest": {"vid": 703, "city": "노팅엄", "stadium": "시티 그라운드", "founded": 1865,
                          "nick": "Forest", "desc": "두 차례 유러피언컵을 들어올린 역사적 클럽."},
    "Sunderland": {"vid": 289, "city": "선덜랜드", "stadium": "스타디움 오브 라이트", "founded": 1879,
                   "nick": "The Black Cats", "desc": "북동부 열성 클럽. 25/26 시즌 승격."},
    "Tottenham Hotspur": {"vid": 148, "city": "런던 (북부·토트넘)", "stadium": "토트넘 홋스퍼 스타디움",
                          "founded": 1882, "nick": "Spurs", "desc": "북런던 클럽. 24/25 유로파리그 우승."},
    "West Ham United": {"vid": 379, "city": "런던 (동부·스트랫퍼드)", "stadium": "런던 스타디움",
                        "founded": 1895, "nick": "The Hammers", "desc": "이스트런던 클럽. 22/23 컨퍼런스리그 우승."},
    "Wolves": {"vid": 543, "city": "울버햄프턴", "stadium": "몰리뉴 스타디움", "founded": 1877,
               "nick": "Wolves", "desc": "미들랜즈 전통 클럽. 강한 포르투갈 커넥션."},
}


# team_logo moved to src/ui/common.py


def team_logo_box(team: str, size: int = 50, box: int = 56) -> str:
    """흰 라운드 박스 안의 크레스트 로고 <img> (로드 실패 시 박스만)."""
    logo = team_logo(team)
    img = (f"<img src=\"{logo}\" referrerpolicy=\"no-referrer\" "
           f"onerror=\"this.style.display='none'\" "
           f"style=\"width:{size}px;height:{size}px;object-fit:contain\"/>") if logo else ""
    return (f"<div style=\"width:{box}px;height:{box}px;border-radius:13px;background:#fff;"
            f"border:1px solid #e4e8f0;display:flex;align-items:center;justify-content:center;"
            f"flex:none;box-shadow:0 2px 6px rgba(16,24,40,.06)\">{img}</div>")


# TEAM_EXTRA moved to src/ui/common.py


# 25/26 유럽대항전 참가 (24/25 성적 기반). 국내컵(FA/카라바오)은 전 팀 공통.
# ※ 유럽 배정은 UEFA 규정/판정에 따라 바뀔 수 있으니 검증 후 수정 가능.
TEAM_CAPTAINS = {
    "Arsenal": "Martin Odegaard",
    "Aston Villa": "John McGinn",
    "Bournemouth": "Adam Smith",
    "Brentford": "Nathan Collins",
    "Brighton": "Lewis Dunk",
    "Burnley": "Josh Cullen",
    "Chelsea": "Reece James",
    "Crystal Palace": "Dean Henderson",
    "Everton": "Seamus Coleman",
    "Fulham": "Tom Cairney",
    "Leeds United": "Ethan Ampadu",
    "Liverpool": "Virgil van Dijk",
    "Manchester City": "Bernardo Silva",
    "Manchester Utd": "Bruno Fernandes",
    "Newcastle United": "Bruno Guimaraes",
    "Nottingham Forest": "Ryan Yates",
    "Sunderland": "Granit Xhaka",
    "Tottenham Hotspur": "Cristian Romero",
    "West Ham United": "Jarrod Bowen",
    "Wolves": "Toti Gomes",
}


TEAM_EURO = {
    "Liverpool": "챔피언스리그", "Arsenal": "챔피언스리그", "Manchester City": "챔피언스리그",
    "Chelsea": "챔피언스리그", "Newcastle United": "챔피언스리그", "Tottenham Hotspur": "챔피언스리그",
    "Aston Villa": "유로파리그", "Nottingham Forest": "유로파리그",
    "Crystal Palace": "컨퍼런스리그",
}
COMP_STYLE = {
    "프리미어리그": "#37003c", "FA컵": "#c8102e", "카라바오컵": "#00a14b",
    "챔피언스리그": "#0a1a4f", "유로파리그": "#ff6a00", "컨퍼런스리그": "#149e54",
}


def _competition_label(comp: str) -> str:
    labels = {
        "EPL": "프리미어리그",
        "Champions": "챔피언스리그",
        "Europa": "유로파리그",
        "Conference": "컨퍼런스리그",
        "FA Cup": "FA컵",
        "EFL Trophy": "카라바오컵",
        "Carabao": "카라바오컵",
        "Club World": "클럽월드컵",
        "Community": "커뮤니티실드",
        "Super Cup": "슈퍼컵",
    }
    return labels.get(str(comp).strip(), str(comp).strip())


def _cup_stage(comp: str, latest) -> str:
    dt = pd.to_datetime(latest, errors="coerce")
    if pd.isna(dt):
        return "참가"
    comp = str(comp)
    md = (dt.month, dt.day)
    if comp in ("Champions", "Europa", "Conference"):
        if md >= (5, 20):
            return "결승"
        if md >= (4, 28):
            return "4강"
        if md >= (4, 7):
            return "8강"
        if md >= (3, 10):
            return "16강"
        if md >= (2, 18):
            return "녹아웃 PO"
        return "리그 페이즈"
    if comp == "FA Cup":
        if md >= (5, 16):
            return "결승"
        if md >= (4, 25):
            return "4강"
        if md >= (4, 4):
            return "8강"
        if md >= (3, 6):
            return "5라운드"
        if md >= (2, 13):
            return "4라운드"
        return "3라운드"
    if comp in ("EFL Trophy", "Carabao"):
        if md >= (3, 15):
            return "결승권"
        if md >= (1, 6):
            return "4강권"
        if md >= (12, 1):
            return "8강권"
        if md >= (10, 28):
            return "4라운드"
        if md >= (9, 23):
            return "3라운드"
        return "2라운드"
    return "참가"


def competition_results_html(team: str, rank=None, points=None,
                             fl_matches: pd.DataFrame | None = None) -> str:
    rows = []
    if rank:
        detail = f"{points}점 · 38경기" if points is not None else "리그 최종 순위"
        rows.append(("프리미어리그", f"{rank}위", detail))

    if fl_matches is not None and not fl_matches.empty:
        tm = fl_matches[fl_matches["squad"] == team].copy()
        tm["date_dt"] = pd.to_datetime(tm["date"], errors="coerce")
        tm = tm[tm["comp"].fillna("").astype(str).str.strip().ne("")]
        tm = tm[~tm["comp"].isin(["EPL"])]
        comp_order = ["Champions", "Europa", "Conference", "FA Cup", "EFL Trophy", "Carabao",
                      "Club World", "Community", "Super Cup"]
        for comp in comp_order:
            g = tm[tm["comp"] == comp].sort_values("date_dt")
            if g.empty:
                continue
            last = g.iloc[-1]
            latest = last.get("date_dt")
            date_txt = latest.strftime("%m/%d") if pd.notna(latest) else "-"
            detail = f"{len(g)}경기 · 마지막 {date_txt} vs {last.get('opponent', '-')}"
            rows.append((_competition_label(comp), _cup_stage(comp, latest), detail))

    if not rows:
        return ""

    items = "".join(
        f"<div style='background:#f8fafc;border:1px solid #eef1f6;border-radius:9px;"
        f"padding:8px 10px;min-width:0'>"
        f"<div style='font-size:10px;color:#8a93a5;font-weight:900;letter-spacing:.4px;"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{label}</div>"
        f"<div style='font-size:14px;color:#1a1f2e;font-weight:950;margin-top:2px'>{result}</div>"
        f"<div style='font-size:10.5px;color:#667085;margin-top:2px;white-space:nowrap;"
        f"overflow:hidden;text-overflow:ellipsis'>{detail}</div>"
        f"</div>"
        for label, result, detail in rows
    )
    return (
        "<div style='margin-top:13px;border-top:1px solid #eef1f6;padding-top:12px'>"
        "<div style='font-size:10px;color:#8a93a5;text-transform:uppercase;letter-spacing:.5px;"
        "margin-bottom:8px;font-weight:900'>참가 대회 최종 성적 25/26</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px'>{items}</div>"
        "</div>"
    )


def team_info_html(team: str, manager=None, rank=None, points=None, value_rank=None,
                   fl_matches: pd.DataFrame | None = None) -> str:
    """구단 정보 카드 (FM 스타일) — 팀컬러 헤더 + 크레스트 + 명성★ + 팩트 그리드 + 설명."""
    info = TEAM_INFO.get(team)
    if not info:
        return ""
    full, cap = TEAM_EXTRA.get(team, (team, None))
    tcol = team_color(team)
    logo = team_logo(team)
    crest = (f"<img src=\"{logo}\" referrerpolicy=\"no-referrer\" onerror=\"this.style.display='none'\" "
             f"style=\"width:46px;height:46px;object-fit:contain\"/>") if logo else ""

    # 명성 ★ — 스쿼드 가치 리그 순위 기반
    rep = (5.0 if value_rank and value_rank <= 2 else 4.5 if value_rank and value_rank <= 5
           else 4.0 if value_rank and value_rank <= 9 else 3.5 if value_rank and value_rank <= 14 else 3.0)
    _fl = int(rep); _half = (rep - _fl) >= 0.5
    stars = ""
    for i in range(5):
        if i < _fl:
            stars += "<span style='color:#ffc531;font-size:15px'>★</span>"
        elif i == _fl and _half:
            stars += "<span style='color:#ffc531;font-size:15px;opacity:.45'>★</span>"
        else:
            stars += "<span style='color:rgba(255,255,255,.3);font-size:15px'>★</span>"

    def fact(label, val):
        if val is None or val == "":
            return ""
        return (f"<div><div style='font-size:10px;color:#8a93a5;text-transform:uppercase;"
                f"letter-spacing:.5px'>{label}</div>"
                f"<div style='font-size:13.5px;font-weight:700;color:#1a1f2e;margin-top:2px'>{val}</div></div>")

    stad = info["stadium"] + (f" ({cap:,}석)" if cap else "")
    mgr = manager.get("name") if isinstance(manager, dict) else (manager or None)
    captain = TEAM_CAPTAINS.get(team)
    facts = "".join([
        fact("창단", f"{info['founded']}년"),
        fact("연고지", info["city"]),
        fact("홈구장", stad),
        fact("감독", mgr),
        fact("주장(C)", captain),
        fact("스쿼드 가치", f"리그 {value_rank}위" if value_rank else None),
    ])
    comp_results = competition_results_html(team, rank, points, fl_matches)
    return f"""
    <div style="border-radius:16px;overflow:hidden;border:1px solid #e4e8f0;
                box-shadow:0 1px 3px rgba(16,24,40,.05),0 8px 22px rgba(16,24,40,.06)">
      <div style="background:linear-gradient(135deg,{tcol},#10151c 80%);padding:16px 20px;
                  display:flex;align-items:center;gap:15px">
        <div style="width:60px;height:60px;border-radius:14px;background:rgba(255,255,255,.94);
                    display:flex;align-items:center;justify-content:center;flex:none">{crest}</div>
        <div style="flex:1;min-width:0">
          <div style="font-size:20px;font-weight:900;color:#fff;line-height:1.12;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{full}</div>
          <div style="font-size:12px;color:rgba(255,255,255,.82);margin-top:4px;line-height:1.35">
            {info['nick']} · 프리미어리그 2025/26</div>
        </div>
        <div style="text-align:right;flex:none">
          <div style="white-space:nowrap">{stars}</div>
          <div style="font-size:9px;color:rgba(255,255,255,.65);letter-spacing:1.5px;margin-top:2px">REPUTATION</div>
        </div>
      </div>
      <div style="background:#fff;padding:15px 20px">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px 14px">{facts}</div>
        {comp_results}
      </div>
    </div>"""


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


# 시장가치(€) 표시 + 국적 코드 (Transfermarkt 데이터)
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


# 여름 이적시장 IN/OUT 카드 (Transfermarkt transfers 페이지)
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


def transfer_side_html(direction: str, rows: list, limit: int = 14) -> str:
    """IN 또는 OUT 한쪽 카드 — 사진·이름·상대클럽·이적료 행 리스트."""
    is_in = direction == "in"
    color = "#16a34a" if is_in else "#ef4444"
    title = "IN · 영입" if is_in else "OUT · 방출"
    icon, arrow = ("↓", "←") if is_in else ("↑", "→")
    items = []
    for r in rows[:limit]:
        photo = r.get("photo") or ""
        photo = photo if isinstance(photo, str) and photo.startswith("http") else ""
        fee = fee_label(r.get("fee_eur"), r.get("fee_text"))
        items.append(
            f"<div style='display:flex;align-items:center;gap:9px;padding:7px 2px;"
            f"border-bottom:1px solid #eef1f6'>"
            f"{avatar(photo, '#cdd5e0', 30, 'flex:none', '1px solid #e4e8f0')}"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-size:13px;font-weight:700;color:#1a1f2e;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{r['player']}</div>"
            f"<div style='font-size:11px;color:#8a93a5;white-space:nowrap;overflow:hidden;"
            f"text-overflow:ellipsis'>{arrow} {r['club']}</div></div>"
            f"<div style='font-size:12px;font-weight:800;color:{color};flex:none'>{fee}</div></div>"
        )
    more = len(rows) - limit
    if more > 0:
        items.append(f"<div style='padding:7px 2px;font-size:12px;color:#8a93a5'>+{more}건 더…</div>")
    if not items:
        items.append("<div style='padding:10px 2px;font-size:12px;color:#b6bdc9'>기록 없음</div>")
    return (f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;"
            f"padding:4px 14px 10px;box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)'>"
            f"<div style='font-size:13px;font-weight:800;color:{color};padding:11px 2px 7px;"
            f"border-bottom:2px solid {color};margin-bottom:2px'>{icon} {title} ({len(rows)})</div>"
            f"{''.join(items)}</div>")


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
    """메인 상단 팀 배지 헤더 — 구단 크레스트 로고 + 팀명 + 리그·시즌."""
    return f"""
    <div style="display:flex;align-items:center;gap:14px;margin:-6px 0 18px">
      {team_logo_box(team, 44, 52)}
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
                       sid_map: dict, raw_rating: dict, ovr_map: dict | None = None,
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
        if ovr_map is not None and r["player"] in ovr_map:
            ovr = ovr_map[r["player"]]
        else:
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
        {avatar(r['sid'], r['tcol'], 52, 'flex:none')}
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


def team_ratings_legacy(team: str, traits: pd.DataFrame, standings) -> list[tuple]:
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


def _rank_pct(values: pd.Series, team: str, high_is_good: bool = True) -> float | None:
    values = values.dropna()
    if values.empty or team not in values.index:
        return None
    return float(values.rank(ascending=high_is_good, pct=True)[team])


def _blend_pcts(parts: list[tuple[float | None, float]]) -> float | None:
    valid = [(float(v), float(w)) for v, w in parts if v is not None and not pd.isna(v) and w > 0]
    if not valid:
        return None
    total = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total


def _blend_scores(parts: list[tuple[int | float | None, float]]) -> int | None:
    valid = [(float(v), float(w)) for v, w in parts if v is not None and not pd.isna(v) and w > 0]
    if not valid:
        return None
    total = sum(w for _, w in valid)
    return int(max(1, min(99, round(sum(v * w for v, w in valid) / total))))


def _pct_to_rating(pct: float | None) -> int | None:
    return fm_rating(pct) if pct is not None and not pd.isna(pct) else None


def _power_from_pct(pct: float | None, lo: int = 58, hi: int = 94) -> int | None:
    """Convert league percentile to a display power rating, not a raw 1-99 rank score."""
    if pct is None or pd.isna(pct):
        return None
    pct = max(0.0, min(1.0, float(pct)))
    return int(round(lo + pct * (hi - lo)))


def _power_from_index(value: int | float | None, lo: int = 58, hi: int = 94) -> int | None:
    """Convert stored 1-99 percentile-like indices into bounded team power ratings."""
    if value is None or pd.isna(value):
        return None
    pct = (max(1.0, min(99.0, float(value))) - 1.0) / 98.0
    return int(round(lo + pct * (hi - lo)))


def _team_metric_pct(team: str, traits: pd.DataFrame, col: str,
                     high_is_good: bool = True) -> float | None:
    if col not in traits.columns or team not in traits.index:
        return None
    return _rank_pct(traits[col], team, high_is_good=high_is_good)


def _full_team_metric_pct(team: str, full_df: pd.DataFrame | None, col: str,
                          high_is_good: bool = True) -> float | None:
    if full_df is None or col not in full_df.columns or "squad" not in full_df.columns:
        return None
    vals = full_df.groupby("squad")[col].mean(numeric_only=True)
    return _rank_pct(vals, team, high_is_good=high_is_good)


def _role_quality_pct(team: str, full_df: pd.DataFrame | None, role: str) -> float | None:
    if full_df is None or "squad" not in full_df.columns:
        return None
    required = {"minutes", "ss_rating", "market_value_eur", "goals", "assists"}
    if not required.issubset(full_df.columns):
        return None

    pool = full_df[full_df["minutes"].fillna(0) > 0].copy()
    if pool.empty:
        return None
    pos = pool.get("pos", pd.Series("", index=pool.index)).fillna("").str.upper()
    fl = pool.get("fl_group", pd.Series("", index=pool.index)).fillna("").str.upper()

    if role == "attack":
        pool = pool[fl.isin(["ST", "W", "RW", "LW", "AM"]) | pos.str.contains("FW", na=False)]
        top_n = 6
    elif role == "midfield":
        pool = pool[fl.isin(["DM", "CM", "AM"]) | pos.str.contains("MF", na=False)]
        top_n = 7
    elif role == "defense":
        pool = pool[fl.isin(["CB", "FB", "RB", "LB", "GK"]) |
                    pos.str.contains("DF|GK", regex=True, na=False)]
        top_n = 7
    else:
        top_n = 15

    if pool.empty:
        return None
    pool["_ovr"] = pool.apply(
        lambda r: player_ovr(r.get("market_value_eur"), r.get("ss_rating"),
                             r.get("minutes"), r.get("goals"), r.get("assists")),
        axis=1,
    )

    scores = {}
    for squad, rows in pool.groupby("squad"):
        eligible = rows[rows["minutes"].fillna(0) >= 300]
        if eligible.empty:
            eligible = rows
        top = eligible.sort_values("_ovr", ascending=False).head(top_n).copy()
        weights = top["minutes"].fillna(0).clip(lower=1, upper=2500) ** 0.5
        scores[squad] = float((top["_ovr"] * weights).sum() / weights.sum())
    return _rank_pct(pd.Series(scores), team, high_is_good=True)


def team_ratings(team: str, traits: pd.DataFrame, standings,
                 full_df: pd.DataFrame | None = None,
                 unit_metrics: pd.DataFrame | None = None) -> list[tuple]:
    """Team ratings blend results, team metrics, and squad role quality."""
    if unit_metrics is not None and team in unit_metrics.index:
        row = unit_metrics.loc[team]

        def iv(col: str) -> int:
            v = row.get(col)
            return int(v) if pd.notna(v) else 1

        rank = None
        points_idx = None
        gd_idx = None
        if standings is not None and (standings["squad"] == team).any():
            srow = standings[standings["squad"] == team].iloc[0]
            rank = int(srow["rank"])
            st = standings.set_index("squad")
            points_idx = _power_from_pct(_rank_pct(st["points"], team, high_is_good=True), 58, 94)
            gd_idx = _power_from_pct(_rank_pct(st["gd"], team, high_is_good=True), 58, 94)

        squad_idx = _power_from_pct(_role_quality_pct(team, full_df, "overall"), 60, 95)
        attack_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "attack"), 58, 94)
        midfield_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "midfield"), 58, 94)
        defense_quality_idx = _power_from_pct(_role_quality_pct(team, full_df, "defense"), 58, 94)

        attack = _blend_scores([
            (_power_from_index(iv("attack_index"), 56, 94), 0.48),
            (_power_from_index(iv("attack_output_index"), 56, 94), 0.17),
            (_power_from_index(iv("attack_creation_index"), 56, 94), 0.17),
            (attack_quality_idx, 0.18),
        ]) or iv("attack_index")
        midfield = _blend_scores([
            (midfield_quality_idx, 0.35),
            (_power_from_index(iv("midfield_creativity_index"), 56, 94), 0.25),
            (points_idx, 0.15),
            (gd_idx, 0.10),
            (_power_from_index(iv("midfield_control_index"), 56, 94), 0.10),
            (_power_from_index(iv("pressing_index"), 56, 94), 0.05),
        ]) or iv("midfield_index")
        defense = _blend_scores([
            (_power_from_index(iv("defense_index"), 56, 94), 0.40),
            (_power_from_index(iv("defense_output_index"), 56, 94), 0.24),
            (_power_from_index(iv("defense_box_aerial_index"), 56, 94), 0.12),
            (_power_from_index(iv("discipline_index"), 56, 94), 0.08),
            (defense_quality_idx, 0.16),
        ]) or iv("defense_index")
        overall = _blend_scores([
            (points_idx, 0.25),
            (gd_idx, 0.15),
            (squad_idx, 0.15),
            (attack, 0.15),
            (midfield, 0.15),
            (defense, 0.15),
        ]) or iv("overall_index")

        return [
            ("종합 지수", overall, f"리그 {rank}위 + 유닛 전력" if rank else "성적 + 유닛 전력"),
            ("공격 지수", attack,
             f"득점 {iv('attack_output_index')} / 창출 {iv('attack_creation_index')} / 세트피스 {iv('set_piece_attack_index')}"),
            ("미드필드 지수", midfield,
             f"장악 {iv('midfield_control_index')} / 창의성 {iv('midfield_creativity_index')} / 압박 {iv('pressing_index')}"),
            ("수비 지수", defense,
             f"실점억제 {iv('defense_output_index')} / 저지 {iv('defense_disruption_index')} / 징계관리 {iv('discipline_index')}"),
        ]

    def tval(col):
        if col in traits.columns and team in traits.index and pd.notna(traits.loc[team, col]):
            return traits.loc[team, col]
        return None

    rank = None
    points_pct = None
    if standings is not None and (standings["squad"] == team).any():
        srow = standings[standings["squad"] == team].iloc[0]
        rank = int(srow["rank"])
        points_pct = _rank_pct(standings.set_index("squad")["points"], team, high_is_good=True)

    squad_q = _role_quality_pct(team, full_df, "overall")
    att_q = _role_quality_pct(team, full_df, "attack")
    mid_q = _role_quality_pct(team, full_df, "midfield")
    def_q = _role_quality_pct(team, full_df, "defense")

    attack_perf = (
        _full_team_metric_pct(team, full_df, "team_attack_score", True)
        or _team_metric_pct(team, traits, "gf", True)
    )
    defense_perf = (
        _full_team_metric_pct(team, full_df, "team_defense_score", True)
        or _team_metric_pct(team, traits, "ga", False)
    )
    build = _blend_pcts([
        (_team_metric_pct(team, traits, "pass_pct", True), 0.35),
        (_team_metric_pct(team, traits, "key_passes_per90", True), 0.25),
        (_team_metric_pct(team, traits, "recoveries_per90", True), 0.25),
        (_team_metric_pct(team, traits, "long_ball_pct", True), 0.15),
    ])
    pressure = _blend_pcts([
        (_team_metric_pct(team, traits, "recoveries_per90", True), 0.45),
        (_team_metric_pct(team, traits, "interceptions_per90", True), 0.35),
        (_team_metric_pct(team, traits, "aerial_won_pct", True), 0.20),
    ])

    overall = _blend_pcts([(points_pct, 0.55), (squad_q, 0.45)])
    attack = _blend_pcts([
        (attack_perf, 0.50),
        (att_q, 0.35),
        (_team_metric_pct(team, traits, "key_passes_per90", True), 0.15),
    ])
    midfield = _blend_pcts([(mid_q, 0.60), (build, 0.40)])
    defense = _blend_pcts([(defense_perf, 0.60), (def_q, 0.25), (pressure, 0.15)])

    gf_v, ga_v, pass_v = tval("gf"), tval("ga"), tval("pass_pct")

    def rt(p):
        return fm_rating(p) if p is not None else 1

    return [
        ("Overall Rating", rt(overall), f"League #{rank} + squad quality" if rank else "Results + squad quality"),
        ("Attack Rating", rt(attack), f"{int(gf_v)} goals for" if gf_v is not None else "Output + attacker quality"),
        ("Midfield Rating", rt(midfield), f"Pass accuracy {pass_v:.0f}%" if pass_v is not None else "Midfield quality + build-up"),
        ("Defense Rating", rt(defense), f"{int(ga_v)} goals against" if ga_v is not None else "Defensive output + back line"),
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


def overview_scout_dossier_html(team: str, standings: pd.DataFrame | None,
                                ratings: list[tuple], manager: dict | None,
                                statbunker: pd.DataFrame | None,
                                unit_metrics: pd.DataFrame | None) -> str:
    """Team Overview 상단용 스카우트 도시에어 패널."""
    color = team_color(team)
    initial = html.escape(team.strip()[0].upper() if team.strip() else "?")
    safe_team = html.escape(team)
    logo = team_logo(team)
    crest = (
        f"<img src=\"{logo}\" referrerpolicy=\"no-referrer\" onerror=\"this.style.display='none'\" "
        f"style=\"width:46px;height:46px;object-fit:contain\"/>"
        if logo else f"<span>{initial}</span>"
    )
    manager_name = html.escape(str((manager or {}).get("name", "감독 정보 없음")))
    manager_style = html.escape(str((manager or {}).get("style", "전술 스타일 분석 중")))
    formation_txt = html.escape(str((manager or {}).get("formation", "")))

    rank = points = record = gd_str = "-"
    gf = ga = "-"
    if standings is not None and (standings["squad"] == team).any():
        s = standings[standings["squad"] == team].iloc[0]
        rank = f"{int(s['rank'])}위"
        points = str(int(s["points"]))
        record = f"{int(s['won'])}-{int(s['drawn'])}-{int(s['lost'])}"
        gd = int(s["gd"])
        gd_str = f"+{gd}" if gd > 0 else str(gd)
        gf = str(int(s["gf"]))
        ga = str(int(s["ga"]))

    rating_map = {label: val for label, val, _ in ratings}
    overall = int(rating_map.get("종합 지수", 1))
    attack = int(rating_map.get("공격 지수", 1))
    midfield = int(rating_map.get("미드필드 지수", 1))
    defense = int(rating_map.get("수비 지수", 1))

    sp_goals = "-"
    discipline = "-"
    if statbunker is not None and team in statbunker.index:
        sb = statbunker.loc[team]
        v = sb.get("non_penalty_set_piece_goals")
        if pd.notna(v):
            sp_goals = str(int(v))
        y = sb.get("yellow_cards")
        r = sb.get("red_cards")
        sy = sb.get("second_yellow_reds")
        if pd.notna(y):
            discipline = f"YC {int(y)}"
            if pd.notna(r) or pd.notna(sy):
                discipline += f" / RC {int((r or 0) + (sy or 0))}"

    pressing = "-"
    set_piece_idx = "-"
    if unit_metrics is not None and team in unit_metrics.index:
        um = unit_metrics.loc[team]
        if pd.notna(um.get("pressing_index")):
            pressing = str(int(um.get("pressing_index")))
        if pd.notna(um.get("set_piece_attack_index")):
            set_piece_idx = str(int(um.get("set_piece_attack_index")))

    if overall >= 90:
        verdict = "우승권 전력"
    elif overall >= 75:
        verdict = "상위권 경쟁 전력"
    elif overall >= 55:
        verdict = "중위권 안정권"
    else:
        verdict = "리빌딩 필요 구간"

    def index_bar(label: str, value: int) -> str:
        c = rating_color(value)
        return f"""
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
            <span style="font-size:11px;color:rgba(255,255,255,.70);font-weight:800">{label}</span>
            <span style="font-size:13px;color:#fff;font-weight:950">{value}</span>
          </div>
          <div style="height:7px;border-radius:999px;background:rgba(255,255,255,.13);overflow:hidden">
            <div style="width:{max(2, min(100, value))}%;height:100%;background:{c};border-radius:999px"></div>
          </div>
        </div>"""

    def tile(label: str, value: str, sub: str = "") -> str:
        return f"""
        <div style="background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);
                    border-radius:10px;padding:10px 11px;min-height:62px">
          <div style="font-size:20px;font-weight:950;color:#fff;line-height:1">{value}</div>
          <div style="font-size:10px;color:rgba(255,255,255,.62);font-weight:800;margin-top:6px">{label}</div>
          <div style="font-size:10px;color:rgba(255,255,255,.46);margin-top:2px">{sub}</div>
        </div>"""

    return f"""
    <div style="position:relative;overflow:hidden;border-radius:16px;
                background:linear-gradient(135deg,{color},#10151c 68%);
                color:#fff;box-shadow:0 16px 42px rgba(16,24,40,.18);padding:22px 24px;margin-bottom:14px">
      <div style="position:absolute;right:-52px;top:-86px;width:240px;height:240px;border-radius:50%;
                  background:rgba(255,255,255,.08)"></div>
      <div style="position:absolute;right:42px;bottom:-72px;width:170px;height:170px;border-radius:50%;
                  border:1px solid rgba(255,255,255,.13)"></div>
      <div style="display:grid;grid-template-columns:1.45fr .9fr;gap:22px;position:relative">
        <div>
          <div style="display:flex;align-items:center;gap:14px">
            <div style="width:60px;height:60px;border-radius:15px;background:rgba(255,255,255,.94);
                        border:1px solid rgba(255,255,255,.35);display:flex;align-items:center;
                        justify-content:center;font-size:28px;font-weight:950;color:{color};
                        box-shadow:0 10px 26px rgba(0,0,0,.18);flex:none">{crest}</div>
            <div style="min-width:0">
              <div style="font-size:11px;color:rgba(255,255,255,.62);font-weight:900;letter-spacing:1.4px">
                팀 스카우트 파일
              </div>
              <div style="font-size:31px;font-weight:950;line-height:1.05;white-space:nowrap;
                          overflow:hidden;text-overflow:ellipsis">{safe_team}</div>
              <div style="font-size:13px;color:rgba(255,255,255,.70);margin-top:6px">
                {manager_name} · {formation_txt} · {manager_style}
              </div>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin-top:19px">
            {tile("순위", rank)}
            {tile("승점", points)}
            {tile("승-무-패", record)}
            {tile("득점", gf)}
            {tile("실점", ga)}
            {tile("득실", gd_str)}
          </div>

          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:15px">
            <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.13);
                         border:1px solid rgba(255,255,255,.16);font-size:11px;font-weight:900">
              판정: {verdict}
            </span>
            <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.13);
                         border:1px solid rgba(255,255,255,.16);font-size:11px;font-weight:900">
              세트피스 지수 {set_piece_idx} · 비PK 세트피스 득점 {sp_goals}
            </span>
            <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.13);
                         border:1px solid rgba(255,255,255,.16);font-size:11px;font-weight:900">
              압박 {pressing} · {discipline}
            </span>
          </div>
        </div>

        <div style="background:rgba(0,0,0,.20);border:1px solid rgba(255,255,255,.12);
                    border-radius:13px;padding:16px 16px 13px">
          <div style="font-size:11px;font-weight:950;color:rgba(255,255,255,.62);letter-spacing:1px;
                      margin-bottom:12px">유닛 인덱스</div>
          {index_bar("종합", overall)}
          {index_bar("공격", attack)}
          {index_bar("중원", midfield)}
          {index_bar("수비", defense)}
        </div>
      </div>
    </div>"""


# ── Team Analytics — 팀 퍼포먼스 레이더 (리그 백분위) ─────────────────────────
def _manager_tenure(appointed) -> str:
    """'Dec 2019' → '재임 6년 6개월' (25/26 시즌 기준 2026.6)."""
    import re
    if not appointed:
        return ""
    M = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
         "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    m = re.search(r"([A-Za-z]{3,})?\s*(\d{4})", str(appointed))
    if not m:
        return ""
    yr = int(m.group(2)); mon = M.get((m.group(1) or "")[:3].lower(), 1)
    total = (2026 - yr) * 12 + (6 - mon)
    if total < 0:
        return ""
    y, mo = divmod(total, 12)
    if y and mo:
        return f"재임 {y}년 {mo}개월"
    return f"재임 {y}년" if y else f"재임 {mo}개월"


def manager_profile_html(team: str, profile: dict | None, standings=None) -> str:
    if not profile:
        return ""
    color = team_color(team)
    name = profile.get("name", "Unknown")
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    photo_url = str(profile.get("photo_url", "") or "").strip()
    nat = profile.get("nationality", "")
    flag = flag_chip(nat, h=14)
    appointed = profile.get("appointed", "")
    tenure = _manager_tenure(appointed)
    meta = " · ".join(x for x in [nat, f"부임 {appointed}" if appointed else "", tenure] if x)
    style_val = profile.get("style", "")
    focus_val = profile.get("focus", "")
    formation = profile.get("formation", "")
    manager_avatar = portrait_photo(
        photo_url, color, 92, 110,
        "margin-top:0;box-shadow:0 12px 28px rgba(16,24,40,.14)",
        16, "4px solid #fff", initials,
    )

    # 이번 시즌 성적 타일 (standings)
    tiles_html = ""
    if standings is not None:
        srow = standings[standings["squad"] == team]
        if not srow.empty:
            s = srow.iloc[0]
            rank, pts = int(s["rank"]), int(s["points"])
            w, d, l = int(s["won"]), int(s["drawn"]), int(s["lost"])
            played = w + d + l
            ppg = pts / played if played else 0

            def stat(label, val, fs=20):
                return (f"<div style='background:#f8fafc;border:1px solid #e4e8f0;border-radius:10px;"
                        f"padding:9px 10px;text-align:center'>"
                        f"<div style='font-size:{fs}px;font-weight:950;color:#1a1f2e;line-height:1'>{val}</div>"
                        f"<div style='font-size:9.5px;font-weight:800;color:#8a93a5;margin-top:5px'>{label}</div></div>")
            tiles_html = (
                "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px'>"
                + stat("리그 순위", f"{rank}위")
                + stat("승점", str(pts))
                + stat("전적", f"{w}-{d}-{l}", 16)
                + stat("경기당 승점", f"{ppg:.2f}")
                + "</div>"
            )

    chip = (f"<span style='display:inline-flex;align-items:center;gap:5px;padding:4px 10px;"
            f"border-radius:7px;background:{color}12;color:{color};border:1px solid {color}30;"
            f"font-size:11px;font-weight:800'>"
            f"<span style='color:#8a93a5;font-weight:700'>기본 전형</span>{formation}</span>") if formation else ""

    def row(label, val, strong=False):
        if not val:
            return ""
        vc = "#1a1f2e;font-weight:800" if strong else "#3a4253"
        return (f"<div style='display:grid;grid-template-columns:88px minmax(0,1fr);gap:10px;"
                f"padding:9px 0;border-bottom:1px solid #f1f3f7'>"
                f"<div style='font-size:11px;font-weight:950;color:#8a93a5;letter-spacing:.5px'>{label}</div>"
                f"<div style='font-size:13px;color:{vc};line-height:1.45'>{val}</div></div>")

    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:0;
                overflow:hidden;box-shadow:0 1px 3px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.08)">
      <div style="height:78px;background:linear-gradient(135deg,{color},#10151c);position:relative">
        <div style="position:absolute;right:-28px;top:-54px;width:130px;height:130px;border-radius:50%;
                    background:rgba(255,255,255,.10)"></div>
        <div style="position:absolute;left:18px;bottom:13px;font-size:11px;font-weight:950;
                    color:rgba(255,255,255,.70);letter-spacing:1px">감독 리포트</div>
      </div>
      <div style="padding:18px 20px 20px">
        <div style="display:flex;align-items:flex-start;gap:18px">
          {manager_avatar}
          <div style="flex:1;min-width:0">
            <div style="font-size:10px;font-weight:900;color:{color};letter-spacing:.7px">2025/26 감독</div>
            <div style="font-size:18px;font-weight:900;color:#1a1f2e;line-height:1.2;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}{flag}</div>
            <div style="font-size:12px;color:#8a93a5;margin-top:4px">{meta}</div>
            <div style="margin-top:9px">{chip}</div>
          </div>
        </div>
        {tiles_html}
        <div style="margin-top:15px">
          {row("전술 스타일", style_val, strong=True)}
          {row("감독 포커스", focus_val)}
        </div>
      </div>
    </div>"""


def _rank_text(df: pd.DataFrame | None, team: str, col: str,
               high_is_good: bool = True) -> tuple[int | None, float | None]:
    if df is None or team not in df.index or col not in df.columns:
        return None, None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if team not in s.index or s.empty:
        return None, None
    rank = int(s.rank(ascending=not high_is_good, method="min")[team])
    return rank, float(s[team])


def _ko_num(value: float | None) -> str:
    if value is None:
        return "-"
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.1f}"


def _insight_item(title: str, detail: str, tone: str = "good") -> str:
    color = "#16a34a" if tone == "good" else "#ef4444"
    bg = "#f0fdf4" if tone == "good" else "#fff1f2"
    label = "EDGE" if tone == "good" else "RISK"
    return (
        f"<div style='position:relative;overflow:hidden;padding:10px 11px 10px 12px;"
        f"border-radius:10px;background:{bg};border:1px solid {color}26;"
        f"box-shadow:0 1px 2px rgba(16,24,40,.03)'>"
        f"<div style='position:absolute;left:0;top:0;bottom:0;width:4px;background:{color}'></div>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;gap:8px'>"
        f"<div style='font-size:13px;font-weight:950;color:#1a1f2e;white-space:nowrap;"
        f"overflow:hidden;text-overflow:ellipsis'>{title}</div>"
        f"<div style='font-size:8.5px;font-weight:950;color:{color};background:#fff;"
        f"border:1px solid {color}22;border-radius:999px;padding:2px 6px'>{label}</div>"
        f"</div>"
        f"<div style='font-size:11.5px;color:#667085;margin-top:5px;line-height:1.35;"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{detail}</div>"
        f"</div>"
    )


def team_snapshot_html(team: str, statbunker: pd.DataFrame | None,
                       unit_metrics: pd.DataFrame | None) -> str:
    strengths: list[tuple[str, str]] = []
    weaknesses: list[tuple[str, str]] = []

    # 중립 제목(강점·약점 어느 쪽이든 자연스럽게 읽힘) + 다양한 지표 풀.
    # 전부 high_is_good 인덱스/카운트라 순위 비교가 일관적이다.
    metric_defs = [
        ("오픈플레이 득점", statbunker, "open_play_goals", True, "오픈플레이 득점"),
        ("코너 득점력", statbunker, "corner_goals", True, "코너킥 득점"),
        ("세트피스 공격", unit_metrics, "set_piece_attack_index", True, "세트피스 지수"),
        ("찬스 창출", unit_metrics, "midfield_creativity_index", True, "창의성 지수"),
        ("미드필드 장악", unit_metrics, "midfield_control_index", True, "장악 지수"),
        ("볼 탈취", unit_metrics, "midfield_ball_winning_index", True, "볼위닝 지수"),
        ("전방 압박", unit_metrics, "pressing_index", True, "압박 지수"),
        ("수비 안정성", unit_metrics, "defense_index", True, "수비 지수"),
        ("공중 수비", unit_metrics, "defense_box_aerial_index", True, "공중수비 지수"),
        ("수비 방해력", unit_metrics, "defense_disruption_index", True, "방해 지수"),
        ("규율", unit_metrics, "discipline_index", True, "규율 지수"),
        ("페널티 관리", unit_metrics, "penalty_control_index", True, "PK관리 지수"),
    ]

    scored = []
    for title, df, col, high_good, label in metric_defs:
        rank, value = _rank_text(df, team, col, high_good)
        if rank is not None:
            scored.append((rank, title, f"{label} {_ko_num(value)} · 리그 {rank}위"))
    if not scored:
        return ""

    # 순위 좋은 순 정렬 → 상위 3 = 강점, 하위 3 = 약점 (지표 풀이 커서 상호 배타).
    scored.sort(key=lambda x: x[0])
    strengths = [(t, d) for _, t, d in scored[:3]]
    weaknesses = [(t, d) for _, t, d in reversed(scored[-3:])]

    good_html = "".join(_insight_item(t, d, "good") for t, d in strengths[:3])
    weak_html = "".join(_insight_item(t, d, "bad") for t, d in weaknesses[:3])
    color = team_color(team)
    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:0;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 9px 26px rgba(16,24,40,.07);
                position:relative;overflow:hidden;height:100%;box-sizing:border-box">
      <div style="background:linear-gradient(135deg,{color},#10151c);padding:15px 18px;
                  color:#fff;position:relative;overflow:hidden">
        <div style="position:absolute;right:-42px;top:-62px;width:150px;height:150px;border-radius:50%;
                    background:rgba(255,255,255,.10)"></div>
        <div style="position:relative;display:flex;align-items:center;justify-content:space-between;gap:12px">
          <div>
            <div style="font-size:10px;font-weight:950;color:rgba(255,255,255,.62);letter-spacing:1.3px">
              TEAM SCOUT SNAPSHOT
            </div>
            <div style="font-size:20px;font-weight:950;margin-top:2px">팀 스냅샷</div>
          </div>
          <div style="font-size:9px;font-weight:950;letter-spacing:.9px;color:#fff;
                      border:1px solid rgba(255,255,255,.24);background:rgba(255,255,255,.13);
                      border-radius:999px;padding:5px 9px;white-space:nowrap">This Season</div>
        </div>
      </div>
      <div style="padding:15px 16px 17px">
        <div style="font-size:12px;color:#667085;margin-bottom:12px;line-height:1.45">
          현재 경기력에서 두드러지는 강점과 보완 지점을 리그 순위 기반으로 압축했습니다.
        </div>
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;position:relative">
          <div style="background:#fbfdfc;border:1px solid #e6f4ec;border-radius:12px;padding:11px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px">
              <div style="font-size:11px;font-weight:950;color:#16a34a;letter-spacing:.4px">강점 3줄</div>
              <div style="font-size:10px;color:#16a34a;font-weight:950">TOP SIGNAL</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">{good_html}</div>
          </div>
          <div style="background:#fffafa;border:1px solid #ffe2e5;border-radius:12px;padding:11px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px">
              <div style="font-size:11px;font-weight:950;color:#ef4444;letter-spacing:.4px">리스크 3줄</div>
              <div style="font-size:10px;color:#ef4444;font-weight:950">WATCH LIST</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">{weak_html}</div>
          </div>
        </div>
      </div>
    </div>"""


def set_piece_discipline_html(team: str, statbunker: pd.DataFrame | None,
                              unit_metrics: pd.DataFrame | None) -> str:
    if statbunker is None or team not in statbunker.index:
        return ""
    color = team_color(team)
    sb = statbunker.loc[team]

    def iv(col: str) -> int | None:
        v = sb.get(col)
        return int(v) if pd.notna(v) else None

    def fmt(v: int | None) -> str:
        return str(v) if v is not None else "-"

    non_pen_sp = iv("non_penalty_set_piece_goals")
    corner = iv("corner_goals")
    fk = (iv("free_kick_goals") or 0) + (iv("direct_free_kick_goals") or 0) + (iv("throw_in_goals") or 0)
    pens_for = iv("penalties_for")
    pens_against = iv("penalties_against")
    yellows = iv("yellow_cards")
    reds = (iv("red_cards") or 0) + (iv("second_yellow_reds") or 0)

    sp_idx = "-"
    discipline_idx = "-"
    if unit_metrics is not None and team in unit_metrics.index:
        row = unit_metrics.loc[team]
        if pd.notna(row.get("set_piece_attack_index")):
            sp_idx = str(int(row.get("set_piece_attack_index")))
        if pd.notna(row.get("discipline_index")):
            discipline_idx = str(int(row.get("discipline_index")))

    def tile(label: str, value: str, tone: str = "#1a1f2e") -> str:
        return f"""
        <div style="background:#f8fafc;border:1px solid #e4e8f0;border-radius:10px;padding:11px 12px">
          <div style="font-size:22px;font-weight:950;color:{tone};line-height:1">{value}</div>
          <div style="font-size:10px;font-weight:850;color:#8a93a5;margin-top:7px">{label}</div>
        </div>"""

    def bar(label: str, value: str, width: int, bar_color: str) -> str:
        return f"""
        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:11px;font-weight:900;color:#667085">{label}</span>
            <span style="font-size:12px;font-weight:950;color:#1a1f2e">{value}</span>
          </div>
          <div style="height:7px;background:#eef1f6;border-radius:999px;overflow:hidden">
            <div style="width:{max(2, min(100, width))}%;height:100%;background:{bar_color};border-radius:999px"></div>
          </div>
        </div>"""

    return f"""
    <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:18px 20px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 9px 26px rgba(16,24,40,.07);
                overflow:hidden;position:relative;height:100%;box-sizing:border-box">
      <div style="position:absolute;right:-36px;bottom:-48px;width:128px;height:128px;border-radius:50%;
                  background:{color}0f"></div>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;position:relative">
        <div>
          <div style="font-size:11px;font-weight:950;color:{color};letter-spacing:.9px">Match Control</div>
          <div style="font-size:18px;font-weight:950;color:#1a1f2e;margin-top:2px">세트피스 & 징계 노트</div>
          <div style="font-size:12px;color:#8a93a5;margin-top:2px">득점 루트와 경기 운영 리스크</div>
        </div>
        <div style="display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end">
          <span style="padding:5px 10px;border-radius:999px;background:{color}12;color:{color};
                       border:1px solid {color}30;font-size:11px;font-weight:950">세트피스 {sp_idx}</span>
          <span style="padding:5px 10px;border-radius:999px;background:#f8fafc;color:#667085;
                       border:1px solid #e4e8f0;font-size:11px;font-weight:950">징계관리 {discipline_idx}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1.1fr .9fr;gap:16px;margin-top:16px;position:relative">
        <div>
          <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-bottom:13px">
            {tile("비PK 세트피스 득점", fmt(non_pen_sp), color)}
            {tile("코너킥 득점", fmt(corner), "#16a34a")}
            {tile("프리킥 계열", fmt(fk), "#2563eb")}
          </div>
          {bar("세트피스 위협", sp_idx, int(sp_idx) if str(sp_idx).isdigit() else 0, color)}
          {bar("징계 관리", discipline_idx, int(discipline_idx) if str(discipline_idx).isdigit() else 0, "#16a34a")}
        </div>
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px">
          {tile("페널티 획득", fmt(pens_for), "#1a1f2e")}
          {tile("페널티 허용", fmt(pens_against), "#ef4444")}
          {tile("옐로카드", fmt(yellows), "#d97706")}
          {tile("퇴장", fmt(reds), "#b91c1c")}
        </div>
      </div>
    </div>"""


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
      <div style="font-size:15px;font-weight:800;color:#1a1f2e;margin-bottom:14px">AI 스카우트 리포트</div>
      {block("✓", "강점", "#16a34a", chips([l for l, _ in strengths], "#16a34a"))}
      {block("✕", "약점", "#ef4444", chips([l for l, _ in weaknesses], "#ef4444"))}
      {block("⚡", "전술 성향", "#2563eb", chips(styles, "#2563eb"))}
      <div style="border-top:1px solid #eef1f6;padding-top:11px">
        <div style="font-size:11px;font-weight:800;letter-spacing:.5px;color:#d97706;
                    margin-bottom:6px">추천 보강 포인트</div>{improv}
      </div>
    </div>"""


# Analytics code has been extracted to src/ui/analytics.py
# (for agent clarity). See src/ui/analytics.py for the full implementation.
# Only the import at the top and the call site below remain.

# (Analytics implementation removed — see src/ui/analytics.py)
# The call to analytics_dashboard_html(...) is still in the tab router below.

# ── Team Analytics 추가 패널 (폼 · xG · 스쿼드 · 리더) ───────────────────────
def _panel(title: str, body: str) -> str:
    return (f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:16px;"
            f"padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05);"
            f"margin-bottom:16px'>"
            f"<div style='font-size:14px;font-weight:800;color:#1a1f2e;margin-bottom:12px'>{title}</div>"
            f"{body}</div>")


def form_block_html(sched) -> str:
    """최근 폼(최근5) + 홈/원정 성적 + 경기당 승점."""
    s = sched.sort_values("gw")
    played = len(s)
    pts = int((s["result"] == "W").sum() * 3 + (s["result"] == "D").sum())
    ppg = pts / played if played else 0
    LAB = {"W": "승", "D": "무", "L": "패"}
    COL = {"W": "#16a34a", "D": "#9aa3b2", "L": "#ef4444"}
    dots = "".join(
        f"<span style='display:inline-flex;align-items:center;justify-content:center;width:26px;"
        f"height:26px;border-radius:7px;background:{COL.get(r, '#9aa3b2')};color:#fff;font-size:12px;"
        f"font-weight:800;margin-right:5px'>{LAB.get(r, r)}</span>"
        for r in s.tail(5)["result"]
    )

    def rec(v):
        vv = s[s["home_away"] == v]
        w = int((vv["result"] == "W").sum()); d = int((vv["result"] == "D").sum())
        ll = int((vv["result"] == "L").sum())
        return f"{w}승 {d}무 {ll}패 · {int(vv['gf'].sum())}:{int(vv['ga'].sum())}"

    body = (
        f"<div style='color:#8a93a5;font-size:11px;font-weight:700;margin-bottom:6px'>최근 5경기</div>"
        f"<div style='margin-bottom:14px'>{dots}</div>"
        f"<div style='display:flex;gap:18px'>"
        f"<div><div style='font-size:11px;color:#8a93a5'>🏠 홈</div>"
        f"<div style='font-size:14px;font-weight:700;color:#1a1f2e'>{rec('H')}</div></div>"
        f"<div><div style='font-size:11px;color:#8a93a5'>✈️ 원정</div>"
        f"<div style='font-size:14px;font-weight:700;color:#1a1f2e'>{rec('A')}</div></div>"
        f"<div style='margin-left:auto;text-align:right'><div style='font-size:11px;color:#8a93a5'>경기당 승점</div>"
        f"<div style='font-size:20px;font-weight:800;color:{ACCENT}'>{ppg:.2f}</div></div></div>"
    )
    return _panel("최근 폼 &amp; 결과", body)


def xg_block_html(team_xg: float, gf: int, ga: int, league_ga: float, played: int) -> str:
    """팀 기대득점(xG) vs 실제 득점 + 실점 vs 리그평균."""
    diff = gf - team_xg
    if diff >= 3:
        lab, lc = "클리니컬 (과득점)", "#16a34a"
    elif diff <= -3:
        lab, lc = "비효율 (저득점)", "#ef4444"
    else:
        lab, lc = "기대치 부합", "#d97706"
    dstr = f"+{diff:.1f}" if diff >= 0 else f"{diff:.1f}"
    ga_diff = ga - league_ga
    ga_lab = "리그평균보다 견고" if ga_diff < -2 else "리그평균보다 허술" if ga_diff > 2 else "리그평균 수준"
    ga_col = "#16a34a" if ga_diff < -2 else "#ef4444" if ga_diff > 2 else "#d97706"

    def big(label, val, sub, color):
        return (f"<div style='flex:1'><div style='font-size:11px;color:#8a93a5'>{label}</div>"
                f"<div style='font-size:24px;font-weight:800;color:{color};line-height:1.2'>{val}</div>"
                f"<div style='font-size:11px;color:#8a93a5'>{sub}</div></div>")

    body = (
        f"<div style='display:flex;gap:14px;margin-bottom:6px'>"
        f"{big('기대득점 xG', f'{team_xg:.1f}', f'경기당 {team_xg/played:.2f}' if played else '', '#1a1f2e')}"
        f"{big('실제 득점', str(gf), f'차이 {dstr}', lc)}"
        f"{big('실점', str(ga), f'리그평균 {league_ga:.0f}', ga_col)}</div>"
        f"<div style='display:flex;gap:6px;margin-top:8px'>"
        f"<span style='font-size:12px;font-weight:700;color:{lc};background:{lc}14;"
        f"border:1px solid {lc}40;border-radius:12px;padding:3px 11px'>공격: {lab}</span>"
        f"<span style='font-size:12px;font-weight:700;color:{ga_col};background:{ga_col}14;"
        f"border:1px solid {ga_col}40;border-radius:12px;padding:3px 11px'>수비: {ga_lab}</span></div>"
    )
    return _panel("xG 퍼포먼스 (결정력)", body)


def squad_profile_html(avg_age: float, sq_value, value_rank, buckets, league_avg_age: float) -> str:
    """평균 나이 · 스쿼드 가치(리그 순위) · 나이 분포."""
    u23, peak, old = buckets
    tot = max(1, u23 + peak + old)
    bar = (
        f"<div style='display:flex;height:10px;border-radius:5px;overflow:hidden;margin:6px 0 4px'>"
        f"<div style='width:{u23/tot*100:.0f}%;background:#38bdf8'></div>"
        f"<div style='width:{peak/tot*100:.0f}%;background:#16a34a'></div>"
        f"<div style='width:{old/tot*100:.0f}%;background:#d97706'></div></div>"
        f"<div style='font-size:11px;color:#8a93a5'>"
        f"<span style='color:#38bdf8'>●</span> U23 {u23} · "
        f"<span style='color:#16a34a'>●</span> 전성기(24-29) {peak} · "
        f"<span style='color:#d97706'>●</span> 30+ {old}</div>"
    )
    age_col = "#16a34a" if avg_age < league_avg_age - 0.5 else "#d97706" if avg_age > league_avg_age + 0.5 else "#1a1f2e"
    body = (
        f"<div style='display:flex;gap:18px;margin-bottom:12px'>"
        f"<div><div style='font-size:11px;color:#8a93a5'>평균 나이</div>"
        f"<div style='font-size:22px;font-weight:800;color:{age_col}'>{avg_age:.1f}세</div>"
        f"<div style='font-size:11px;color:#8a93a5'>리그평균 {league_avg_age:.1f}</div></div>"
        f"<div><div style='font-size:11px;color:#8a93a5'>스쿼드 가치</div>"
        f"<div style='font-size:22px;font-weight:800;color:#16a34a'>{fmt_value(sq_value)}</div>"
        f"<div style='font-size:11px;color:#8a93a5'>리그 {int(value_rank)}위</div></div></div>"
        f"<div style='font-size:11px;color:#8a93a5;font-weight:700'>나이 분포</div>{bar}"
    )
    return _panel("스쿼드 프로필", body)


def team_leaders(team: str, full: pd.DataFrame) -> list:
    """팀 기여 리더 — 득점/도움/xG/키패스/태클 톱."""
    t = full[(full["squad"] == team) & (full["minutes"] > 0)].copy()
    t = t.sort_values("minutes", ascending=False).drop_duplicates("player")
    if t.empty:
        return []
    t["_xg"] = t["npxg_p90"] * t["minutes"] / 90
    t["_kp"] = t["key_passes_per90"] * t["minutes"] / 90
    t["_tk"] = t["tackles_won_per90"] * t["minutes"] / 90
    out = []
    specs = [("goals", "득점", "#ef4444", 0), ("assists", "도움", "#e8344e", 0),
             ("_xg", "xG", "#d97706", 1), ("_kp", "키패스", "#16a34a", 0),
             ("_tk", "태클", "#2563eb", 0)]
    for col, label, color, dec in specs:
        if col not in t.columns or not t[col].notna().any():
            continue
        r = t.loc[t[col].idxmax()]
        v = float(r[col])
        val = f"{v:.1f}" if dec else f"{int(round(v))}"
        out.append((label, color, r["player"].split()[-1], val, _photo("", r.get("tm_photo"))))
    return out


def leader_card_html(item) -> str:
    label, color, player, val, photo = item
    return (
        f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:14px 10px;"
        f"text-align:center;box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)'>"
        f"<div style='font-size:10px;font-weight:800;letter-spacing:.5px;color:{color}'>{label}</div>"
        f"{avatar(photo, '#cdd5e0', 46, 'margin:8px auto 6px')}"
        f"<div style='font-size:12px;font-weight:700;color:#1a1f2e;white-space:nowrap;overflow:hidden;"
        f"text-overflow:ellipsis'>{player}</div>"
        f"<div style='font-size:20px;font-weight:800;color:{color};margin-top:2px'>{val}</div></div>"
    )


def db_player_card_html(name, squad, age, value_eur, nat, photo, ovr, display_pos) -> str:
    """Player Database 카드 — 사진·이름·국기·소속·나이·포지션·가치·OVR."""
    oc = rating_color(int(ovr)) if ovr else "#6b7280"
    pc = pos_chip_color(display_pos or "")
    tcol = team_color(squad)
    has_photo = isinstance(photo, str) and photo.startswith("http")
    sub = squad + (f" · {int(age)}세" if (age is not None and not pd.isna(age)) else "")
    return (
        f"<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:14px'>"
        f"<div style='display:flex;align-items:center;gap:11px'>"
        f"{avatar(photo, tcol, 46, 'flex:none')}"
        f"<div style='flex:1;min-width:0'>"
        f"<div style='font-weight:800;font-size:14px;color:#1a1f2e;white-space:nowrap;overflow:hidden;"
        f"text-overflow:ellipsis'>{name}{flag_chip(nat)}</div>"
        f"<div style='font-size:12px;color:#8a93a5;white-space:nowrap;overflow:hidden;"
        f"text-overflow:ellipsis'>{sub}</div></div>"
        f"<div style='text-align:center;flex:none'>"
        f"<div style='font-size:22px;font-weight:800;color:{oc};line-height:1'>{ovr}</div>"
        f"<div style='font-size:9px;color:#8a93a5;letter-spacing:1px'>OVR</div></div></div>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;margin-top:10px'>"
        f"<span style='padding:2px 9px;background:{pc}1a;color:{pc};border-radius:6px;"
        f"font-size:11px;font-weight:800'>{display_pos or '—'}</span>"
        f"<span style='font-size:13px;font-weight:800;color:#16a34a'>{fmt_value(value_eur)}</span></div></div>"
    )


def _iframe(inner_html: str, height: int, scrolling: bool = False) -> None:
    """카드 HTML을 components.html(iframe)로 렌더 — st.markdown과 달리 외부 이미지
    (background-image)가 sanitize되지 않아 선수 사진이 정상 표시된다."""
    st.components.v1.html(
        "<style>body{margin:0;background:#eef1f6;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}</style>" + inner_html,
        height=height, scrolling=scrolling,
    )


def _grid(cards: list, ncols: int) -> str:
    return (f"<div style='display:grid;grid-template-columns:repeat({ncols},1fr);gap:14px'>"
            + "".join(cards) + "</div>")


# ── Star Players — 팀 내 ss_rating 상위 N명 ───────────────────────────────────
def pos_chip_color(pos: str) -> str:
    p = str(pos).upper().split("/")[0]
    if p in ("ST", "RW", "LW", "W", "AM", "WING_AM") or "FW" in p: return "#ef4444"
    if p in ("CM", "DM", "CAM_CM") or "MF" in p: return "#16a34a"
    if p in ("CB", "RB", "LB", "FB") or "DF" in p: return "#2563eb"
    if "GK" in p: return "#d97706"
    return "#6b7280"


def team_star_players(team: str, full: pd.DataFrame, fine_map: dict, sid_map: dict,
                      ovr_map: dict | None = None,
                      n: int = 5, min_minutes: int = 450) -> list[dict]:
    """팀 내 ss_rating 상위 N명. OVR는 Player Database와 같은 통합 OVR를 사용."""
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
            "ovr": (ovr_map.get(name) if ovr_map is not None and name in ovr_map
                    else player_ovr(r.get("market_value_eur"), r.get("ss_rating"),
                                    r.get("minutes"), r.get("goals"), r.get("assists"))),
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
    name = s["name"].split()[-1] if len(s["name"]) > 14 else s["name"]
    nat_chip = flag_chip(s.get("nat"))
    val = s.get("value", "—")
    age = f"{s['age']}세" if s.get("age") is not None else "-"
    photo_html = portrait_photo(
        s.get("sid", ""), s["tcol"], 78, 92,
        "margin:12px 0 0;box-shadow:0 10px 22px rgba(16,24,40,.14)",
        14, "3px solid #fff", s.get("name", ""),
    )

    def mini_stat(label: str, value: str, color: str = "#1a1f2e") -> str:
        return (
            f"<div style='display:flex;align-items:center;justify-content:space-between;gap:6px;"
            f"border-bottom:1px solid #eef1f6;padding:0 0 5px;margin-bottom:6px'>"
            f"<span style='font-size:9px;color:#8a93a5;font-weight:900;letter-spacing:.5px'>{label}</span>"
            f"<span style='font-size:11px;color:{color};font-weight:950;white-space:nowrap'>{value}</span>"
            f"</div>"
        )

    return f"""
    <div style="position:relative;background:#fff;border:1px solid #e4e8f0;border-radius:14px;
                padding:0;overflow:hidden;text-align:left;min-height:258px;
                box-shadow:0 1px 3px rgba(16,24,40,.04),0 10px 26px rgba(16,24,40,.07)">
      <div style="height:76px;background:linear-gradient(135deg,{s['tcol']},#10151c);position:relative">
        <div style="position:absolute;top:10px;left:12px;padding:3px 8px;border-radius:999px;
                    background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.22);
                    color:#fff;font-size:10px;font-weight:950">#{s['rank']}</div>
        <div style="position:absolute;right:12px;bottom:9px;text-align:right">
          <div style="font-size:27px;font-weight:950;color:{oc};line-height:1">{s['ovr']}</div>
          <div style="font-size:9px;color:rgba(255,255,255,.66);font-weight:900;letter-spacing:.8px">OVR</div>
        </div>
      </div>
      <div style="padding:0 13px 14px">
        <div style="display:grid;grid-template-columns:86px minmax(0,1fr);gap:10px;align-items:start">
          {photo_html}
          <div style="margin-top:16px">
            {mini_stat("포지션", s['pos'], pc)}
            {mini_stat("나이", age)}
            {mini_stat("가치", val, "#16a34a")}
          </div>
        </div>
        <div style="font-weight:950;font-size:14px;color:#1a1f2e;margin-top:10px;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}{nat_chip}</div>
        <div style="font-size:10px;color:#8a93a5;margin-top:7px;font-weight:800">평점 {s['rating']}</div>
      </div>
    </div>"""


def player_picker_card_html(p: dict, selected: bool = False) -> str:
    """Player Detail 선택용 스카우트 카드."""
    name = html.escape(str(p.get("name", "")))
    short_name = html.escape(str(p.get("short_name", p.get("name", ""))))
    pos = html.escape(str(p.get("pos", "")))
    pc = pos_chip_color(pos)
    ovr = int(p.get("ovr") or 60)
    oc = rating_color(ovr)
    tcol = p.get("tcol", "#1a1f2e")
    sid = str(p.get("sid", "") or "")
    disc = (f"background-image:url('{sid}'),linear-gradient(135deg,{tcol},#0b0f17);"
            if sid else f"background:{tcol};")
    border = f"1.5px solid {tcol}" if selected else "1px solid #e4e8f0"
    shadow = "0 12px 28px rgba(16,24,40,.13)" if selected else "0 1px 3px rgba(16,24,40,.04),0 8px 22px rgba(16,24,40,.05)"
    badge = (
        f"<div style='position:absolute;top:11px;right:11px;width:9px;height:9px;"
        f"border-radius:50%;background:{tcol};box-shadow:0 0 0 4px {tcol}22'></div>"
        if selected else ""
    )
    mins = p.get("minutes")
    mins_txt = f"{int(mins)}분" if mins is not None and pd.notna(mins) else "-"
    g = int(p.get("goals") or 0)
    a = int(p.get("assists") or 0)
    value = html.escape(str(p.get("value", "—")))
    return f"""
    <div title="{name}" style="position:relative;background:#fff;border:{border};border-radius:12px;
                padding:0;text-align:left;min-height:214px;overflow:hidden;
                box-shadow:{shadow}">
      {badge}
      <div style="height:74px;background:linear-gradient(135deg,{tcol}ee,#10151c);
                  position:relative">
        {avatar(sid, tcol, 62, 'position:absolute;left:12px;bottom:-28px;box-shadow:0 8px 18px rgba(16,24,40,.18)', '3px solid #fff')}
        <div style="position:absolute;right:12px;bottom:10px;text-align:right">
          <div style="font-size:26px;font-weight:950;color:#fff;line-height:1">{ovr}</div>
          <div style="font-size:9px;color:rgba(255,255,255,.72);font-weight:900;letter-spacing:.9px">OVR</div>
        </div>
      </div>
      <div style="padding:35px 12px 12px">
        <div style="font-weight:950;font-size:14px;color:#1a1f2e;line-height:1.2;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{short_name}</div>
        <div style="margin-top:6px;display:flex;align-items:center;justify-content:space-between;gap:8px">
          <span style="display:inline-block;padding:3px 8px;background:{pc}1a;color:{pc};
                       border-radius:6px;font-size:10px;font-weight:900">{pos}</span>
          <span style="font-size:11px;font-weight:900;color:#16a34a;white-space:nowrap">{value}</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:11px">
          <div style="background:#f8fafc;border:1px solid #eef1f6;border-radius:8px;padding:6px 3px;text-align:center">
            <div style="font-size:12px;font-weight:950;color:#1a1f2e">{mins_txt}</div>
            <div style="font-size:9px;color:#8a93a5">출전</div>
          </div>
          <div style="background:#f8fafc;border:1px solid #eef1f6;border-radius:8px;padding:6px 3px;text-align:center">
            <div style="font-size:12px;font-weight:950;color:#16a34a">{g}</div>
            <div style="font-size:9px;color:#8a93a5">골</div>
          </div>
          <div style="background:#f8fafc;border:1px solid #eef1f6;border-radius:8px;padding:6px 3px;text-align:center">
            <div style="font-size:12px;font-weight:950;color:#2563eb">{a}</div>
            <div style="font-size:9px;color:#8a93a5">도움</div>
          </div>
        </div>
      </div>
    </div>"""


def selected_player_spotlight_html(p: dict) -> str:
    """선택된 선수용 상단 스포트라이트."""
    name = html.escape(str(p.get("name", "")))
    pos = html.escape(str(p.get("pos", "")))
    pc = pos_chip_color(pos)
    ovr = int(p.get("ovr") or 60)
    oc = rating_color(ovr)
    tcol = p.get("tcol", "#1a1f2e")
    sid = str(p.get("sid", "") or "")
    disc = (f"background-image:url('{sid}'),linear-gradient(135deg,{tcol},#0b0f17);"
            if sid else f"background:{tcol};")
    mins = p.get("minutes")
    mins_txt = f"{int(mins)}분" if mins is not None and pd.notna(mins) else "-"
    value = html.escape(str(p.get("value", "—")))
    g = int(p.get("goals") or 0)
    a = int(p.get("assists") or 0)

    def tile(label: str, val: str, color: str) -> str:
        return (
            f"<div style='background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.16);"
            f"border-radius:9px;padding:9px 10px;min-width:86px'>"
            f"<div style='font-size:18px;font-weight:950;color:{color};line-height:1'>{val}</div>"
            f"<div style='font-size:10px;color:rgba(255,255,255,.68);margin-top:4px'>{label}</div></div>"
        )

    return f"""
    <div style="position:relative;overflow:hidden;border-radius:14px;margin:2px 0 14px;
                background:linear-gradient(135deg,{tcol},#10151c 72%);
                box-shadow:0 12px 34px rgba(16,24,40,.16);padding:20px 22px">
      <div style="position:absolute;right:-42px;top:-70px;width:190px;height:190px;border-radius:50%;
                  background:rgba(255,255,255,.08)"></div>
      <div style="display:flex;align-items:center;gap:18px;position:relative">
        {avatar(sid, tcol, 86, 'box-shadow:0 10px 24px rgba(0,0,0,.25);flex:none', '3px solid rgba(255,255,255,.75)')}
        <div style="flex:1;min-width:0">
          <div style="font-size:11px;font-weight:900;letter-spacing:.8px;color:rgba(255,255,255,.62);
                      text-transform:uppercase">선택된 선수</div>
          <div style="font-size:26px;font-weight:950;color:#fff;line-height:1.12;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:9px">
            <span style="display:inline-block;padding:3px 9px;background:#fff;color:{pc};
                         border-radius:7px;font-size:11px;font-weight:950">{pos}</span>
            <span style="font-size:12px;font-weight:900;color:#bbf7d0">{value}</span>
          </div>
        </div>
        <div style="width:96px;text-align:center;flex:none">
          <div style="font-size:44px;font-weight:950;color:{oc};line-height:.95">{ovr}</div>
          <div style="font-size:10px;color:rgba(255,255,255,.68);font-weight:900;letter-spacing:1px">OVR</div>
        </div>
      </div>
      <div style="display:flex;gap:9px;flex-wrap:wrap;margin-top:18px;position:relative">
        {tile("출전 시간", mins_txt, "#fff")}
        {tile("골", str(g), "#bbf7d0")}
        {tile("도움", str(a), "#bfdbfe")}
      </div>
    </div>"""


# ── Squad Depth Chart — 포지션별 주전/백업 + 깊이 점수 ────────────────────────
# 주전=실제 XI(placements), 백업=벤치(bench_pls). fine_group 버킷으로 묶고,
# 깊이 점수 = 0.7·백업 최고 OVR + 0.3·스쿼드 규모(최대 100). 백업 없으면 얕음.
_SLOT_BUCKET = {
    "GK": "GK",
    "RB": "RB", "RWB": "RB",
    "LB": "LB", "LWB": "LB",
    "RCB": "CB", "LCB": "CB", "CB": "CB",
    "DM": "DM", "RDM": "DM", "LDM": "DM",
    "CM": "CM", "RCM": "CM", "LCM": "CM",
    "CAM": "AM", "AM": "AM",
    "RM": "RW", "RW": "RW",
    "LM": "LW", "LW": "LW",
    "ST": "ST", "FW": "ST",
}


def squad_depth_html(placements: list, bench_pls: list,
                     ovr_map: dict, fine_map: dict) -> str:
    BUCKETS = [("GK", "GK"), ("CB", "CB"), ("RB", "RB"), ("LB", "LB"),
               ("DM", "DM"), ("CM", "CM"), ("AM", "AM"),
               ("RW", "RW"), ("LW", "LW"), ("W", "WF"),
               ("ST", "ST")]
    valid = {b for b, _ in BUCKETS}

    def bucket_of(name, kind, slot=""):
        if kind == "GK":
            return "GK"
        if slot:
            b = _SLOT_BUCKET.get(slot.upper())
            if b and b in valid:
                return b
        b = fine_map.get(name)
        return b if b in valid else None

    def ovr(n):
        return ovr_map.get(n)

    data = {b: {"s": [], "k": []} for b, _ in BUCKETS}
    for p in placements:
        b = bucket_of(p["full"], p.get("kind"), p.get("slot", ""))
        if b:
            data[b]["s"].append(p["full"])
    for p in bench_pls:
        b = bucket_of(p["full"], p.get("kind"), "")
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


def _series_pct(series: pd.Series, value, high_is_good: bool = True) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if value is None or pd.isna(value) or s.empty:
        return None
    vals = list(s) + [float(value)]
    rank = pd.Series(vals).rank(ascending=not high_is_good, method="min").iloc[-1]
    n = len(vals)
    return 1 - (rank - 1) / (n - 1) if n > 1 else 1.0


def goalkeeper_ovr(row: pd.Series, gk_pool: pd.DataFrame) -> int:
    """GK 전용 OVR.

    공통 OVR은 시장가치와 평균평점 중심이라 클린시트/박스 장악 같은 GK 성과가 눌린다.
    여기서는 GK 풀 안에서 시즌 성과를 따로 환산하고, 클린시트 1위는 Golden Glove급
    시즌으로 소폭 보너스를 준다.
    """
    base = player_ovr(row.get("market_value_eur"), row.get("ss_rating"), row.get("minutes"), 0, 0)
    gk_pool = gk_pool[pd.to_numeric(gk_pool.get("minutes"), errors="coerce").fillna(0) >= 300]

    def pct(col: str, high: bool = True) -> float | None:
        if col not in gk_pool.columns:
            return None
        return _series_pct(gk_pool[col], row.get(col), high)

    parts = [
        (pct("gk_clean_sheets"), 0.33),
        (pct("gk_cs_pct"), 0.22),
        (pct("gk_save_pct"), 0.15),
        (pct("gk_high_claims_per90"), 0.10),
        (pct("gk_runs_out_per90"), 0.08),
        (pct("minutes"), 0.12),
    ]
    score = _blend_pcts(parts)
    if score is None:
        return base

    perf = fm_rating(score)
    minutes = float(row.get("minutes") or 0)
    weight = min(0.58, 0.30 + min(1.0, minutes / 2500) * 0.28)
    out = (1 - weight) * base + weight * perf

    clean_sheets = pd.to_numeric(gk_pool.get("gk_clean_sheets"), errors="coerce").dropna()
    if minutes >= 1800 and pd.notna(row.get("gk_clean_sheets")) and not clean_sheets.empty:
        if float(row.get("gk_clean_sheets")) >= float(clean_sheets.max()):
            out += 4
        elif float(row.get("gk_clean_sheets")) >= float(clean_sheets.quantile(0.85)):
            out += 2

    return int(max(50, min(95, round(out))))


def season_achievement_bonus(row: pd.Series, player_pool: pd.DataFrame) -> float:
    """포지션별 시즌 업적 보너스.

    특정 선수 수동 보정이 아니라 리그 내 순위/상위 백분위에 따라 작은 보너스를 준다.
    OVR 본체는 여전히 시장가치+평점 기반이고, 이 함수는 득점왕/도움왕/수비 리더처럼
    시즌 서사가 분명한 선수들이 과소평가되지 않게 보정하는 레이어다.
    """
    minutes = float(row.get("minutes") or 0)
    if minutes < 900:
        return 0.0

    pool = player_pool[pd.to_numeric(player_pool.get("minutes"), errors="coerce").fillna(0) >= 900].copy()
    pos = str(row.get("pos", "")).upper()
    fl = str(row.get("fl_group", "")).upper()
    is_def = "DF" in pos or fl in {"CB", "FB", "RB", "LB"}
    is_mid = "MF" in pos or fl in {"DM", "CM", "AM"}
    is_att = "FW" in pos or fl in {"ST", "W", "RW", "LW"}

    def rank_bonus(col: str, top1: float, top5: float, top10: float = 0.0) -> float:
        if col not in pool.columns or pd.isna(row.get(col)):
            return 0.0
        s = pool[["player", col]].copy()
        s[col] = pd.to_numeric(s[col], errors="coerce")
        s = s.dropna().drop_duplicates("player").set_index("player")[col]
        player = row.get("player")
        if s.empty:
            return 0.0
        rank = int(s.rank(ascending=False, method="min").get(player, 9999))
        if rank == 1:
            return top1
        if rank <= 5:
            return top5
        if rank <= 10:
            return top10
        return 0.0

    def pct_bonus(col: str, p95: float, p85: float = 0.0) -> float:
        if col not in pool.columns:
            return 0.0
        pct = _series_pct(pool[col], row.get(col), True)
        if pct is None:
            return 0.0
        if pct >= 0.95:
            return p95
        if pct >= 0.85:
            return p85
        return 0.0

    bonus = 0.0
    goals = float(row.get("goals") or 0)
    assists = float(row.get("assists") or 0)
    row_ga = goals + assists
    pool_ga = pd.to_numeric(pool.get("goals"), errors="coerce").fillna(0) + pd.to_numeric(
        pool.get("assists"), errors="coerce"
    ).fillna(0)
    pool_ga.index = pool["player"]
    if not pool_ga.empty:
        ga_rank = int(pool_ga.rank(ascending=False, method="min").get(row.get("player"), 9999))
        if ga_rank == 1:
            bonus += 2.0
        elif ga_rank <= 5:
            bonus += 1.2
        elif ga_rank <= 10:
            bonus += 0.6

    if is_att:
        bonus += rank_bonus("goals", 3.0, 2.0, 1.0)
        bonus += rank_bonus("assists", 1.4, 0.9, 0.4)
        bonus += pct_bonus("npxg_p90", 1.0, 0.5)
    elif is_mid:
        bonus += rank_bonus("assists", 3.0, 2.0, 1.0)
        bonus += pct_bonus("key_passes_per90", 1.4, 0.7)
        bonus += pct_bonus("big_chances_created_per90", 1.4, 0.7)
        bonus += pct_bonus("final_third_passes_per90", 0.8, 0.4)
        bonus += pct_bonus("tackles_won_per90", 0.6, 0.3)
        bonus += pct_bonus("interceptions_per90", 0.6, 0.3)
    elif is_def:
        bonus += pct_bonus("interceptions_per90", 1.2, 0.6)
        bonus += pct_bonus("tackles_won_per90", 1.0, 0.5)
        bonus += pct_bonus("aerial_won_pct", 0.9, 0.4)
        bonus += pct_bonus("clearances_per90", 0.8, 0.4)
        bonus += rank_bonus("gk_clean_sheets", 1.4, 0.8, 0.4)
    else:
        bonus += rank_bonus("goals", 1.5, 0.8, 0.4)
        bonus += rank_bonus("assists", 1.5, 0.8, 0.4)

    return min(4.0, bonus)


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
                        "full": r["player"], "tip": f"{slot} · {minutes}분 · {chip}",
                        "slot": slot})
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
                        "minutes": minutes, "full": r["player"], "tip": tip,
                        "slot": slot})
    return out


def _match_db_row(name: str, team: str, full: pd.DataFrame) -> pd.DataFrame:
    """ESPN 선수명 → 우리 DB 행. norm_key 정확매칭 후 성(姓) 폴백."""
    nk = _norm(name)
    drow = full[full["norm_key"] == nk]
    if not drow.empty:
        return drow
    # 성 기준 폴백 — 같은 팀 우선
    last = nk.split()[-1] if nk else ""
    if not last:
        return drow
    cand = full[full["norm_key"].str.split().str[-1] == last]
    if "squad" in cand.columns:
        same = cand[cand["squad"] == team]
        if not same.empty:
            cand = same
    return cand.head(1)


def placements_from_espn(team: str, starters: list[dict], formation: str,
                         full: pd.DataFrame, pct: pd.DataFrame) -> list[dict] | None:
    """ESPN 경기 선발 11명(dict: player·espn_pos·jersey) → 배치 리스트.

    ESPN position을 espn_assign_slots로 포메이션 슬롯에 매핑한 뒤, 선수명을
    DB와 norm 매칭해 사진·스탯·강점 툴팁을 채운다(placements_from_slots와 동일 형식).
    DB 매칭 실패 선수는 토큰만(사진 없이) 표시한다.
    """
    starters = [s for s in starters if s.get("starter", True)][:11]
    if len(starters) < 11:
        return None
    slots = espn_assign_slots([str(s.get("espn_pos") or "") for s in starters], formation)
    tcol = team_color(team)
    out: list[dict] = []
    for r, slot in zip(starters, slots):
        if not slot:
            continue
        x, y = slot_xy(slot, formation)
        disp = display_slot(slot, formation)
        kind = slot_kind(slot)
        pname = str(r.get("player") or "")
        drow = _match_db_row(pname, team, full)
        nk = drow.iloc[0]["norm_key"] if not drow.empty else _norm(pname)
        prow = pct[pct["norm_key"] == nk]
        minutes = int(drow.iloc[0]["minutes"]) if not drow.empty else 0
        sid = _photo(drow.iloc[0].get("sofa_id"), drow.iloc[0].get("tm_photo")) if not drow.empty else ""
        name = pname.split()[-1] if pname else "?"
        num = _num_str(r.get("jersey"))
        if kind == "GK":
            save = drow.iloc[0].get("gk_save_pct") if not drow.empty else None
            chip = f"세이브% {save:.0f}" if (save is not None and pd.notna(save)) else "GK"
            out.append({"name": name, "x": x, "y": y, "kind": "GK", "abbr": "GK",
                        "num": num, "sid": sid, "tcol": tcol, "role": slot, "chip": chip,
                        "minutes": minutes, "full": pname, "tip": f"{slot} · {chip}",
                        "slot": slot})
        elif not prow.empty:
            prow0 = prow.iloc[0]
            role, _ = assign_role(prow0, position_group(prow0["pos"]))
            strengths = top_strengths(prow0)
            ga = _ga_str(drow.iloc[0] if not drow.empty else None)
            tip = f"{disp} · {minutes}분{ga}<br>" + "<br>".join(f"{lab} {v}%" for lab, v in strengths)
            out.append({"name": name, "x": x, "y": y, "kind": kind, "abbr": disp,
                        "num": num, "sid": sid, "tcol": tcol,
                        "role": f"{disp} · {role.split(' (')[0]}",
                        "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": minutes, "full": pname, "tip": tip, "slot": slot})
        else:
            out.append({"name": name, "x": x, "y": y, "kind": kind, "abbr": disp,
                        "num": num, "sid": sid, "tcol": tcol, "role": disp, "chip": "",
                        "minutes": minutes, "full": pname, "tip": disp, "slot": slot})

    # 좌표 충돌 해소 — 다중 미드라인 포메이션(4-2-2-2·4-1-3-2 등, 전체의 2.6%)에서
    # formation_slots가 같은 슬롯(RDM/LDM)을 두 번 만들어 두 선수가 겹친다.
    # 같은 좌표 그룹을 가로로 분산해 시각적 중첩을 막는다.
    coord_groups: dict[tuple[int, int], list[dict]] = {}
    for p in out:
        coord_groups.setdefault((round(p["x"]), round(p["y"])), []).append(p)
    for (gx, _), members in coord_groups.items():
        k = len(members)
        if k > 1:
            for i, p in enumerate(members):
                p["x"] = min(92, max(8, gx + (i - (k - 1) / 2) * 13))
    return out


def espn_main_xi(team: str, espn_all):
    """ESPN 라인업에서 팀의 주 포메이션 + 그 포메이션을 쓴 가장 최근 경기의 실제 XI.
    반환: (formation, match_rows) 또는 (None, None)."""
    if espn_all is None:
        return None, None
    et = espn_all[espn_all["squad"] == team]
    if et.empty:
        return None, None
    pm = et.drop_duplicates("event_id")[["event_id", "formation", "date"]].dropna(subset=["formation"])
    if pm.empty:
        return None, None
    main_form = pm["formation"].mode().iloc[0]
    cand = pm[pm["formation"] == main_form].sort_values("date")
    evid = cand.iloc[-1]["event_id"]
    mrows = et[(et["event_id"] == evid) & (et["starter"])].to_dict("records")
    return str(main_form), mrows


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
                        "minutes": int(r["minutes"]), "full": r["player"], "tip": tip,
                        "slot": ""})
    if gk is not None:
        save = gk.get("gk_save_pct")
        chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
        out.append({"name": gk["player"].split()[-1], "x": 50, "y": GK_Y, "kind": "GK",
                    "abbr": "GK", "num": "", "sid": _photo("", gk.get("tm_photo")), "tcol": tcol,
                    "role": "골키퍼", "chip": chip, "minutes": int(gk["minutes"]),
                    "full": gk["player"], "tip": f"{int(gk['minutes'])}분 · {chip}",
                    "slot": "GK"})
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

