"""
Streamlit 프론트엔드 — 팀 포메이션 보드 + 선수 역할/프로필 + 비슷한 선수.

실행:
    streamlit run app.py

좌측에서 팀/포메이션/최소출전을 고르면 피치 위에 주전 XI 가 배치되고,
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

from similar_players import FEATURES, DATA_PATH, build_embeddings, find_similar  # noqa: E402
from team_analysis import (  # noqa: E402
    league_percentiles, assign_role, position_group,
    pick_bands, team_formations, team_goalkeeper, load_formations,
    load_slots, team_xi_from_slots, slot_xy, slot_kind,
    compute_player_badges,
    GK_Y, BAND_Y_TOP, BAND_Y_BOTTOM,
)

# 피처 → 한글 라벨 (숫자만 보이는 문제 해결의 핵심)
LABELS = {
    "npxg_p90": "npxG/90", "xa_p90": "xA/90", "kp_p90": "키패스/90", "shots_p90": "슈팅/90",
    "crosses_per90": "크로스/90", "fouled_per90": "피파울(전진)/90", "offsides_per90": "침투/90",
    "interceptions_per90": "인터셉트/90", "tackles_won_per90": "태클성공/90", "fouls_per90": "수비파울/90",
}
# 밴드 색상: 수비(파랑) → 중원(주황) → 공격(빨강)
BAND_DEF, BAND_MID, BAND_FWD = "#4d80e0", "#e0a23a", "#e0584c"

st.set_page_config(page_title="FC Analytics — 포메이션·역할", layout="wide")


@st.cache_data
def load() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


def top_strengths(prow: pd.Series, n: int = 3) -> list[tuple[str, int]]:
    s = prow[FEATURES].sort_values(ascending=False)
    return [(LABELS[f], round(prow[f] * 100)) for f in s.index[:n]]


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
        kind = slot_kind(slot)
        norm = r["norm_key"]
        prow = pct[pct["norm_key"] == norm]
        drow = full[full["norm_key"] == norm]
        minutes = int(drow.iloc[0]["minutes"]) if not drow.empty else 0
        if kind == "GK":
            save = drow.iloc[0].get("gk_save_pct") if not drow.empty else None
            chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
            out.append({"name": r["player"].split()[-1], "x": x, "y": y, "kind": "GK",
                        "role": slot, "chip": chip, "minutes": minutes,
                        "full": r["player"], "tip": f"{slot} · {minutes}분 · {chip}"})
        elif not prow.empty:
            prow = prow.iloc[0]
            role, _ = assign_role(prow, position_group(prow["pos"]))
            strengths = top_strengths(prow)
            tip = f"{slot} · {minutes}분<br>" + "<br>".join(f"{lab} {v}%" for lab, v in strengths)
            out.append({"name": r["player"].split()[-1], "x": x, "y": y, "kind": kind,
                        "role": f"{slot} · {role.split(' (')[0]}",
                        "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": minutes, "full": r["player"], "tip": tip})
    return out


def placements_from_bands(bands: list[pd.DataFrame], pct: pd.DataFrame,
                          gk: pd.Series | None) -> list[dict]:
    """휴리스틱 밴드 → 배치 리스트(슬롯 데이터 없는 팀용)."""
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
            tip = f"{int(r['minutes'])}분<br>" + "<br>".join(f"{lab} {v}%" for lab, v in strengths)
            out.append({"name": r["player"].split()[-1], "x": xs[i], "y": y, "kind": kind,
                        "role": role.split(" (")[0], "chip": f"{strengths[0][0]} {strengths[0][1]}%",
                        "minutes": int(r["minutes"]), "full": r["player"], "tip": tip})
    if gk is not None:
        save = gk.get("gk_save_pct")
        chip = f"세이브% {save:.0f}" if pd.notna(save) else "GK"
        out.append({"name": gk["player"].split()[-1], "x": 50, "y": GK_Y, "kind": "GK",
                    "role": "골키퍼", "chip": chip, "minutes": int(gk["minutes"]),
                    "full": gk["player"], "tip": f"{int(gk['minutes'])}분 · {chip}"})
    return out


def pitch_html(placements: list[dict]) -> str:
    cards = []
    for p in placements:
        color = KIND_COLOR[p["kind"]]
        gk_cls = " gk" if p["kind"] == "GK" else ""
        cards.append(f"""
        <div class="pl" style="left:{p['x']}%;top:{p['y']}%">
          <div class="tok{gk_cls}" style="border-color:{color}"></div>
          <div class="nm">{p['name']}</div>
          <div class="rl">{p['role']}</div>
          <div class="chip">{p['chip']}</div>
          <div class="tip"><b>{p['full']}</b><br>{p['tip']}</div>
        </div>""")
    return f"""
    <style>
      .wrap {{ max-width:520px; margin:0 auto; }}
      .pitch {{ position:relative; width:100%; padding-top:130%; background:#2e7d4f;
                border-radius:12px; border:2px solid rgba(255,255,255,.5); overflow:visible; }}
      .pitch .mid {{ position:absolute; top:50%; left:0; width:100%; height:2px; background:rgba(255,255,255,.4); }}
      .pitch .circ {{ position:absolute; top:50%; left:50%; width:26%; padding-top:26%;
                      transform:translate(-50%,-50%); border:2px solid rgba(255,255,255,.4); border-radius:50%; }}
      .pl {{ position:absolute; transform:translate(-50%,-50%); text-align:center; width:120px; }}
      .tok {{ width:34px; height:34px; margin:0 auto; background:#fff; border:4px solid #888;
              border-radius:50%; box-shadow:0 2px 4px rgba(0,0,0,.3); }}
      .tok.gk {{ border-color:#3aa99a; }}
      .nm {{ color:#fff; font-weight:700; font-size:14px; margin-top:4px; text-shadow:0 1px 2px rgba(0,0,0,.5); }}
      .rl {{ color:#fff; font-size:11px; opacity:.9; }}
      .chip {{ display:inline-block; margin-top:3px; padding:1px 7px; font-size:11px; color:#fff;
               background:rgba(0,0,0,.32); border-radius:10px; }}
      .tip {{ display:none; position:absolute; left:50%; bottom:108%; transform:translateX(-50%);
              background:#1a1a1a; color:#fff; padding:8px 10px; border-radius:8px; font-size:12px;
              white-space:nowrap; z-index:10; box-shadow:0 4px 12px rgba(0,0,0,.4); }}
      .pl:hover .tip {{ display:block; }}
      .pl:hover .tok {{ transform:scale(1.12); }}
    </style>
    <div class="wrap"><div class="pitch"><div class="mid"></div><div class="circ"></div>{''.join(cards)}</div></div>
    """


def _norm(s) -> str:
    return unidecode(str(s)).lower().strip()


# ---------------- UI ----------------
full = load().copy()                # GK 포함 전체
full["norm_key"] = full["player"].map(_norm)
df = full[~full["pos"].fillna("").str.contains("GK")]  # 필드플레이어
slots_df = load_slots()
slot_teams = set(slots_df["squad"].unique()) if slots_df is not None else set()
st.title("⚽ FC Analytics — 포메이션 & 역할 (EPL 2025/26)")

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

    min_min = st.slider("최소 출전(분)", 0, 2000, 600, step=100)
    st.caption("실측 슬롯: fetch_lineups.py로 수집 · 포메이션: team_formations.json")

dff = df[df["minutes"] >= min_min].reset_index(drop=True)
dff["pos_group"] = dff["pos"].map(position_group)  # find_similar(same_position=True)용
pct = league_percentiles(dff)
pct["norm_key"] = pct["player"].map(_norm)
team_df = dff[dff["squad"] == team]

# 실측 슬롯이 있으면 정확 배치, 없으면 휴리스틱 밴드
placements = None
if has_real:
    placements = placements_from_slots(team, slots_df, full, pct, formation)
if not placements:
    bands = pick_bands(team_df, formation)
    gk = team_goalkeeper(full, team)
    placements = placements_from_bands(bands, pct, gk)

xi_players = [p["full"] for p in placements if p["kind"] != "GK"]
xi_all = {p["full"] for p in placements}  # GK 포함 — 벤치 필터링용


def build_bench(team: str, xi_all: set[str], formation: str) -> pd.DataFrame:
    """팀에서 XI에 없는 선수들 → 벤치 테이블. 슬롯 데이터가 있으면 우선 활용."""
    t = full[full["squad"] == team].copy()
    bench = t[~t["player"].isin(xi_all)].sort_values("minutes", ascending=False)
    if bench.empty:
        return bench

    # Sofascore 슬롯 매핑 (있으면 — 현재 포메이션 우선, 없으면 다른 포메이션)
    slot_map = {}
    if slots_df is not None:
        sf = slots_df[slots_df["squad"] == team]
        if "formation" in sf.columns:
            cur = sf[sf["formation"] == formation]
            other = sf[sf["formation"] != formation]
            for _, r in cur.iterrows():
                slot_map[r["player"]] = (r["slot"], int(r["apps"]), "현재")
            for _, r in other.iterrows():
                if r["player"] not in slot_map:
                    slot_map[r["player"]] = (r["slot"], int(r["apps"]),
                                             str(r["formation"]))
        else:
            for _, r in sf.iterrows():
                slot_map[r["player"]] = (r["slot"], int(r["apps"]), "—")

    rows = []
    for _, p in bench.iterrows():
        name, pos, minutes = p["player"], p["pos"], int(p["minutes"])
        slot_info = slot_map.get(name)
        slot_label = f"{slot_info[0]} ({slot_info[1]}경기, {slot_info[2]})" if slot_info else "—"

        if "GK" in str(pos):
            role = "골키퍼"
        else:
            prow = pct[pct["norm_key"] == p["norm_key"]]
            if not prow.empty and minutes > 0:
                grp = position_group(pos)
                r_full, _ = assign_role(prow.iloc[0], grp)
                role = r_full.split(" (")[0]
            else:
                role = "—"
        rows.append({"선수": name, "포지션": pos, "분": minutes,
                     "슬롯(Sofascore)": slot_label, "역할(데이터)": role})
    return pd.DataFrame(rows)


bench_df = build_bench(team, xi_all, formation)
# 벤치 중 필드 플레이어만(상세 분석은 outfield 한정)
bench_outfield = ([n for n in bench_df["선수"].tolist()
                   if "GK" not in str(full[full["player"] == n].iloc[0]["pos"])]
                  if not bench_df.empty else [])

left, right = st.columns([1.1, 1])
with left:
    src = "실측 라인업" if has_real else "휴리스틱"
    tag = ""
    if sub_form:
        tag = " · 메인" if formation == main_form else " · 서브"
    st.subheader(f"{team} · 주전 XI ({formation}){tag} · {src}")
    st.caption("토큰에 호버하면 강점 지표가 라벨과 함께 표시 · 색=라인(🔴공격 🟠중원 🔵수비 🟢GK)")
    st.components.v1.html(pitch_html(placements), height=720)

    with st.expander(f"🪑 벤치 & 백업 (XI 외 {len(bench_df)}명)", expanded=False):
        if bench_df.empty:
            st.caption("벤치 데이터 없음")
        else:
            st.dataframe(bench_df, hide_index=True, use_container_width=True)

with right:
    st.subheader("선수 상세")
    include_bench = (st.checkbox(f"벤치/백업 포함 ({len(bench_outfield)}명)", value=False)
                     if bench_outfield else False)
    pool = xi_players + bench_outfield if include_bench else xi_players
    pick = st.selectbox("선수 선택", pool)

    prow_match = pct[pct["player"] == pick]
    if prow_match.empty:
        # 출전 min_min 미만 — 백분위/유사선수 계산 풀에 없음
        raw_match = full[full["player"] == pick]
        if not raw_match.empty:
            raw = raw_match.iloc[0]
            st.markdown(f"**{pick}** · {raw['pos']} · {int(raw['minutes'])}분")
        st.info(f"⚠️ 출전 {min_min}분 미만 — 백분위·역할·유사선수 분석을 보려면 "
                f"사이드바에서 최소 출전을 낮춰주세요.")
    else:
        prow = prow_match.iloc[0]
        grp = position_group(prow["pos"])
        role, _ = assign_role(prow, grp)
        raw = dff[dff["player"] == pick].iloc[0]
        st.markdown(f"**{pick}** · {raw['pos']} · {int(raw['minutes'])}분 → **{role}**")

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

        bar = pd.DataFrame(
            {"지표": [LABELS[f] for f in FEATURES], "리그 백분위": [round(prow[f] * 100) for f in FEATURES]}
        ).set_index("지표")
        st.bar_chart(bar, horizontal=True, height=320)

        same_pos = st.checkbox("같은 포지션 그룹만 비교", value=True,
                               help=f"{grp} 그룹(FW/MF/DF) 내에서만 코사인 유사도 탐색")
        st.markdown("**스타일이 비슷한 선수 (리그 전체)**")
        emb = build_embeddings(dff)
        sim = find_similar(dff, emb, pick, top=5, same_position=same_pos)
        sim_show = sim[["player", "squad", "pos", "similarity"]].copy()
        sim_show["similarity"] = (sim_show["similarity"] * 100).round(0).astype(int).astype(str) + "%"
        st.dataframe(sim_show, hide_index=True, use_container_width=True)

st.caption(
    "데이터: FBref 2025/26 (basic 티어, GK 제외) · 역할=리그 백분위 기반 아키타입 매칭 · 시뮬레이션 아님"
)
