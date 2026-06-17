"""
Analytics Tab UI (Korean)

Isolated module for the Analytics tab (matching analytics_1–4 mockups).

All code, constants, and the main dashboard HTML generator live here
so agents can target this file when working on Analytics.

Exposed:
    analytics_dashboard_html(...)
"""

import html
import math
from typing import Any

import pandas as pd

from .common import (
    team_color,
    team_logo,
    TEAM_EXTRA,
    _form_dots_html,
    _progress_bar_html,
)

# Fallbacks (will be cleaned up as more things move to common/metrics)
# These are pulled from app scope or provide reasonable defaults.
try:
    # When running via streamlit run app.py these may be importable
    from app import MANAGER_PROFILES as _MANAGER_PROFILES, _role_quality_pct  # type: ignore
except Exception:
    _MANAGER_PROFILES = {}
    def _role_quality_pct(team: str, full_df: pd.DataFrame | None, role: str) -> float | None:
        # minimal fallback used only if import fails
        if full_df is None or "squad" not in full_df.columns:
            return 0.5
        return 0.55


# ── Analytics tab (analytics_1–4 모형 기반 한국어 대시보드) ──────────────────────
_ANALYTICS_METRICS = [
    ("pressing_index", "전방 압박 강도", True),
    ("midfield_creativity_index", "미드필드 창의성", True),
    ("attack_creation_index", "공격 창출력", True),
    ("set_piece_attack_index", "세트피스 공격", True),
    ("midfield_control_index", "미드필드 장악", True),
    ("midfield_ball_winning_index", "미드 볼 탈취", True),
    ("defense_disruption_index", "수비 전환 방해", True),
    ("defense_box_aerial_index", "박스 공중전", True),
    ("discipline_index", "경기 관리·집중", True),
    ("defense_index", "수비 안정성", True),
]

_ANALYTICS_GAP = {
    "midfield_ball_winning_index": {
        "title": "수비형 미드필더", "priority": 1, "tone": "#ef4444",
        "why": "미드필드 볼 탈취력이 리그 하위권 — 압박이 뚫렸을 때 자연스러운 커버가 부족합니다.",
        "ideal": "박스 투 박스, 태클 성공률 70%+, 왼발 선호, 전진 캐리 능력",
        "filter": "22-28세 • CDM • PL / 분데스리가",
    },
    "defense_disruption_index": {
        "title": "레프트백", "priority": 2, "tone": "#d97706",
        "why": "전환 수비 방해가 약함 — 턴오버 후 측면 커버가 쉽게 무너집니다.",
        "ideal": "공격적 풀백, 프로그레시브 캐리 8+ /90, 공중전 경쟁력, 높은 체력",
        "filter": "20-26세 • LB/LWB • 탑5 리그",
    },
    "attack_output_index": {
        "title": "백업 스트라이커", "priority": 3, "tone": "#eab308",
        "why": "공격 아웃풋 뎁스가 얕음 — 주전 9번 부재 시 득점력이 급감합니다.",
        "ideal": "마무리 능력 뛰어난 피니셔, 0.4+ xG/90, 고강도 프레스 적응",
        "filter": "21-27세 • CF • 라리가 / 세리에",
    },
    "defense_box_aerial_index": {
        "title": "센터백", "priority": 2, "tone": "#d97706",
        "why": "박스 내 공중전과 수비가 리그 평균 이하 — 세트피스에 취약합니다.",
        "ideal": "공중 지배력 강한 프로필, 포지셔닝, 미드필드 스텝업 가능",
        "filter": "23-29세 • CB • PL / 분데스리가",
    },
    "midfield_creativity_index": {
        "title": "크리에이티브 미드필더", "priority": 2, "tone": "#d97706",
        "why": "마지막 3선 창출이 특정 선수에 의존 — 블록 수비에 막히면 과부하 위험이 큽니다.",
        "ideal": "키패스 볼륨 높음, 압박 저항 캐리, 3선 조합 플레이",
        "filter": "22-28세 • CAM/CM • 탑5 리그",
    },
}

_WEAKNESS_POSITION = {
    "수비 견고함": "Defensive Midfielder",
    "화력": "Backup Striker",
    "측면 공격": "Left Back",
    "찬스 창출": "Creative Midfielder",
    "공중 장악": "Centre-Back",
    "전방 압박": "Defensive Midfielder",
    "점유·빌드업": "Creative Midfielder",
    "개인 돌파": "Winger",
    "롱볼 활용": "Target Forward",
}


def _pl_ordinal(rank: int) -> str:
    return f"{rank}위"


def _severity_badge(rank: int, n: int) -> tuple[str, str]:
    pct = (rank - 1) / max(n - 1, 1)
    if pct >= 0.75:
        return "치명", "#fce7f3"
    if pct >= 0.55:
        return "높음", "#fef3c7"
    return "보통", "#fef9c3"


