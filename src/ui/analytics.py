"""
Analytics Tab UI (Korean)

Isolated module for the Analytics tab. Analytics is the *evidence layer* for the
transfer agent — it compresses team signals (factors, strengths, risks, core
players, recruitment impact) into a clean brief, not another overview or a
transfer-candidate list.

Exposed:
    analytics_dashboard_html(team, formation, unit_metrics, standings, manager,
                             schedule, full_df, rep_df, trait_weaknesses,
                             statbunker=None, transfers=None) -> str
"""

import html
import math

import pandas as pd
from unidecode import unidecode

from .common import (
    team_color,
    team_logo,
    TEAM_EXTRA,
    _photo,
    avatar,
)

# ── Metric vocabulary ────────────────────────────────────────────────────────
_CLEAN_METRICS = [
    ("overall_index", "팀 종합력", "전체 지표를 통합한 현재 전력", "#1a1f2e"),
    ("attack_index", "공격 생산성", "득점, xG, 찬스 생성의 결합 지표", "#ef4444"),
    ("midfield_index", "중원 영향력", "점유, 창의성, 볼 회수의 균형", "#16a34a"),
    ("defense_index", "수비 안정성", "실점 억제와 박스 방어의 결합", "#2563eb"),
    ("pressing_index", "전방 압박", "상대 진영에서 압박과 회수 압력", "#f97316"),
    ("set_piece_attack_index", "세트피스 위협", "코너킥/세트피스 공격 영향력", "#7c3aed"),
]

_CLEAN_LABELS = {
    "overall_index": "팀 종합력",
    "attack_index": "공격 지수",
    "attack_output_index": "득점 효율",
    "attack_creation_index": "찬스 생성",
    "midfield_index": "중원 지수",
    "midfield_control_index": "중원 장악",
    "midfield_creativity_index": "창의적 패스",
    "midfield_ball_winning_index": "볼 회수",
    "pressing_index": "전방 압박",
    "defense_index": "수비 지수",
    "defense_output_index": "실점 억제",
    "defense_disruption_index": "전환 차단",
    "defense_box_aerial_index": "박스/공중전",
    "set_piece_attack_index": "세트피스",
    "discipline_index": "경기 관리",
    "penalty_control_index": "페널티 관리",
}


# ── Frame / ranking helpers ──────────────────────────────────────────────────
def _clean_unit_frame(unit_metrics: pd.DataFrame | None) -> pd.DataFrame:
    if unit_metrics is None or unit_metrics.empty:
        return pd.DataFrame()
    df = unit_metrics.copy()
    if "squad" in df.columns:
        df = df.set_index("squad")
    return df


def _clean_rank(df: pd.DataFrame, team: str, col: str, high_good: bool = True) -> tuple[int, int, float]:
    if df.empty or col not in df.columns or team not in df.index:
        return 10, 50, 50.0
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty or team not in s.index:
        return 10, 50, 50.0
    rank = int(s.rank(ascending=not high_good, method="min")[team])
    pct = int(round((1 - (rank - 1) / max(len(s) - 1, 1)) * 100))
    val = float(s.loc[team])
    return rank, max(0, min(100, pct)), val


def _clean_bar(value: int, color: str, h: int = 7) -> str:
    value = max(0, min(100, int(value)))
    return (
        f"<div style='height:{h}px;background:#eef1f6;border-radius:999px;overflow:hidden;margin-top:8px'>"
        f"<div style='height:100%;width:{value}%;background:{color};border-radius:999px'></div></div>"
    )


def _clean_radar(team: str, df: pd.DataFrame, full_df: pd.DataFrame, color: str) -> str:
    axes = [
        ("공격", "attack_index"),
        ("수비", "defense_index"),
        ("중원", "midfield_index"),
        ("압박", "pressing_index"),
        ("창의", "midfield_creativity_index"),
        ("스쿼드", None),
    ]
    vals = []
    for label, col in axes:
        if col:
            _, pct, _ = _clean_rank(df, team, col)
            vals.append((label, pct / 100))
        else:
            sq = full_df[full_df["squad"].astype(str) == team] if "squad" in full_df.columns else pd.DataFrame()
            if not sq.empty and "ss_rating" in sq.columns:
                val = pd.to_numeric(sq["ss_rating"], errors="coerce").dropna().mean()
                vals.append((label, max(0.35, min(0.95, float(val) / 8.5)) if pd.notna(val) else 0.55))
            else:
                vals.append((label, 0.55))
    n = len(vals)
    W = H = 340
    cx = cy = W / 2
    R = 105

    def pt(i: int, frac: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang)

    grid = "".join(
        f"<polygon points='{' '.join(f'{x:.1f},{y:.1f}' for x, y in (pt(i, g) for i in range(n)))}' "
        "fill='none' stroke='#e4e8f0' stroke-width='1'/>"
        for g in (0.25, 0.5, 0.75, 1.0)
    )
    spokes = "".join(
        f"<line x1='{cx}' y1='{cy}' x2='{x:.1f}' y2='{y:.1f}' stroke='#eef1f6' stroke-width='1'/>"
        for x, y in (pt(i, 1.0) for i in range(n))
    )
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, (_, v) in enumerate(vals)))
    labels = []
    for i, (label, val) in enumerate(vals):
        lx, ly = pt(i, 1.22)
        anchor = "middle" if abs(lx - cx) < 10 else ("end" if lx < cx else "start")
        labels.append(
            f"<text x='{lx:.1f}' y='{ly-3:.1f}' fill='#1a1f2e' font-size='11' "
            f"font-weight='900' text-anchor='{anchor}'>{label}</text>"
            f"<text x='{lx:.1f}' y='{ly+11:.1f}' fill='#8a93a5' font-size='10' "
            f"text-anchor='{anchor}'>{round(val * 100)}</text>"
        )
    dots = "".join(
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.2' fill='{color}'/>"
        for x, y in (pt(i, v) for i, (_, v) in enumerate(vals))
    )
    return (
        f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:340px'>"
        f"{grid}{spokes}<polygon points='{poly}' fill='{color}24' stroke='{color}' "
        f"stroke-width='2.5' stroke-linejoin='round'/>{dots}{''.join(labels)}</svg>"
    )


