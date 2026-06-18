"""
피치/포메이션/스쿼드 렌더 함수.

피치 SVG + 선수 토큰 배치(placements_from_slots/espn/bands), 스쿼드 뎁스 차트,
벤치/이적 스트립, 핵심 선수(star). 배치 좌표는 team_analysis의 slot_xy/포메이션 기반.

bench_placements·departed_placements는 원래 app.py 전역(full·slots_df·pct·left_out)을
참조했으나, 모듈 분리를 위해 해당 값들을 인자로 받도록 변경했다(호출부는 app.py).
"""
from __future__ import annotations

import pandas as pd

from .common import (
    team_color, _photo, _num_str, _ga_str, _norm, portrait_photo, flag_chip, fmt_value,
    pos_chip_color, rating_color, avatar, BAND_DEF, BAND_MID, BAND_FWD,
)
from .metrics import player_ovr, top_strengths
from team_analysis import (
    slot_xy, slot_kind, display_slot, espn_assign_slots, team_xi_from_slots,
    assign_role, position_group, pick_bands, team_goalkeeper, league_percentiles,
    GK_Y, BAND_Y_TOP, BAND_Y_BOTTOM,
)

# ── Squad Depth 버킷 매핑 (실제 슬롯 → 뎁스 차트 버킷) ──
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


# ==== 아래 함수는 app.py에서 sed로 정밀 이동됨 ====

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


# moved to src/ui/player.py: player_picker_card_html, selected_player_spotlight_html
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


# _num_str·_ga_str → src/ui/common.py (상단 import)


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
            role, _ = assign_role(prow, position_group(prow["pos"]), slot)
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
            role, _ = assign_role(prow0, position_group(prow0["pos"]), slot)
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


def espn_frequent_xi(team: str, espn_all, full: pd.DataFrame, pct: pd.DataFrame,
                     last_n: int | None = None):
    """팀의 주 포메이션 + 그 포메이션에서 '슬롯별 최빈 선발 선수'로 합성한 XI.

    last_n=None → 시즌 전체, last_n=5 → 최근 5경기.
    각 formation_place(슬롯)마다 가장 자주 선발된 선수를 뽑아 평균 베스트 XI를 만든다.
    반환: (formation, placements) 또는 (formation, None) / (None, None).
    """
    if espn_all is None:
        return None, None
    et = espn_all[(espn_all["squad"] == team) & (espn_all["starter"])].copy()
    if et.empty:
        return None, None
    matches = (et.drop_duplicates("event_id")[["event_id", "date", "formation"]]
               .dropna(subset=["formation"]).sort_values("date"))
    if matches.empty:
        return None, None
    if last_n:
        keep = set(matches.tail(last_n)["event_id"])
        et = et[et["event_id"].isin(keep)]
        matches = matches[matches["event_id"].isin(keep)]
    main_form = matches["formation"].mode().iloc[0]
    fe = et[et["formation"] == main_form]
    if fe.empty or "formation_place" not in fe.columns:
        return str(main_form), None
    rows: list[dict] = []
    for place in sorted(fe["formation_place"].dropna().unique()):
        grp = fe[fe["formation_place"] == place]
        top = grp["player"].mode()
        if top.empty:
            continue
        tp = top.iloc[0]
        prow = grp[grp["player"] == tp].iloc[0]
        rows.append({"player": tp, "espn_pos": prow.get("espn_pos"),
                     "jersey": prow.get("jersey"), "starter": True,
                     "formation_place": place})
    return str(main_form), placements_from_espn(team, rows[:11], str(main_form), full, pct)