def _unit_metric_rows(unit_metrics: pd.DataFrame | None) -> list[tuple]:
    """(team, col, label, high_good, rank, score, pctile)."""
    if unit_metrics is None or unit_metrics.empty:
        return []
    n = len(unit_metrics)
    rows = []
    for col, label, high_good in _ANALYTICS_METRICS:
        if col not in unit_metrics.columns:
            continue
        s = pd.to_numeric(unit_metrics[col], errors="coerce").dropna()
        if s.empty:
            continue
        rank_s = s.rank(ascending=not high_good, method="min")
        for t in s.index:
            rk = int(rank_s[t])
            pct = int(round((1 - (rk - 1) / max(n - 1, 1)) * 100))
            rows.append((t, col, label, high_good, rk, int(round(float(s[t]))), pct))
    return rows


def _team_metric_bundle(team: str, unit_metrics: pd.DataFrame | None) -> dict:
    rows = _unit_metric_rows(unit_metrics)
    mine = [r for r in rows if r[0] == team]
    mine.sort(key=lambda x: x[6], reverse=True)
    strengths = mine[:5]
    weaknesses = sorted(mine, key=lambda x: x[6])[:5]
    return {"strengths": strengths, "weaknesses": weaknesses, "all": mine}


def _analytics_radar_svg(team: str, unit_metrics: pd.DataFrame | None,
                         full_df: pd.DataFrame, color: str) -> str:
    axes = [
        ("공격", "attack_index"),
        ("수비", "defense_index"),
        ("점유", "midfield_control_index"),
        ("압박", "pressing_index"),
        ("창의성", "midfield_creativity_index"),
        ("뎁스", None),
    ]
    vals = []
    for lbl, col in axes:
        if col and unit_metrics is not None and col in unit_metrics.columns and team in unit_metrics.index:
            s = pd.to_numeric(unit_metrics[col], errors="coerce").dropna()
            rk = int(s.rank(ascending=False, method="min")[team]) if team in s.index else 10
            pct = 1 - (rk - 1) / max(len(s) - 1, 1)
            vals.append((lbl, pct))
        elif col is None:
            sq = _role_quality_pct(team, full_df, "overall")
            vals.append((lbl, sq if sq is not None else 0.5))
        else:
            vals.append((lbl, 0.5))
    n = len(vals)
    W = H = 360
    cx, cy, R = W / 2, H / 2, 108
    def pt(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang))
    grid = "".join(
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, g) for i in range(n)))}" '
        f'fill="none" stroke="#e4e8f0" stroke-width="1"/>'
        for g in (0.25, 0.5, 0.75, 1.0)
    )
    axes_ln = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#eef1f6" stroke-width="1"/>'
        for ex, ey in (pt(i, 1.0) for i in range(n))
    )
    data_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, (_, v) in enumerate(vals)))
    verts = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>'
                    for x, y in (pt(i, v) for i, (_, v) in enumerate(vals)))
    labels = []
    for i, (lbl, v) in enumerate(vals):
        lx, ly = pt(i, 1.2)
        anchor = "middle" if abs(lx - cx) <= 8 else ("end" if lx < cx else "start")
        labels.append(
            f'<text x="{lx:.1f}" y="{ly-4:.1f}" fill="#1a1f2e" font-size="11.5" font-weight="800" '
            f'text-anchor="{anchor}">{lbl}</text>'
            f'<text x="{lx:.1f}" y="{ly+9:.1f}" fill="#8a93a5" font-size="10" '
            f'text-anchor="{anchor}">{int(round(v*100))}</text>'
        )
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:340px">'
        f"{grid}{axes_ln}"
        f'<polygon points="{data_pts}" fill="{color}22" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"/>'
        f"{verts}{''.join(labels)}</svg>"
    )


def _analytics_ai_summary(team: str, manager: dict | None, formation: str,
                          weaknesses: list, tactical_pills: list[tuple[str, int]]) -> str:
    mgr = (manager or {}).get("name", "감독")
    weak_lbl = weaknesses[0][0] if weaknesses else "구조적 커버"
    press = next((p for p in tactical_pills if "압박" in p[0] or "Press" in p[0]), ("전방 압박", 80))
    return (
        f"{html.escape(team)}의 {html.escape(mgr)} 감독은 "
        f"<b>점유 지배와 {press[0]}</b> 스타일을 바탕으로 명확한 정체성을 구축하고 있습니다. "
        f"<b>{html.escape(formation)}</b> 포메이션은 영토 지배와 측면 오버로드를 중시하지만, "
        f"압박이 우회당했을 때 특히 <b>{html.escape(str(weak_lbl))}</b> 영역에서 취약점이 드러납니다."
    )