# ── Need-profile / chips / cards ─────────────────────────────────────────────
def _ko_need_profile(label: str) -> tuple[str, str, str]:
    text = str(label)
    if any(k in text for k in ["압박", "볼 회수", "중원"]):
        return "수비형/박스투박스 MF", "압박 지속성, 볼 회수, 전진 패스", "CDM / CM"
    if any(k in text for k in ["창의", "찬스", "공격"]):
        return "창의형 8/10번", "박스 진입 패스, 키패스, 하프스페이스 점유", "CM / AM"
    if any(k in text for k in ["수비", "공중", "박스", "전환"]):
        return "전환 대응 수비수", "커버 범위, 공중전, 전진 수비", "CB / FB"
    if "세트" in text:
        return "세트피스 타깃/키커", "공중전, 킥 품질, 박스 점유", "CB / ST / AM"
    return "멀티롤 로테이션", "출전 안정성, 전술 적응도, 포지션 유연성", "멀티 포지션"


def _agent_tag(label: str, value: str, color: str = "#1a1f2e") -> str:
    return (
        f"<span style='display:inline-flex;align-items:center;gap:6px;padding:7px 10px;"
        f"border-radius:999px;background:{color}10;border:1px solid {color}24;color:{color};"
        f"font-size:11px;font-weight:900;margin:0 6px 7px 0'>"
        f"<span style='color:#8a93a5;font-weight:800'>{html.escape(label)}</span>{html.escape(value)}</span>"
    )


def _brief_metric_card(label: str, rank: int, pct: int, score: float, color: str, note: str) -> str:
    return (
        "<div style='background:#fff;border:1px solid #e4e8f0;border-radius:12px;padding:14px 15px;"
        "box-shadow:0 1px 3px rgba(16,24,40,.04)'>"
        "<div style='display:flex;justify-content:space-between;align-items:center;gap:10px'>"
        f"<div style='font-size:11px;font-weight:950;color:#8a93a5;letter-spacing:.55px'>{html.escape(label)}</div>"
        f"<div style='font-size:10px;font-weight:950;color:{color};background:{color}14;"
        f"border:1px solid {color}28;border-radius:999px;padding:3px 8px'>{rank}위</div></div>"
        f"<div style='font-size:26px;font-weight:950;color:#1a1f2e;line-height:1;margin-top:9px'>{int(round(score))}</div>"
        f"{_clean_bar(pct, color, 7)}"
        f"<div style='font-size:11.5px;color:#667085;line-height:1.38;margin-top:8px'>{html.escape(note)}</div>"
        "</div>"
    )


# ── Match Factor Lab ─────────────────────────────────────────────────────────
def _player_metric_leaders(team: str, full_df: pd.DataFrame, metrics: list[str],
                           mode: str = "sum", n: int = 3, min_minutes: int = 450) -> list[tuple[str, float]]:
    if full_df is None or full_df.empty or "squad" not in full_df.columns or "player" not in full_df.columns:
        return []
    sq = full_df[full_df["squad"].astype(str) == team].copy()
    if sq.empty:
        return []
    if "minutes" in sq.columns:
        sq = sq[pd.to_numeric(sq["minutes"], errors="coerce").fillna(0) >= min_minutes]
    available = [m for m in metrics if m in sq.columns]
    if not available or sq.empty:
        return []
    vals = [pd.to_numeric(sq[m], errors="coerce").fillna(0) for m in available]
    sq["_factor_score"] = sum(vals) / len(vals) if mode == "avg" else sum(vals)
    sq = sq.sort_values("_factor_score", ascending=False)
    return [(str(r["player"]), float(r["_factor_score"])) for _, r in sq.head(n).iterrows()]


