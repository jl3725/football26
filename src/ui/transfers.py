"""
이적/영입 추천 렌더 함수 + 적합도 스코어링 상수.

여름 이적시장 IN/OUT 카드, 팀 스타일 벡터, 약점 기반 영입 후보 추천, 추천 카드.
모두 인자로 데이터를 받는 순수 함수다(common·metrics 헬퍼만 사용).
"""
from __future__ import annotations

import html

import pandas as pd

from .common import (
    ACCENT, team_color, _photo, avatar, fmt_value, nation_code, flag_chip, fee_label,
    pos_chip_color, rating_color,
)
from .metrics import player_ovr


# ==== 아래 함수/상수는 app.py에서 sed로 이동됨 ====

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
# moved to src/ui/overview.py: rating_color, team_ratings(+legacy/helpers), overview_scout_dossier_html, donut/stat_card, manager_profile, snapshot, set_piece, radar, ai_scout, form/xg/squad_profile, leaders