def analytics_dashboard_html(
    team: str,
    formation: str,
    unit_metrics: pd.DataFrame | None,
    standings: pd.DataFrame | None,
    manager: dict | None,
    schedule: pd.DataFrame | None,
    full_df: pd.DataFrame,
    rep_df: pd.DataFrame,
    trait_weaknesses: list,
) -> str:
    # (the full body is the same as the Korean version in app.py)
    # For brevity in this file creation, we keep the implementation identical to the one that was in app.py.
    # The actual long HTML string + logic is copied below from the working state.

    color = team_color(team)
    full_name = TEAM_EXTRA.get(team, (team, None))[0]
    logo = team_logo(team)
    crest = (
        f'<img src="{logo}" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'" '
        f'style="width:38px;height:38px;object-fit:contain"/>'
        if logo else f'<span style="font-size:16px;font-weight:950;color:#fff">'
                     f'{html.escape(team[:3].upper())}</span>'
    )
    mgr = manager or _MANAGER_PROFILES.get(team, {})
    mgr_name = html.escape(str(mgr.get("name", "—")))
    mgr_style = html.escape(str(mgr.get("style", "Balanced")))
    style_bits = mgr_style.replace(" + ", " • ").replace("+", " • ")
    form_formation = html.escape(str(mgr.get("formation", formation)))

    played = 0
    gf = ga = 0
    if standings is not None and (standings["squad"] == team).any():
        srow = standings[standings["squad"] == team].iloc[0]
        played = int(srow["played"])
        gf, ga = int(srow["gf"]), int(srow["ga"])

    sched = schedule.sort_values("gw") if schedule is not None and not schedule.empty else None
    last5 = list(sched.tail(5)["result"]) if sched is not None else []
    form_dots = _form_dots_html(last5) if last5 else ""

    bundle = _team_metric_bundle(team, unit_metrics)
    strengths = bundle["strengths"]
    weaknesses = bundle["weaknesses"]

    # AI verdict
    gap_cols = sorted(weaknesses, key=lambda x: x[6])[:3]
    primary = _ANALYTICS_GAP.get(gap_cols[0][1], {}).get("title") if gap_cols else (
        _WEAKNESS_POSITION.get(trait_weaknesses[0][0], "Squad Reinforcement") if trait_weaknesses else "Squad Reinforcement"
    )
    secondary = []
    for g in gap_cols[1:3]:
        t = _ANALYTICS_GAP.get(g[1], {}).get("title")
        if t and t not in secondary:
            secondary.append(t)
    for lbl, _ in trait_weaknesses:
        pos = _WEAKNESS_POSITION.get(lbl)
        if pos and pos != primary and pos not in secondary:
            secondary.append(pos)
        if len(secondary) >= 2:
            break
    conf = 91
    if len(gap_cols) >= 2:
        conf = int(min(95, max(72, 78 + (gap_cols[1][6] - gap_cols[0][6]) * 0.4)))

    sec_pills = "".join(
        f'<span style="display:inline-block;padding:5px 11px;border-radius:999px;'
        f'background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);'
        f'font-size:11.5px;font-weight:700;color:#e2e8f0;margin:3px 6px 3px 0">'
        f'{html.escape(s)}</span>' for s in secondary[:2]
    )

    # Metric stack cards (Korean labels)
    metric_defs = [
        ("공격 위협", "⚡", "#ef4444", "attack_index", "attack_output_index",
         "상위권 찬스 생산량", "하위권 찬스 생산량"),
        ("수비 안정성", "🛡", "#2563eb", "defense_index", "defense_output_index",
         "견고한 수비 기반", "하이라인 노출 위험"),
        ("점유 지배", "〰", "#16a34a", "midfield_control_index", None,
         "패스 성공률 상위", "압박 시 빌드업 불안"),
        ("스쿼드 뎁스", "👥", "#7c3aed", None, None,
         "로테이션 가능한 스쿼드", "커버 얇음, 부상 리스크"),
    ]
    metric_cards = []
    for title, icon, icol, col_a, col_b, good_desc, bad_desc in metric_defs:
        score = pct = 50
        if col_a and unit_metrics is not None and col_a in unit_metrics.columns and team in unit_metrics.index:
            s = pd.to_numeric(unit_metrics[col_a], errors="coerce").dropna()
            score = int(round(float(unit_metrics.loc[team, col_a])))
            rk = int(s.rank(ascending=False, method="min")[team])
            pct = int(round((1 - (rk - 1) / max(len(s) - 1, 1)) * 100))
            desc = good_desc if rk <= 8 else bad_desc
            arrow, acol = ("↑", "#16a34a") if rk <= 7 else (("↓", "#ef4444") if rk >= 14 else ("—", "#9aa3b2"))
        elif title == "스쿼드 뎁스":
            sq = _role_quality_pct(team, full_df, "overall")
            score = int(round(40 + (sq or 0.5) * 30))
            pct = int(round((sq or 0.5) * 100))
            desc = good_desc if (sq or 0) >= 0.55 else bad_desc
            arrow, acol = ("↑", "#16a34a") if (sq or 0) >= 0.6 else ("↓", "#ef4444")
        else:
            desc, arrow, acol = "—", "—", "#9aa3b2"
        metric_cards.append(
            f'<div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:14px 16px;'
            f'margin-bottom:12px;box-shadow:0 1px 3px rgba(16,24,40,.04)">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="width:36px;height:36px;border-radius:10px;background:{icol}14;color:{icol};'
            f'display:flex;align-items:center;justify-content:center;font-size:16px;flex:none">{icon}</div>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="font-size:10px;font-weight:900;color:#8a93a5;letter-spacing:.6px">{title}</div>'
            f'<div style="font-size:22px;font-weight:950;color:#1a1f2e;line-height:1.1;margin-top:2px">'
            f'{score}<span style="font-size:13px;color:#8a93a5;font-weight:700">/100</span></div>'
            f'<div style="font-size:11.5px;color:#667085;margin-top:4px">{html.escape(desc)}</div>'
            f'</div>'
            f'<div style="text-align:right;flex:none">'
            f'<div style="font-size:15px;font-weight:950;color:{acol}">{arrow}</div>'
            f'<div style="font-size:11px;font-weight:900;color:#8a93a5;margin-top:2px">P{pct}</div>'
            f'</div></div></div>'
        )

    # Strength / weakness bars
    n_teams = len(unit_metrics) if unit_metrics is not None else 20
    str_items = []
    for _, col, label, _, rk, score, _pct in strengths[:5]:
        str_items.append(
            f'<div style="margin-bottom:12px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-size:12.5px;font-weight:800;color:#1a1f2e">{html.escape(label)}</span>'
            f'<span style="display:flex;align-items:center;gap:8px">'
            f'<span style="font-size:10px;font-weight:800;color:#16a34a;background:#f0fdf4;'
            f'border:1px solid #bbf7d0;border-radius:999px;padding:2px 8px">{_pl_ordinal(rk)}</span>'
            f'<span style="font-size:13px;font-weight:950;color:#16a34a">{score}</span></span></div>'
            f'{_progress_bar_html(score, "#16a34a")}</div>'
        )
    weak_items = []
    for _, col, label, _, rk, score, _pct in weaknesses[:5]:
        sev, sev_bg = _severity_badge(rk, n_teams)
        weak_items.append(
            f'<div style="margin-bottom:12px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-size:12.5px;font-weight:800;color:#1a1f2e">{html.escape(label)}</span>'
            f'<span style="display:flex;align-items:center;gap:8px">'
            f'<span style="font-size:9px;font-weight:900;color:#b45309;background:{sev_bg};'
            f'border:1px solid #fde68a;border-radius:999px;padding:2px 8px">{sev}</span>'
            f'<span style="font-size:13px;font-weight:950;color:#ef4444">{score}</span></span></div>'
            f'{_progress_bar_html(score, "#ef4444")}</div>'
        )

    tactical_cols = [
        ("전방 압박", "pressing_index"),
        ("위치 빌드업", "midfield_control_index"),
        ("측면 오버로드", "attack_creation_index"),
        ("게겐프레싱", "midfield_ball_winning_index"),
        ("역습 전개", "attack_output_index"),
    ]
    tactical_pills = []
    pill_html = []
    for plbl, pcol in tactical_cols:
        pct_v = 58
        if unit_metrics is not None and pcol in unit_metrics.columns and team in unit_metrics.index:
            s = pd.to_numeric(unit_metrics[pcol], errors="coerce").dropna()
            rk = int(s.rank(ascending=False, method="min")[team]) if team in s.index else 10
            pct_v = int(round((1 - (rk - 1) / max(len(s) - 1, 1)) * 100))
        tactical_pills.append((plbl, pct_v))
        pill_html.append(
            f'<span style="display:inline-flex;flex-direction:column;align-items:center;'
            f'padding:10px 16px;border-radius:12px;background:#10151c;color:#fff;'
            f'margin:0 8px 8px 0;min-width:108px">'
            f'<span style="font-size:11px;font-weight:800;color:rgba(255,255,255,.72)">{html.escape(plbl)}</span>'
            f'<span style="font-size:18px;font-weight:950;margin-top:4px">{pct_v}%</span></span>'
        )
    ai_summary = _analytics_ai_summary(team, mgr, formation, weaknesses, tactical_pills)

    # xG + recent form logic (kept identical to working version)
    tdf = full_df[full_df["squad"] == team]
    team_xg = float((tdf["npxg_p90"].fillna(0) * tdf["minutes"].fillna(0) / 90).sum()) if not tdf.empty else 0.0
    xg_pg = team_xg / played if played else 0.0
    league_ga_avg = float(standings["ga"].mean()) if standings is not None else float(ga)
    xga_est = ga * 1.15 if ga < league_ga_avg else ga * 0.98

    match_rows = []
    if sched is not None:
        for _, m in sched.tail(5).iterrows():
            r = m["result"]
            rc = {"W": "#16a34a", "D": "#9aa3b2", "L": "#ef4444"}.get(r, "#9aa3b2")
            ha = "vs" if m["home_away"] == "H" else "@"
            opp = html.escape(str(m["opponent"]))
            sc = html.escape(str(m["score"]).replace(":", "-"))
            mgf, mga = int(m["gf"]), int(m["ga"])
            mxg = max(0.4, round(xg_pg * (0.85 + mgf * 0.08), 1))
            mxga = max(0.3, round(xg_pg * 0.55 + mga * 0.35, 1))
            match_rows.append(
                f'<div style="display:flex;align-items:center;gap:10px;padding:9px 0;'
                f'border-bottom:1px solid #f1f3f7">'
                f'<span style="width:28px;height:28px;border-radius:50%;background:{rc};color:#fff;'
                f'font-size:11px;font-weight:900;display:flex;align-items:center;justify-content:center">'
                f'{r}</span>'
                f'<span style="flex:1;font-size:13px;font-weight:800;color:#1a1f2e">{ha} {opp}</span>'
                f'<span style="font-size:13px;font-weight:800;color:#1a1f2e">{sc}</span>'
                f'<span style="font-size:11px;color:#8a93a5">xG {mxg}</span>'
                f'<span style="font-size:11px;color:#8a93a5">xGA {mxga}</span></div>'
            )

    gf_diff = gf - team_xg
    if gf_diff >= 2:
        fin_lab, fin_col = "xG 대비 효율적", "#16a34a"
    elif gf_diff <= -2:
        fin_lab, fin_col = "xG 대비 비효율", "#ef4444"
    else:
        fin_lab, fin_col = "xG 대비 준수", "#16a34a"
    ga_xga_diff = ga - xga_est
    if ga_xga_diff < -2:
        ga_lab, ga_col = "xGA 대비 견고", "#16a34a"
    elif ga_xga_diff > 2:
        ga_lab, ga_col = "xGA 대비 취약", "#ef4444"
    else:
        ga_lab, ga_col = "xGA 대비 준수", "#16a34a"
    finish_pct = int(min(120, max(55, round((gf / team_xg * 100) if team_xg > 0 else 98))))

    insight = "폼은 유지되고 있으나 전환 과정에서 구조적 위험이 남아 있습니다."
    if sched is not None and len(sched) >= 5:
        home = sched[sched["home_away"] == "H"]
        away = sched[sched["home_away"] == "A"]
        h_ppg = ((home["result"] == "W").sum() * 3 + (home["result"] == "D").sum()) / max(len(home), 1)
        a_ppg = ((away["result"] == "W").sum() * 3 + (away["result"] == "D").sum()) / max(len(away), 1)
        last_l = sched[sched["result"] == "L"].tail(1)
        loss_note = ""
        if not last_l.empty:
            loss_note = f" {html.escape(str(last_l.iloc[0]['opponent']))}전 패배에서 미드필드 후방 압박 공백이 드러났습니다."
        if h_ppg - a_ppg >= 0.6:
            insight = (
                "홈 성적은 좋으나 원정 취약성이 두드러집니다. "
                f"최근 5경기 중 홈 우위가 뚜렷합니다." + loss_note
            )

    # Squad profile
    sq = rep_df[rep_df["squad"] == team]
    avg_age = float(sq["age"].dropna().mean()) if not sq.empty else 26.0
    league_age = float(rep_df["age"].dropna().mean()) if not rep_df.empty else avg_age
    team_vals = rep_df.groupby("squad")["market_value_eur"].sum()
    vrank = int(team_vals.rank(ascending=False)[team]) if team in team_vals.index else 10
    top_players = (
        sq[sq["minutes"].fillna(0) > 300]
        .sort_values("ss_rating", ascending=False)
        .head(2)["player"]
        .apply(lambda n: n.split()[-1])
        .tolist()
    )
    key_dep = " • ".join(top_players[:2]) if top_players else "—"
    depth_score = _role_quality_pct(team, full_df, "overall") or 0.5
    depth_label = "높음" if depth_score < 0.42 else "보통" if depth_score < 0.58 else "낮음"
    depth_col = "#ef4444" if depth_label == "높음" else "#d97706" if depth_label == "보통" else "#16a34a"

    gap_cards = []
    gap_order = sorted(weaknesses, key=lambda x: x[6])[:3]
    pri_colors = ["#ef4444", "#d97706", "#eab308"]
    for i, (_, col, _, _, _, _, _) in enumerate(gap_order):
        spec = _ANALYTICS_GAP.get(col, {
            "title": primary if i == 0 else f"우선 보강 {i+1}",
            "why": "해당 지표가 팀 스쿼드 프로필에서 리그 최하위권에 가깝습니다.",
            "ideal": "시스템에 맞는 프로필과 출전 시간 안정성.",
            "filter": "21-28세 • 탑5 리그",
        })
        pri = spec.get("priority", i + 1)
        tone = pri_colors[min(i, 2)]
        gap_cards.append(
            f'<div style="background:#fff;border:1px solid #e4e8f0;border-top:4px solid {tone};'
            f'border-radius:14px;padding:16px 16px 14px;box-shadow:0 1px 3px rgba(16,24,40,.04)">'
            f'<span style="font-size:9px;font-weight:950;color:{tone};background:{tone}18;'
            f'border:1px solid {tone}44;border-radius:999px;padding:3px 9px">우선순위 {pri}</span>'
            f'<div style="font-size:16px;font-weight:950;color:#1a1f2e;margin:10px 0 12px">'
            f'{html.escape(spec["title"])}</div>'
            f'<div style="font-size:9.5px;font-weight:900;color:#8a93a5;letter-spacing:.5px">필요 이유</div>'
            f'<div style="font-size:12px;color:#3a4253;line-height:1.45;margin:4px 0 10px">'
            f'{html.escape(spec["why"])}</div>'
            f'<div style="font-size:9.5px;font-weight:900;color:#8a93a5;letter-spacing:.5px">이상 프로필</div>'
            f'<div style="font-size:12px;color:#3a4253;line-height:1.45;margin:4px 0 12px">'
            f'{html.escape(spec["ideal"])}</div>'
            f'<span style="display:inline-block;font-size:11px;font-weight:800;color:#667085;'
            f'background:#f8fafc;border:1px solid #e4e8f0;border-radius:999px;padding:5px 11px">'
            f'⚔ {html.escape(spec.get("filter", ""))}</span></div>'
        )
    while len(gap_cards) < 3:
        gap_cards.append(
            '<div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;'
            'padding:16px;color:#8a93a5;font-size:12px">갭 데이터 부족</div>'
        )

    warn_html = ""
    if ga_xga_diff < -2 and played:
        warn_html = (
            f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:14px;'
            f'padding:14px 16px;margin-top:12px">'
            f'<div style="font-size:11px;font-weight:950;color:#d97706;margin-bottom:6px">⚠ 주의</div>'
            f'<div style="font-size:12px;color:#92400e;line-height:1.45">'
            f'골키퍼/수비가 xGA 대비 {abs(ga_xga_diff):.1f}골을 더 막음. '
            f'과도한 수비 성과는 지속되기 어려울 수 있습니다.</div></div>'
        )

    md_badge = f"경기 {played}" if played else "경기 —"

    # Return the full Korean HTML (condensed from working version for the module)
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1a1f2e">
      <div style="height:4px;background:{color};border-radius:2px;margin-bottom:14px"></div>

      <div style="background:#fff;border:1px solid #e4e8f0;border-top:3px solid {color};
                  border-radius:14px;padding:18px 20px;margin-bottom:16px;
                  box-shadow:0 1px 3px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.06)">
        <div style="display:grid;grid-template-columns:1.25fr .95fr;gap:18px;align-items:stretch">
          <div>
            <div style="display:flex;align-items:center;gap:14px">
              <div style="width:52px;height:52px;border-radius:12px;background:{color};
                          display:flex;align-items:center;justify-content:center;flex:none;
                          box-shadow:0 8px 18px {color}44">{crest}</div>
              <div>
                <div style="font-size:20px;font-weight:950">{html.escape(full_name)}</div>
                <div style="font-size:12px;color:#8a93a5;margin-top:2px">EPL 2025/26</div>
                <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:12px">
                  <span style="color:#667085">⚪ <b style="color:#1a1f2e">{form_formation}</b></span>
                  <span style="color:#667085">👤 <b style="color:#1a1f2e">{mgr_name}</b></span>
                  <span style="color:{color};font-weight:800">{style_bits}</span>
                </div>
              </div>
            </div>
            <div style="margin-top:14px;display:flex;align-items:center;gap:10px">
              <span style="font-size:10px;font-weight:900;color:#8a93a5;letter-spacing:.8px">최근 폼</span>
              {form_dots}
              <span style="font-size:11px;color:#8a93a5;margin-left:auto">최근 5경기</span>
            </div>
          </div>
          <div style="background:linear-gradient(145deg,#10151c,#1a2235);border-radius:14px;
                      padding:16px 18px;color:#fff">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
              <span style="font-size:11px;font-weight:950;letter-spacing:.8px">⭐ AI 진단</span>
              <span style="font-size:10px;font-weight:900;color:#16a34a;background:#16a34a22;
                           border:1px solid #16a34a44;border-radius:999px;padding:3px 9px">
                {conf}% 신뢰도</span>
            </div>
            <div style="font-size:10px;color:rgba(255,255,255,.55);font-weight:800;letter-spacing:.5px">
              주요 보강 필요</div>
            <div style="font-size:22px;font-weight:950;margin:4px 0 12px">{html.escape(primary)}</div>
            <div style="font-size:10px;color:rgba(255,255,255,.55);font-weight:800;letter-spacing:.5px">
              보조 보강 필요</div>
            <div style="margin-top:6px">{sec_pills}</div>
          </div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1.15fr .85fr;gap:16px;margin-bottom:16px">
        <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 14px 10px;
                    box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <div>
              <div style="font-size:12px;font-weight:950;letter-spacing:.6px">퍼포먼스 레이더</div>
              <div style="font-size:11px;color:#8a93a5;margin-top:2px">6축 종합 지표 • EPL 2025/26</div>
            </div>
            <span style="font-size:10px;font-weight:900;color:#667085;background:#f8fafc;
                         border:1px solid #e4e8f0;border-radius:999px;padding:4px 10px">{md_badge}</span>
          </div>
          <div style="text-align:center">{_analytics_radar_svg(team, unit_metrics, full_df, color)}</div>
        </div>
        <div>{''.join(metric_cards)}</div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div style="background:#fff;border:1px solid #e4e8f0;border-top:3px solid #16a34a;
                    border-radius:14px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <span style="font-size:12px;font-weight:950;color:#16a34a">✓ 강점</span>
            <span style="font-size:10px;font-weight:900;color:#16a34a;background:#f0fdf4;
                         border:1px solid #bbf7d0;border-radius:999px;padding:3px 9px">
              {len(str_items)}개</span>
          </div>
          {''.join(str_items)}
        </div>
        <div style="background:#fff;border:1px solid #e4e8f0;border-top:3px solid #ef4444;
                    border-radius:14px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <span style="font-size:12px;font-weight:950;color:#ef4444">⚠ 약점</span>
            <span style="font-size:10px;font-weight:900;color:#ef4444;background:#fff1f2;
                         border:1px solid #fecdd3;border-radius:999px;padding:3px 9px">
              {len(weak_items)}개</span>
          </div>
          {''.join(weak_items)}
        </div>
      </div>

      <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:18px 20px;
                  margin-bottom:16px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
        <div style="font-size:12px;font-weight:950;letter-spacing:.6px">전술 지문</div>
        <div style="font-size:11px;color:#8a93a5;margin:3px 0 14px">
          AI 스타일 프로필 • {md_badge} • {html.escape(formation)} 시스템</div>
        <div style="display:flex;flex-wrap:wrap">{''.join(pill_html)}</div>
        <div style="font-size:10px;font-weight:900;color:#8a93a5;letter-spacing:.5px;margin:12px 0 6px">
          AI 요약</div>
        <div style="font-size:13px;color:#3a4253;line-height:1.55">{ai_summary}</div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 18px;
                    box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="font-size:12px;font-weight:950;margin-bottom:10px">🕐 최근 폼</div>
          <div style="margin-bottom:12px">{form_dots}</div>
          {''.join(match_rows)}
        </div>
        <div>
          <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 18px;
                      box-shadow:0 1px 3px rgba(16,24,40,.04)">
            <div style="font-size:12px;font-weight:950;margin-bottom:12px">📊 xG 진단</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div style="background:#f8fafc;border:1px solid #e4e8f0;border-radius:12px;padding:14px">
                <div style="font-size:10px;font-weight:900;color:#8a93a5">득점 vs xG</div>
                <div style="font-size:28px;font-weight:950;color:#1a1f2e;line-height:1.1;margin-top:6px">
                  {gf} <span style="font-size:14px;color:#8a93a5;font-weight:700">/ xG {team_xg:.1f}</span></div>
                {_progress_bar_html(int(min(100, gf / max(team_xg, 1) * 100)), "#16a34a")}
                <div style="font-size:11px;font-weight:800;color:{fin_col};margin-top:8px">{fin_lab}</div>
              </div>
              <div style="background:#f8fafc;border:1px solid #e4e8f0;border-radius:12px;padding:14px">
                <div style="font-size:10px;font-weight:900;color:#8a93a5">실점 vs xGA</div>
                <div style="font-size:28px;font-weight:950;color:#1a1f2e;line-height:1.1;margin-top:6px">
                  {ga} <span style="font-size:14px;color:#8a93a5;font-weight:700">/ xGA {xga_est:.1f}</span></div>
                {_progress_bar_html(int(min(100, ga / max(xga_est, 1) * 100)), "#16a34a")}
                <div style="font-size:11px;font-weight:800;color:{ga_col};margin-top:8px">{ga_lab}</div>
              </div>
            </div>
          </div>
          <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:14px 16px;
                      margin-top:12px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
            <div style="font-size:10px;font-weight:950;color:#2563eb;letter-spacing:.5px">마무리 효율</div>
            <div style="font-size:30px;font-weight:950;color:#1a1f2e;margin:4px 0 6px">{finish_pct}%</div>
            {_progress_bar_html(finish_pct, "#2563eb")}
            <div style="font-size:11px;color:#667085;margin-top:6px">안정적 컨버터</div>
          </div>
          {warn_html}
        </div>
      </div>

      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 16px;
                  margin-bottom:16px;font-size:12.5px;color:#92400e;line-height:1.5">{insight}</div>

      <div style="margin-bottom:10px;font-size:12px;font-weight:950;letter-spacing:.6px">스쿼드 프로필</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px">
        <div style="background:#eff6ff;border:1px solid #dbeafe;border-radius:14px;padding:14px">
          <div style="font-size:10px;font-weight:900;color:#2563eb">평균 연령</div>
          <div style="font-size:26px;font-weight:950;color:#2563eb;margin-top:6px">{avg_age:.1f}
            <span style="font-size:13px">yrs</span></div>
          <div style="font-size:11px;color:#667085;margin-top:4px">
            {'젊고 성장 중인 스쿼드' if avg_age < league_age else '경험 많은 핵심'}</div>
        </div>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;padding:14px">
          <div style="font-size:10px;font-weight:900;color:#16a34a">스쿼드 가치 순위</div>
          <div style="font-size:26px;font-weight:950;color:#1a1f2e;margin-top:6px">#{vrank}</div>
          <div style="font-size:11px;color:#667085;margin-top:4px">PL 시장 가치 상위 {min(vrank,5)}</div>
        </div>
        <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:14px;padding:14px">
          <div style="font-size:10px;font-weight:900;color:#d97706">핵심 선수 의존도</div>
          <div style="font-size:18px;font-weight:950;color:#d97706;margin-top:8px;line-height:1.2">
            {depth_label}</div>
          <div style="font-size:11px;color:#667085;margin-top:6px">{html.escape(key_dep)}</div>
        </div>
        <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:14px;padding:14px">
          <div style="font-size:10px;font-weight:900;color:#ef4444">뎁스 리스크</div>
          <div style="font-size:18px;font-weight:950;color:{depth_col};margin-top:8px">{depth_label}</div>
          <div style="font-size:11px;color:#667085;margin-top:6px">측면·CDM 포지션</div>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div style="font-size:12px;font-weight:950;letter-spacing:.6px">🔍 갭 분석</div>
        <div style="font-size:11px;color:#8a93a5;font-weight:800">이적 시장 우선순위</div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px">
        {''.join(gap_cards)}
      </div>

      <div style="background:linear-gradient(135deg,#10151c,#1a2235);border-radius:16px;padding:22px 24px;
                  color:#fff;box-shadow:0 12px 32px rgba(16,24,40,.18)">
        <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap">
          <div style="flex:1;min-width:240px">
            <div style="font-size:11px;font-weight:950;letter-spacing:.8px;color:#fb923c;margin-bottom:8px">
              🎯 스카우팅 인텔리전스</div>
            <div style="font-size:22px;font-weight:950">스카우팅 미션 생성</div>
            <div style="font-size:13px;color:rgba(255,255,255,.72);margin-top:8px;line-height:1.5;max-width:520px">
              팀의 전술적 약점을 해결할 선수를 찾습니다. 40개 이상 리그에서 포지션별 퍼포먼스 필터로 AI 매칭된 후보를 제안합니다.</div>
            <div style="display:flex;gap:14px;margin-top:14px;font-size:12px;font-weight:800">
              <span style="color:#ef4444">● {html.escape(primary)}</span>
              {''.join(f'<span style="color:{c}">● {html.escape(s)}</span>'
                       for c, s in zip(["#fb923c", "#eab308"], secondary[:2]))}
            </div>
          </div>
          <div style="font-size:12px;font-weight:900;color:rgba(255,255,255,.45);padding-bottom:4px">
            아래 버튼으로 숏리스트를 생성하세요 ↓
          </div>
        </div>
      </div>
    </div>"""