def _player_metric_gaps(team: str, full_df: pd.DataFrame, metrics: list[str],
                        n: int = 2, min_minutes: int = 900) -> list[tuple[str, float]]:
    if full_df is None or full_df.empty or "squad" not in full_df.columns or "player" not in full_df.columns:
        return []
    sq = full_df[full_df["squad"].astype(str) == team].copy()
    if sq.empty:
        return []
    if "minutes" in sq.columns:
        sq = sq[pd.to_numeric(sq["minutes"], errors="coerce").fillna(0) >= min_minutes]
    available = [m for m in metrics if m in sq.columns]
    if not available or sq.empty:
        return []
    vals = [pd.to_numeric(sq[m], errors="coerce").fillna(0) for m in available]
    sq["_factor_gap"] = sum(vals) / len(vals)
    sq = sq.sort_values("_factor_gap", ascending=True)
    return [(str(r["player"]), float(r["_factor_gap"])) for _, r in sq.head(n).iterrows()]


def _player_chips(rows: list[tuple[str, float]], pmap: dict, tcol: str, size: int = 26) -> str:
    """기여/보완 선수를 작은 아바타 + 성(姓) 칩으로 렌더."""
    if not rows:
        return "<div style='font-size:11px;color:#8a93a5;margin-top:5px'>데이터 확인 필요</div>"
    out = []
    for name, _ in rows:
        short = html.escape(name.split()[-1] if name else "")
        out.append(
            "<div style='display:flex;align-items:center;gap:7px'>"
            f"{avatar(pmap.get(name, ''), tcol, size, 'flex:none')}"
            f"<span style='font-size:11.5px;font-weight:900;color:#1a1f2e;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{short}</span></div>"
        )
    return "<div style='display:flex;flex-direction:column;gap:7px;margin-top:7px'>" + "".join(out) + "</div>"


def _factor_rank_text(df: pd.DataFrame, team: str, col: str) -> tuple[int, int, float]:
    return _clean_rank(df, team, col) if col in getattr(df, "columns", []) else (10, 50, 50.0)


def _build_match_factor_cards(team: str, df: pd.DataFrame, full_df: pd.DataFrame,
                              statbunker: pd.DataFrame | None) -> str:
    specs = [
        {
            "key": "setpiece",
            "title": "세트피스 무기",
            "col": "set_piece_attack_index",
            "tone": "#7c3aed",
            "metrics": ["key_passes_per90", "big_chances_created_per90", "final_third_passes_per90"],
            "gap_metrics": ["aerial_won_per90", "aerial_won_pct"],
            "why": "데드볼 공급과 박스 타깃 연결이 득점 루트로 이어지는지 확인합니다.",
        },
        {
            "key": "creation",
            "title": "찬스 생성 엔진",
            "col": "midfield_creativity_index",
            "tone": "#ef4444",
            "metrics": ["key_passes_per90", "big_chances_created_per90", "successful_dribbles_per90"],
            "gap_metrics": ["key_passes_per90", "big_chances_created_per90"],
            "why": "오픈플레이에서 박스 진입 패스와 마지막 패스가 누구에게서 나오는지 봅니다.",
        },
        {
            "key": "pressing",
            "title": "압박/볼 회수",
            "col": "pressing_index",
            "tone": "#f97316",
            "metrics": ["possession_won_att_per90", "recoveries_per90", "tackles_won_per90_ss"],
            "gap_metrics": ["possession_won_att_per90", "recoveries_per90", "tackles_won_per90_ss"],
            "why": "전방 압박이 실제 회수와 역습 차단으로 이어지는지 추적합니다.",
        },
        {
            "key": "box_defense",
            "title": "박스 방어/공중전",
            "col": "defense_box_aerial_index",
            "tone": "#2563eb",
            "metrics": ["aerial_won_per90", "clearances_per90", "blocked_shots_per90"],
            "gap_metrics": ["aerial_won_per90", "clearances_per90", "blocked_shots_per90"],
            "why": "크로스, 세컨볼, 박스 안 슈팅을 누가 지우는지 확인합니다.",
        },
        {
            "key": "discipline",
            "title": "경기 관리",
            "col": "discipline_index",
            "tone": "#16a34a",
            "metrics": ["fouls_per90", "fouled_per90", "errors_per90"],
            "gap_metrics": ["fouls_per90", "errors_per90"],
            "why": "파울, 카드 리스크, 불필요한 실수가 경기 운영에 주는 영향을 봅니다.",
        },
    ]

    tcol = team_color(team)
    pmap = {}
    if full_df is not None and not full_df.empty and {"player", "squad"} <= set(full_df.columns):
        ft = full_df[full_df["squad"].astype(str) == team]
        for _, r in ft.iterrows():
            pmap[str(r["player"])] = _photo(r.get("sofa_id"), r.get("tm_photo"))

    chosen = []
    for spec in specs:
        rank, pct, score = _factor_rank_text(df, team, spec["col"])
        spec = {**spec, "rank": rank, "pct": pct, "score": score}
        if rank <= 6 or rank >= 15:
            chosen.append(spec)
    if len(chosen) < 3:
        remaining = sorted(
            [{**s, "rank": _factor_rank_text(df, team, s["col"])[0],
              "pct": _factor_rank_text(df, team, s["col"])[1],
              "score": _factor_rank_text(df, team, s["col"])[2]} for s in specs],
            key=lambda s: min(s["rank"], 21 - s["rank"]),
        )
        for spec in remaining:
            if spec["key"] not in {c["key"] for c in chosen}:
                chosen.append(spec)
            if len(chosen) >= 3:
                break

    cards = []
    for spec in chosen[:4]:
        leaders = _player_metric_leaders(team, full_df, spec["metrics"])
        gaps = _player_metric_gaps(team, full_df, spec["gap_metrics"])
        status = "강점" if spec["rank"] <= 7 else ("리스크" if spec["rank"] >= 14 else "관찰")
        sb_line = ""
        if spec["key"] == "setpiece" and statbunker is not None:
            sb_df = statbunker.copy()
            if "squad" in sb_df.columns:
                sb_df = sb_df.set_index("squad")
            if team in sb_df.index:
                sb = sb_df.loc[team]
                corner = int(pd.to_numeric(sb.get("corner_goals", 0), errors="coerce") or 0)
                set_piece = int(pd.to_numeric(sb.get("non_penalty_set_piece_goals", 0), errors="coerce") or 0)
                sb_line = f"코너 득점 {corner}골 · 비PK 세트피스 {set_piece}골"
        cards.append(
            "<div style='background:#fff;border:1px solid #e4e8f0;border-top:4px solid "
            f"{spec['tone']};border-radius:12px;padding:15px 16px;box-shadow:0 1px 3px rgba(16,24,40,.04)'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px'>"
            f"<div style='font-size:10px;font-weight:950;color:{spec['tone']};letter-spacing:.65px'>{status} FACTOR</div>"
            f"<div style='font-size:10px;font-weight:950;color:{spec['tone']};background:{spec['tone']}14;"
            f"border:1px solid {spec['tone']}28;border-radius:999px;padding:3px 8px'>{spec['rank']}위 · P{spec['pct']}</div></div>"
            f"<div style='font-size:17px;font-weight:950;color:#1a1f2e;margin-top:8px'>{html.escape(spec['title'])}</div>"
            f"<div style='font-size:12px;color:#667085;line-height:1.45;margin-top:8px'>{html.escape(spec['why'])}</div>"
            f"<div style='font-size:11px;color:#8a93a5;margin-top:8px'>{html.escape(sb_line)}</div>"
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px'>"
            "<div style='background:#f8fafc;border:1px solid #e4e8f0;border-radius:10px;padding:10px'>"
            "<div style='font-size:9.5px;font-weight:950;color:#8a93a5;letter-spacing:.45px'>기여 선수</div>"
            f"{_player_chips(leaders, pmap, tcol)}"
            "</div>"
            "<div style='background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:10px'>"
            "<div style='font-size:9.5px;font-weight:950;color:#c2410c;letter-spacing:.45px'>보완 관찰</div>"
            f"{_player_chips(gaps, pmap, tcol)}"
            "</div></div>"
            "</div>"
        )
    return "".join(cards)


