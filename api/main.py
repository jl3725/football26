"""
FastAPI 백엔드 — football.db(datastore)를 JSON API 로 노출.

이 POC 는 "Next.js + FastAPI 로 앱 느낌을 낼 수 있는가"를 증명하기 위한 것.
데이터 층은 이미 만든 src/datastore.py 를 그대로 재사용하므로, UI 프레임워크와
무관하게 리그/시즌 좌표로 데이터를 얻는다.

실행:
    .venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000

주의: OVR/레이더 수치는 team_unit_metrics 인덱스를 그대로/근사 매핑한 POC 값.
추후 overview.team_ratings(유저가 튜닝한 공식)를 순수 로직으로 추출해 교체 가능.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import datastore as ds  # noqa: E402
import teammeta as tm  # noqa: E402
import ratings as rt  # noqa: E402
import ratings_v2 as rv  # noqa: E402  (절대·퍼포먼스 우선 모델)
import transfer_adjust as ta  # noqa: E402
from leagues import ACTIVE_LEAGUE, league_config  # noqa: E402
from team_analysis import (  # noqa: E402  (streamlit 비의존)
    espn_assign_slots, slot_xy, slot_kind, formation_slots, display_slot,
)

app = FastAPI(title="Football Scout API", version="0.1.0")
# CORS — 배포 시 ALLOWED_ORIGINS 환경변수(쉼표구분)로 도메인 지정. 기본 "*"
# (읽기전용 공개 API. 단, Vercel rewrites 로 프록시하면 브라우저는 same-origin 이라 CORS 미발생)
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

MANAGER_JSON = ROOT / "data" / "manager_profiles_2025_2026.json"
TEAM_PROFILES_JSON = ROOT / "data" / "team_profiles.json"
SEASON_TEAMS_JSON = ROOT / "data" / "season_teams.json"


def _managers() -> dict:
    try:
        return json.loads(MANAGER_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _team_profiles() -> dict:
    """위키백과 자동 수집 구단 설명(enrich_team_profiles.py). teammeta 하드코딩 폴백."""
    try:
        return json.loads(TEAM_PROFILES_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _idx_to_ovr(idx: float) -> int:
    """team_unit_metrics 인덱스(0-99) → 체감 OVR 밴드(대략 60-90). POC 근사."""
    return int(round(55 + float(idx) * 0.36))


def _team_row(table: str, team: str, league: str, key: str = "squad"):
    df = ds.read_table(table, league=league)
    if df is None or key not in df.columns:
        return None
    hit = df[df[key] == team]
    return hit.iloc[0] if not hit.empty else None


def _current_window(today: datetime.date | None = None) -> dict:
    """현재 날짜 기준 활성 이적시장 감지 (Streamlit _current_transfer_window 포팅).

    season_id = 시즌 시작 연도. 여름(6/14~9/1)=season_id y, 겨울(1월~2/3)=season_id y-1.
    그 외에는 시즌 진행 중(윈도우 닫힘).
    """
    today = today or datetime.date.today()
    y, m, d = today.year, today.month, today.day
    if (m == 6 and d >= 14) or m in (7, 8) or (m == 9 and d == 1):
        sy = y
        return {"season_id": sy, "window": "summer", "label": f"{sy % 100:02d}/{(sy + 1) % 100:02d}",
                "state": "summer", "is_open": True, "kr": "여름"}
    if m == 1 or (m == 2 and d <= 3):
        sy = y - 1
        return {"season_id": sy, "window": "winter", "label": f"{sy % 100:02d}/{(sy + 1) % 100:02d}",
                "state": "winter", "is_open": True, "kr": "겨울"}
    sy = y if m >= 7 else y - 1
    return {"season_id": sy, "window": "summer", "label": f"{sy % 100:02d}/{(sy + 1) % 100:02d}",
            "state": "closed", "is_open": False, "kr": None}


def _data_season_label() -> str:
    from leagues import SEASON_START
    return f"{SEASON_START % 100:02d}/{(SEASON_START + 1) % 100:02d}"


def _window_filter(tt, win):
    """이적 DF 를 활성 윈도우로 필터. 해당 윈도우 데이터 없으면 (원본, False)."""
    if tt is None or "season_id" not in tt.columns or "window" not in tt.columns:
        return tt, False
    f = tt[(pd.to_numeric(tt["season_id"], errors="coerce") == win["season_id"])
           & (tt["window"].astype(str) == win["window"])]
    if f.empty:
        return tt, False
    return f, True


@app.get("/api/context")
def context():
    win = _current_window()
    return {
        "today": str(datetime.date.today()),
        "data_season": _data_season_label(),
        "window": win,
    }


@app.get("/api/leagues")
def leagues():
    out = []
    for lk in ds.available_leagues():
        try:
            cfg = league_config(lk)
            out.append({"key": lk, "name": cfg.name, "country": cfg.country})
        except KeyError:
            out.append({"key": lk, "name": lk, "country": ""})
    return out


@app.get("/api/teams")
def teams(league: str = ACTIVE_LEAGUE):
    st = ds.read_table("standings", league=league)
    if st is None:
        raise HTTPException(404, "standings not found")
    st = st.sort_values("rank")
    return [
        {
            "name": r["squad"],
            "color": tm.team_color(r["squad"]),
            "logo": tm.team_logo(r["squad"]),
            "rank": int(r["rank"]),
            "points": int(r["points"]),
        }
        for _, r in st.iterrows()
    ]


@app.get("/api/teams/next")
def teams_next(league: str = ACTIVE_LEAGUE):
    """다음 시즌(개막 전) 로스터 — detect_season_teams.py 가 위키에서 감지해 기록.
    없으면 현재 팀을 폴백으로 반환(승격/강등 미반영)."""
    try:
        d = json.loads(SEASON_TEAMS_JSON.read_text(encoding="utf-8"))
        if d.get("teams"):
            return d
    except (OSError, json.JSONDecodeError):
        pass
    st = ds.read_table("standings", league=league)
    teams = []
    if st is not None and "squad" in st.columns:
        for sq in sorted(st["squad"].astype(str)):
            teams.append({"name": sq, "color": tm.team_color(sq),
                          "logo": tm.team_logo(sq), "promoted": False})
    return {"season_label": "", "source_title": "", "detected_at": "",
            "teams": teams, "promoted": [], "relegated": [], "meta_missing": []}


@app.get("/api/overview/{team}")
def overview(team: str, league: str = ACTIVE_LEAGUE):
    stand = _team_row("standings", team, league)
    if stand is None:
        raise HTTPException(404, f"team '{team}' not found in {league}")
    um = _team_row("team_unit_metrics", team, league)

    # 최근 5경기 폼
    sch = ds.read_table("schedule", league=league)
    form: list[str] = []
    if sch is not None and "squad" in sch.columns:
        ts = sch[sch["squad"] == team]
        if "gw" in ts.columns:
            ts = ts.sort_values("gw")
        form = [str(x) for x in ts["result"].dropna().tolist()[-5:]]

    # 감독
    mgr = _managers().get(team)
    manager = None
    if mgr:
        manager = {
            "name": mgr.get("name", ""),
            "nationality": mgr.get("nationality", ""),
            "style": mgr.get("style", ""),
            "formation": mgr.get("formation", ""),
            "appointed": mgr.get("appointed", ""),
            "focus": mgr.get("focus", ""),
            "photo": mgr.get("photo_url", "") if str(mgr.get("photo_url") or "").startswith("http") else "",
            "bio": mgr.get("bio_ko", ""),          # 위키백과 자동 (감독 바뀌면 자동 갱신)
            "tactics": mgr.get("tactics_ko", ""),  # 감독 본인 위키 전술 섹션
        }
        if mgr.get("previous_name"):
            manager["previous"] = {
                "name": mgr.get("previous_name", ""),
                "left_date": str(mgr.get("previous_left_date") or ""),
            }
            manager["changed_at"] = str(mgr.get("change_detected_at") or "")[:10]

    # 이적 — 현재 활성 윈도우(26/27 등)만. 없으면 폴백. 임대복귀는 제외.
    win = _current_window()
    tr = ds.read_table("transfers", league=league)
    tin, tout = [], []
    if tr is not None and "squad" in tr.columns:
        tt = tr[tr["squad"] == team].copy()
        tt, _wf = _window_filter(tt, win)
        tt = tt[~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)].copy()
        tt["_fee"] = tt["fee_eur"].map(lambda v: _num(v, 0.0))
        for direction, bucket in (("in", tin), ("out", tout)):
            sub = tt[tt["direction"] == direction].sort_values("_fee", ascending=False).head(6)
            for _, r in sub.iterrows():
                bucket.append({
                    "player": r.get("player", ""),
                    "club": r.get("club", ""),
                    "fee_eur": _num(r.get("fee_eur"), 0.0),
                    "fee_text": str(r.get("fee_text") or ""),
                    "pos": str(r.get("pos") or ""),
                })

    def _ix(col, default=50):
        if um is None or col not in um:
            return default
        try:
            return int(um[col])
        except (TypeError, ValueError):
            return default

    # 절대 OVR (v2) — 스쿼드 현재 실력의 출전가중 평균. 리그 순위·폼과 분리.
    # 표시 OVR = 이번 창 이적 반영 스쿼드 기준. delta = 이적 전 대비 변화.
    ovr = {
        "overall": _idx_to_ovr(_ix("overall_index")),
        "attack": _idx_to_ovr(_ix("attack_index")),
        "midfield": _idx_to_ovr(_ix("midfield_index")),
        "defense": _idx_to_ovr(_ix("defense_index")),
        "top_xi": _idx_to_ovr(_ix("overall_index")),
    }
    ovr_delta = {"overall": 0, "attack": 0, "midfield": 0, "defense": 0}
    full_df = ds.read_table("players_full", league=league)
    base = rv.team_ratings(full_df, team)                       # 이적 전(현재 스쿼드)
    if base:
        adj = rv.team_ratings(ta.build_adjusted_full(full_df, tr, win), team) or base  # 이번 창 반영
        for k in ("overall", "attack", "midfield", "defense"):
            ovr[k] = adj[k]
            ovr_delta[k] = adj[k] - base[k]
        ovr["top_xi"] = adj.get("top_xi", adj["overall"])

    # 구단 정보 + 스쿼드 가치 순위
    info = dict(tm.team_info(team))
    # 팀 설명 — 위키백과 자동 수집분으로 덮어씀(없으면 teammeta 하드코딩 유지)
    tp = _team_profiles().get(team)
    if tp and tp.get("desc_ko"):
        info["desc"] = tp["desc_ko"]
    value_rank = None
    if full_df is not None and "market_value_eur" in full_df.columns:
        tv = full_df.groupby("squad")["market_value_eur"].sum()
        if team in tv.index:
            value_rank = int(tv.rank(ascending=False)[team])
            info["squad_value"] = float(tv[team])
    info["value_rank"] = value_rank

    # 핵심 선수 — ss_rating 상위 5
    stars = []
    if full_df is not None:
        sq = full_df[full_df["squad"] == team].copy()
        if "left_for" in sq.columns:
            sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]
        sq["_r"] = pd.to_numeric(sq.get("ss_rating"), errors="coerce").fillna(0)
        for _, r in sq.sort_values("_r", ascending=False).head(5).iterrows():
            stars.append({
                "player": r["player"], "pos": str(r.get("fl_group") or r.get("pos") or ""),
                "ovr": _player_ovr(r), "pot": _player_pot(r), "rating": round(_num(r.get("_r")), 2),
                "goals": int(_num(r.get("goals"))), "assists": int(_num(r.get("assists"))),
                "photo": _photo(r),
            })

    # 득점 유형 + 규율(statbunker)
    sb = _team_row("statbunker_team_stats", team, league)
    snapshot = None
    if sb is not None:
        snapshot = {
            "open_play": int(_num(sb.get("open_play_goals"))),
            "set_piece": int(_num(sb.get("non_penalty_set_piece_goals"))),
            "penalty": int(_num(sb.get("penalty_goals_type"))),
            "yellows": int(_num(sb.get("yellow_cards"))),
            "reds": int(_num(sb.get("red_cards")) + _num(sb.get("second_yellow_reds"))),
            "yellow_per_match": round(_num(sb.get("yellow_cards_per_match")), 2),
        }

    # 현재 부상자
    inj_tbl = ds.read_table("transfermarkt_injuries", league=league)
    injuries = []
    if inj_tbl is not None and "squad" in inj_tbl.columns:
        ti = inj_tbl[inj_tbl["squad"].astype(str) == team]
        if "active" in ti.columns:
            ti = ti[ti["active"].astype(str).str.lower().isin({"true", "1", "yes", "y"})]
        for _, r in ti.iterrows():
            injuries.append({
                "player": str(r.get("player") or ""), "injury": str(r.get("injury") or ""),
                "until": str(r.get("until") or ""), "pos": str(r.get("position") or ""),
                "photo": str(r.get("tm_photo") or "") if str(r.get("tm_photo") or "").startswith("http") else "",
            })

    # 팀 리더 (지표별 1위)
    leaders = []
    if full_df is not None:
        sq_all = full_df[full_df["squad"] == team]
        for label, col, kind in [("득점", "goals", "tot"), ("도움", "assists", "tot"),
                                 ("xG", "xg_p90", "p90"), ("키패스", "key_passes_per90", "p90"),
                                 ("태클", "tackles_won_per90_ss", "p90")]:
            if col in sq_all.columns and not sq_all.empty:
                ss = sq_all.copy()
                ss["_v"] = pd.to_numeric(ss[col], errors="coerce").fillna(0)
                ss = ss[ss["_v"] > 0].sort_values("_v", ascending=False)
                if not ss.empty:
                    r = ss.iloc[0]
                    leaders.append({"label": label, "player": r["player"], "photo": _photo(r),
                                    "value": round(float(r["_v"]), 2) if kind == "p90" else int(r["_v"])})

    # 시즌 중 이적으로 팀을 떠난 선수
    departed = []
    if full_df is not None and "left_for" in full_df.columns:
        dep = full_df[(full_df["squad"] == team) & full_df["left_for"].notna()
                      & (full_df["left_for"].astype(str).str.strip() != "")]
        for _, r in dep.iterrows():
            departed.append({"player": r["player"], "left_for": str(r.get("left_for") or ""),
                             "pos": str(r.get("fl_group") or r.get("pos") or ""), "photo": _photo(r)})

    # 강점/약점 (지수 상·하위 라벨)
    edge = {"strengths": [], "weaknesses": []}
    if um is not None:
        scored = []
        for col, label, _line in _FACTOR_DEFS:
            try:
                val = int(um[col]) if pd.notna(um.get(col)) else None
            except (TypeError, ValueError):
                val = None
            if val is not None:
                scored.append((label, val))
        scored.sort(key=lambda x: -x[1])
        edge = {"strengths": [{"label": l, "value": v} for l, v in scored[:3]],
                "weaknesses": [{"label": l, "value": v} for l, v in scored[-3:][::-1]]}

    return {
        "team": team,
        "league": league,
        "color": tm.team_color(team),
        "logo": tm.team_logo(team),
        "fullName": tm.team_fullname(team),
        "capacity": tm.team_capacity(team),
        "info": info,
        "standing": {
            "rank": int(stand["rank"]), "played": int(stand["played"]),
            "won": int(stand["won"]), "drawn": int(stand["drawn"]),
            "lost": int(stand["lost"]), "gf": int(stand["gf"]),
            "ga": int(stand["ga"]), "gd": int(stand["gd"]),
            "points": int(stand["points"]),
        },
        "ovr": ovr,
        "ovr_delta": ovr_delta,
        "radar": [
            {"axis": "ATT OUT", "value": _ix("attack_output_index")},
            {"axis": "CREATE", "value": _ix("attack_creation_index")},
            {"axis": "CONTROL", "value": _ix("midfield_control_index")},
            {"axis": "PRESS", "value": _ix("pressing_index")},
            {"axis": "DEF OUT", "value": _ix("defense_output_index")},
            {"axis": "SET PC", "value": _ix("set_piece_attack_index")},
        ],
        "form": form,
        "manager": manager,
        "snapshot": snapshot,
        "edge": edge,
        "stars": stars,
        "leaders": leaders,
        "departed": departed,
        "injuries": injuries,
        "transfers": {"in": tin, "out": tout},
        "window": win,
        "data_season": _data_season_label(),
    }


@app.get("/api/calendar")
def calendar():
    cal = ds.read_table("calendar_events")
    events = []
    if cal is not None:
        for _, r in cal.iterrows():
            events.append({
                "name": str(r.get("name") or ""), "start": str(r.get("start") or ""),
                "end": str(r.get("end") or ""), "icon": str(r.get("icon") or ""),
                "kind": str(r.get("kind") or "event"),
            })
    return {"events": events}


def _num(v, default=0.0):
    try:
        f = float(v)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def _photo(row) -> str:
    p = row.get("tm_photo")
    return str(p) if p is not None and not pd.isna(p) and str(p).startswith("http") else ""


def _line_of(fl_group, pos) -> str:
    g = str(fl_group or "").upper()
    p = str(pos or "").upper()
    if g == "GK" or "GK" in p:
        return "GK"
    if g in ("CB", "FB", "RB", "LB") or "DF" in p:
        return "DEF"
    if g in ("DM", "CM", "AM") or "MF" in p:
        return "MID"
    if g in ("ST", "W", "RW", "LW") or "FW" in p:
        return "FWD"
    return "MID"


def _player_ovr(row) -> int:
    # v2: 퍼포먼스 앵커 + 표본회귀 + 나이곡선, 시장가치는 약한 prior (잠재력 분리)
    return rv.current_ovr(
        ss_rating=row.get("ss_rating"), minutes=row.get("minutes"), age=row.get("age"),
        value=row.get("market_value_eur"), goals=row.get("goals"), assists=row.get("assists"),
        pos_group=str(row.get("fl_group") or row.get("pos") or ""),
    )


def _player_pot(row) -> int:
    return rv.potential(current=_player_ovr(row), age=row.get("age"),
                        value=row.get("market_value_eur"))


def _squad_df(team: str, league: str):
    full = ds.read_table("players_full", league=league)
    if full is None:
        return None
    df = full[full["squad"] == team].copy()
    if "left_for" in df.columns:
        df = df[df["left_for"].isna() | (df["left_for"].astype(str).str.strip() == "")]
    return df


@app.get("/api/squad/{team}")
def squad(team: str, league: str = ACTIVE_LEAGUE):
    df = _squad_df(team, league)
    if df is None or df.empty:
        raise HTTPException(404, "squad not found")
    lines: dict[str, list] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for _, r in df.iterrows():
        line = _line_of(r.get("fl_group"), r.get("pos"))
        lines[line].append({
            "player": r["player"],
            "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "age": int(_num(r.get("age"))),
            "minutes": int(_num(r.get("minutes"))),
            "value_eur": _num(r.get("market_value_eur")),
            "ovr": _player_ovr(r),
            "photo": _photo(r),
            "goals": int(_num(r.get("goals"))),
            "assists": int(_num(r.get("assists"))),
        })
    for k in lines:
        lines[k].sort(key=lambda x: (-x["ovr"], -x["minutes"]))

    # 포지션 버킷 + 뎁스 점수 (원본 squad_depth_html)
    BUCKET_ORDER = ["GK", "CB", "RB", "LB", "DM", "CM", "AM", "RW", "LW", "W", "ST"]
    BUCKET_MAP = {"GK": "GK", "CB": "CB", "RB": "RB", "LB": "LB", "RWB": "RB", "LWB": "LB",
                  "DM": "DM", "CM": "CM", "AM": "AM", "RW": "RW", "LW": "LW", "W": "W", "ST": "ST"}
    raw: dict[str, list] = {}
    for _, r in df.iterrows():
        g = str(r.get("fl_group") or "").upper()
        bucket = BUCKET_MAP.get(g)
        if bucket is None:
            continue
        raw.setdefault(bucket, []).append({
            "player": r["player"], "ovr": _player_ovr(r), "minutes": int(_num(r.get("minutes"))),
            "age": int(_num(r.get("age"))), "photo": _photo(r),
        })
    buckets = []
    for b in BUCKET_ORDER:
        pls = raw.get(b)
        if not pls:
            continue
        pls.sort(key=lambda x: (-x["ovr"], -x["minutes"]))
        best_backup = pls[1]["ovr"] if len(pls) > 1 else 38
        depth = round(0.7 * best_backup + 0.3 * min(100, len(pls) * 22))
        buckets.append({"pos": b, "count": len(pls), "depth": depth,
                        "starter": pls[0], "rotation": pls[1:]})
    return {"team": team, "color": tm.team_color(team), "lines": lines, "buckets": buckets}


@app.get("/api/schedule/{team}")
def schedule(team: str, league: str = ACTIVE_LEAGUE):
    sch = ds.read_table("schedule", league=league)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    ts = sch[sch["squad"] == team].copy()
    if "gw" in ts.columns:
        ts = ts.sort_values("gw")

    # espn 라인업이 있는 경기: date → (event_id, formation) 매핑
    el = ds.read_table("espn_lineups", league=league)
    date_ev: dict[str, tuple[str, str]] = {}
    if el is not None:
        te = el[el["squad"] == team]
        for eid, g in te.groupby("event_id"):
            d = str(g["date"].iloc[0])
            date_ev[d] = (str(eid), str(g["formation"].iloc[0]))

    out = []
    for _, r in ts.iterrows():
        d = str(r.get("date") or "")
        ev = date_ev.get(d)
        out.append({
            "gw": int(_num(r.get("gw"))),
            "date": d,
            "home_away": str(r.get("home_away") or ""),
            "opponent": str(r.get("opponent") or ""),
            "opp_logo": tm.team_logo(str(r.get("opponent") or "")),
            "gf": None if pd.isna(r.get("gf")) else int(_num(r.get("gf"))),
            "ga": None if pd.isna(r.get("ga")) else int(_num(r.get("ga"))),
            "score": str(r.get("score") or ""),
            "result": str(r.get("result") or ""),
            "event_id": ev[0] if ev else None,
            "formation": ev[1] if ev else None,
        })
    return {"team": team, "color": tm.team_color(team), "matches": out}


@app.get("/api/match/{team}/{event_id}")
def match(team: str, event_id: str, league: str = ACTIVE_LEAGUE):
    el = ds.read_table("espn_lineups", league=league)
    if el is None:
        raise HTTPException(404, "lineups not found")
    m = el[(el["squad"] == team) & (el["event_id"].astype(str) == str(event_id))]
    if m.empty:
        raise HTTPException(404, "match not found")
    formation = str(m["formation"].iloc[0])
    home_away = str(m["home_away"].iloc[0])
    starters = m[pd.to_numeric(m["starter"], errors="coerce") == 1].sort_values("formation_place")
    resolve = _players_lookup(league)

    placements = []
    try:
        slots = espn_assign_slots([str(x) for x in starters["espn_pos"].tolist()], formation)
    except Exception:  # noqa: BLE001
        slots = [None] * len(starters)
    for (_, row), slot in zip(starters.iterrows(), slots):
        if not slot:
            continue
        x, y = slot_xy(slot, formation)
        pr = resolve(str(row["player"]))
        placements.append({
            "slot": display_slot(slot, formation), "player": str(row["player"]),
            "x": round(float(x), 1), "y": round(float(y), 1), "kind": slot_kind(slot),
            "ovr": _player_ovr(pr) if pr is not None else None, "photo": _photo(pr) if pr is not None else "",
        })

    # 교체 타임라인
    subs_tbl = ds.read_table("espn_subs", league=league)
    subs = []
    if subs_tbl is not None:
        sm = subs_tbl[subs_tbl["event_id"].astype(str) == str(event_id)]
        sm = sm[sm["home_away"].astype(str) == home_away]
        for _, r in sm.iterrows():
            subs.append({"minute": str(r.get("minute") or ""),
                         "player_in": str(r.get("player_in") or ""), "player_out": str(r.get("player_out") or "")})

    # 벤치(선발 아닌 선수) — 교체 없을 때 폴백
    bench = [str(p) for p in m[pd.to_numeric(m["starter"], errors="coerce") != 1]["player"].tolist()]

    return {"team": team, "color": tm.team_color(team), "event_id": str(event_id),
            "formation": formation, "home_away": home_away,
            "placements": placements, "subs": subs, "bench": bench}


@app.get("/api/players/{team}")
def players(team: str, league: str = ACTIVE_LEAGUE):
    df = _squad_df(team, league)
    if df is None or df.empty:
        raise HTTPException(404, "players not found")
    df = df.copy()
    df["_ovr"] = df.apply(_player_ovr, axis=1)
    df = df.sort_values("_ovr", ascending=False)
    out = []
    for _, r in df.iterrows():
        out.append({
            "player": r["player"],
            "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "line": _line_of(r.get("fl_group"), r.get("pos")),
            "age": int(_num(r.get("age"))),
            "nationality": str(r.get("nationality") or ""),
            "value_eur": _num(r.get("market_value_eur")),
            "ovr": int(r["_ovr"]),
            "photo": _photo(r),
        })
    return {"team": team, "color": tm.team_color(team), "players": out}


# 선수 상세 지표 — FM 스타일 카테고리 그룹 (아웃필더/골키퍼)
_PL_CATS = [
    ("공격", [("결정력", "npxg_p90"), ("슈팅/90", "shots_p90"), ("유효슈팅/90", "sot_per90")]),
    ("창조", [("기대도움 xA", "xa_p90"), ("키패스/90", "key_passes_per90"), ("빅찬스/90", "big_chances_created_per90")]),
    ("배급", [("패스성공%", "pass_pct"), ("롱패스%", "long_ball_pct"), ("전진패스/90", "final_third_passes_per90")]),
    ("볼 운반", [("드리블/90", "successful_dribbles_per90"), ("드리블성공%", "dribble_success_pct"), ("크로스%", "cross_acc_pct")]),
    ("수비", [("태클/90", "tackles_won_per90_ss"), ("인터셉트/90", "interceptions_per90_ss"), ("회수/90", "recoveries_per90")]),
    ("피지컬·듀얼", [("공중볼%", "aerial_won_pct"), ("지상경합%", "ground_duels_won_pct"), ("종합듀얼%", "total_duels_won_pct")]),
]
_GK_CATS = [
    ("선방", [("선방%", "gk_save_pct"), ("선방/90", "gk_saves_per90")]),
    ("무실점", [("클린시트%", "gk_cs_pct")]),
    ("박스 지배", [("하이클레임/90", "gk_high_claims_per90"), ("펀칭/90", "gk_punches_per90"), ("스위핑/90", "gk_runs_out_per90")]),
    ("빌드업", [("패스성공%", "pass_pct"), ("롱볼%", "long_ball_pct")]),
]
# 리그 랭크 배지 후보 — (라벨, 컬럼)
_BADGE_METRICS = [
    ("득점왕", "goals"), ("도움왕", "assists"), ("결정력", "npxg_p90"), ("키패스", "key_passes_per90"),
    ("드리블", "successful_dribbles_per90"), ("태클", "tackles_won_per90_ss"), ("인터셉트", "interceptions_per90_ss"),
    ("공중볼", "aerial_won_pct"), ("평점", "ss_rating"),
]


@app.get("/api/player/{team}/{player}")
def player_detail(team: str, player: str, league: str = ACTIVE_LEAGUE):
    full = ds.read_table("players_full", league=league)
    if full is None:
        raise HTTPException(404, "players not found")
    hit = full[(full["squad"] == team) & (full["player"] == player)]
    if hit.empty:
        hit = full[full["player"] == player]
    if hit.empty:
        raise HTTPException(404, f"player '{player}' not found")
    row = hit.iloc[0]
    is_gk = _line_of(row.get("fl_group"), row.get("pos")) == "GK"

    pool = full.copy()
    min_min = 300 if is_gk else 450
    pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= min_min]
    if is_gk:
        pool = pool[pool.apply(lambda r: _line_of(r.get("fl_group"), r.get("pos")) == "GK", axis=1)]

    def pctile(col: str) -> int | None:
        if col not in pool.columns:
            return None
        s = pd.to_numeric(pool[col], errors="coerce").dropna()
        v = _num(row.get(col), None) if row.get(col) is not None else None
        try:
            v = float(row.get(col))
        except (TypeError, ValueError):
            return None
        if pd.isna(v) or s.empty:
            return None
        return int(round((s < v).mean() * 100))

    # 카테고리 그룹 + 카테고리 평균
    cats_cfg = _GK_CATS if is_gk else _PL_CATS
    categories = []
    for cat_name, subs in cats_cfg:
        ms = []
        for label, col in subs:
            p = pctile(col)
            if p is not None:
                ms.append({"label": label, "pct": p, "raw": round(_num(row.get(col)), 2)})
        if ms:
            avg = int(round(sum(m["pct"] for m in ms) / len(ms)))
            categories.append({"name": cat_name, "avg": avg, "metrics": ms})
    radar = [{"axis": c["name"], "value": c["avg"]} for c in categories]

    # 리그 랭크 배지
    badge_cfg = [("선방율", "gk_save_pct"), ("클린시트", "gk_cs_pct")] if is_gk else _BADGE_METRICS
    badges = []
    for label, col in badge_cfg:
        if col not in pool.columns:
            continue
        s = pd.to_numeric(pool[col], errors="coerce").dropna()
        try:
            v = float(row.get(col))
        except (TypeError, ValueError):
            continue
        if pd.isna(v) or v <= 0 or s.empty:
            continue
        rank = int((s > v).sum()) + 1
        if rank <= 3:
            badges.append({"label": label, "rank": rank,
                           "medal": "🥇" if rank == 1 else ("🥈" if rank == 2 else "🥉")})
    badges.sort(key=lambda b: b["rank"])

    return {
        "player": row["player"], "team": team, "color": tm.team_color(team),
        "pos": str(row.get("fl_group") or row.get("pos") or ""),
        "line": _line_of(row.get("fl_group"), row.get("pos")),
        "age": int(_num(row.get("age"))), "nationality": str(row.get("nationality") or ""),
        "value_eur": _num(row.get("market_value_eur")), "photo": _photo(row),
        "ovr": _player_ovr(row), "ss_rating": _num(row.get("ss_rating")),
        "minutes": int(_num(row.get("minutes"))), "goals": int(_num(row.get("goals"))),
        "assists": int(_num(row.get("assists"))),
        "contract_until": str(row.get("tm_contract_until") or ""),
        "is_gk": is_gk, "categories": categories, "radar": radar, "badges": badges,
    }


def _tf_list(tt, direction):
    sub = tt[tt["direction"] == direction].copy()
    if "fee_text" in sub.columns:  # 임대복귀 제외 (원본과 동일)
        sub = sub[~sub["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
    sub["_fee"] = sub["fee_eur"].map(lambda v: _num(v))
    sub = sub.sort_values("_fee", ascending=False)
    out = []
    for _, r in sub.iterrows():
        out.append({
            "player": str(r.get("player") or ""), "club": str(r.get("club") or ""),
            "pos": str(r.get("pos") or ""), "age": int(_num(r.get("age"))),
            "nat": str(r.get("nat") or ""), "fee_eur": _num(r.get("fee_eur")),
            "fee_text": str(r.get("fee_text") or ""),
            "photo": str(r.get("photo") or "") if str(r.get("photo") or "").startswith("http") else "",
            "window": str(r.get("window") or ""),
        })
    return out


@app.get("/api/transfers/{team}")
def transfers(team: str, league: str = ACTIVE_LEAGUE, window: str = "current"):
    tr = ds.read_table("transfers", league=league)
    if tr is None:
        raise HTTPException(404, "transfers not found")
    tt = tr[tr["squad"] == team].copy()
    win = _current_window()
    filtered = False
    if window == "current":
        tt, filtered = _window_filter(tt, win)
    tin, tout = _tf_list(tt, "in"), _tf_list(tt, "out")
    spend = sum(x["fee_eur"] for x in tin)
    income = sum(x["fee_eur"] for x in tout)
    return {
        "team": team, "color": tm.team_color(team),
        "in": tin, "out": tout,
        "window": win, "data_season": _data_season_label(),
        "window_has_data": filtered,
        "summary": {"spend": spend, "income": income, "net": spend - income,
                    "in_count": len(tin), "out_count": len(tout)},
    }


@app.get("/api/news/{team}")
def news(team: str, league: str = ACTIVE_LEAGUE):
    na = ds.read_table("news_articles", league=league)
    if na is None:
        return {"team": team, "color": tm.team_color(team), "articles": []}
    ta = na[na["team"] == team].copy()
    if "published" in ta.columns:
        ta = ta.sort_values("published", ascending=False)
    today = str(datetime.date.today())
    out = []
    for _, r in ta.head(24).iterrows():
        fs = str(r.get("first_seen") or "")[:10]
        out.append({
            "headline": str(r.get("headline_ko") or r.get("headline") or ""),
            "headline_en": str(r.get("headline") or ""),
            "descr": str(r.get("descr_ko") or r.get("descr") or ""),
            "source": str(r.get("source") or ""),
            "published": str(r.get("published") or ""),
            "image": str(r.get("image") or "") if str(r.get("image") or "").startswith("http") else "",
            "link": str(r.get("link") or ""),
            "is_new": bool(fs and fs >= today),
        })
    return {"team": team, "color": tm.team_color(team), "articles": out, "sparse": len(out) < 3}


@app.get("/api/analytics/{team}")
def analytics(team: str, league: str = ACTIVE_LEAGUE):
    # 부상 임팩트 — 결장 경기 상위, 라인별 집계
    inj = ds.read_table("tm_injury_history", league=league)
    full = ds.read_table("players_full", league=league)
    line_map = {}
    if full is not None:
        for _, r in full[full["squad"] == team].iterrows():
            line_map[str(r["player"])] = _line_of(r.get("fl_group"), r.get("pos"))
    injuries, line_missed = [], {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    if inj is not None:
        ti = inj[inj["squad"] == team].copy()
        ti["_gm"] = ti["games_missed"].map(lambda v: _num(v))
        ti = ti[ti["_gm"] > 0].sort_values("_gm", ascending=False)
        for _, r in ti.head(10).iterrows():
            spells = []
            try:
                spells = json.loads(r.get("spells_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                spells = []
            latest = spells[-1]["injury"] if spells and isinstance(spells[-1], dict) and spells[-1].get("injury") else str(r.get("injuries") or "")
            line = line_map.get(str(r["player"]), "MID")
            gm = int(r["_gm"])
            line_missed[line] = line_missed.get(line, 0) + gm
            injuries.append({"player": str(r["player"]), "games_missed": gm,
                             "days_out": int(_num(r.get("days_out"))), "injury": latest, "line": line})
    total_missed = sum(line_missed.values()) or 1
    line_share = {k: round(v / total_missed * 100) for k, v in line_missed.items()}

    # 홈/원정 성과
    sch = ds.read_table("schedule", league=league)
    def _ppg(sub):
        if sub.empty:
            return 0.0
        pts = sub["result"].map({"W": 3, "D": 1, "L": 0}).fillna(0).sum()
        return round(pts / len(sub), 2)
    home = away = 0.0
    if sch is not None:
        ts = sch[sch["squad"] == team]
        home = _ppg(ts[ts["home_away"] == "H"])
        away = _ppg(ts[ts["home_away"] == "A"])

    # 상대 강도별 성과 (상위6/중위/하위6)
    stand = ds.read_table("standings", league=league)
    rank_map = {}
    if stand is not None:
        rank_map = {r["squad"]: int(r["rank"]) for _, r in stand.iterrows()}
    tier_pts = {"top": [], "mid": [], "bottom": []}
    if sch is not None:
        for _, r in sch[sch["squad"] == team].iterrows():
            res = str(r.get("result") or "")
            rk = rank_map.get(str(r.get("opponent") or ""))
            if res not in ("W", "D", "L") or rk is None:
                continue
            grp = "top" if rk <= 6 else ("bottom" if rk >= 15 else "mid")
            tier_pts[grp].append({"W": 3, "D": 1, "L": 0}[res])
    tier_ppg = {k: (round(sum(v) / len(v), 2) if v else 0.0) for k, v in tier_pts.items()}

    # OVR + 게임타일 + 레이더 (유저 튜닝 공식)
    um_df = ds.read_table("team_unit_metrics", league=league)
    ovr, radar = {}, []
    if um_df is not None and "squad" in um_df.columns:
        rl = rt.compute_team_ratings(team, full, stand, um_df.set_index("squad"))
        if rl:
            v = {lbl: int(val) for (lbl, val, _s) in rl}
            urow = um_df[um_df["squad"] == team]
            u = urow.iloc[0] if not urow.empty else None

            def _u(c, dflt=50):
                try:
                    return int(u[c]) if u is not None and pd.notna(u.get(c)) else dflt
                except (TypeError, ValueError):
                    return dflt
            ovr = {"overall": v.get("종합 지수", 60), "form": v.get("시즌 폼", 60),
                   "attack": v.get("공격 지수", 60), "midfield": v.get("미드필드 지수", 60),
                   "defense": v.get("수비 지수", 60), "set_piece": _u("set_piece_attack_index")}
            radar = [
                {"axis": "ATT OUT", "value": _u("attack_output_index")},
                {"axis": "CREATE", "value": _u("attack_creation_index")},
                {"axis": "CONTROL", "value": _u("midfield_control_index")},
                {"axis": "PRESS", "value": _u("pressing_index")},
                {"axis": "DEF OUT", "value": _u("defense_output_index")},
                {"axis": "SET PC", "value": _u("set_piece_attack_index")},
            ]

    # Match Factor Lab — 지수 상/하위 팩터 + 기여 선수
    factors = _match_factors(team, league, full, um_df)

    # 이적 요약
    tr = ds.read_table("transfers", league=league)
    tf_summary = {"spend": 0.0, "income": 0.0, "in_count": 0, "out_count": 0}
    if tr is not None:
        tt = tr[tr["squad"] == team]
        ins = tt[tt["direction"] == "in"]
        outs = tt[tt["direction"] == "out"]
        tf_summary = {
            "spend": float(pd.to_numeric(ins["fee_eur"], errors="coerce").fillna(0).sum()),
            "income": float(pd.to_numeric(outs["fee_eur"], errors="coerce").fillna(0).sum()),
            "in_count": int(len(ins)), "out_count": int(len(outs)),
        }

    return {
        "team": team, "color": tm.team_color(team),
        "ovr": ovr, "radar": radar,
        "injuries": injuries, "line_missed": line_missed, "line_share": line_share,
        "context": {"home_ppg": home, "away_ppg": away, "tier_ppg": tier_ppg},
        "factors": factors,
        "transfer_summary": tf_summary,
        "audit": _signing_audit(team, league, full),
        "manager_evo": _manager_evo(team),
    }


# 지수명 → (표시라벨, 관련 라인) — Match Factor Lab 기여선수 매핑용
_FACTOR_DEFS = [
    ("attack_output_index", "공격 마무리", "FWD"),
    ("attack_creation_index", "찬스 창출", "MID"),
    ("midfield_control_index", "중원 장악", "MID"),
    ("pressing_index", "전방 압박", "MID"),
    ("defense_output_index", "수비 안정", "DEF"),
    ("defense_box_aerial_index", "공중 장악", "DEF"),
    ("set_piece_attack_index", "세트피스", "DEF"),
    ("discipline_index", "규율 관리", "MID"),
]


def _match_factors(team, league, full, um_df):
    if um_df is None or "squad" not in um_df.columns:
        return {"strengths": [], "weaknesses": []}
    urow = um_df[um_df["squad"] == team]
    if urow.empty:
        return {"strengths": [], "weaknesses": []}
    u = urow.iloc[0]
    scored = []
    for col, label, line in _FACTOR_DEFS:
        try:
            val = int(u[col]) if pd.notna(u.get(col)) else None
        except (TypeError, ValueError):
            val = None
        if val is not None:
            scored.append((label, line, val))
    scored.sort(key=lambda x: -x[2])

    def _contrib(line):
        if full is None:
            return []
        sq = full[full["squad"] == team].copy()
        sq = sq[sq.apply(lambda r: _line_of(r.get("fl_group"), r.get("pos")) == line, axis=1)]
        sq["_r"] = pd.to_numeric(sq.get("ss_rating"), errors="coerce").fillna(0)
        return [{"player": r["player"], "photo": _photo(r), "ovr": _player_ovr(r)}
                for _, r in sq.sort_values("_r", ascending=False).head(3).iterrows()]

    strengths = [{"label": l, "value": v, "line": ln, "players": _contrib(ln)} for l, ln, v in scored[:3]]
    weaknesses = [{"label": l, "value": v, "line": ln, "players": _contrib(ln)} for l, ln, v in scored[-3:][::-1]]
    return {"strengths": strengths, "weaknesses": weaknesses}


def _signing_audit(team: str, league: str, full):
    """여름 영입 선수들의 이번 시즌 소화도 평가(출전/기여)."""
    tr = ds.read_table("transfers", league=league)
    if tr is None or full is None:
        return []
    ins = tr[(tr["squad"] == team) & (tr["direction"] == "in")].copy()
    if "window" in ins.columns:
        ins = ins[ins["window"].astype(str).str.lower().str.contains("summer") | (ins["window"].astype(str) == "")]
    fmap = {str(r["player"]): r for _, r in full[full["squad"] == team].iterrows()}
    out = []
    for _, r in ins.iterrows():
        name = str(r.get("player") or "")
        pf = fmap.get(name)
        mins = int(_num(pf.get("minutes"))) if pf is not None else 0
        goals = int(_num(pf.get("goals"))) if pf is not None else 0
        assists = int(_num(pf.get("assists"))) if pf is not None else 0
        if mins >= 1500:
            verdict, tone = "핵심 전력화", "good"
        elif mins >= 600:
            verdict, tone = "로테이션 정착", "ok"
        elif mins > 0:
            verdict, tone = "적응 중", "low"
        else:
            verdict, tone = "출전 기회 부족", "bad"
        out.append({
            "player": name, "fee_text": str(r.get("fee_text") or ""),
            "fee_eur": _num(r.get("fee_eur")), "pos": str(r.get("pos") or ""),
            "minutes": mins, "goals": goals, "assists": assists,
            "verdict": verdict, "tone": tone,
        })
    out.sort(key=lambda x: -x["fee_eur"])
    return out[:8]


def _manager_evo(team: str):
    """감독 전술 진화 — 현재 vs 이전(감독 교체 시)."""
    mp = _managers().get(team)
    if not mp:
        return None
    evo = {
        "name": mp.get("name", ""), "style": mp.get("style", ""),
        "formation": mp.get("formation", ""), "focus": mp.get("focus", ""),
        "appointed": mp.get("appointed", ""),
    }
    if mp.get("previous_name"):
        evo["previous"] = {
            "name": mp.get("previous_name", ""), "style": mp.get("previous_style", ""),
            "formation": mp.get("previous_formation", ""),
        }
    return evo


def _players_lookup(league):
    """이름 → 선수행 resolver. 악센트/이름순서 차이에 강건.
    예: 'Martin Odegaard'↔'Martin Ødegaard', ESPN 'Alisson Becker'↔'Alisson'."""
    from unidecode import unidecode

    def norm(x):
        return unidecode(str(x)).lower().strip()

    full = ds.read_table("players_full", league=league)
    exact, byfull, last, first = {}, {}, {}, {}
    if full is not None:
        for _, r in full.iterrows():
            nm = str(r["player"])
            exact[nm] = r
            n = norm(nm)
            byfull[n] = r
            toks = n.split()
            if toks:
                last.setdefault(toks[-1], r)
                first.setdefault(toks[0], r)

    def resolve(name):
        if name is None:
            return None
        s = str(name)
        if s in exact:
            return exact[s]
        n = norm(s)
        if n in byfull:
            return byfull[n]
        toks = n.split()
        if not toks:
            return None
        r = last.get(toks[-1])
        if r is None:
            r = first.get(toks[0])
        return r

    return resolve


def _placements(team: str, league: str, last_n: int | None = None):
    el = ds.read_table("espn_lineups", league=league)
    if el is None:
        return None
    df = el[(el["squad"] == team) & (pd.to_numeric(el["starter"], errors="coerce") == 1)].copy()
    if df.empty:
        return None
    df["date"] = df["date"].astype(str)
    matches = sorted(df["event_id"].unique(), key=lambda e: df[df["event_id"] == e]["date"].iloc[0])
    if last_n:
        matches = matches[-last_n:]
    sub = df[df["event_id"].isin(matches)]
    fm = sub.groupby("event_id")["formation"].first().mode()
    formation = str(fm.iloc[0]) if not fm.empty else "4-3-3"

    slot_counts: dict[str, dict[str, int]] = {}
    for eid in matches:
        m = sub[(sub["event_id"] == eid) & (sub["formation"] == formation)].sort_values("formation_place")
        if len(m) < 11:
            continue
        try:
            slots = espn_assign_slots([str(x) for x in m["espn_pos"].tolist()], formation)
        except Exception:  # noqa: BLE001
            continue
        for (_, row), slot in zip(m.iterrows(), slots):
            if not slot:
                continue
            slot_counts.setdefault(slot, {})
            slot_counts[slot][row["player"]] = slot_counts[slot].get(row["player"], 0) + 1

    resolve = _players_lookup(league)
    placements = []
    for slot in formation_slots(formation):
        cand = slot_counts.get(slot)
        player = max(cand, key=cand.get) if cand else None
        x, y = slot_xy(slot, formation)
        row = resolve(player) if player else None
        placements.append({
            "slot": display_slot(slot, formation),
            "player": player or "—",
            "x": round(float(x), 1), "y": round(float(y), 1),
            "kind": slot_kind(slot),
            "ovr": _player_ovr(row) if row is not None else None,
            "photo": _photo(row) if row is not None else "",
        })
    return {"formation": formation, "placements": placements}


@app.get("/api/lineup/{team}")
def lineup(team: str, league: str = ACTIVE_LEAGUE):
    season = _placements(team, league)
    if season is None:
        raise HTTPException(404, "lineup data not found")
    recent = _placements(team, league, last_n=5)

    # 벤치 — 시즌 XI 에 없는 스쿼드 선수(OVR 순 상위 8)
    xi_names = {p["player"] for p in season["placements"]}
    bench = []
    df = _squad_df(team, league)
    if df is not None:
        df = df.copy()
        df["_ovr"] = df.apply(_player_ovr, axis=1)
        for _, r in df[~df["player"].isin(xi_names)].sort_values("_ovr", ascending=False).head(8).iterrows():
            bench.append({"player": r["player"], "pos": str(r.get("fl_group") or r.get("pos") or ""),
                          "ovr": int(r["_ovr"]), "photo": _photo(r)})
    return {"team": team, "color": tm.team_color(team), "season": season, "recent": recent, "bench": bench}


# 유사 선수 엔진 — 임베딩은 최초 1회 빌드 후 캐시(요청마다 재계산 방지)
_SIM = None


def _sim_engine():
    global _SIM
    if _SIM is None:
        from similar_players import load_players, build_embeddings
        df = load_players()
        _SIM = (df, build_embeddings(df))
    return _SIM


@app.get("/api/similar/{player}")
def similar(player: str, same_position: bool = True, alpha: float = 0.6, league: str = ACTIVE_LEAGUE):
    from similar_players import find_similar
    try:
        df, emb = _sim_engine()
        res = find_similar(df, emb, player, top=6, same_position=same_position, alpha=alpha)
    except Exception:  # noqa: BLE001
        return {"player": player, "results": []}
    out = []
    for _, r in res.iterrows():
        out.append({
            "player": str(r.get("player") or ""), "squad": str(r.get("squad") or ""),
            "pos": str(r.get("fl_group") or r.get("pos") or ""), "age": int(_num(r.get("age"))),
            "value_eur": _num(r.get("market_value_eur")),
            "logo": tm.team_logo(str(r.get("squad") or "")),
            "score": round(_num(r.get("score")) * 100), "style": round(_num(r.get("style_sim")) * 100),
            "perf": round(_num(r.get("perf_score")) * 100),
        })
    return {"player": player, "results": out}


@app.get("/api/recommend/{team}")
def recommend(team: str, league: str = ACTIVE_LEAGUE):
    full = ds.read_table("players_full", league=league)
    um_df = ds.read_table("team_unit_metrics", league=league)
    stand = ds.read_table("standings", league=league)
    if full is None:
        return {"team": team, "weakest": None, "recommendations": []}

    # 가장 약한 유닛 판정
    weakest_line, weakest_label = "MID", "미드필드"
    if um_df is not None and "squad" in um_df.columns:
        rl = rt.compute_team_ratings(team, full, stand, um_df.set_index("squad"))
        if rl:
            vals = {lbl: int(v) for (lbl, v, _s) in rl}
            units = {"FWD": vals.get("공격 지수", 99), "MID": vals.get("미드필드 지수", 99), "DEF": vals.get("수비 지수", 99)}
            weakest_line = min(units, key=units.get)
            weakest_label = {"FWD": "공격", "MID": "미드필드", "DEF": "수비"}[weakest_line]

    # 해당 라인의 리그 최고 선수(타팀), OVR 순
    pool = full[full["squad"] != team].copy()
    pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= 600]
    if "left_for" in pool.columns:
        pool = pool[pool["left_for"].isna() | (pool["left_for"].astype(str).str.strip() == "")]
    pool = pool[pool.apply(lambda r: _line_of(r.get("fl_group"), r.get("pos")) == weakest_line, axis=1)].copy()

    # 전술 적합도 = 약점 라인 핵심 지표 백분위, 스쿼드 매치 = 평점 백분위
    fit_col = {"FWD": "npxg_p90", "MID": "key_passes_per90", "DEF": "tackles_won_per90_ss"}[weakest_line]
    fit_label = {"FWD": "득점 위협", "MID": "찬스 창출", "DEF": "수비 기여"}[weakest_line]
    fit_s = pd.to_numeric(pool.get(fit_col), errors="coerce") if fit_col in pool.columns else pd.Series(dtype=float)
    rate_s = pd.to_numeric(pool.get("ss_rating"), errors="coerce")

    def _pct_in(s, v):
        sv = s.dropna()
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0
        if pd.isna(v) or sv.empty:
            return 0
        return int(round((sv < v).mean() * 100))

    pool["_ovr"] = pool.apply(_player_ovr, axis=1)
    pool = pool.sort_values("_ovr", ascending=False).head(6)
    recs = []
    for _, r in pool.iterrows():
        recs.append({
            "player": r["player"], "squad": str(r.get("squad") or ""),
            "logo": tm.team_logo(str(r.get("squad") or "")),
            "pos": str(r.get("fl_group") or r.get("pos") or ""), "age": int(_num(r.get("age"))),
            "ovr": int(r["_ovr"]), "value_eur": _num(r.get("market_value_eur")),
            "photo": _photo(r), "rating": round(_num(r.get("ss_rating")), 2),
            "tactical_fit": _pct_in(fit_s, r.get(fit_col)),
            "squad_match": _pct_in(rate_s, r.get("ss_rating")),
        })
    return {"team": team, "color": tm.team_color(team),
            "weakest": {"line": weakest_line, "label": weakest_label, "fit_label": fit_label},
            "recommendations": recs}


@app.get("/api/database")
def database(league: str = ACTIVE_LEAGUE):
    """전 리그 선수 DB — 클라이언트에서 필터링(이름/포지션/나이/가치/국적)."""
    full = ds.read_table("players_full", league=league)
    if full is None:
        raise HTTPException(404, "players not found")
    df = full.copy()
    if "left_for" in df.columns:
        df = df[df["left_for"].isna() | (df["left_for"].astype(str).str.strip() == "")]
    df["_ovr"] = df.apply(_player_ovr, axis=1)
    df = df.sort_values("_ovr", ascending=False)
    out = []
    for _, r in df.iterrows():
        out.append({
            "player": r["player"], "squad": str(r.get("squad") or ""),
            "logo": tm.team_logo(str(r.get("squad") or "")),
            "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "line": _line_of(r.get("fl_group"), r.get("pos")),
            "age": int(_num(r.get("age"))), "nationality": str(r.get("nationality") or ""),
            "value_eur": _num(r.get("market_value_eur")), "ovr": int(r["_ovr"]),
            "photo": _photo(r),
        })
    nats = sorted({p["nationality"] for p in out if p["nationality"]})
    return {"league": league, "players": out, "nationalities": nats}


@app.get("/api/captains/{team}")
def captains(team: str, league: str = ACTIVE_LEAGUE):
    """주장단 — 공식 주장(TEAM_CAPTAINS) + football-lineups (c) 기록 부주장."""
    from unidecode import unidecode
    def _key(nm):
        t = unidecode(str(nm)).lower().split()
        return t[-1] if t else str(nm).lower()

    resolve = _players_lookup(league)
    out, seen = [], set()

    official = tm.team_captain(team)
    if official:
        r = resolve(official)
        nm = r["player"] if r is not None else official
        seen.add(_key(nm))
        out.append({"name": nm, "photo": _photo(r) if r is not None else "",
                    "ovr": _player_ovr(r) if r is not None else None,
                    "pos": (str(r.get("fl_group") or r.get("pos") or "") if r is not None else ""),
                    "role": "주장", "is_main": True})

    fl = ds.read_table("fl_positions", league=league)
    if fl is not None and "fl_name" in fl.columns:
        cap = fl[(fl["squad"] == team) & fl["fl_name"].astype(str).str.contains(r"\(c\)", na=False, regex=True)].copy()
        if not cap.empty:
            cap["base"] = (cap["fl_name"].astype(str).str.replace(r"\s*\(c\)", "", regex=True)
                           .str.replace(r"\s+(in|out)\d.*", "", regex=True).str.strip())
            cap["_apps"] = pd.to_numeric(cap["starts"], errors="coerce").fillna(0)
            cap = cap.sort_values("_apps", ascending=False).drop_duplicates("base")
            for _, c in cap.iterrows():
                base = str(c["base"])
                r = resolve(base)
                nm = r["player"] if r is not None else base
                ln = _key(nm)
                if ln in seen:
                    continue
                seen.add(ln)
                out.append({"name": nm, "photo": _photo(r) if r is not None else "",
                            "ovr": _player_ovr(r) if r is not None else None,
                            "pos": (str(r.get("fl_group") or r.get("pos") or "") if r is not None else str(c.get("fl_pos") or "")),
                            "role": "부주장", "is_main": False})
    return {"team": team, "color": tm.team_color(team), "captains": out[:5]}


@app.get("/api/signals")
def signals(team: str = "", league: str = ACTIVE_LEAGUE, limit: int = 60):
    """agent 자동감지 통합 피드 — 부상·감독·이적·계약 변화를 한 곳에.
    team 지정 시 해당 팀만, 없으면 리그 전체."""
    resolve = _players_lookup(league)
    win = _current_window()
    out = []

    # 리그 소속 팀만 (비-EPL 팀 데이터 혼입 방지)
    st = ds.read_table("standings", league=league)
    valid = set(st["squad"].tolist()) if st is not None else set()

    def tfilter(sq):
        if team:
            return sq == team
        return (not valid) or (sq in valid)

    def add(date, sq, typ, tone, icon, player, title, detail):
        r = resolve(player) if player else None
        out.append({"date": date, "team": sq, "logo": tm.team_logo(sq), "type": typ,
                    "tone": tone, "icon": icon, "player": player or "",
                    "photo": _photo(r) if r is not None else "", "title": title, "detail": detail})

    # 1. 부상 변화 (신규/복귀)
    ic = ds.read_table("transfermarkt_injury_changes", league=league)
    if ic is not None:
        for _, r in ic.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            if str(r.get("event_type")) == "new_injury":
                add(str(r.get("run_date") or ""), sq, "injury_new", "bad", "🚑",
                    str(r.get("player") or ""), "부상 발생", str(r.get("new_injury") or "부상"))
            else:
                add(str(r.get("run_date") or ""), sq, "injury_return", "good", "✅",
                    str(r.get("player") or ""), "부상 복귀", f"{r.get('old_injury') or ''} 회복")

    # 2. 감독 변화
    mc = ds.read_table("manager_changes", league=league)
    if mc is not None:
        for _, r in mc.iterrows():
            sq = str(r.get("team") or "")
            if not tfilter(sq):
                continue
            add(str(r.get("detected_at") or "")[:10], sq, "manager", "info", "🎓", "",
                "감독 변화", f"{r.get('previous_manager')} → {r.get('detected_manager')}")

    # (이적은 Transfer 탭 / Overview 티커 / 예상 XI 진단에서 다룸 — 중복 방지 위해 Signals 제외)

    # 4. 계약 만료 예정 (2년 이내) — 년/개월 표기
    def _fmt_remaining(days: int) -> str:
        m = max(0, round(days / 30.44))
        if m >= 12:
            y, mm = divmod(m, 12)
            return f"{y}년" + (f" {mm}개월" if mm else "") + " 남음"
        return f"{m}개월 남음"

    ct = ds.read_table("transfermarkt_contracts", league=league)
    if ct is not None:
        today = datetime.date.today()
        for _, r in ct.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            cu = str(r.get("contract_until") or "")
            try:
                du = datetime.date.fromisoformat(cu[:10])
            except ValueError:
                continue
            days = (du - today).days
            if 0 <= days <= 365:
                add(cu[:10], sq, "contract", "bad", "📄", str(r.get("player") or ""),
                    "계약 만료 임박", f"{cu[:10]} · {_fmt_remaining(days)}")
            elif 365 < days <= 730:
                add(cu[:10], sq, "resign", "warn", "✍️", str(r.get("player") or ""),
                    "재계약 대상", f"{cu[:10]} · {_fmt_remaining(days)}")

    # 5. 시장가치 급등/급락 (market-value agent 델타)
    mv = ds.read_table("market_value_changes", league=league)
    if mv is not None and not mv.empty:
        for _, r in mv.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            delta = _num(r.get("delta"))
            pct = _num(r.get("pct"))
            up = delta >= 0
            add(str(r.get("run_date") or ""), sq, "value", "good" if up else "bad",
                "📈" if up else "📉", str(r.get("player") or ""),
                "시장가치 " + ("급등" if up else "급락"),
                f"{'+' if up else '-'}€{abs(delta) / 1e6:.1f}M ({pct:+.0f}%)")

    # 6. 프로스펙트 레이더 (나이·시장가치·출전 기반 다층 감지)
    pf = ds.read_table("players_full", league=league)
    if pf is not None:
        yb = pf.copy()
        if "left_for" in yb.columns:
            yb = yb[yb["left_for"].isna() | (yb["left_for"].astype(str).str.strip() == "")]
        yb["_age"] = pd.to_numeric(yb.get("age"), errors="coerce")
        yb["_min"] = pd.to_numeric(yb.get("minutes"), errors="coerce").fillna(0)
        yb["_mv"] = pd.to_numeric(yb.get("market_value_eur"), errors="coerce").fillna(0)
        yb["_r"] = pd.to_numeric(yb.get("ss_rating"), errors="coerce").fillna(0)
        young = yb[(yb["_age"] > 0) & (yb["_age"] <= 21)].sort_values("_mv", ascending=False)
        for _, r in young.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            age, mn, mv, rt = int(r["_age"]), int(r["_min"]), float(r["_mv"]), float(r["_r"])
            name = str(r.get("player") or "")
            mvs = f"€{mv / 1e6:.0f}M" if mv > 0 else "가치 미정"
            if age <= 17 and mn >= 1:
                add("", sq, "youth", "good", "🌟", name, "초유망주 데뷔", f"{age}세 · 1군 {mn}′ 소화 · {mvs}")
            elif mv >= 25_000_000:
                add("", sq, "youth", "good", "💎", name, "고평가 유망주", f"{age}세 · {mvs} · {mn}′")
            elif mn >= 900 and rt >= 6.9:
                add("", sq, "youth", "info", "⭐", name, "유망주 주목", f"{age}세 · {mn}′ · 평점 {round(rt, 2)}")
            elif mn < 600:
                add("", sq, "youth", "warn", "🔁", name, "임대·기회 검토", f"{age}세 · 출전 {mn}′ (부족) · {mvs}")

        # 노장 핵심 — 승계 계획 필요 (32세+)
        vets = yb[(yb["_age"] >= 32) & (yb["_min"] >= 900)].sort_values("_age", ascending=False)
        for _, r in vets.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            add("", sq, "veteran", "warn", "🧓", str(r.get("player") or ""),
                "노장 핵심 · 승계 검토", f"{int(r['_age'])}세 · {int(r['_min'])}′ 주전급")

    # 7. 상관관계 감지 — 부상 잦은 고가 자산 (결장경기 × 시장가치)
    inj_hist = ds.read_table("tm_injury_history", league=league)
    if inj_hist is not None and pf is not None:
        mv_map = {str(r["player"]): _num(r.get("market_value_eur")) for _, r in pf.iterrows()}
        for _, r in inj_hist.iterrows():
            sq = str(r.get("squad") or "")
            if not tfilter(sq):
                continue
            nm = str(r.get("player") or "")
            gm = _num(r.get("games_missed"))
            mv = mv_map.get(nm, 0.0)
            if gm >= 12 and mv >= 40_000_000:
                add("", sq, "risk", "bad", "🩹", nm, "유리몸 주의",
                    f"€{mv / 1e6:.0f}M · 시즌 {int(gm)}경기 결장 (잦은 부상)")

    rank = {"injury_new": 3, "injury_return": 3, "manager": 3, "value": 3, "risk": 3,
            "youth": 2, "veteran": 2, "contract": 1, "resign": 1}

    def _key(s):
        return (rank.get(s["type"], 0), s["date"] if rank.get(s["type"]) == 3 else "")
    out.sort(key=_key, reverse=True)

    counts = {"injury": 0, "manager": 0, "value": 0, "youth": 0, "contract": 0, "resign": 0}
    for s in out:
        if s["type"].startswith("injury"):
            counts["injury"] += 1
        else:
            counts[s["type"]] = counts.get(s["type"], 0) + 1
    return {"team": team, "window": win, "counts": counts, "signals": out[:limit]}


@app.get("/api/home")
def home(league: str = ACTIVE_LEAGUE):
    """리그 홈 대시보드 집계 — 이적 펄스·시그널·감독교체·순위·뉴스 한 번에."""
    win = _current_window()

    # 1) 이적 펄스 (이번 창 · 영구이적만)
    tr = ds.read_table("transfers", league=league)
    top_deals, net = [], []
    spend_total, deals_in = 0.0, 0
    if tr is not None and "squad" in tr.columns:
        tt, _wf = _window_filter(tr.copy(), win)
        tt = tt[~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)].copy()
        tt["_fee"] = tt["fee_eur"].map(lambda v: _num(v, 0.0))
        _in = tt[tt["direction"] == "in"]
        deals_in = int(len(_in))
        spend_total = float(_in["_fee"].sum())
        for _, r in tt[tt["direction"] == "in"].sort_values("_fee", ascending=False).head(8).iterrows():
            sq = str(r.get("squad") or "")
            top_deals.append({
                "player": str(r.get("player") or ""), "to": sq, "to_logo": tm.team_logo(sq),
                "from": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                "fee_eur": _num(r.get("fee_eur"), 0.0), "fee_text": str(r.get("fee_text") or ""),
            })
        for sq, g in tt.groupby("squad"):
            spend = float(g[g["direction"] == "in"]["_fee"].sum())
            income = float(g[g["direction"] == "out"]["_fee"].sum())
            if spend == 0 and income == 0:
                continue
            net.append({"team": str(sq), "logo": tm.team_logo(str(sq)),
                        "spend": spend, "income": income, "net": spend - income})
        net.sort(key=lambda x: -x["spend"])

    # 2) 시그널 (리그 전체) · 3) 감독 교체 · 4) 뉴스 헤드라인
    sig = signals(team="", league=league, limit=24)

    changes = []
    for t, p in _managers().items():
        if p.get("previous_name"):
            changes.append({
                "team": t, "logo": tm.team_logo(t),
                "previous": p.get("previous_name", ""), "current": p.get("name", ""),
                "photo": p.get("photo_url", "") if str(p.get("photo_url") or "").startswith("http") else "",
                "formation": p.get("formation", ""),
                "changed_at": str(p.get("change_detected_at") or "")[:10],
            })
    changes.sort(key=lambda x: x["changed_at"], reverse=True)

    na = ds.read_table("news_articles", league=league)
    news_out, seen = [], set()
    if na is not None:
        nn = na.sort_values("published", ascending=False) if "published" in na.columns else na
        for _, r in nn.iterrows():
            h = str(r.get("headline_ko") or r.get("headline") or "")
            if not h or h in seen:
                continue
            seen.add(h)
            news_out.append({
                "headline": h, "team": str(r.get("team") or ""),
                "source": str(r.get("source") or ""),
                "image": str(r.get("image") or "") if str(r.get("image") or "").startswith("http") else "",
                "link": str(r.get("link") or ""),
            })
            if len(news_out) >= 10:
                break

    # 5) 이적 속보/루머 피드 (Guardian·BBC RSS → 번역·분류)
    bz = ds.read_table("transfer_buzz", league=league)
    buzz = []
    if bz is not None:
        for _, r in bz.head(18).iterrows():
            buzz.append({
                "title": str(r.get("title_ko") or r.get("title_en") or ""),
                "title_en": str(r.get("title_en") or ""),
                "source": str(r.get("source") or ""),
                "tier": str(r.get("tier") or "rumor"),
                "link": str(r.get("link") or ""),
                "published": str(r.get("published") or ""),
            })

    return {
        "season": _data_season_label(), "window": win,
        "kpi": {
            "spend": spend_total, "deals": deals_in,
            "mgr_changes": len(changes), "injuries": int(sig["counts"].get("injury", 0)),
        },
        "buzz": buzz,
        "transfers": {"top_deals": top_deals, "net_spend": net[:8]},
        "signals": sig["signals"], "signal_counts": sig["counts"],
        "manager_changes": changes, "news": news_out,
        "standings": teams(league=league), "roster_next": teams_next(league=league),
    }


_WC_ROUNDS = ["group-stage", "round-of-32", "round-of-16", "quarterfinals",
              "semifinals", "3rd-place-match", "final"]
_WC_ROUND_KR = {"group-stage": "조별리그", "round-of-32": "32강", "round-of-16": "16강",
                "quarterfinals": "8강", "semifinals": "4강", "3rd-place-match": "3·4위전", "final": "결승"}


def _wc_read(table):
    return ds.read_table(table, league=ACTIVE_LEAGUE)


def _wc_epl_index():
    """WC 선수명(norm) → EPL players_full 행. 클럽 교차참조용."""
    from unidecode import unidecode
    def norm(s):
        return unidecode(str(s)).lower().strip()
    pf = ds.read_table("players_full", league=ACTIVE_LEAGUE)
    idx = {}
    if pf is not None:
        for _, r in pf.iterrows():
            idx[norm(r["player"])] = r
    return idx, norm


@app.get("/api/wc")
def world_cup():
    """2026 월드컵 — 경기(라운드별)·조별순위·득점왕 + EPL 클럽 차출 교차참조."""
    m = _wc_read("wc_matches")
    if m is None:
        raise HTTPException(404, "WC 데이터 없음 — src/fetch_wc.py 실행 필요")
    g, sc, sq = _wc_read("wc_groups"), _wc_read("wc_scorers"), _wc_read("wc_squads")

    nation_logo = {}
    for _, r in m.iterrows():
        for nm, lg in ((str(r.get("home")), str(r.get("home_logo"))), (str(r.get("away")), str(r.get("away_logo")))):
            if nm and lg and lg.startswith("http") and nm not in nation_logo:
                nation_logo[nm] = lg

    def _mrow(r):
        return {
            "date": str(r.get("date") or ""), "group": str(r.get("group") or ""),
            "home": str(r.get("home") or ""), "home_abbr": str(r.get("home_abbr") or ""),
            "home_logo": str(r.get("home_logo") or ""), "home_score": _numornone(r.get("home_score")),
            "away": str(r.get("away") or ""), "away_abbr": str(r.get("away_abbr") or ""),
            "away_logo": str(r.get("away_logo") or ""), "away_score": _numornone(r.get("away_score")),
            "status": str(r.get("status") or ""), "completed": bool(r.get("completed")),
        }

    rounds = []
    for slug in _WC_ROUNDS:
        sub = m[m["round"] == slug] if "round" in m.columns else m.iloc[0:0]
        items = [_mrow(r) for _, r in sub.iterrows()]
        if items:
            rounds.append({"round": slug, "label": _WC_ROUND_KR.get(slug, slug), "matches": items})

    groups = {}
    if g is not None:
        for _, r in g.iterrows():
            groups.setdefault(str(r.get("group")), []).append({
                "team": str(r.get("team") or ""), "logo": str(r.get("logo") or ""),
                "P": int(_num(r.get("P"))), "W": int(_num(r.get("W"))), "D": int(_num(r.get("D"))),
                "L": int(_num(r.get("L"))), "GF": int(_num(r.get("GF"))), "GA": int(_num(r.get("GA"))),
                "GD": int(_num(r.get("GD"))), "Pts": int(_num(r.get("Pts"))),
            })
    groups_list = [{"group": k, "table": v} for k, v in sorted(groups.items()) if k]

    idx, norm = _wc_epl_index()
    goalmap = {}
    scorers = []
    if sc is not None:
        for _, r in sc.iterrows():
            goalmap[norm(r.get("player"))] = int(_num(r.get("goals")))
        for _, r in sc.head(20).iterrows():
            scorers.append({
                "player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                "goals": int(_num(r.get("goals"))), "pens": int(_num(r.get("pens"))),
                "logo": nation_logo.get(str(r.get("nation")), ""),
            })

    byclub = {}
    if sq is not None:
        for _, r in sq.iterrows():
            hit = idx.get(norm(r.get("player")))
            if hit is None:
                continue
            club = str(hit["squad"])
            byclub.setdefault(club, []).append({
                "player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                "pos": str(r.get("pos") or ""), "photo": _photo(hit),
                "goals": goalmap.get(norm(r.get("player")), 0),
            })
    epl_clubs = []
    for club, players in byclub.items():
        players.sort(key=lambda x: -x["goals"])
        epl_clubs.append({"club": club, "logo": tm.team_logo(club), "count": len(players), "players": players})
    epl_clubs.sort(key=lambda x: -x["count"])

    nations = []
    if sq is not None:
        seen = {}
        for _, r in sq.iterrows():
            n = str(r.get("nation") or "")
            if n:
                seen[n] = seen.get(n, 0) + 1
        nations = [{"nation": n, "logo": nation_logo.get(n, ""), "count": c} for n, c in sorted(seen.items())]

    return {"matches": rounds, "groups": groups_list, "scorers": scorers,
            "epl_clubs": epl_clubs, "nations": nations}


@app.get("/api/wc/squad/{nation}")
def wc_squad(nation: str):
    """국가대표 스쿼드 (선수 + EPL 소속이면 클럽 표시)."""
    sq = _wc_read("wc_squads")
    if sq is None or "nation" not in sq.columns:
        raise HTTPException(404, "WC 스쿼드 데이터 없음")
    idx, norm = _wc_epl_index()
    rows = sq[sq["nation"].astype(str) == nation]
    if rows.empty:
        raise HTTPException(404, f"'{nation}' 스쿼드 없음")
    players = []
    for _, r in rows.iterrows():
        hit = idx.get(norm(r.get("player")))
        players.append({
            "player": str(r.get("player") or ""), "pos": str(r.get("pos") or ""),
            "jersey": str(r.get("jersey") or ""), "age": str(r.get("age") or ""),
            "epl_club": str(hit["squad"]) if hit is not None else "",
            "club_logo": tm.team_logo(str(hit["squad"])) if hit is not None else "",
            "photo": _photo(hit) if hit is not None else "",
        })
    _order = {"G": 0, "D": 1, "M": 2, "F": 3}
    players.sort(key=lambda p: (_order.get(p["pos"], 9), p["player"]))
    return {"nation": nation, "count": len(players), "players": players}


def _numornone(v):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _pos_line(tm_pos: str) -> str:
    p = str(tm_pos or "").lower()
    if "keeper" in p or p == "gk":
        return "GK"
    if "back" in p or "defen" in p or "centre-back" in p:
        return "DEF"
    if "wing" in p or "forward" in p or "striker" in p or "centre-forward" in p:
        return "FWD"
    if "midfield" in p or p in ("dm", "cm", "am"):
        return "MID"
    return "MID"


@app.get("/api/projection/{team}")
def projection(team: str, league: str = ACTIVE_LEAGUE):
    """다음 시즌(현재 이적창) 예상 XI + 진단.
    25/26 주전 XI 에서 이탈 선수를 빼고 영입/스쿼드로 채운 뒤, 손실·보강 진단을 낸다."""
    season = _placements(team, league)
    if season is None:
        raise HTTPException(404, "lineup data not found")
    win = _current_window()
    resolve = _players_lookup(league)
    next_label = win["label"]

    def _last(nm):
        t = str(nm).split()
        return t[-1].lower() if t else str(nm).lower()

    # 이탈: 이적 OUT(현재창, 임대제외) + left_for
    tr = ds.read_table("transfers", league=league)
    departing = {}   # last-name → {player, club}
    if tr is not None:
        tt, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        tt = tt[(tt["direction"] == "out") & ~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in tt.iterrows():
            departing[_last(r.get("player"))] = {"player": str(r.get("player") or ""), "club": str(r.get("club") or "")}
    full = ds.read_table("players_full", league=league)
    if full is not None and "left_for" in full.columns:
        lf = full[(full["squad"] == team) & full["left_for"].notna() & (full["left_for"].astype(str).str.strip() != "")]
        for _, r in lf.iterrows():
            departing.setdefault(_last(r.get("player")), {"player": str(r["player"]), "club": str(r.get("left_for") or "")})

    # 영입: 이적 IN(현재창, 임대제외)
    signings = []
    if tr is not None:
        ins, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        ins = ins[(ins["direction"] == "in") & ~ins["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in ins.iterrows():
            signings.append({"player": str(r.get("player") or ""), "pos": str(r.get("pos") or ""),
                             "line": _pos_line(r.get("pos")), "fee": str(r.get("fee_text") or ""),
                             "photo": str(r.get("photo") or "") if str(r.get("photo") or "").startswith("http") else "",
                             "used": False})

    # 스쿼드 내부 대체 후보
    squad = _squad_df(team, league)
    squad_pool = []
    if squad is not None:
        sd = squad.copy()
        sd["_ovr"] = sd.apply(_player_ovr, axis=1)
        for _, r in sd.sort_values("_ovr", ascending=False).iterrows():
            squad_pool.append({"player": str(r["player"]), "line": _line_of(r.get("fl_group"), r.get("pos")),
                               "ovr": int(r["_ovr"]), "photo": _photo(r)})

    xi_names = {_last(p["player"]) for p in season["placements"]}

    def _pick_replacement(line):
        # 영입 우선(같은 라인), 없으면 스쿼드 미출전 선수
        for s in signings:
            if not s["used"] and s["line"] == line:
                s["used"] = True
                r = resolve(s["player"])
                return {"player": s["player"], "ovr": _player_ovr(r) if r is not None else None,
                        "photo": s["photo"] or (_photo(r) if r is not None else ""), "src": "signing"}
        for c in squad_pool:
            if c["line"] == line and _last(c["player"]) not in xi_names:
                xi_names.add(_last(c["player"]))
                return {"player": c["player"], "ovr": c["ovr"], "photo": c["photo"], "src": "squad"}
        return {"player": "영입 필요", "ovr": None, "photo": "", "src": "gap"}

    projected, diagnosis = [], []
    for p in season["placements"]:
        key = _last(p["player"])
        if key in departing and p["player"] != "—":
            rep = _pick_replacement(p["kind"])
            projected.append({**p, "player": rep["player"], "ovr": rep["ovr"], "photo": rep["photo"], "changed": True})
            sev = "핵심" if (p.get("ovr") or 0) >= 80 else "로테이션"
            note = (f"{rep['player']} 승격" if rep["src"] == "squad"
                    else (f"영입 {rep['player']}로 대체" if rep["src"] == "signing" else "대체자 영입 필요"))
            diagnosis.append({"kind": "loss", "severity": sev, "player": p["player"], "slot": p["slot"],
                              "line": p["kind"], "to": departing[key]["club"], "replacement": rep["player"],
                              "note": f"{sev} {p['slot']} 이탈 → {note}", "photo": p.get("photo", "")})
        else:
            projected.append({**p, "changed": False})

    # 사용되지 않은 영입 = 보강
    line_top = {}
    for p in season["placements"]:
        k = p["kind"]
        if k not in line_top or (p.get("ovr") or 0) > line_top[k][1]:
            line_top[k] = (p["player"], p.get("ovr") or 0)
    for s in signings:
        if s["used"]:
            continue
        rival = line_top.get(s["line"], ("", 0))[0]
        r = resolve(s["player"])
        diagnosis.append({"kind": "gain", "severity": "보강", "player": s["player"], "slot": s["pos"],
                          "line": s["line"], "fee": s["fee"], "replacement": "",
                          "note": (f"기존 {rival} 경쟁/보강" if rival else f"{s['line']} 보강"),
                          "photo": s["photo"] or (_photo(r) if r is not None else "")})

    diagnosis.sort(key=lambda d: 0 if d["kind"] == "loss" and d["severity"] == "핵심" else (1 if d["kind"] == "loss" else 2))

    return {"team": team, "color": tm.team_color(team),
            "current_label": _data_season_label(), "next_label": next_label,
            "current": season, "projected": {"formation": season["formation"], "placements": projected},
            "diagnosis": diagnosis}


@app.get("/api/health")
def health():
    return {"ok": True, "active_league": ACTIVE_LEAGUE, "leagues": ds.available_leagues()}