def season_workload_html(team: str, espn_all, full: pd.DataFrame, top: int = 10) -> str:
    """시즌 누적 출전 패널 — 선발 횟수 + 총 출전시간 바 (좌측 시즌 보드 대칭용)."""
    ft = full[(full["squad"] == team) & (full["minutes"] > 0)].copy()
    if ft.empty:
        return ""
    ft = ft.sort_values("minutes", ascending=False).drop_duplicates("player").head(top)
    starts_norm: dict[str, int] = {}
    if espn_all is not None:
        et = espn_all[(espn_all["squad"] == team) & (espn_all["starter"] == True)]  # noqa: E712
        for k, v in et.groupby("player").size().items():
            starts_norm[_norm(k)] = int(v)
    _tm = ft["tm_photo"] if "tm_photo" in ft.columns else [None] * len(ft)
    _sid = ft["sofa_id"] if "sofa_id" in ft.columns else [None] * len(ft)
    pm = {_norm(p): _photo(sid, tm) for p, sid, tm in zip(ft["player"], _sid, _tm)}
    maxmin = float(ft["minutes"].max()) or 1.0
    tc = team_color(team)
    rows = ""
    for _, r in ft.iterrows():
        p = str(r["player"]); mins = int(r["minutes"])
        st = starts_norm.get(_norm(p), 0)
        nm = p.split()[-1] if len(p) > 14 else p
        bw = max(4, min(100, mins / maxmin * 100))
        rows += (
            f"<div style='display:flex;align-items:center;gap:9px;padding:7px 2px;"
            f"border-bottom:1px solid #f4f6f9'>"
            f"{avatar(pm.get(_norm(p), ''), '#cdd5e0', 26)}"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-size:12.5px;font-weight:700;color:#1a1f2e;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{nm}</div>"
            f"<div style='height:6px;background:#eef1f6;border-radius:4px;margin-top:5px'>"
            f"<div style='height:100%;width:{bw:.0f}%;background:{tc};border-radius:4px'></div></div></div>"
            f"<div style='text-align:right;flex:none'>"
            f"<div style='font-size:13px;font-weight:900;color:#1a1f2e'>{mins:,}<span style='font-size:10px;font-weight:700;color:#9aa3b2'>분</span></div>"
            f"<div style='font-size:10px;color:#9aa3b2'>{st}선발</div></div></div>")
    return (
        "<div style='font-family:sans-serif'>"
        "<div style='font-size:11px;font-weight:800;color:#8a93a5;margin-bottom:8px'>"
        "시즌 누적 출전 · 총 출전시간 / 선발 횟수</div>"
        f"{rows}</div>")


def recent_form_html(team: str, espn_all, subs_df, full: pd.DataFrame, last_n: int = 5) -> str:
    """최근 N경기 출전/선발 기반 '컨디션' 패널.
    선발=팀색 채움 · 교체투입=주황 · 미출전=회색 dot. 우측=선발 횟수(많을수록 핫·빨강)."""
    if espn_all is None:
        return ""
    et = espn_all[espn_all["squad"] == team]
    if et.empty:
        return ""
    matches = (et.drop_duplicates("event_id")[["event_id", "date", "home_away"]]
               .sort_values("date").tail(last_n))
    ev = list(matches["event_id"])
    if not ev:
        return ""
    ha_map = dict(zip(matches["event_id"], matches["home_away"]))
    per: list[tuple[set, set]] = []
    allp: set[str] = set()
    for evid in ev:
        sub_et = et[et["event_id"] == evid]
        starters = set(sub_et[sub_et["starter"] == True]["player"])  # noqa: E712
        ins: set[str] = set()
        if subs_df is not None:
            sd = subs_df[(subs_df["event_id"] == evid) & (subs_df["home_away"] == ha_map.get(evid))]
            ins = set(sd["player_in"].astype(str))
        per.append((starters, ins))
        allp |= set(sub_et["player"]) | ins

    ft = full[full["squad"] == team]
    _tm = ft["tm_photo"] if "tm_photo" in ft.columns else [None] * len(ft)
    _sid = ft["sofa_id"] if "sofa_id" in ft.columns else [None] * len(ft)
    pm = {_norm(p): _photo(sid, tm) for p, sid, tm in zip(ft["player"], _sid, _tm)}

    form = []
    for p in allp:
        seq = [("S" if p in s else ("I" if p in i else "-")) for s, i in per]
        starts, subs = seq.count("S"), seq.count("I")
        if starts + subs:
            form.append((p, seq, starts, subs))
    form.sort(key=lambda x: (x[2], x[3]), reverse=True)
    form = form[:10]
    if not form:
        return ""

    def heat(st):
        r = st / max(1, last_n)
        return ("#ef4444" if r >= 0.99 else "#f97316" if r >= 0.75 else "#f59e0b"
                if r >= 0.5 else "#eab308" if r >= 0.3 else "#94a3b8")

    tc = team_color(team)

    def dots(seq):
        out = ""
        for s in seq:
            c = tc if s == "S" else ("#f59e0b" if s == "I" else "#dfe3ea")
            out += (f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
                    f"background:{c};margin-right:3px'></span>")
        return out

    rows = ""
    for p, seq, starts, _subs in form:
        hc = heat(starts)
        nm = p.split()[-1] if len(p) > 14 else p
        rows += (
            f"<div style='display:flex;align-items:center;gap:9px;padding:7px 2px;"
            f"border-bottom:1px solid #f4f6f9'>"
            f"{avatar(pm.get(_norm(p), ''), '#cdd5e0', 26)}"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-size:12.5px;font-weight:700;color:#1a1f2e;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{nm}</div>"
            f"<div style='margin-top:4px'>{dots(seq)}</div></div>"
            f"<div style='text-align:right;flex:none'>"
            f"<div style='font-size:14px;font-weight:900;color:{hc}'>{starts}/{last_n}</div>"
            f"<div style='font-size:9px;color:#9aa3b2'>선발</div></div></div>")
    return (
        "<div style='font-family:sans-serif'>"
        f"<div style='font-size:11px;font-weight:800;color:#8a93a5;margin-bottom:8px'>"
        f"최근 {last_n}경기 컨디션 · "
        f"<span style='color:{tc}'>●</span>선발 "
        f"<span style='color:#f59e0b'>●</span>교체 "
        f"<span style='color:#dfe3ea'>●</span>미출전</div>"
        f"{rows}</div>")


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