# ── Recruitment Impact Audit ─────────────────────────────────────────────────
def _audit_norm(value) -> str:
    return unidecode(str(value or "")).lower().strip()


def _impact_status(row: pd.Series, fee_eur: float) -> tuple[str, str, str]:
    rating = float(pd.to_numeric(row.get("ss_rating", 0), errors="coerce") or 0)
    minutes = float(pd.to_numeric(row.get("minutes", 0), errors="coerce") or 0)
    goals = float(pd.to_numeric(row.get("goals", 0), errors="coerce") or 0)
    assists = float(pd.to_numeric(row.get("assists", 0), errors="coerce") or 0)
    npxg = float(pd.to_numeric(row.get("npxg_p90", 0), errors="coerce") or 0)
    xa = float(pd.to_numeric(row.get("xa_p90", 0), errors="coerce") or 0)
    kp = float(pd.to_numeric(row.get("key_passes_per90", 0), errors="coerce") or 0)
    press = float(pd.to_numeric(row.get("possession_won_att_per90", 0), errors="coerce") or 0)
    ga = goals + assists
    premium = fee_eur >= 60_000_000

    score = rating
    score += min(0.45, ga / 28)
    score += min(0.22, npxg * 0.25 + xa * 0.25)
    score += min(0.18, kp * 0.04 + press * 0.05)
    if premium and minutes >= 900:
        score -= 0.12
    if minutes < 600:
        return "판단 보류", "#d97706", "표본이 작아 적응 맥락을 더 봐야 합니다."
    if score >= 7.25:
        return "값어치 중", "#16a34a", "성과·과정 지표가 이적료 기대치에 근접합니다."
    if score >= 6.85:
        return "적응 구간", "#d97706", "결과는 일부 나오지만 세부 기여가 더 올라와야 합니다."
    return "미달 신호", "#ef4444", "비용 대비 즉시 전력화가 부족합니다."


