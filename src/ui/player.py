"""
Player Detail / Player Database 탭 렌더 함수 + FM 능력치 매핑 상수.

선수 카드(DB), 선수 선택 카드/스포트라이트, FM 스타일 세부 능력치 패널,
카테고리 평균, 레이더 차트. 모두 인자로 데이터를 받는 순수 렌더 함수다.
"""
from __future__ import annotations

import html

import pandas as pd

from .common import (
    team_color, _photo, avatar, portrait_photo, fmt_value, nation_code, flag_chip, _grid,
    rating_color, pos_chip_color,
)
from .metrics import fm_rating, fm_color, player_ovr
from similar_players import fine_group


# ==== 아래 함수/상수는 app.py에서 sed로 이동됨 ====

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


# _iframe·_grid → src/ui/common.py (상단 import)



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


# fm_rating·fm_color·ovr_from_*·perf_ovr·player_ovr·_series_pct·goalkeeper_ovr
# ·season_achievement_bonus → src/ui/metrics.py (상단 import)

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


