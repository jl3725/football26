"""
Team Overview 탭 렌더 함수 + 구단 정보/특성 상수.

구단 정보 카드, 스카우트 도시에, 팀 레이팅(도넛), 스냅샷/셋피스, 감독 프로필,
레이더, AI 스카우트 리포트, 폼/xG/스쿼드 패널, 리더, 순위 배너 등.
모두 인자로 데이터를 받는 순수 렌더 함수다(common·metrics 헬퍼만 사용).
"""
from __future__ import annotations

import html

import pandas as pd

from .common import (
    ACCENT, TEAM_EXTRA, team_color, team_logo, rating_color,
    _photo, avatar, portrait_photo, fmt_value, nation_code, flag_chip, fee_label,
)
from .metrics import (
    fm_rating, player_ovr, top_strengths,
    _rank_pct, _blend_pcts, _blend_scores, _pct_to_rating,
    _power_from_pct, _power_from_index,
)


# ==== 아래 함수/상수는 app.py에서 sed로 이동됨 (TEAM_INFO, team_info_html,
# ==== team_ratings, overview_scout_dossier_html, 등) ====

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


# sofa_photo·_photo·avatar·portrait_photo·fmt_value·nation_code·flag_chip·fee_label

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


# _rank_pct·_blend_pcts·_blend_scores·_pct_to_rating·_power_from_pct·_power_from_index
# → src/ui/metrics.py (상단 import)


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