def _recruitment_audit_html(team: str, transfers: pd.DataFrame | None,
                            full_df: pd.DataFrame, color: str) -> str:
    if transfers is None or transfers.empty or "squad" not in transfers.columns:
        return ""
    ins = transfers[
        (transfers["squad"].astype(str) == team)
        & (transfers["direction"].astype(str).str.lower() == "in")
    ].copy()
    if ins.empty:
        return ""
    ins["fee_eur_num"] = pd.to_numeric(ins.get("fee_eur"), errors="coerce").fillna(0)
    ins = ins[ins["fee_eur_num"] > 0].sort_values("fee_eur_num", ascending=False).head(3)
    if ins.empty:
        return ""

    full = full_df.copy()
    full["_audit_norm"] = full["player"].map(_audit_norm) if "player" in full.columns else ""
    full_team = full[full["squad"].astype(str) == team] if "squad" in full.columns else full
    cards = []
    summary = {"green": 0, "amber": 0, "red": 0, "missing": 0}
    for _, tr in ins.iterrows():
        key = _audit_norm(tr.get("norm_key") or tr.get("player"))
        player = str(tr.get("player", "Unknown"))
        fee_text = str(tr.get("fee_text") or "")
        pos = str(tr.get("pos") or "")
        fee = float(tr.get("fee_eur_num", 0))
        match = full_team[full_team["_audit_norm"] == key]
        if match.empty and key:
            match = full_team[full_team["_audit_norm"].str.contains(key, regex=False, na=False)]
        if match.empty:
            summary["missing"] += 1
            status, tone, note = "데이터 대기", "#8a93a5", "경기 성과 데이터와 아직 매칭되지 않았습니다."
            stat_line = "출전/성과 데이터 확인 필요"
            photo = _photo("", tr.get("tm_photo"))
        else:
            row = match.iloc[0]
            status, tone, note = _impact_status(row, fee)
            if tone == "#16a34a":
                summary["green"] += 1
            elif tone == "#ef4444":
                summary["red"] += 1
            else:
                summary["amber"] += 1
            minutes = int(pd.to_numeric(row.get("minutes", 0), errors="coerce") or 0)
            goals = int(pd.to_numeric(row.get("goals", 0), errors="coerce") or 0)
            assists = int(pd.to_numeric(row.get("assists", 0), errors="coerce") or 0)
            rating = float(pd.to_numeric(row.get("ss_rating", 0), errors="coerce") or 0)
            stat_line = f"{minutes}분 · {goals}골 {assists}도움 · 평점 {rating:.2f}"
            photo = _photo(row.get("sofa_id"), row.get("tm_photo"))
        cards.append(
            "<div style='background:#fff;border:1px solid #e4e8f0;border-top:4px solid "
            f"{tone};border-radius:12px;padding:15px 16px;box-shadow:0 1px 3px rgba(16,24,40,.04)'>"
            "<div style='display:flex;align-items:center;gap:11px'>"
            f"{avatar(photo, color, 44, 'flex:none')}"
            "<div style='flex:1;min-width:0'>"
            f"<div style='font-size:16px;font-weight:950;color:#1a1f2e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{html.escape(player)}</div>"
            f"<div style='font-size:11px;color:#8a93a5;margin-top:2px'>{html.escape(pos)}</div></div>"
            f"<div style='font-size:10px;font-weight:950;color:{tone};background:{tone}14;border:1px solid {tone}28;"
            f"border-radius:999px;padding:3px 8px;flex:none'>{html.escape(fee_text)}</div></div>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:11px'>"
            f"<div style='font-size:10px;font-weight:950;color:{tone};letter-spacing:.5px'>{html.escape(status)}</div></div>"
            f"<div style='font-size:12px;font-weight:900;color:#1a1f2e;line-height:1.4;margin-top:6px'>{html.escape(stat_line)}</div>"
            f"<div style='font-size:11.5px;color:#667085;line-height:1.42;margin-top:6px'>{html.escape(note)}</div>"
            "</div>"
        )

    verdict = "이적 시장 성과는 추가 관찰 구간입니다."
    if summary["red"] >= 2:
        verdict = "고가 영입 중 미달 신호가 있어 다음 시장 추천 가중치에 반영해야 합니다."
    elif summary["green"] >= 2:
        verdict = "핵심 영입이 팀 강점 유지에 기여 — 보완형 후보 위주로 좁힐 수 있습니다."
    elif summary["amber"] >= 2:
        verdict = "성과가 터지기 전 적응 구간 — 역할 조정과 보완 후보를 함께 봐야 합니다."

    return (
        "<div style='font-size:13px;font-weight:950;letter-spacing:.4px;margin:0 0 10px'>Recruitment Impact Audit</div>"
        "<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 18px;"
        "box-shadow:0 1px 3px rgba(16,24,40,.04);margin-bottom:16px'>"
        "<div style='display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:14px'>"
        "<div style='font-size:12px;color:#8a93a5'>이적료 대비 결과·과정 지표 점검</div>"
        f"<div style='font-size:12px;font-weight:900;color:{color};text-align:right;max-width:360px'>{html.escape(verdict)}</div></div>"
        f"<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:14px'>{''.join(cards[:3])}</div>"
        "</div>"
    )


# ── Injury impact ────────────────────────────────────────────────────────────
_LINE_LABEL = {"GK": "골키퍼", "DF": "수비", "MF": "중원", "FW": "공격"}
_LINE_TONE = {"GK": "#0891b2", "DF": "#2563eb", "MF": "#16a34a", "FW": "#ef4444"}