def bench_placements(team: str, xi_all: set[str], full: pd.DataFrame,
                     slots_df, pct: pd.DataFrame, left_out: dict) -> list[dict]:
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


def departed_placements(team: str, full: pd.DataFrame, left_out: dict) -> list[dict]:
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


def bench_strip_html(subs: list[dict], title: str = "벤치 & 백업") -> str:
    """벤치 선수 스트립 — 라이트 카드 + 원형 사진 토큰 (앱 톤 통일)."""
    if not subs:
        return ("<style>body{margin:0;background:#eef1f6}</style>"
                "<div style='color:#94a3b8;font-size:12px;padding:10px;font-family:sans-serif'>"
                "벤치 데이터 없음</div>")
    cards = []
    for p in subs:
        num = p.get("num", "")
        tcol = p.get("tcol", "#444a55")
        sid = p.get("sid", "")
        num_badge = (f"<div style='position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;"
                     f"padding:0 3px;background:#10151c;color:#fff;font-size:9px;font-weight:800;"
                     f"line-height:16px;border-radius:8px;border:1.5px solid #fff'>{num}</div>") if num else ""
        tip = f"{p.get('full', '')} · {p.get('minutes', 0)}분"
        cards.append(
            f"<div title='{tip}' style='width:76px;text-align:center'>"
            f"<div style='position:relative;width:48px;margin:0 auto'>"
            f"{avatar(sid, tcol, 48)}{num_badge}</div>"
            f"<div style='font-size:12px;font-weight:700;color:#1a1f2e;margin-top:7px;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{p['name']}</div>"
            f"<div style='font-size:10px;color:#8a93a5;margin-top:1px;white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis'>{p['role']}</div>"
            f"<div style='font-size:9.5px;color:#b6bdc9;margin-top:1px'>{p['minutes']}분</div></div>")
    return (
        "<style>body{margin:0;background:#eef1f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}</style>"
        "<div style='background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:14px 16px 16px;"
        "box-shadow:0 1px 3px rgba(16,24,40,.04),0 6px 18px rgba(16,24,40,.05)'>"
        f"<div style='font-size:11px;font-weight:800;color:#8a93a5;letter-spacing:1px;"
        f"text-transform:uppercase;margin-bottom:13px'>{title} ({len(subs)}명)</div>"
        "<div style='display:flex;flex-wrap:wrap;gap:15px 12px'>" + "".join(cards) + "</div></div>")