def _line_of(pos) -> str:
    """FBref(pos) · Transfermarkt(position) 문자열 → 라인(GK/DF/MF/FW)."""
    p = str(pos or "").lower().strip()
    if not p:
        return "MF"
    if "goal" in p or p == "gk":
        return "GK"
    if "midfield" in p or p in ("mf", "dm", "cm", "am", "cdm", "cam"):
        return "MF"
    if "back" in p or "defender" in p or p in ("df", "cb", "rb", "lb", "rwb", "lwb"):
        return "DF"
    if "wing" in p or "forward" in p or "striker" in p or p in ("fw", "st", "cf", "rw", "lw"):
        return "FW"
    token = p.split(",")[0].strip().upper()
    return {"GK": "GK", "DF": "DF", "MF": "MF", "FW": "FW"}.get(token, "MF")


def _injury_impact_html(team: str, inj_hist: pd.DataFrame | None,
                        full_df: pd.DataFrame, color: str) -> str:
    """시즌 부상 결장(전 대회 기준 games missed) → 라인별 전력 공백.
    약화 지표 = 결장 경기수 × 기여 가중(시즌 출전분)."""
    if inj_hist is None or inj_hist.empty or "squad" not in inj_hist.columns:
        return ""
    inj = inj_hist[inj_hist["squad"].astype(str) == team].copy()
    if inj.empty:
        return ""
    inj["__gm"] = pd.to_numeric(inj.get("games_missed"), errors="coerce").fillna(0).astype(int)
    inj = inj[inj["__gm"] > 0]
    if inj.empty:
        return ""

    sq = full_df[full_df["squad"].astype(str) == team].copy() if "squad" in getattr(full_df, "columns", []) else pd.DataFrame()
    if not sq.empty and "player" in sq.columns:
        sq["_n"] = sq["player"].map(_audit_norm)

    line_score = {"GK": 0.0, "DF": 0.0, "MF": 0.0, "FW": 0.0}
    line_games = {"GK": 0, "DF": 0, "MF": 0, "FW": 0}
    line_count = {"GK": 0, "DF": 0, "MF": 0, "FW": 0}
    rows = []
    for _, ir in inj.iterrows():
        name = str(ir.get("player", ""))
        gm = int(ir["__gm"])
        spells = int(pd.to_numeric(ir.get("spells"), errors="coerce") or 0)
        injuries = str(ir.get("injuries") or "부상")
        minutes = goals = assists = 0
        rating = 0.0
        pos = ""
        photo = ""
        if not sq.empty:
            m = sq[sq["_n"] == _audit_norm(name)]
            if not m.empty:
                mr = m.iloc[0]
                minutes = int(pd.to_numeric(mr.get("minutes"), errors="coerce") or 0)
                goals = int(pd.to_numeric(mr.get("goals"), errors="coerce") or 0)
                assists = int(pd.to_numeric(mr.get("assists"), errors="coerce") or 0)
                rating = float(pd.to_numeric(mr.get("ss_rating"), errors="coerce") or 0)
                pos = str(mr.get("pos") or "")
                photo = _photo(mr.get("sofa_id"), mr.get("tm_photo"))
        line = _line_of(pos)
        # 기여 가중: 풀시즌(3420분) 대비 출전 비중. 무출전 선수는 최소 가중.
        weight = max(0.08, minutes / 3420.0)
        score = gm * weight
        line_score[line] += score
        line_games[line] += gm
        line_count[line] += 1
        rows.append({
            "name": name, "photo": photo, "line": line, "pos": pos,
            "gm": gm, "spells": spells, "injuries": injuries,
            "minutes": minutes, "goals": goals, "assists": assists,
            "rating": rating, "score": score,
        })
    rows.sort(key=lambda x: (-x["score"], -x["gm"]))
    total_gm = sum(r["gm"] for r in rows)

    cards = []
    for r in rows[:6]:
        tone = _LINE_TONE[r["line"]]
        contrib = (
            f"{r['minutes']}분 · {r['goals']}골 {r['assists']}도움"
            + (f" · 평점 {r['rating']:.2f}" if r["rating"] else "")
            if r["minutes"] else "이번 시즌 EPL 출전 기록 없음"
        )
        cards.append(
            "<div style='background:#fff;border:1px solid #e4e8f0;border-left:4px solid "
            f"{tone};border-radius:12px;padding:13px 14px;box-shadow:0 1px 3px rgba(16,24,40,.04)'>"
            "<div style='display:flex;align-items:center;gap:11px'>"
            f"{avatar(r['photo'], '#9aa3b2', 44, 'flex:none;filter:grayscale(.4)')}"
            "<div style='flex:1;min-width:0'>"
            f"<div style='font-size:14px;font-weight:950;color:#1a1f2e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{html.escape(r['name'])}</div>"
            f"<div style='font-size:11px;color:#8a93a5;margin-top:2px'>{_LINE_LABEL[r['line']]}{(' · ' + html.escape(r['pos'])) if r['pos'] else ''}</div></div>"
            "<div style='text-align:right;flex:none'>"
            f"<div style='font-size:20px;font-weight:950;color:{tone};line-height:1'>{r['gm']}</div>"
            "<div style='font-size:9.5px;font-weight:900;color:#8a93a5'>경기 결장</div></div></div>"
            f"<div style='font-size:11px;font-weight:900;color:#b91c1c;margin-top:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>🤕 {html.escape(r['injuries'])} · {r['spells']}회</div>"
            "<div style='font-size:10px;font-weight:950;color:#8a93a5;letter-spacing:.4px;margin-top:9px'>시즌 기여(공백분)</div>"
            f"<div style='font-size:12.5px;font-weight:900;color:#1a1f2e;margin-top:3px'>{html.escape(contrib)}</div>"
            "</div>"
        )

    # 라인별 약화: score(결장×기여가중)를 최대 라인=100으로 정규화
    max_score = max(line_score.values()) or 1.0
    bars = []
    for ln in ["DF", "MF", "FW", "GK"]:
        if line_count[ln] == 0:
            continue
        pct = int(round(line_score[ln] / max_score * 100))
        tone = _LINE_TONE[ln]
        bars.append(
            "<div style='margin-bottom:11px'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;gap:8px'>"
            f"<div style='font-size:12px;font-weight:900;color:#1a1f2e'>{_LINE_LABEL[ln]} "
            f"<span style='color:#8a93a5;font-weight:800'>· {line_count[ln]}명</span></div>"
            f"<div style='font-size:11.5px;font-weight:950;color:{tone}'>{line_games[ln]}경기 공백</div></div>"
            f"{_clean_bar(pct, tone, 7)}"
            "</div>"
        )
    bars_html = "".join(bars) or "<div style='font-size:12px;color:#8a93a5'>라인별 영향 데이터 없음</div>"
    worst = max([ln for ln in line_count if line_count[ln]], key=lambda l: line_score[l], default=None)
    worst_txt = f"{_LINE_LABEL[worst]} 라인 타격 최다" if worst else ""

    return (
        "<div style='font-size:13px;font-weight:950;letter-spacing:.4px;margin:0 0 4px'>시즌 부상 결장 · Injury Impact</div>"
        "<div style='font-size:11px;color:#8a93a5;margin:0 0 10px'>Transfermarkt 부상이력 기준 25/26 결장 경기수(전 대회). 약화 지표 = 결장 경기수 × 시즌 기여 가중.</div>"
        "<div style='display:grid;grid-template-columns:1.5fr 1fr;gap:16px;margin-bottom:16px'>"
        f"<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:12px;align-content:start'>{''.join(cards)}</div>"
        "<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)'>"
        "<div style='display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:4px'>"
        "<div style='font-size:12px;font-weight:950;color:#1a1f2e'>라인별 약화</div>"
        f"<div style='font-size:11px;color:#8a93a5'>{len(rows)}명 · 총 {total_gm}경기</div></div>"
        f"<div style='font-size:11px;font-weight:900;color:{color};line-height:1.4;margin-bottom:12px'>{worst_txt}</div>"
        f"{bars_html}"
        "</div></div>"
    )


# ── Main dashboard ───────────────────────────────────────────────────────────
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
    statbunker: pd.DataFrame | None = None,
    transfers: pd.DataFrame | None = None,
    inj_hist: pd.DataFrame | None = None,
) -> str:
    df = _clean_unit_frame(unit_metrics)
    color = team_color(team)
    full_name = TEAM_EXTRA.get(team, (team, None))[0]
    logo = team_logo(team)
    crest = (
        f"<img src='{logo}' referrerpolicy='no-referrer' onerror=\"this.style.display='none'\" "
        "style='width:42px;height:42px;object-fit:contain'/>"
        if logo else f"<span style='font-size:15px;font-weight:950;color:#fff'>{html.escape(team[:3].upper())}</span>"
    )
    mgr = manager or {}
    mgr_name = str(mgr.get("name", "확인 필요"))
    mgr_style = str(mgr.get("style", "Tactical profile pending"))
    mgr_form = str(mgr.get("formation") or formation or "-")

    # rank rows → strengths / risks
    rank_rows = []
    for col in [c for c in _CLEAN_LABELS if c in df.columns]:
        rk, pct, val = _clean_rank(df, team, col)
        rank_rows.append((col, _CLEAN_LABELS[col], rk, pct, float(val)))
    strengths = sorted(rank_rows, key=lambda x: x[2])[:4]
    risks = sorted(rank_rows, key=lambda x: x[2], reverse=True)[:4]
    primary_strength = strengths[0][1] if strengths else "강점 데이터"
    primary_risk = risks[0][1] if risks else "리스크 데이터"
    profile_name, profile_traits, profile_positions = _ko_need_profile(primary_risk)

    signal_cards = "".join(
        _brief_metric_card(title, *_clean_rank(df, team, col), tone, desc)
        for col, title, desc, tone in _CLEAN_METRICS
    )

    def evidence_rows(rows: list[tuple], tone: str) -> str:
        out = []
        for _, label, rk, pct, score in rows:
            out.append(
                "<div style='padding:10px 0;border-bottom:1px solid #f1f3f7'>"
                "<div style='display:flex;align-items:center;justify-content:space-between;gap:10px'>"
                f"<div style='font-size:13px;font-weight:900;color:#1a1f2e'>{html.escape(label)}</div>"
                f"<div style='font-size:10px;font-weight:950;color:{tone};background:{tone}14;"
                f"border:1px solid {tone}28;border-radius:999px;padding:3px 8px'>{rk}위 · P{pct}</div></div>"
                f"{_clean_bar(pct, tone, 6)}"
                "</div>"
            )
        return "".join(out) or "<div style='font-size:12px;color:#8a93a5'>표시할 근거가 없습니다.</div>"

    sq_full = full_df[full_df["squad"].astype(str) == team] if "squad" in full_df.columns else pd.DataFrame()
    avg_rating = 0.0
    if not sq_full.empty and "ss_rating" in sq_full.columns:
        avg_rating = float(pd.to_numeric(sq_full["ss_rating"], errors="coerce").dropna().mean())
    sample_size = len(sq_full) if not sq_full.empty else 0

    profile_chips = (
        _agent_tag("보강", profile_name, color)
        + _agent_tag("포지션", profile_positions, "#2563eb")
        + _agent_tag("요건", profile_traits, color)
    )

    factor_cards = _build_match_factor_cards(team, df, full_df, statbunker)
    injury_html = _injury_impact_html(team, inj_hist, full_df, color) or ""
    audit_html = _recruitment_audit_html(team, transfers, full_df, color) or ""

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1a1f2e">

      <!-- 1. Header -->
      <div style="background:linear-gradient(135deg,{color},#10151c);border-radius:16px;padding:20px 22px;
                  color:#fff;margin-bottom:16px;box-shadow:0 12px 32px rgba(16,24,40,.16)">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:14px;min-width:280px">
            <div style="width:56px;height:56px;border-radius:14px;background:rgba(255,255,255,.14);
                        border:1px solid rgba(255,255,255,.20);display:flex;align-items:center;
                        justify-content:center">{crest}</div>
            <div>
              <div style="font-size:11px;font-weight:950;color:rgba(255,255,255,.64);letter-spacing:.9px">ANALYTICS BRIEF</div>
              <div style="font-size:24px;font-weight:950;line-height:1.08">{html.escape(full_name)}</div>
              <div style="font-size:12px;color:rgba(255,255,255,.72);margin-top:4px">
                {html.escape(mgr_name)} · {html.escape(mgr_form)} · {html.escape(mgr_style)}</div>
            </div>
          </div>
          <div style="flex:1;min-width:320px;max-width:520px">
            <div style="font-size:18px;font-weight:950;line-height:1.25">
              {html.escape(primary_strength)} 유지 · <span style="color:#fca5a5">{html.escape(primary_risk)}</span> 보강</div>
            <div style="margin-top:10px">{profile_chips}</div>
          </div>
        </div>
      </div>

      <!-- 2. Radar + signal cards -->
      <div style="display:grid;grid-template-columns:1.02fr .98fr;gap:16px;margin-bottom:16px">
        <div style="background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:17px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
            <div style="font-size:13px;font-weight:950;letter-spacing:.4px">근거 레이더</div>
            <span style="font-size:10px;font-weight:900;color:#667085;background:#f8fafc;border:1px solid #e4e8f0;border-radius:999px;padding:4px 10px">{sample_size}명 표본</span>
          </div>
          <div style="text-align:center">{_clean_radar(team, df, full_df, color)}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">{signal_cards}</div>
      </div>

      <!-- 3. Match Factor Lab -->
      <div style="font-size:13px;font-weight:950;letter-spacing:.4px;margin:0 0 10px">Match Factor Lab</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px">{factor_cards}</div>

      <!-- 4. Injury impact -->
      {injury_html}

      <!-- 5. Strengths / Risks -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div style="background:#fff;border:1px solid #e4e8f0;border-top:3px solid #16a34a;border-radius:14px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="font-size:13px;font-weight:950;color:#16a34a;margin-bottom:6px">유지해야 할 팀 강점</div>
          {evidence_rows(strengths, "#16a34a")}
        </div>
        <div style="background:#fff;border:1px solid #e4e8f0;border-top:3px solid #ef4444;border-radius:14px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04)">
          <div style="font-size:13px;font-weight:950;color:#ef4444;margin-bottom:6px">보강 우선 리스크</div>
          {evidence_rows(risks, "#ef4444")}
        </div>
      </div>

      <!-- 5. Recruitment audit -->
      {audit_html}

      <!-- Handoff strip -->
      <div style="background:linear-gradient(135deg,#10151c,#1a2235);border-radius:14px;padding:15px 18px;color:#fff;
                  display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;
                  box-shadow:0 8px 24px rgba(16,24,40,.16)">
        <div style="font-size:12px;font-weight:950;color:#fb923c;letter-spacing:.7px">TRANSFER AGENT 입력 신호</div>
        <div>
          {_agent_tag("avg_rating", f"{avg_rating:.2f}" if avg_rating else "n/a", "#fb923c")}
          {_agent_tag("보강", primary_risk, "#fb923c")}
          {_agent_tag("표본", f"{sample_size}명", "#fb923c")}
        </div>
      </div>
    </div>
    """
