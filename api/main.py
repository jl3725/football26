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
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import datastore as ds  # noqa: E402
import teammeta as tm  # noqa: E402
import ratings as rt  # noqa: E402
import ratings_v3 as rv3  # noqa: E402  (절대 클래스·폼·POT·신뢰도)
import transfer_adjust as ta  # noqa: E402
from leagues import ACTIVE_LEAGUE, league_config, data_path  # noqa: E402
from team_analysis import (  # noqa: E402  (streamlit 비의존)
    espn_assign_slots, slot_xy, slot_kind, formation_slots, display_slot,
)

app = FastAPI(title="Football Scout API", version="0.1.0")
# gzip — 큰 응답(예: database 전리그 766KB) 전송량을 ~5분의 1로 줄여 로딩 단축.
app.add_middleware(GZipMiddleware, minimum_size=1024)
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


def _managers(league: str = "EPL") -> dict:
    """감독 프로필(리그별). LaLiga 등은 manager_profiles_{league}_*.json — 없으면 {} (EPL 감독 오출력 방지)."""
    path = MANAGER_JSON if league == "EPL" else data_path("manager_profiles", league, ext="json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    """다음 시즌(개막 전) 로스터 — 리그별. season_teams JSON(EPL 감지) → 26/27 스케줄 도출 → 현 순위."""
    # 1) 리그별 season_teams JSON (EPL 은 위키 감지본, 승격/강등 플래그 포함)
    path = SEASON_TEAMS_JSON if league == "EPL" else data_path("season_teams", league, ext="json")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("teams"):
            return d
    except (OSError, json.JSONDecodeError):
        pass
    # 2) 26/27 스케줄에서 팀 도출 (LaLiga 등 — 승격 감지본 없을 때)
    try:
        sf = pd.read_csv(data_path("schedule_full", league, "2026_2027"))
        squads = sorted(set(sf["squad"].astype(str)))
        if squads:
            teams = [{"name": s, "color": tm.team_color(s), "logo": tm.team_logo(s), "promoted": False}
                     for s in squads]
            return {"season_label": "26/27", "source_title": "schedule 2026-27", "detected_at": "",
                    "teams": teams, "promoted": [], "relegated": [], "meta_missing": []}
    except (OSError, KeyError, ValueError):
        pass
    # 3) 최종 폴백 — 현 시즌 순위
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
    mgr = _managers(league).get(team)
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
    full_df = _pf(league)
    base = rv3.team_ratings(full_df, team)                       # 이적 전(현재 스쿼드)
    if base:
        adj = rv3.team_ratings(ta.build_adjusted_full(full_df, tr, win), team) or base  # 이번 창 반영
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

    # 이번 창 이탈 선수(이적 OUT·임대종료 + left_for) — 핵심선수/떠난선수 일관 처리
    deps = _departures(team, league, win)

    # 핵심 선수 — 절대 OVR(실력) 상위 5. 이탈 선수 제외.
    # ss_rating(경기당 폼)은 소표본 유스·저출전 수비수를 과대평가(예: Militão 1139분이 벨링엄 상회)
    # 하므로 OVR 로 정렬하고 ss_rating 은 동점 처리·표시용으로만 쓴다.
    stars = []
    squad_ratings = []
    if full_df is not None:
        usage_idx = _comp_usage(league)
        sq = full_df[full_df["squad"] == team].copy()
        if "left_for" in sq.columns:
            sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]
        if deps:
            sq = sq[~sq["player"].map(_dep_last).isin(deps.keys())]
        sq["_r"] = pd.to_numeric(sq.get("ss_rating"), errors="coerce").fillna(0)
        sq["_ovr"] = sq.apply(_player_ovr, axis=1)
        # 소표본 유스 인플레 방지 — 출전시간 확보 선수만(부족하면 완화)
        sq_star = sq[pd.to_numeric(sq.get("minutes"), errors="coerce").fillna(0) >= 450]
        if len(sq_star) < 5:
            sq_star = sq
        for _, r in sq_star.sort_values(["_ovr", "_r"], ascending=False).head(5).iterrows():
            prof = _comp_profile(r, usage_idx)
            stars.append({
                "player": r["player"], "pos": str(r.get("fl_group") or r.get("pos") or ""),
                "ovr": _player_ovr(r), "pot": _player_pot(r), "form": _player_form(r),
                "rating": round(_num(r.get("_r")), 2),
                "goals": int(_num(r.get("goals"))), "assists": int(_num(r.get("assists"))),
                "photo": _photo(r), "role": prof["role"], "big_match": prof["big_match"],
            })
        # 절대 OVR/POT 분포·산점도용 (45분+ 출전)
        for _, r in sq.iterrows():
            mn = int(_num(r.get("minutes")))
            if mn < 45:
                continue
            p_ovr = _player_ovr(r)  # 팀 ovr dict 과 이름 충돌 금지
            squad_ratings.append({
                "player": r["player"], "ovr": p_ovr, "pot": _player_pot(r), "form": _player_form(r),
                "age": int(_num(r.get("age"))), "minutes": mn,
                "line": rv3.line_of_row(r),
            })
        squad_ratings.sort(key=lambda x: -x["ovr"])

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

    # 시즌 중 이적으로 팀을 떠난 선수 (이적 OUT·임대종료 + left_for 통합)
    departed = []
    resolve_dep = _players_lookup(league)
    for v in deps.values():
        r = resolve_dep(v["player"])
        departed.append({"player": v["player"], "left_for": v["club"],
                         "pos": v["pos"] or (str(r.get("fl_group") or r.get("pos") or "") if r is not None else ""),
                         "photo": _photo(r) if r is not None else ""})

    # 강점/약점 (지수 상·하위 라벨)
    edge = {"strengths": [], "weaknesses": []}
    if um is not None:
        scored = []
        for col, label, _line in _FACTOR_DEFS:
            try:
                val = int(um[col]) if pd.notna(um.get(col)) else None
            except (TypeError, ValueError):
                val = None
            if val is not None and val > 0:   # 0 = 소스 데이터 미수집(예: SerieA 압박지표) → 제외
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
        "squad_ratings": squad_ratings,
        "leaders": leaders,
        "departed": departed,
        "injuries": injuries,
        "transfers": {"in": tin, "out": tout},
        "window": win,
        "data_season": _data_season_label(),
    }


@app.get("/api/identity/{team}")
def identity(team: str, league: str = ACTIVE_LEAGUE):
    """팀 정체성 — 감독 전술(현재 스냅샷 + 장기성향 블렌드·재임) · 영입 성향 · 예산(프록시).

    CSV만 사용(Qdrant/Neo4j 불필요)하므로 배포 환경에서도 동작. 실패 시 부분 null 반환.
    """
    import manager_tactics as mt  # noqa: PLC0415 (지연 import — 이 엔드포인트만 CSV 로더 사용)
    import club_profile as cp     # noqa: PLC0415

    tactics = None
    try:
        p = mt.tactical_profile(team)
    except Exception:  # noqa: BLE001
        p = None
    if p:
        ten = p.get("tenure") or {}
        v = p.get("tactical_vector") or {}
        tactics = {
            "manager": p.get("manager"), "formation": p.get("formation"),
            "current_tags": p.get("style_tags") or [],
            "tendency_tags": p.get("descriptor_tags") or [],
            "vector": {k: v.get(k) for k in
                       ("pressing", "control", "creativity", "attack_output", "aerial", "disruption")
                       if v.get(k) is not None},
            "role_usage": [{"role": r["role"], "share": r["minutes_share"]}
                           for r in (p.get("role_usage") or [])[:5]],
            "tenure": {"appointed": ten.get("appointed"), "months": ten.get("months"),
                       "is_new": ten.get("is_new"), "w_current": ten.get("w_current"),
                       "w_tendency": ten.get("w_tendency")},
        }

    recruitment = budget = None
    try:
        dna = cp.recruitment_dna(team)
    except Exception:  # noqa: BLE001
        dna = None
    if dna:
        recruitment = {k: dna.get(k) for k in
                       ("age_profile", "spend_profile", "profile", "avg_age", "u21_ratio",
                        "u23_ratio", "prime_ratio", "veteran_ratio", "n_signings", "avg_fee_eur")}
    try:
        aff = cp.affordability(team)
    except Exception:  # noqa: BLE001
        aff = None
    if aff:
        budget = {k: aff.get(k) for k in
                  ("spend_tier", "squad_value_eur", "net_spend_eur", "gross_spend_eur",
                   "max_fee_paid_eur", "price_ceiling_eur", "value_pct")}

    return {"team": team, "league": league, "tactics": tactics,
            "recruitment": recruitment, "budget": budget}


@app.get("/api/fit")
def fit(candidate: str, club: str, role: str, source_league: str = "",
        league: str = ACTIVE_LEAGUE):
    """Transfer Fit Evaluator — (후보, 대상클럽, 역할) → Fit Score + 전 컴포넌트 분해.

    로컬 전용: Qdrant(스타일 벡터)·Neo4j(선례) 필요. 스택 미가동 시 available=False 로
    우아하게 degrade(프론트가 안내 표시). 온디맨드(버튼)로만 호출되는 무거운 계산.
    """
    try:
        import transfer_fit as tf  # noqa: PLC0415 (지연 import — 이 엔드포인트만 벡터스택 사용)
        tf._qdrant().get_collections()  # 가용성 프로브
    except Exception as e:  # noqa: BLE001
        return {"available": False, "candidate": candidate, "club": club, "role": role,
                "reason": f"로컬 벡터/그래프 스택 미가동 (Qdrant): {str(e)[:80]}"}
    try:
        r = tf.evaluate_fit(candidate, club, role, source_league or None)
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": str(e)[:140],
                "candidate": candidate, "club": club, "role": role}
    r["available"] = True
    return r


@app.get("/api/managersim")
def managersim(club: str, manager: str, league: str = ACTIVE_LEAGUE):
    """Manager Change Simulator — 새 감독 부임 시 전술변화·스쿼드 미스핏·영입 우선순위.

    manager 는 감독명(현 클럽 전술로 대체) 또는 클럽명. 로컬 전용(Qdrant/Neo4j).
    """
    try:
        import transfer_fit as tf  # noqa: PLC0415
        tf._qdrant().get_collections()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "club": club, "manager": manager,
                "reason": f"로컬 벡터/그래프 스택 미가동 (Qdrant): {str(e)[:80]}"}
    try:
        import manager_sim as ms  # noqa: PLC0415
        r = ms.simulate(club, manager)
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": str(e)[:140], "club": club, "manager": manager}
    if "error" in r:
        return {"available": True, "error": r["error"], "club": club, "manager": manager}
    cur, new = r["current"], r["new"]
    axes = ["pressing", "control", "creativity", "attack_output", "aerial", "disruption"]
    changes = []
    for ax in axes:
        a, b = cur["tactical_vector"].get(ax), new["tactical_vector"].get(ax)
        if a is not None and b is not None:
            changes.append({"axis": ax, "from": round(a), "to": round(b), "delta": round(b - a)})
    return {
        "available": True, "target_club": r["target_club"], "new_manager": r["new_manager"],
        "new_from_club": r["new_from_club"],
        "current": {"manager": cur["manager"], "formation": cur["formation"], "style_tags": cur["style_tags"]},
        "new": {"manager": new["manager"], "formation": new["formation"], "style_tags": new["style_tags"]},
        "vector_changes": changes, "squad_misfit": r["squad_misfit"], "priorities": r["priorities"],
    }


@app.get("/api/scout")
def scout(q: str, team: str = "", league: str = ACTIVE_LEAGUE,
          x_scout_token: str = Header(default="")):
    """Ask Scout — 자연어 질문 → OpenAI 툴 라우팅 → 결정적 엔진 실행 → 답변 + 카드용 결과.

    LLM은 라우팅·요약만, 판단은 엔진. OPENAI_API_KEY 없으면 available=False.
    SCOUT_TOKEN 설정 시 X-Scout-Token 헤더 일치 필요(공개 배포 시 OpenAI 크레딧 보호).
    """
    need = os.getenv("SCOUT_TOKEN")
    if need and x_scout_token != need:
        return {"available": False, "auth_required": True,
                "reason": "Ask Scout 접근 토큰이 필요합니다 (비밀번호 입력)"}
    import scout_agent as sa  # noqa: PLC0415 (지연 import — OpenAI 의존)
    return sa.answer(q, team or None, league)


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


_XPHOTO_CACHE: dict = {}


def _xtra_photo(league: str) -> dict:
    """players_full 에 없는 선수(임대/방출/신규) 사진 폴백 맵 — TM 이적·계약·부상 소스 통합."""
    if league in _XPHOTO_CACHE:
        return _XPHOTO_CACHE[league]
    from unidecode import unidecode
    m: dict[str, str] = {}
    for tbl, pcol in (("transfers", "photo"), ("transfermarkt_contracts", "tm_photo"),
                      ("transfermarkt_injuries", "tm_photo")):
        t = ds.read_table(tbl, league=league)
        if t is not None and pcol in t.columns and "player" in t.columns:
            for _, r in t.iterrows():
                ph = str(r.get(pcol) or "")
                if ph.startswith("http"):
                    m.setdefault(unidecode(str(r.get("player"))).lower().strip(), ph)
    _XPHOTO_CACHE[league] = m
    return m


def _resolve_photo(name, resolve, league: str) -> str:
    """이름 → 사진 URL. players_full(resolve) 우선, 없으면 TM 폴백 맵(정확 이름 키)."""
    if not name:
        return ""
    from unidecode import unidecode
    r = resolve(name)
    ph = _photo(r) if r is not None else ""
    return ph or _xtra_photo(league).get(unidecode(str(name)).lower().strip(), "")




def _pf(league: str):
    """players_full 로드 + 대회별 선발수 컬럼 머지(빅매치 가산점·역할용) — 단일 진입점.

    comp usage 있는 리그(EPL·LaLiga…)만 머지. 없으면 컬럼 없음 → absolute_ovr 가 0 처리.
    """
    df = ds.read_table("players_full", league=league)
    if df is not None:
        # norm_key 비었으면(예: LaLiga — 컬럼은 있으나 전부 null) player 로 생성 → 조인 정합
        from unidecode import unidecode
        df = df.copy()
        if "norm_key" not in df.columns:
            df["norm_key"] = None
        _m = df["norm_key"].isna() | (df["norm_key"].astype(str).str.strip().isin(["", "nan", "None"]))
        if _m.any():
            df.loc[_m, "norm_key"] = df.loc[_m, "player"].map(lambda x: unidecode(str(x)).lower().strip())
        try:
            u = pd.read_csv(data_path("player_comp_usage", league),
                            usecols=["squad", "norm_key", "ucl_starts", "uel_starts", "conf_starts", "cup_starts"])
            df = df.merge(u, on=["squad", "norm_key"], how="left")
        except (OSError, KeyError, ValueError):
            pass
    return df


def _lineups(league: str):
    """espn_lineups(리그) + 컵·유럽 라인업 concat — 스케줄/경기상세용. 리그별 파일."""
    base = ds.read_table("espn_lineups", league=league)
    try:
        cup = pd.read_csv(data_path("espn_lineups_cups", league))
    except (OSError, ValueError):
        cup = None
    if base is None:
        return cup
    if cup is None:
        return base
    return pd.concat([base, cup], ignore_index=True)


def _subs(league: str):
    """espn_subs(리그) + 컵·유럽 교체 concat."""
    base = ds.read_table("espn_subs", league=league)
    try:
        cup = pd.read_csv(data_path("espn_subs_cups", league))
    except (OSError, ValueError):
        cup = None
    if base is None:
        return cup
    if cup is None:
        return base
    return pd.concat([base, cup], ignore_index=True)


def _player_ovr(row) -> int:
    # v3 절대 OVR = 커리어 클래스 (시장가+포지션 공정보정+검증/베테랑, GK 는 선방%/CS%, 빅매치 소량 가산)
    return rv3.absolute_ovr(
        value=row.get("market_value_eur"), ss_rating=row.get("ss_rating"),
        minutes=row.get("minutes"), age=row.get("age"),
        pos_group=str(row.get("fl_group") or row.get("pos") or ""),
        gk_save_pct=row.get("gk_save_pct"), gk_cs_pct=row.get("gk_cs_pct"),
        ucl_starts=row.get("ucl_starts"), uel_starts=row.get("uel_starts"),
        conf_starts=row.get("conf_starts"), cup_starts=row.get("cup_starts"),
    )


def _player_form(row):
    return rv3.form_rating(
        ss_rating=row.get("ss_rating"), minutes=row.get("minutes"),
        goals=row.get("goals"), assists=row.get("assists"),
        pos_group=str(row.get("fl_group") or row.get("pos") or ""),
    )


def _player_pot(row) -> int:
    return rv3.potential(absolute=_player_ovr(row), age=row.get("age"),
                         value=row.get("market_value_eur"))


# ── 대회별 사용량 (역할 축 · EPL Phase 1) ─────────────────────────────
# 리그 minutes = 능력치, 대회별 선발/출전 = '실제 역할'. 컵 스탯을 OVR 에 섞지 않는다.
_COMP_USAGE_CACHE: dict = {}


def _comp_usage(league: str):
    """player_comp_usage → {'exact':{(squad,norm_key):row}, 'last':{(squad,성):row}}.
    리그별(EPL·LaLiga…). 파일 없으면 None → 역할은 리그 출전만으로 폴백."""
    if league in _COMP_USAGE_CACHE:
        return _COMP_USAGE_CACHE[league]
    idx = None
    try:
        df = pd.read_csv(data_path("player_comp_usage", league))
        exact, last = {}, {}
        for _, r in df.iterrows():
            d = r.to_dict()
            sq, nk = str(r["squad"]), str(r["norm_key"])
            exact[(sq, nk)] = d
            toks = nk.split()
            if toks:
                last.setdefault((sq, toks[-1]), d)  # 성 폴백(Andy↔Andrew 등)
        idx = {"exact": exact, "last": last}
    except (OSError, KeyError, ValueError):
        idx = None
    _COMP_USAGE_CACHE[league] = idx
    return idx


def _usage_for(idx, squad, norm_key):
    if not idx:
        return None
    row = idx["exact"].get((str(squad), str(norm_key)))
    if row is None:
        toks = str(norm_key).split()
        if toks:
            row = idx["last"].get((str(squad), toks[-1]))
    return row


_COMP_LABELS = [("ucl", "챔피언스리그"), ("uel", "유로파리그"), ("conf", "컨퍼런스리그"),
                ("facup", "FA컵"), ("lcup", "리그컵"), ("copa", "코파델레이")]


def _comp_profile(row, usage_idx) -> dict:
    """players_full 행 + comp usage → 역할 + 대회별 상세(선발/출전).

    role/big_match 는 리그분 + 유럽/컵 사용량 기반. comps 는 출전>0 대회만.
    comp usage 없으면(라리가 등) comps=[], 역할은 리그분만으로 폴백.
    """
    u = _usage_for(usage_idx, row.get("squad"), row.get("norm_key")) or {}
    es, ea = _num(u.get("euro_starts")), _num(u.get("euro_apps"))
    cs, ca = _num(u.get("cup_starts")), _num(u.get("cup_apps"))
    lm = _num(row.get("minutes"))
    role = rv3.role_tag(league_min=lm, euro_starts=es, euro_apps=ea,
                        cup_starts=cs, cup_apps=ca, age=row.get("age"))
    comps = []
    for key, label in _COMP_LABELS:
        st, ap = int(_num(u.get(f"{key}_starts"))), int(_num(u.get(f"{key}_apps")))
        if ap > 0:
            comps.append({"key": key, "label": label, "starts": st, "apps": ap})
    parts = [f"리그 {int(lm)}′"] + [f"{c['label']} {c['starts']}선발" for c in comps if c["starts"]]
    return {"role": role, "role_evidence": " · ".join(parts),
            "big_match": rv3.big_match_proven(euro_starts=es, euro_apps=ea),
            "league_min": int(lm), "comps": comps}


def _role_for(row, usage_idx) -> dict:
    """{role, role_evidence, big_match} — recommend 카드용 서브셋(단일 소스)."""
    p = _comp_profile(row, usage_idx)
    return {"role": p["role"], "role_evidence": p["role_evidence"], "big_match": p["big_match"]}


def _squad_df(team: str, league: str):
    full = _pf(league)
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
    lines: dict[str, list] = {"GK": [], "DEF": [], "MID": [], "ATT": []}
    for _, r in df.iterrows():
        line = rv3.line_of_row(r)
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


def _avail_schedule_seasons(league: str) -> list[str]:
    """schedule_full_*.csv 존재하는 시즌(최신 우선) — 리그별."""
    out = []
    for s in ("2026_2027", "2025_2026"):
        if data_path("schedule_full", league, s).exists():
            out.append(s)
    return out


@app.get("/api/schedule/{team}")
def schedule(team: str, league: str = ACTIVE_LEAGUE, season: str = ""):
    """대회 통합 스케줄 — 리그+컵+유럽. season 미지정 시 최신(26/27) 기본.
    치러진 경기는 라인업 event_id 로 포메이션 링크."""
    seasons = _avail_schedule_seasons(league)
    if not seasons:  # 레거시 폴백(schedule_full 없는 리그)
        sch = ds.read_table("schedule", league=league)
        if sch is None:
            raise HTTPException(404, "schedule not found")
        ts = sch[sch["squad"] == team].copy()
        if "gw" in ts.columns:
            ts = ts.sort_values("gw")
        out = [{"comp": "리그", "date": str(r.get("date") or ""),
                "home_away": str(r.get("home_away") or ""),
                "opponent": str(r.get("opponent") or ""),
                "opp_logo": tm.team_logo(str(r.get("opponent") or "")),
                "gf": None if pd.isna(r.get("gf")) else int(_num(r.get("gf"))),
                "ga": None if pd.isna(r.get("ga")) else int(_num(r.get("ga"))),
                "score": str(r.get("score") or ""), "result": str(r.get("result") or ""),
                "status": "completed" if str(r.get("score") or "") else "scheduled",
                "event_id": None, "formation": None, "has_lineup": False}
               for _, r in ts.iterrows()]
        return {"team": team, "color": tm.team_color(team), "season": "", "seasons": [], "matches": out}

    sea = season if season in seasons else seasons[0]
    sch = pd.read_csv(data_path("schedule_full", league, sea))
    ts = sch[sch["squad"] == team].copy().sort_values("date")

    # 라인업(리그+컵·유럽) event_id → formation
    el = _lineups(league)
    ev_formation: dict[str, str] = {}
    if el is not None:
        te = el[el["squad"] == team]
        for eid, g in te.groupby("event_id"):
            ev_formation[str(eid)] = str(g["formation"].iloc[0])

    out = []
    for _, r in ts.iterrows():
        eid = str(r.get("event_id") or "")
        formation = ev_formation.get(eid)
        out.append({
            "comp": str(r.get("comp") or ""),
            "date": str(r.get("date") or ""),
            "home_away": str(r.get("home_away") or ""),
            "opponent": str(r.get("opponent") or ""),
            "opp_logo": tm.team_logo(str(r.get("opponent") or "")),
            "gf": None if pd.isna(r.get("gf")) else int(_num(r.get("gf"))),
            "ga": None if pd.isna(r.get("ga")) else int(_num(r.get("ga"))),
            "score": str(r.get("score") or ""),
            "result": str(r.get("result") or ""),
            "status": str(r.get("status") or ""),
            "event_id": eid or None,
            "formation": formation,
            "has_lineup": formation is not None,
        })
    return {"team": team, "color": tm.team_color(team), "season": sea,
            "seasons": seasons, "matches": out}


@app.get("/api/match/{team}/{event_id}")
def match(team: str, event_id: str, league: str = ACTIVE_LEAGUE):
    el = _lineups(league)
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

    # 교체 타임라인 (리그+컵·유럽)
    subs_tbl = _subs(league)
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
    usage_idx = _comp_usage(league)
    out = []
    for _, r in df.iterrows():
        prof = _comp_profile(r, usage_idx)
        out.append({
            "player": r["player"],
            "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "line": rv3.line_of_row(r),
            "age": int(_num(r.get("age"))),
            "nationality": str(r.get("nationality") or ""),
            "value_eur": _num(r.get("market_value_eur")),
            "ovr": int(r["_ovr"]),
            "photo": _photo(r),
            "role": prof["role"], "big_match": prof["big_match"], "comps": prof["comps"],
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
    full = _pf(league)
    if full is None:
        raise HTTPException(404, "players not found")
    hit = full[(full["squad"] == team) & (full["player"] == player)]
    if hit.empty:
        hit = full[full["player"] == player]
    if hit.empty:
        raise HTTPException(404, f"player '{player}' not found")
    row = hit.iloc[0]
    is_gk = rv3.line_of_row(row) == "GK"

    pool = full.copy()
    min_min = 300 if is_gk else 450
    pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= min_min]
    if is_gk:
        pool = pool[pool.apply(lambda r: rv3.line_of_row(r) == "GK", axis=1)]

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
        "line": rv3.line_of_row(row),
        "age": int(_num(row.get("age"))), "nationality": str(row.get("nationality") or ""),
        "value_eur": _num(row.get("market_value_eur")), "photo": _photo(row),
        "ovr": _player_ovr(row), "ss_rating": _num(row.get("ss_rating")),
        "minutes": int(_num(row.get("minutes"))), "goals": int(_num(row.get("goals"))),
        "assists": int(_num(row.get("assists"))),
        "contract_until": str(row.get("tm_contract_until") or ""),
        "is_gk": is_gk, "categories": categories, "radar": radar, "badges": badges,
        "comp_usage": _comp_profile(row, _comp_usage(league)),
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
    full = _pf(league)
    resolve = _players_lookup(league)
    line_map = {}
    if full is not None:
        for _, r in full[full["squad"] == team].iterrows():
            line_map[str(r["player"])] = rv3.line_of_row(r)
    injuries, line_missed = [], {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0}
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
                             "days_out": int(_num(r.get("days_out"))), "injury": latest, "line": line,
                             "photo": _resolve_photo(str(r["player"]), resolve, league)})
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
            # 코어 OVR은 v2 절대모델로 통일(Overview 와 일치). form 은 v1(성적 기반), set_piece 는 지수.
            _t2 = rv3.team_ratings(full, team) or {}
            ovr = {"overall": _t2.get("overall", v.get("종합 지수", 60)), "form": v.get("시즌 폼", 60),
                   "attack": _t2.get("attack", v.get("공격 지수", 60)), "midfield": _t2.get("midfield", v.get("미드필드 지수", 60)),
                   "defense": _t2.get("defense", v.get("수비 지수", 60)), "set_piece": _u("set_piece_attack_index")}
            radar = [{"axis": ax, "value": _u(col)} for ax, col in [
                ("ATT OUT", "attack_output_index"), ("CREATE", "attack_creation_index"),
                ("CONTROL", "midfield_control_index"), ("PRESS", "pressing_index"),
                ("DEF OUT", "defense_output_index"), ("SET PC", "set_piece_attack_index"),
            ] if _u(col) > 0]   # 0 = 소스 미수집(SerieA 압박 등) → 축 제외

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
        "manager_evo": _manager_evo(team, league),
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
        if val is not None and val > 0:   # 0 = 소스 미수집 지표 → 강점/약점에서 제외
            scored.append((label, line, val))
    scored.sort(key=lambda x: -x[2])

    def _contrib(line):
        if full is None:
            return []
        sq = full[full["squad"] == team].copy()
        # _FACTOR_DEFS 는 'FWD', line_of_row 는 'ATT' → 정규화 후 비교(공격 팩터에 선수 누락 방지)
        sq = sq[sq.apply(lambda r: _canon_line(rv3.line_of_row(r)) == _canon_line(line), axis=1)]
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
        ph = str(r.get("photo") or "")
        if not ph.startswith("http") and pf is not None:
            ph = str(pf.get("tm_photo") or "")
        out.append({
            "player": name, "fee_text": str(r.get("fee_text") or ""),
            "fee_eur": _num(r.get("fee_eur")), "pos": str(r.get("pos") or ""),
            "minutes": mins, "goals": goals, "assists": assists,
            "verdict": verdict, "tone": tone,
            "photo": ph if ph.startswith("http") else "",
        })
    out.sort(key=lambda x: -x["fee_eur"])
    return out[:8]


def _manager_evo(team: str, league: str = "EPL"):
    """감독 전술 진화 — 현재 vs 이전(감독 교체 시)."""
    mp = _managers(league).get(team)
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

    full = _pf(league)
    exact, byfull, last = {}, {}, {}
    last_names: dict[str, set] = {}
    if full is not None:
        # 중복 행(이적으로 떠난 옛 소속 행 + 새 소속 행) 대비:
        # '미이적(현 소속) · 사진 보유 · 고출전' 순으로 정렬 후 setdefault(먼저 = 최선)로 채운다.
        f = full.copy()
        if "left_for" in f.columns:
            f["_dep"] = f["left_for"].notna() & (f["left_for"].astype(str).str.strip() != "")
        else:
            f["_dep"] = False
        f["_pic"] = f.get("tm_photo", pd.Series("", index=f.index)).astype(str).str.startswith("http")
        f["_mn"] = pd.to_numeric(f.get("minutes"), errors="coerce").fillna(0)
        f = f.sort_values(["_dep", "_pic", "_mn"], ascending=[True, False, False])
        for _, r in f.iterrows():
            nm = str(r["player"])
            exact.setdefault(nm, r)
            n = norm(nm)
            byfull.setdefault(n, r)
            toks = n.split()
            if toks:
                last.setdefault(toks[-1], r)
                last_names.setdefault(toks[-1], set()).add(n)
    # 동명(성 중복)은 폴백에서 제외 — 오매칭 방지
    ambiguous = {k for k, v in last_names.items() if len(v) > 1}

    def resolve(name):
        # first-name 폴백은 엉뚱한 동명이인(예: Emegha→다른 Emmanuel)을 물어 제거.
        # 성(last) 폴백만, 그것도 동명이인 아닐 때만 사용.
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
        ln = toks[-1]
        return last.get(ln) if ln not in ambiguous else None

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


# 세부 포지션 버킷 (좌우·라인 구분) — 포메이션 내 특정 약점 포지션 추천용
_BUCKET_LABEL = {"GK": "골키퍼", "CB": "센터백", "LB": "왼쪽 풀백", "RB": "오른쪽 풀백",
                 "DM": "수비형MF", "CM": "중앙MF", "AM": "공격형MF",
                 "LW": "왼쪽 윙어", "RW": "오른쪽 윙어", "ST": "스트라이커"}
_BUCKET_BY_LINE = {"ATT": ["ST", "LW", "RW"], "MID": ["DM", "CM", "AM"],
                   "DEF": ["CB", "LB", "RB"], "GK": ["GK"]}
_STARTER_ROLES = {"핵심 주전", "주전·유럽 로테이션", "리그 주전"}


def _pos_bucket(row) -> str:
    """세부 포지션 버킷. tm_position(역할) 우선 — fl_group(포메이션 슬롯)은 좌우 판별 보조.
    예: Elliot Anderson fl_group=LW 지만 tm_position='Central Midfield' → CM."""
    t = str(row.get("tm_position") or "").lower()
    g = str(row.get("fl_group") or "").upper()
    # 1) tm_position(역할)이 명확하면 그걸로
    if t:
        if "keeper" in t:
            return "GK"
        if "back" in t:
            if "left" in t:
                return "LB"
            if "right" in t:
                return "RB"
            return "CB" if ("centre" in t or "center" in t) else "RB"
        if "defensive mid" in t:
            return "DM"
        if "attacking mid" in t:
            return "AM"
        if "midfield" in t:            # central/left/right midfield → CM
            return "CM"
        if "wing" in t or "winger" in t:
            return "LW" if "left" in t else ("RW" if "right" in t else ("RW" if g == "RW" else "LW"))
        if "striker" in t or "forward" in t:
            return "ST"
    # 2) fl_group 폴백
    if g == "GK":
        return "GK"
    if g == "CB":
        return "CB"
    if g in ("LB", "LWB"):
        return "LB"
    if g in ("RB", "RWB"):
        return "RB"
    if g in ("FB", "WB"):
        return "RB"
    if g == "DM":
        return "DM"
    if g == "AM":
        return "AM"
    if g == "LW":
        return "LW"
    if g == "RW":
        return "RW"
    if g == "W":
        return "LW"
    if g in ("ST", "CF", "FW"):
        return "ST"
    return "CM"


_CLUB_STR_CACHE: dict = {}


def _club_strength(league: str) -> dict:
    """{클럽: 팀 종합 OVR} — 영입 현실성(클럽 티어) 판단용. 캐시."""
    if league in _CLUB_STR_CACHE:
        return _CLUB_STR_CACHE[league]
    full = _pf(league)
    m: dict[str, float] = {}
    if full is not None:
        for c in full["squad"].dropna().unique():
            tr = rv3.team_ratings(full, str(c))
            m[str(c)] = tr["overall"] if tr else 75
    _CLUB_STR_CACHE[league] = m
    return m


def _attainable(cand_ovr: int, club_ovr: float, team_ovr: float, role: str, minutes) -> tuple[bool, str]:
    """현실적 영입 가능성 + 사유 — 하드 티어컷이 아니라 '가용성(밀리는 선수)'을 반영.

    핵심: 강팀이라도 '밀리는(비주전·출전감소)' 선수는 이적 가능. 진짜 주전만 동급까지로 제한.
    - 비주전/저출전 → reach 넓음(상위팀에서도 데려올 여지)
    - 확실한 주전 → 동급 클럽까지만 (홀란드 같은 상위팀 핵심은 제외)
    - 우리 수준 대비 월등한 선수(약팀이 초고평가) → 비현실
    """
    mn = _num(minutes)
    starter = role in _STARTER_ROLES and mn >= 1200      # 밀리는 주전(<1200′)은 주전 취급 안 함
    gap = club_ovr - team_ovr                            # +면 후보 클럽이 더 강함
    reach = 1.5 if starter else 5.0
    if gap > reach:
        return False, ("상위팀 주전(비현실)" if starter else "격상위팀(비현실)")
    if cand_ovr >= team_ovr + 7:                          # 우리 최고 수준보다 월등 → 비현실
        return False, "팀 수준 대비 월등(비현실)"
    if gap <= -3:
        return True, "약체 클럽 → 영입 현실적"
    if not starter and gap > 1.5:
        return True, "상위팀 비주전 → 이적 여지"
    if not starter:
        return True, "비주전 → 이적 가능"
    return True, "동급 클럽 주전"


# 리그 레벨(교차 이적 projection용). EPL 기준 100.
# UEFA 협회계수(data/uefa_association_coefficients)로 근거화 — 없으면 폴백값.
# 리그 키 → UEFA 협회계수 국가명. (신규 리그는 GPT 가 쓰는 키에 맞춤: LigaPortugal·Eredivisie)
_LEAGUE_COUNTRY = {"EPL": "England", "LaLiga": "Spain", "SerieA": "Italy",
                   "Bundesliga": "Germany", "Ligue1": "France",
                   "LigaPortugal": "Portugal", "Eredivisie": "Netherlands"}
_LEAGUE_LEVEL_FALLBACK = {"EPL": 100.0, "LaLiga": 98.0, "SerieA": 96.0,
                          "Bundesliga": 96.0, "Ligue1": 93.0}


def _build_league_level() -> dict:
    """UEFA 협회계수 → 압축 리그레벨. 최상위(잉글랜드)=100, 기울기 0.2로 압축
    (선수 품질 차이는 유럽성적 계수 비율보다 작음 → 과도한 감점 방지), 하한 82.
    계수 데이터 없으면 폴백값 유지. 신규 리그(포르투갈·네덜란드)도 자동 배치."""
    out = dict(_LEAGUE_LEVEL_FALLBACK)
    try:
        df = ds.read_table("uefa_association_coefficients")
        if df is None or df.empty:
            return out
        coeff = {str(r["country"]): float(r["coefficient"]) for _, r in df.iterrows()}
        top = max(coeff.values())
        for lg, country in _LEAGUE_COUNTRY.items():
            c = coeff.get(country)
            if c is not None:
                out[lg] = round(max(82.0, 100.0 - 0.2 * (top - c)), 1)
    except Exception:  # noqa: BLE001
        pass
    return out


_LEAGUE_LEVEL = _build_league_level()


def _project_ovr(base: int, source: str, target: str, big_match: bool, age, bucket: str) -> tuple[int, str, str]:
    """타 리그 → 우리 리그 이적 시 예상 OVR + (검증근거, 적응리스크 노트).

    기본 OVR(그 리그 실력)은 그대로 두고, '오면 얼마나 통할까'만 보정:
      - 리그 계수(더 센 리그로 갈수록 감점, 약한 리그로 가도 인플레 없음)
      - 유럽(UCL/UEL) 검증 → 완화   - 나이·포지션 적응 리스크(공격수 템포↑, 수비/GK 이식 잘됨)
    """
    if source == target:
        return base, "", ""
    lvl_s, lvl_t = _LEAGUE_LEVEL.get(source, 96.0), _LEAGUE_LEVEL.get(target, 100.0)
    adj = base * (min(1.0, lvl_s / lvl_t) - 1.0)      # ≤0
    euro = 1.5 if big_match else 0.0
    risk, notes = 0.0, []
    if _num(age) >= 30:
        risk += 1.0; notes.append("노쇠 적응")
    if bucket in ("LW", "RW", "ST", "AM"):
        risk += 1.0; notes.append("템포·피지컬 적응")
    elif bucket in ("CB", "DM", "GK"):
        risk -= 0.5                                    # 수비·전술은 이식 잘 됨
    proj = int(round(base + adj + euro - risk))
    proof = "빅매치(유럽) 검증" if big_match else ""
    return proj, proof, (" · ".join(notes))


def _incoming_ovr(name: str, target_league: str):
    """우리 리그 players_full 에 없는 영입(타 리그에서 온 선수)의 예상 OVR + 사진.
    타 리그 players_full 에서 찾아 base OVR → 리그계수 projection(교차리그). 없으면 (None, '')."""
    from unidecode import unidecode
    nk = unidecode(str(name)).lower().strip()
    ln = nk.split()[-1] if nk.split() else nk
    for src in _LEAGUE_LEVEL:
        if src == target_league:
            continue
        pf = _pf(src)
        if pf is None or "player" not in pf.columns:
            continue
        norm = pf["player"].map(lambda x: unidecode(str(x)).lower().strip())
        cand = pf[norm == nk]
        if cand.empty:                                      # 성(last name)만 매칭 — 유일할 때만
            cand = pf[norm.map(lambda s: s.split()[-1] if s.split() else "") == ln]
            if len(cand) != 1:
                continue
        r = (cand.sort_values("minutes", ascending=False).iloc[0]
             if "minutes" in cand.columns else cand.iloc[0])
        base = _player_ovr(r)
        if not base:
            continue
        proj, _proof, _risk = _project_ovr(base, src, target_league, False, r.get("age"), _pos_bucket(r))
        return proj, (_photo(r) or "")
    return None, ""


_TOUT_CACHE: dict = {}


def _transferred_out(league: str) -> dict:
    """이번 창 '방출(out, 임대 제외)' → {(출발클럽, norm_key): 목적지클럽}. players_full left_for 미동기 보완.

    (source, name) 키로 두어 '리그 내 이적으로 새 클럽에 이미 도착한 선수'(예: João Pedro Brighton→Chelsea)를
    새 클럽에서 떠난 것으로 오판하지 않는다. Gordon(Newcastle 리스트인데 Barcelona행)만 이탈로 잡힘."""
    if league in _TOUT_CACHE:
        return _TOUT_CACHE[league]
    from unidecode import unidecode
    m: dict[tuple, str] = {}
    tr = ds.read_table("transfers", league=league)
    if tr is not None and "direction" in tr.columns:
        out = tr[tr["direction"] == "out"].copy()
        if "fee_text" in out.columns:
            out = out[~out["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in out.iterrows():
            dest = str(r.get("club") or "").strip()
            if not dest or dest.lower() in ("without club", "retired", "career break", "unknown", "-"):
                continue  # 자유계약/은퇴 등 모호한 목적지는 이탈로 안 봄(스크랩 아티팩트 방지)
            key = (str(r.get("squad") or ""), unidecode(str(r.get("player"))).lower().strip())
            m[key] = dest
    _TOUT_CACHE[league] = m
    return m


_LINE_OF_BUCKET = {"GK": "GK", "CB": "DEF", "LB": "DEF", "RB": "DEF",
                   "DM": "MID", "CM": "MID", "AM": "MID", "LW": "ATT", "RW": "ATT", "ST": "ATT"}
_ALL_BUCKETS = ["GK", "CB", "LB", "RB", "DM", "CM", "AM", "LW", "RW", "ST"]
_FIT_BY_LINE = {"ATT": ("npxg_p90", "득점 위협"), "MID": ("key_passes_per90", "찬스 창출"),
                "DEF": ("tackles_won_per90_ss", "수비 기여"), "GK": ("", "안정감")}
_SRC_LABEL = {"EPL": "EPL", "LaLiga": "라리가", "SerieA": "세리에A",
              "Bundesliga": "분데스리가", "Ligue1": "리그1",
              "LigaPortugal": "포르투갈 리그"}


def _formation_bucket_needs(team: str, league: str) -> dict:
    """팀 베스트 XI(현 포메이션)에서 세부 포지션별 필요 인원. 예 4-3-3 → CB 2·LW 1…"""
    pl = _placements(team, league)
    if not pl:
        return {}
    resolve = _players_lookup(league)
    cnt: dict[str, int] = {}
    for p in pl["placements"]:
        r = resolve(p.get("player"))
        bk = _pos_bucket(r) if r is not None else _fine_bucket(p.get("slot"))
        if bk == "W":                       # _fine_bucket 은 윙어를 W로 → 슬롯 좌우로 분리
            s = str(p.get("slot") or "").upper()
            bk = "RW" if s.startswith("R") else "LW"
        if bk in _LINE_OF_BUCKET:
            cnt[bk] = cnt.get(bk, 0) + 1
    return cnt


@app.get("/api/recommend/{team}")
def recommend(team: str, league: str = ACTIVE_LEAGUE):
    """보강 후보 — 포메이션 전 포지션에서 '얇은 세부 포지션(CB/RB/DM…)' 을 가려내고,
    각 포지션마다 팀 티어에 맞는 현실적 후보를 **전 리그(교차리그 projection)** 에서 추천."""
    full = _pf(league)
    if full is None:
        return {"team": team, "weakest": None, "recommendations": [], "lost_targets": [], "addressed": False}

    nd = _compute_needs(team, league)
    trr = rv3.team_ratings(full, team) or {}
    team_ovr = trr.get("overall", 78)
    signed_lines = {s["line"] for s in nd["window"]["signings"]}

    # 1) 포메이션 요구 인원 + 스쿼드 세부 포지션 뎁스 → 라인 무관 '얇은 포지션' 선정
    sq = _squad_df(team, league)
    need_cnt = _formation_bucket_needs(team, league) or \
        {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "DM": 1, "CM": 2, "LW": 1, "RW": 1, "ST": 1}
    depth: dict[str, int] = {}
    if sq is not None:
        for bk in _ALL_BUCKETS:
            ovrs = [_player_ovr(p) for _, p in sq.iterrows() if _pos_bucket(p) == bk]
            depth[bk] = sum(1 for o in ovrs if o >= team_ovr - 5)   # 스쿼드급 옵션 수
    used = [b for b in _ALL_BUCKETS if need_cnt.get(b, 0) > 0]
    # 얇은 정도 = 스쿼드급옵션 − (필요+1). 낮을수록(음수) 시급. 라인 무관 최대 5곳.
    ranked = sorted(used, key=lambda b: depth.get(b, 0) - (need_cnt.get(b, 0) + 1))
    weak_buckets = [b for b in ranked if depth.get(b, 0) < need_cnt.get(b, 0) + 1][:5] or ranked[:2]
    addressed = bool({_LINE_OF_BUCKET[b] for b in weak_buckets} & signed_lines)

    tout = _transferred_out(league)

    def _pct_in(s, v):
        sv = s.dropna()
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0
        if pd.isna(v) or sv.empty:
            return 0
        return int(round((sv < v).mean() * 100))

    def _prep(df):
        df = df.copy()
        df["_mn"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
        df["_bucket"] = df.apply(_pos_bucket, axis=1)
        df["_ovr"] = df.apply(_player_ovr, axis=1)
        df["_left"] = (df["left_for"].notna() & (df["left_for"].astype(str).str.strip() != "")) \
            if "left_for" in df.columns else False
        return df

    # 2) 후보 풀 — 같은 리그 + 데이터 있는 모든 타 리그(EPL·LaLiga·SerieA·…)
    pool = _prep(full[full["squad"] != team])
    pool["_left"] = pool["_left"] | pool.apply(
        lambda r: (str(r.get("squad") or ""), str(r.get("norm_key"))) in tout, axis=1)
    src_meta = {league: {"pool": pool, "usage": _comp_usage(league),
                         "club": _club_strength(league), "resolve": _players_lookup(league)}}
    for olg in ds.available_leagues():
        if olg == league:
            continue
        ox = _pf(olg)
        if ox is None or "player" not in ox.columns:
            continue
        src_meta[olg] = {"pool": _prep(ox), "usage": _comp_usage(olg),
                         "club": _club_strength(olg), "resolve": _players_lookup(olg)}

    _dist_cache: dict = {}

    def _dist(src, bk, col):
        key = (src, bk, col)
        if key not in _dist_cache:
            p = src_meta[src]["pool"]
            sub = p[p["_bucket"] == bk]
            _dist_cache[key] = (pd.to_numeric(sub.get(col), errors="coerce")
                                if col and col in sub.columns else pd.Series(dtype=float))
        return _dist_cache[key]

    def _rphoto(r, src):
        return _photo(r) or _resolve_photo(r["player"], src_meta[src]["resolve"], src)

    def _dest(r):
        lf = str(r.get("left_for") or "").strip()
        return lf if lf else tout.get((str(r.get("squad") or ""), str(r.get("norm_key"))), "")

    def _score(r, src, bk):
        role = _role_for(r, src_meta[src]["usage"])
        base = int(r["_ovr"])
        if src == league:
            proj, proof, risk = base, "", ""
        else:
            proj, proof, risk = _project_ovr(base, src, league, role["big_match"], r.get("age"), bk)
        cstr = src_meta[src]["club"].get(str(r.get("squad") or ""), 78)
        ok, why = _attainable(proj, cstr, team_ovr, role["role"], r.get("minutes"))
        return role, base, proj, proof, risk, ok, why

    # 3) 얇은 포지션마다 전 리그 후보 스코어 → 현실적(picked) + 롱샷
    per = max(2, -(-9 // len(weak_buckets)))
    picked, longshots, seen_long = [], [], set()
    for bk in weak_buckets:
        line = _LINE_OF_BUCKET.get(bk, "MID")
        fit_col, fit_label = _FIT_BY_LINE.get(line, ("", ""))
        cand = []
        for src, meta in src_meta.items():
            p = meta["pool"]
            sub = p[(p["_bucket"] == bk) & (~p["_left"]) & (p["_mn"] >= 600)] \
                .sort_values("_ovr", ascending=False).head(25 if src == league else 15)
            cand += [(r, src) for _, r in sub.iterrows()]
        scored = []
        for r, src in cand:
            role, base, proj, proof, risk, ok, why = _score(r, src, bk)
            fit = _pct_in(_dist(src, bk, fit_col), r.get(fit_col)) if fit_col else 0
            match = _pct_in(_dist(src, bk, "ss_rating"), r.get("ss_rating"))
            scored.append((r, src, role, base, proj, proof, risk, ok, why, fit, match, fit_label, bk))
        scored.sort(key=lambda x: -x[4])
        n = 0
        for t in scored:
            r, src, proj, ok, pl_name = t[0], t[1], t[4], t[7], t[0]["player"]
            if ok and n < per:
                picked.append(t); n += 1
            elif (not ok) and proj >= team_ovr and pl_name not in seen_long and len(longshots) < 4:
                seen_long.add(pl_name); longshots.append(t)
    picked.sort(key=lambda x: -x[4])
    longshots.sort(key=lambda x: -x[4])

    recs = []
    for t in picked[:9]:
        r, src, role, base, proj, proof, risk_note, ok, attain_why, fit, match, fit_label, bk = t
        age, mn = int(_num(r.get("age"))), int(_num(r.get("minutes")))
        val = _num(r.get("market_value_eur")); rating = round(_num(r.get("ss_rating")), 2)
        cross_lg = src != league
        srclabel = _SRC_LABEL.get(src, src)
        why_fit, why_risk = [f"영입 현실성: {attain_why}"], []
        if cross_lg:
            why_fit.append(f"{srclabel} OVR {base} → 예상 {proj}")
        if fit >= 65:
            why_fit.append(f"{fit_label} {srclabel} 상위 {max(1, 100 - fit)}%")
        if match >= 65:
            why_fit.append(f"평점 {rating} 상위권")
        if 23 <= age <= 28:
            why_fit.append(f"{age}세 피크")
        if role["big_match"]:
            why_fit.append("빅매치(유럽) 검증")
        if cross_lg and risk_note:
            why_risk.append(f"적응: {risk_note}")
        if age >= 31:
            why_risk.append(f"{age}세 노쇠 구간")
        if mn < 1000:
            why_risk.append(f"출전 {mn}′ 표본 부족")
        if role["role"] in ("컵 전용", "백업", "주변 자원"):
            why_risk.append(f"역할: {role['role']}")
        conf = "high" if mn >= 1500 else ("med" if mn >= 700 else "low")
        recs.append({
            "player": r["player"], "squad": str(r.get("squad") or ""),
            "logo": tm.team_logo(str(r.get("squad") or "")),
            "pos": str(r.get("fl_group") or r.get("pos") or ""), "age": age,
            "ovr": proj, "current_ovr": base, "projected_ovr": proj,
            "cross_league": cross_lg, "source_league": srclabel, "value_eur": val,
            "photo": _rphoto(r, src), "rating": rating,
            "tactical_fit": fit, "squad_match": match,
            "bucket": bk, "bucket_label": _BUCKET_LABEL.get(bk, bk),
            "role": role["role"], "role_evidence": role["role_evidence"],
            "big_match": role["big_match"],
            "why_fit": why_fit, "why_risk": why_risk, "confidence": conf,
        })

    longshots_out = []
    for t in longshots[:4]:
        r, src, role, base, proj, bk = t[0], t[1], t[2], t[3], t[4], t[12]
        longshots_out.append({
            "player": r["player"], "squad": str(r.get("squad") or ""),
            "logo": tm.team_logo(str(r.get("squad") or "")),
            "ovr": proj, "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "photo": _rphoto(r, src),
            "role": role["role"], "bucket_label": _BUCKET_LABEL.get(bk, bk),
            "cross_league": src != league, "source_league": _SRC_LABEL.get(src, src),
            "current_ovr": base, "reason": t[8],
        })

    # Lost Target Review — 약점 포지션 선수 중 이번 창 이적(완료). 최고가치 1명 별표.
    lost_out = []
    resolve = src_meta[league]["resolve"]
    usage_idx = src_meta[league]["usage"]
    lost = pool[pool["_bucket"].isin(weak_buckets) & pool["_left"]].sort_values("_ovr", ascending=False)
    for i, (_, r) in enumerate(lost.head(4).iterrows()):
        lost_out.append({
            "player": r["player"], "from": str(r.get("squad") or ""),
            "to": _dest(r) or "타팀", "ovr": int(r["_ovr"]),
            "pos": str(r.get("fl_group") or r.get("pos") or ""),
            "photo": _resolve_photo(r["player"], resolve, league),
            "role": _role_for(r, usage_idx)["role"],
            "top_loss": i == 0,
        })

    weak_labels = [_BUCKET_LABEL.get(b, b) for b in weak_buckets]
    top_line = _LINE_OF_BUCKET.get(weak_buckets[0], "MID") if weak_buckets else "MID"
    return {"team": team, "color": tm.team_color(team),
            "weakest": {"line": top_line, "label": " · ".join(weak_labels),
                        "fit_label": _FIT_BY_LINE.get(top_line, ("", ""))[1],
                        "bucket": weak_buckets[0] if weak_buckets else "",
                        "bucket_label": " · ".join(weak_labels), "buckets": weak_labels},
            "addressed": addressed, "recommendations": recs,
            "longshots": longshots_out, "lost_targets": lost_out}


_NEED_LINES = {
    "GK": {"label": "골키퍼", "expect": 2},
    "DEF": {"label": "수비", "expect": 7},
    "MID": {"label": "미드필드", "expect": 5},
    "ATT": {"label": "공격", "expect": 5},
}


def _pos_to_line(pos) -> str:
    p = str(pos or "").lower()
    if "keeper" in p or p.strip() == "gk":
        return "GK"
    if "back" in p or "defen" in p or p in ("cb", "fb", "rb", "lb", "df"):
        return "DEF"
    if "wing" in p or "forward" in p or "striker" in p or p in ("st", "w", "rw", "lw", "fw"):
        return "ATT"
    return "MID"


def _compute_needs(team: str, league: str) -> dict:
    """스카우트 데스크 니즈 산출 (단일 소스). /api/needs 와 /api/recommend 가 공유.

    현실(스쿼드·부상·이적)에서 니즈를 뽑고, 각 니즈가 이번 창 영입으로 보강됐는지/
    방출로 악화됐는지 상태를 붙인다. AI는 '사라'가 아니라 '지금 상황 판단'.
    """
    full = _pf(league)
    if full is None:
        raise HTTPException(404, "players not found")
    sq = full[full["squad"] == team].copy()
    if "left_for" in sq.columns:
        sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]

    byline: dict = {k: [] for k in _NEED_LINES}
    for _, r in sq.iterrows():
        ln = rv3.line_of_row(r)
        byline[ln].append({"ovr": _player_ovr(r), "age": int(_num(r.get("age"))),
                           "min": int(_num(r.get("minutes")))})

    win = _current_window()
    tr = ds.read_table("transfers", league=league)
    ins_line, outs_line, signings, departures = {}, {}, [], []
    if tr is not None and "squad" in tr.columns:
        tt, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        tt = tt[~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in tt.iterrows():
            ln = _pos_to_line(r.get("pos"))
            nm = str(r.get("player") or "")
            if str(r.get("direction")) == "in":
                ins_line.setdefault(ln, []).append(nm)
                signings.append({"player": nm, "line": ln, "pos": str(r.get("pos") or ""), "fee": str(r.get("fee_text") or "")})
            elif str(r.get("direction")) == "out":
                outs_line.setdefault(ln, []).append(nm)
                departures.append({"player": nm, "line": ln, "pos": str(r.get("pos") or "")})

    inj = ds.read_table("transfermarkt_injuries", league=league)
    inj_line: dict = {}
    if inj is not None and "squad" in inj.columns:
        ti = inj[inj["squad"].astype(str) == team]
        if "active" in ti.columns:
            ti = ti[ti["active"].astype(str).str.lower().isin({"true", "1", "yes", "y"})]
        for _, r in ti.iterrows():
            ln = _pos_to_line(r.get("position"))
            inj_line[ln] = inj_line.get(ln, 0) + 1

    out_needs = []
    for ln, cfg in _NEED_LINES.items():
        players = byline[ln]
        quality = [p for p in players if p["ovr"] >= 80]  # v3 절대 스케일
        core = sorted(players, key=lambda x: -x["min"])[:3]
        ages = [p["age"] for p in core if p["age"] > 0]
        avg_age = sum(ages) / len(ages) if ages else 0
        young_q = any(p["age"] and p["age"] <= 22 and p["ovr"] >= 78 for p in players)
        n_inj = inj_line.get(ln, 0)
        sigs, lefts = ins_line.get(ln, []), outs_line.get(ln, [])

        found = []
        gap = cfg["expect"] - len(quality)
        if gap >= 1:
            found.append(("depth", "질·뎁스 부족", "high" if gap >= 2 else "med",
                          f"{cfg['label']} 준척(OVR 80+) {len(quality)}명 · 권장 {cfg['expect']}"))
        if core and avg_age >= 30 and not young_q:
            found.append(("aging", "노쇠·승계 필요", "med",
                          f"{cfg['label']} 주축 평균 {avg_age:.0f}세 · 젊은 대체자 부족"))
        if n_inj >= 2 or (n_inj >= 1 and len(quality) <= cfg["expect"] - 1):
            found.append(("injury", "부상 공백", "high" if n_inj >= 2 else "med",
                          f"{cfg['label']} 현재 부상 {n_inj}명"))

        for kind, title, sev, reason in found:
            status, rel = "open", None
            if sigs:
                status, rel = "addressed", sigs[0]
            elif lefts:
                status, rel = "worsened", lefts[0]
            out_needs.append({"line": ln, "line_label": cfg["label"], "kind": kind,
                              "title": title, "severity": sev, "reason": reason,
                              "status": status, "player": rel})

    _sev = {"high": 0, "med": 1, "low": 2}
    out_needs.sort(key=lambda n: (0 if n["status"] == "open" else 1, _sev.get(n["severity"], 3)))

    mode = "evaluate" if signings else ("gap" if departures else "recruit")
    return {"team": team, "color": tm.team_color(team), "mode": mode,
            "window": {"is_open": win["is_open"], "label": win["label"], "kr": win.get("kr"),
                       "signings": signings, "departures": departures},
            "needs": out_needs}


@app.get("/api/needs/{team}")
def needs(team: str, league: str = ACTIVE_LEAGUE):
    return _compute_needs(team, league)


_DB_CACHE: dict = {"key": None, "body": None}


def _db_mtime() -> float:
    """football.db 수정시각 — 캐시 무효화 키(재빌드되면 자동 갱신)."""
    try:
        return os.path.getmtime(ds.DB_PATH)
    except OSError:
        return 0.0


@app.get("/api/database")
def database(league: str = ACTIVE_LEAGUE):
    """전 리그 선수 DB — 데이터 있는 모든 리그(EPL·LaLiga·…)를 합쳐 반환.
    클라이언트에서 필터링(이름/포지션/나이/가치/국적/리그). 확장성: 리그 추가되면 자동 포함.
    2000+명 OVR·프로필 계산 + 직렬화가 무거워 DB 수정시각 기준으로 '직렬화된 바이트'를 캐시
    (FastAPI 기본 jsonable_encoder 재직렬화를 우회 → 캐시히트 시 즉시 응답). 재빌드 시 자동 무효화."""
    key = _db_mtime()
    if _DB_CACHE["body"] is not None and _DB_CACHE["key"] == key:
        return Response(content=_DB_CACHE["body"], media_type="application/json")
    out, nats, leagues = [], set(), []
    for lg in ds.available_leagues():
        full = _pf(lg)
        if full is None or "player" not in full.columns:
            continue
        df = full.copy()
        if "left_for" in df.columns:
            df = df[df["left_for"].isna() | (df["left_for"].astype(str).str.strip() == "")]
        df["_ovr"] = df.apply(_player_ovr, axis=1)
        usage_idx = _comp_usage(lg)
        n0 = len(out)
        for _, r in df.iterrows():
            prof = _comp_profile(r, usage_idx)
            nat = str(r.get("nationality") or "")
            if nat:
                nats.add(nat)
            out.append({
                "player": r["player"], "squad": str(r.get("squad") or ""), "league": lg,
                "logo": tm.team_logo(str(r.get("squad") or "")),
                "pos": str(r.get("fl_group") or r.get("pos") or ""),
                "line": rv3.line_of_row(r),
                "age": int(_num(r.get("age"))), "nationality": nat,
                "value_eur": _num(r.get("market_value_eur")), "ovr": int(r["_ovr"]),
                "photo": _photo(r),
                "role": prof["role"], "big_match": prof["big_match"],
            })
        if len(out) > n0:
            leagues.append(lg)
    out.sort(key=lambda p: -p["ovr"])
    if not out:
        raise HTTPException(404, "players not found")
    result = {"league": "ALL", "players": out, "nationalities": sorted(nats), "leagues": leagues}
    body = json.dumps(result, ensure_ascii=False).encode("utf-8")   # 빠른 직렬화(jsonable_encoder 우회)
    _DB_CACHE.update(key=key, body=body)
    return Response(content=body, media_type="application/json")


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

    # 사진: 소스 사진(명시) → TM 소스맵(정확 이름 키·부상/계약/이적) → players_full resolve.
    # resolve 는 성(last-name) 폴백이 있어 동명이인 오매칭 위험 → TM 소스맵을 먼저 써 오류 방지.
    from unidecode import unidecode
    _xp = _xtra_photo(league)

    def _nk(x):
        return unidecode(str(x or "")).lower().strip()

    def add(date, sq, typ, tone, icon, player, title, detail, photo=""):
        ph = photo or _xp.get(_nk(player), "") or _resolve_photo(player, resolve, league)
        out.append({"date": date, "team": sq, "logo": tm.team_logo(sq), "type": typ,
                    "tone": tone, "icon": icon, "player": player or "",
                    "photo": ph if str(ph).startswith("http") else "",
                    "title": title, "detail": detail})

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
            _cph = str(r.get("tm_photo") or "")   # 계약 레코드 본인 사진(가장 정확)
            if 0 <= days <= 365:
                add(cu[:10], sq, "contract", "bad", "📄", str(r.get("player") or ""),
                    "계약 만료 임박", f"{cu[:10]} · {_fmt_remaining(days)}", photo=_cph)
            elif 365 < days <= 730:
                add(cu[:10], sq, "resign", "warn", "✍️", str(r.get("player") or ""),
                    "재계약 대상", f"{cu[:10]} · {_fmt_remaining(days)}", photo=_cph)

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
    pf = _pf(league)
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
            ph = str(r.get("photo") or "")
            top_deals.append({
                "player": str(r.get("player") or ""), "to": sq, "to_logo": tm.team_logo(sq),
                "from": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                "fee_eur": _num(r.get("fee_eur"), 0.0), "fee_text": str(r.get("fee_text") or ""),
                "photo": ph if ph.startswith("http") else "",
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

    mgrs = _managers(league)
    changes = []
    for t, p in mgrs.items():
        if p.get("previous_name"):
            changes.append({
                "team": t, "logo": tm.team_logo(t),
                "previous": p.get("previous_name", ""), "current": p.get("name", ""),
                "photo": p.get("photo_url", "") if str(p.get("photo_url") or "").startswith("http") else "",
                "previous_photo": p.get("previous_photo", "") if str(p.get("previous_photo") or "").startswith("http") else "",
                "formation": p.get("formation", ""),
                "changed_at": str(p.get("change_detected_at") or "")[:10],
            })
    # 프로필에 previous_name 이 없는 리그(LaLiga·SerieA)는 manager_changes 테이블로 폴백
    if not changes:
        mc = ds.read_table("manager_changes", league=league)
        if mc is not None and "team" in mc.columns:
            for _, r in mc.iterrows():
                t = str(r.get("team") or "")
                prof = mgrs.get(t, {})
                ph = str(prof.get("photo_url") or "")
                changes.append({
                    "team": t, "logo": tm.team_logo(t),
                    "previous": str(r.get("previous_manager") or ""),
                    "current": str(r.get("detected_manager") or ""),
                    "photo": ph if ph.startswith("http") else "",
                    "previous_photo": "",
                    "formation": str(prof.get("formation") or ""),
                    "changed_at": str(r.get("detected_at") or "")[:10],
                })
    changes.sort(key=lambda x: x["changed_at"], reverse=True)

    na = ds.read_table("news_articles", league=league)
    news_out, seen = [], set()
    if na is not None:
        # news_articles 는 전 리그 통합 테이블 → 이 리그 소속 팀 기사만 (EPL/LaLiga 혼입 방지)
        _stn = ds.read_table("standings", league=league)
        lg_teams = set(_stn["squad"].astype(str)) if _stn is not None and "squad" in _stn.columns else set()
        if lg_teams and "team" in na.columns:
            na = na[na["team"].astype(str).isin(lg_teams)]
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


_HUB_LEAGUES = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal")   # 통합 대시보드 대상 — UI 지원 리그
_HUB_CACHE: dict = {"key": None, "body": None}


_HUB_FILE = ds.DB_PATH.parent / "home_all.json"


def _compute_hub_body() -> bytes:
    """전 리그 통합 대시보드 페이로드 계산 — 전 리그 집계라 무겁다(Render 무료티어 1워커를
    수십초 점유 → 헬스체크 실패·재시작). 배포 시 scripts/precompute_hub.py 로 미리
    data/home_all.json 에 생성해 두고, 런타임엔 그 파일을 서빙한다(_hub_body)."""
    from unidecode import unidecode
    win = _current_window()
    today = datetime.date.today()
    avail = set(ds.available_leagues())
    leagues = [lg for lg in _HUB_LEAGUES if lg in avail]

    def _lname(lg):
        try:
            return league_config(lg).name
        except KeyError:
            return lg

    deals, buzz, changes, snaps = [], [], [], []
    form_c, goal_c, contract_c, injuries = [], [], [], []
    for lg in leagues:
        lname = _lname(lg)
        tr = ds.read_table("transfers", league=lg)
        if tr is not None and "squad" in tr.columns:
            tt, _wf = _window_filter(tr.copy(), win)
            tt = tt[(tt["direction"] == "in")
                    & ~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)].copy()
            tt["_fee"] = tt["fee_eur"].map(lambda v: _num(v, 0.0))
            for _, r in tt.sort_values("_fee", ascending=False).head(6).iterrows():
                sq, ph = str(r.get("squad") or ""), str(r.get("photo") or "")
                deals.append({"player": str(r.get("player") or ""), "to": sq, "to_logo": tm.team_logo(sq),
                              "from": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                              "fee_eur": _num(r.get("fee_eur"), 0.0), "fee_text": str(r.get("fee_text") or ""),
                              "photo": ph if ph.startswith("http") else "", "league": lg, "league_name": lname})
        bz = ds.read_table("transfer_buzz", league=lg)
        if bz is not None:
            for _, r in bz.head(10).iterrows():
                buzz.append({"title": str(r.get("title_ko") or r.get("title_en") or ""),
                             "source": str(r.get("source") or ""), "tier": str(r.get("tier") or "rumor"),
                             "link": str(r.get("link") or ""), "published": str(r.get("published") or ""),
                             "league": lg, "league_name": lname})
        mc = ds.read_table("manager_changes", league=lg)
        mgrs = _managers(lg)
        if mc is not None and "team" in mc.columns:
            for _, r in mc.iterrows():
                t = str(r.get("team") or "")
                prof = mgrs.get(t, {})
                ph = str(prof.get("photo_url") or "")
                changes.append({"team": t, "logo": tm.team_logo(t),
                                "previous": str(r.get("previous_manager") or ""),
                                "current": str(r.get("detected_manager") or ""),
                                "photo": ph if ph.startswith("http") else "",
                                "changed_at": str(r.get("detected_at") or "")[:10],
                                "league": lg, "league_name": lname})
        st = ds.read_table("standings", league=lg)
        table = []
        if st is not None and "rank" in st.columns:
            for _, r in st.sort_values("rank").head(4).iterrows():
                sq = str(r.get("squad") or "")
                table.append({"rank": int(_num(r.get("rank"))), "team": sq,
                              "logo": tm.team_logo(sq), "points": int(_num(r.get("points")))})
        snaps.append({"league": lg, "league_name": lname,
                      "color": tm.team_color(table[0]["team"]) if table else "#888", "table": table})

        # players_full → 최고 폼 · 득점 리더 · 곧 FA (정렬은 벡터화, OVR 은 최종 노출분만)
        pf = _pf(lg)
        if pf is not None and "player" in pf.columns:
            p = pf.copy()
            if "left_for" in p.columns:
                p = p[p["left_for"].isna() | (p["left_for"].astype(str).str.strip() == "")]
            p["_mn"] = pd.to_numeric(p.get("minutes"), errors="coerce").fillna(0)
            p["_ss"] = pd.to_numeric(p.get("ss_rating"), errors="coerce").fillna(0)
            p["_g"] = pd.to_numeric(p.get("goals"), errors="coerce").fillna(0)
            for _, r in p[p["_mn"] >= 900].sort_values("_ss", ascending=False).head(6).iterrows():
                form_c.append((r, lg))
            for _, r in p.sort_values("_g", ascending=False).head(6).iterrows():
                goal_c.append((r, lg))
            if "tm_contract_until" in p.columns:
                cu = pd.to_datetime(p["tm_contract_until"], errors="coerce")
                dd = (cu - pd.Timestamp(today)).dt.days
                exp = p[(dd >= 0) & (dd <= 400)].copy()
                exp["_mv"] = pd.to_numeric(exp.get("market_value_eur"), errors="coerce").fillna(0)
                for _, r in exp.sort_values("_mv", ascending=False).head(6).iterrows():
                    contract_c.append((r, lg))

        # 부상 속보 (신규/복귀)
        ic = ds.read_table("transfermarkt_injury_changes", league=lg)
        if ic is not None and "player" in ic.columns:
            xp = _xtra_photo(lg)
            _sub = ic.sort_values("run_date", ascending=False) if "run_date" in ic.columns else ic
            n = 0
            for _, r in _sub.iterrows():
                if n >= 6:
                    break
                pl = str(r.get("player") or "")
                new = str(r.get("event_type")) == "new_injury"
                ph = xp.get(unidecode(pl).lower().strip(), "")
                injuries.append({"player": pl, "club": str(r.get("squad") or ""),
                                 "club_logo": tm.team_logo(str(r.get("squad") or "")),
                                 "event": "new" if new else "return",
                                 "injury": str(r.get("new_injury") or r.get("old_injury") or "부상"),
                                 "date": str(r.get("run_date") or "")[:10],
                                 "photo": ph if ph.startswith("http") else "",
                                 "league": lg, "league_name": lname})
                n += 1

    def _interleave(items, limit):
        """리그별 라운드로빈 — 한 리그가 최신순 정렬에 밀려 빠지지 않게 고루 노출."""
        groups: dict[str, list] = {}
        for it in items:
            groups.setdefault(it["league"], []).append(it)
        out, i = [], 0
        while len(out) < limit and any(i < len(g) for g in groups.values()):
            for g in groups.values():
                if i < len(g):
                    out.append(g[i])
                if len(out) >= limit:
                    break
            i += 1
        return out

    deals.sort(key=lambda d: -d["fee_eur"])       # 빅딜은 이적료 순(리그 무관 최대)
    buzz.sort(key=lambda b: b["published"], reverse=True)   # 리그별 최신순 → 인터리브
    changes.sort(key=lambda c: c["changed_at"], reverse=True)

    form_c.sort(key=lambda t: -t[0]["_ss"])
    hot_form = [{"player": r["player"], "club": str(r.get("squad") or ""),
                 "club_logo": tm.team_logo(str(r.get("squad") or "")),
                 "rating": round(_num(r.get("ss_rating")), 2), "ovr": _player_ovr(r),
                 "pos": str(r.get("fl_group") or r.get("pos") or ""), "photo": _photo(r),
                 "league": lg, "league_name": _lname(lg)} for r, lg in form_c[:10]]
    goal_c.sort(key=lambda t: (-_num(t[0].get("goals")), -_num(t[0].get("assists"))))
    goal_leaders = [{"player": r["player"], "club": str(r.get("squad") or ""),
                     "club_logo": tm.team_logo(str(r.get("squad") or "")),
                     "goals": int(_num(r.get("goals"))), "assists": int(_num(r.get("assists"))),
                     "photo": _photo(r), "league": lg, "league_name": _lname(lg)} for r, lg in goal_c[:10]]
    contract_c.sort(key=lambda t: -_num(t[0].get("market_value_eur")))
    contracts_out = [{"player": r["player"], "club": str(r.get("squad") or ""),
                      "club_logo": tm.team_logo(str(r.get("squad") or "")),
                      "until": str(r.get("tm_contract_until") or "")[:10],
                      "value_eur": _num(r.get("market_value_eur")), "ovr": _player_ovr(r),
                      "photo": _photo(r), "league": lg, "league_name": _lname(lg)} for r, lg in contract_c[:10]]

    result = {"window": win, "leagues": [{"key": lg, "name": _lname(lg)} for lg in leagues],
              "top_deals": deals[:12], "buzz": _interleave(buzz, 18),
              "manager_changes": _interleave(changes, 12), "snapshots": snaps,
              "injuries": _interleave(injuries, 12), "hot_form": hot_form,
              "goal_leaders": goal_leaders, "contracts": contracts_out}
    return json.dumps(result, ensure_ascii=False).encode("utf-8")


def _hub_body() -> bytes:
    """메모리(DB-mtime) 캐시 → 디스크 프리컴퓨트(배포본) → 즉석 계산 순."""
    key = _db_mtime()
    if _HUB_CACHE["body"] is not None and _HUB_CACHE["key"] == key:
        return _HUB_CACHE["body"]
    try:
        if _HUB_FILE.exists() and os.path.getmtime(_HUB_FILE) >= key:
            body = _HUB_FILE.read_bytes()
            _HUB_CACHE.update(key=key, body=body)
            return body
    except OSError:
        pass
    body = _compute_hub_body()                    # 폴백: 즉석 계산(느림 — 배포 precompute 실패시만)
    _HUB_CACHE.update(key=key, body=body)
    try:
        _HUB_FILE.write_bytes(body)
    except OSError:
        pass
    return body


@app.get("/api/home/all")
def home_all():
    return Response(content=_hub_body(), media_type="application/json")


_WC_ROUNDS = ["group-stage", "round-of-32", "round-of-16", "quarterfinals",
              "semifinals", "3rd-place-match", "final"]
_WC_ROUND_KR = {"group-stage": "조별리그", "round-of-32": "32강", "round-of-16": "16강",
                "quarterfinals": "8강", "semifinals": "4강", "3rd-place-match": "3·4위전", "final": "결승"}


def _wc_read(table):
    return ds.read_table(table, league=ACTIVE_LEAGUE)


# WC 클럽 차출 교차참조 대상 — UI 로 탐색 가능한(로고·오버뷰 완비) 리그.
_WC_CLUB_LEAGUES = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal")


def _wc_player_index():
    """WC 선수명(norm) → (players_full 행, 리그). EPL·LaLiga 클럽 교차참조용.
    한 선수가 여러 리그에 있으면 출전시간 많은 쪽 채택."""
    from unidecode import unidecode
    def norm(s):
        return unidecode(str(s)).lower().strip()
    tmp: dict[str, tuple] = {}   # norm -> (row, league, minutes)
    avail = set(ds.available_leagues())
    for lg in _WC_CLUB_LEAGUES:
        if lg not in avail:
            continue
        try:
            pf = _pf(lg)
        except Exception:  # noqa: BLE001
            pf = None
        if pf is None or "player" not in pf.columns:
            continue
        # 이탈 선수(left_for) 제외 — 현재 소속 클럽만 차출 집계에 반영
        if "left_for" in pf.columns:
            pf = pf[pf["left_for"].isna() | (pf["left_for"].astype(str).str.strip() == "")]
        for _, r in pf.iterrows():
            n = norm(r["player"])
            mn = _num(r.get("minutes"))
            prev = tmp.get(n)
            if prev is None or mn > prev[2]:
                tmp[n] = (r, lg, mn)
    return {n: (v[0], v[1]) for n, v in tmp.items()}, norm


def _fifa_live_ranking():
    """공식 FIFA 점수(기준일) + 월드컵 경기 결과로 재계산한 '실시간 예상' 랭킹.
    FIFA 공식 SUM(Elo) 공식: P += I·(W − We), We = 1/(10^(−dr/600)+1).
    I(중요도): 월드컵 조별 50 · 녹아웃 60. 대회 중엔 공식 갱신이 없어 이걸로 근사한다.
    반환: (전체 랭킹 리스트[예상순위·공식순위·변동·점수변동], 공식 기준일)."""
    import math
    fr = _wc_read("fifa_ranking")
    if fr is None or "code" not in fr.columns or fr.empty:
        return [], ""
    pts, meta = {}, {}
    for _, r in fr.iterrows():
        code = str(r.get("code") or "").strip()
        if not code:
            continue
        pts[code] = _num(r.get("points"))
        meta[code] = {"team": str(r.get("team") or ""), "flag": str(r.get("flag") or ""),
                      "confederation": str(r.get("confederation") or ""),
                      "official_rank": int(_num(r.get("rank")))}
    base_pts = dict(pts)                      # 공식 점수 스냅샷(변동 계산용)
    updated = str(fr.iloc[0].get("updated") or "")

    m = _wc_read("wc_matches")
    if m is not None and "completed" in m.columns:
        done = m[m["completed"].astype(str).str.lower().isin({"true", "1", "yes"})].copy()
        if "date" in done.columns:
            done = done.sort_values("date")
        for _, g in done.iterrows():
            hc, ac = str(g.get("home_abbr") or "").strip(), str(g.get("away_abbr") or "").strip()
            if hc not in pts or ac not in pts:
                continue
            hs, as_ = _numornone(g.get("home_score")), _numornone(g.get("away_score"))
            if hs is None or as_ is None:
                continue
            imp = 50.0 if str(g.get("round")) == "group-stage" else 60.0
            we_h = 1.0 / (10 ** (-(pts[hc] - pts[ac]) / 600.0) + 1.0)
            w_h = 1.0 if hs > as_ else (0.0 if hs < as_ else 0.5)
            pts[hc] += imp * (w_h - we_h)
            pts[ac] += imp * ((1.0 - w_h) - (1.0 - we_h))

    ranked = sorted(pts.items(), key=lambda kv: -kv[1])
    out = []
    for i, (code, p) in enumerate(ranked, start=1):
        mt = meta.get(code, {})
        orank = mt.get("official_rank", i)
        out.append({"rank": i, "team": mt.get("team", code), "code": code,
                    "points": round(p, 2), "official_rank": orank,
                    "rank_change": orank - i, "points_change": round(p - base_pts.get(code, p), 2),
                    "confederation": mt.get("confederation", ""), "flag": mt.get("flag", "")})
    return out, updated


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

    idx, norm = _wc_player_index()
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

    # 도움 순위 + 나이맵 + 임팩트(득점+도움) 선수 풀
    ast = _wc_read("wc_assists")
    assistmap, assists_board = {}, []
    if ast is not None:
        for _, r in ast.iterrows():
            assistmap[norm(r.get("player"))] = int(_num(r.get("assists")))
        for _, r in ast.head(20).iterrows():
            assists_board.append({
                "player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                "assists": int(_num(r.get("assists"))), "logo": nation_logo.get(str(r.get("nation")), ""),
            })
    agemap = {}
    if sq is not None:
        for _, r in sq.iterrows():
            agemap[norm(r.get("player"))] = int(_num(r.get("age")))

    contrib = {}
    if sc is not None:
        for _, r in sc.iterrows():
            n = norm(r.get("player"))
            contrib[n] = {"player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                          "goals": int(_num(r.get("goals"))), "assists": assistmap.get(n, 0),
                          "age": agemap.get(n, 0)}
    if ast is not None:
        for _, r in ast.iterrows():
            n = norm(r.get("player"))
            if n not in contrib:
                contrib[n] = {"player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                              "goals": goalmap.get(n, 0), "assists": int(_num(r.get("assists"))),
                              "age": agemap.get(n, 0)}

    def _impact_card(c):
        n = norm(c["player"])
        hit = idx.get(n)
        row = hit[0] if hit else None
        return {"player": c["player"], "nation": c["nation"], "age": c["age"],
                "goals": c["goals"], "assists": c["assists"], "ga": c["goals"] + c["assists"],
                "logo": nation_logo.get(c["nation"], ""),
                "club": str(row["squad"]) if row is not None else "", "photo": _photo(row) if row is not None else ""}

    rising = sorted([c for c in contrib.values() if 0 < c["age"] <= 21 and (c["goals"] + c["assists"]) >= 1],
                    key=lambda x: -(x["goals"] + x["assists"]))[:6]
    veterans = sorted([c for c in contrib.values() if c["age"] >= 33 and (c["goals"] + c["assists"]) >= 1],
                      key=lambda x: -(x["goals"] + x["assists"]))[:6]
    rising = [_impact_card(c) for c in rising]
    veterans = [_impact_card(c) for c in veterans]

    # 조별 탈락 영웅 — 넉아웃 진출 못 했지만 조별리그 선전한 팀 + 대표선수
    adv = set()
    if "round" in m.columns:
        ko = m[m["round"] != "group-stage"] if "group-stage" in set(m["round"].astype(str)) else m[m["round"].astype(str).str.contains("round|final|quarter|semi", case=False, na=False)]
        for _, r in ko.iterrows():
            adv.add(str(r.get("home") or "")); adv.add(str(r.get("away") or ""))
    group_heroes = []
    if g is not None:
        elim = [r for _, r in g.iterrows() if str(r.get("team")) not in adv]
        elim.sort(key=lambda r: (-int(_num(r.get("Pts"))), -int(_num(r.get("GD"))), -int(_num(r.get("GF")))))
        # '잘했지만 탈락' — 승점 3+ (전형적 불운한 탈락) 우선, 없으면 상위 기록순
        strong = [r for r in elim if int(_num(r.get("Pts"))) >= 3]
        elim = strong or elim[:4]
        for r in elim[:6]:
            nat = str(r.get("team") or "")
            stars = sorted([c for c in contrib.values() if c["nation"] == nat and (c["goals"] + c["assists"]) >= 1],
                           key=lambda x: -(x["goals"] + x["assists"]))[:2]
            group_heroes.append({
                "team": nat, "logo": str(r.get("logo") or "") or nation_logo.get(nat, ""),
                "group": str(r.get("group") or ""),
                "P": int(_num(r.get("P"))), "W": int(_num(r.get("W"))), "D": int(_num(r.get("D"))),
                "L": int(_num(r.get("L"))), "GD": int(_num(r.get("GD"))), "Pts": int(_num(r.get("Pts"))),
                "stars": [{"player": s["player"], "goals": s["goals"], "assists": s["assists"]} for s in stars],
            })

    byclub = {}
    if sq is not None:
        for _, r in sq.iterrows():
            hit = idx.get(norm(r.get("player")))
            if hit is None:
                continue
            row, lg = hit
            club = str(row["squad"])
            b = byclub.setdefault(club, {"league": lg, "players": []})
            b["players"].append({
                "player": str(r.get("player") or ""), "nation": str(r.get("nation") or ""),
                "pos": str(r.get("pos") or ""), "photo": _photo(row),
                "goals": goalmap.get(norm(r.get("player")), 0),
            })
    club_callups = []
    for club, info in byclub.items():
        players = info["players"]
        players.sort(key=lambda x: -x["goals"])
        club_callups.append({"club": club, "league": info["league"], "logo": tm.team_logo(club),
                             "count": len(players), "players": players})
    # 차출 많은 클럽 우선 → 리그 → 클럽명
    club_callups.sort(key=lambda x: (-x["count"], x["league"], x["club"]))

    nations = []
    if sq is not None:
        seen = {}
        for _, r in sq.iterrows():
            n = str(r.get("nation") or "")
            if n:
                seen[n] = seen.get(n, 0) + 1
        nations = [{"nation": n, "logo": nation_logo.get(n, ""), "count": c} for n, c in sorted(seen.items())]

    # FIFA 랭킹 TOP 30 — 공식 기준점수 + 월드컵 결과로 실시간 예상(대회 중 공식 갱신 없음)
    fifa_all, fifa_updated = _fifa_live_ranking()
    fifa_ranking = fifa_all[:30]
    fifa_live = any(f["points_change"] for f in fifa_all)   # 반영된 WC 결과 있으면 True

    return {"matches": rounds, "groups": groups_list, "scorers": scorers,
            "assists": assists_board, "rising_stars": rising, "veterans": veterans,
            "group_heroes": group_heroes,
            "club_callups": club_callups, "nations": nations,
            "fifa_ranking": fifa_ranking, "fifa_updated": fifa_updated, "fifa_live": fifa_live}


@app.get("/api/wc/squad/{nation}")
def wc_squad(nation: str):
    """국가대표 스쿼드 (선수 + 소속 클럽 표시 · 전 리그 교차참조)."""
    sq = _wc_read("wc_squads")
    if sq is None or "nation" not in sq.columns:
        raise HTTPException(404, "WC 스쿼드 데이터 없음")
    idx, norm = _wc_player_index()
    rows = sq[sq["nation"].astype(str) == nation]
    if rows.empty:
        raise HTTPException(404, f"'{nation}' 스쿼드 없음")
    players = []
    for _, r in rows.iterrows():
        hit = idx.get(norm(r.get("player")))
        row = hit[0] if hit else None
        club = str(row["squad"]) if row is not None else ""
        players.append({
            "player": str(r.get("player") or ""), "pos": str(r.get("pos") or ""),
            "jersey": str(r.get("jersey") or ""), "age": str(r.get("age") or ""),
            "club": club, "league": hit[1] if hit else "",
            "club_logo": tm.team_logo(club) if club else "",
            "photo": _photo(row) if row is not None else "",
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


def _canon_line(x) -> str:
    """라인 토큰 통일 — slot_kind/_pos_line 은 'FWD', line_of_row 는 'ATT' 를 쓴다.
    대체 매칭이 어긋나지 않도록 하나로 정규화(ATT)."""
    x = str(x or "").upper()
    return "ATT" if x in ("FWD", "ATT", "ATTACK") else x


def _fine_bucket(s) -> str:
    """슬롯명(LCB·LB·RCM…) 또는 포지션 텍스트(Centre-Back…) → 세부 버킷.
    영입이 같은 자리 주전을 밀어낼 때 정밀 매칭용(CB↔CB, LB↔LB, 윙↔윙…)."""
    t = str(s or "").upper()
    if "GK" in t or "KEEPER" in t:
        return "GK"
    if "LWB" in t or "LEFT-BACK" in t or "LEFT BACK" in t or t == "LB":
        return "LB"
    if "RWB" in t or "RIGHT-BACK" in t or "RIGHT BACK" in t or t == "RB":
        return "RB"
    if "CB" in t or "CENTRE-BACK" in t or "CENTER-BACK" in t or "CENTRE BACK" in t:
        return "CB"
    if "RW" in t or "LW" in t or "RM" in t or "LM" in t or "WING" in t:
        return "W"
    if ("DM" in t or "CM" in t or "AM" in t or "MID" in t
            or "MIDFIELD" in t):
        return "CM"
    if "ST" in t or "CF" in t or "STRIKER" in t or "FORWARD" in t:
        return "ST"
    return ""


def _is_loan_move(fee_text) -> bool:
    """순수 임대(아웃 임대·임대 이적)면 True. '임대 종료(End of loan)'는 실제 이탈이므로 False."""
    f = str(fee_text or "").lower()
    return "loan" in f and "end of loan" not in f


def _dep_last(nm) -> str:
    t = str(nm).split()
    return t[-1].lower() if t else str(nm).lower()


def _departures(team: str, league: str, win: dict) -> dict:
    """이번 창 이탈 선수 — 이적 OUT(순수 임대아웃 제외·임대종료 포함) + players_full left_for.
    left_for 미동기 리그(LaLiga)에서도 이적 테이블로 이탈을 잡는다. 반환 {last_name: {player, club, pos}}."""
    dep: dict[str, dict] = {}
    tr = ds.read_table("transfers", league=league)
    if tr is not None and "squad" in tr.columns:
        tt, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        tt = tt[(tt["direction"] == "out") & ~tt["fee_text"].map(_is_loan_move)]
        for _, r in tt.iterrows():
            dep[_dep_last(r.get("player"))] = {"player": str(r.get("player") or ""),
                "club": str(r.get("club") or ""), "pos": str(r.get("pos") or "")}
    full = _pf(league)
    if full is not None and "left_for" in full.columns:
        lf = full[(full["squad"] == team) & full["left_for"].notna()
                  & (full["left_for"].astype(str).str.strip() != "")]
        for _, r in lf.iterrows():
            dep.setdefault(_dep_last(r.get("player")), {"player": str(r["player"]),
                "club": str(r.get("left_for") or ""),
                "pos": str(r.get("tm_position") or r.get("fl_group") or r.get("pos") or "")})
    return dep


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

    # 이탈: 이적 OUT(현재창) + left_for. 순수 임대아웃만 제외 — '임대 종료(로anee 반환)'는 이탈.
    tr = ds.read_table("transfers", league=league)
    departing = {k: {**v, "line": _canon_line(_pos_line(v["pos"]))}
                 for k, v in _departures(team, league, win).items()}

    # 영입: 이적 IN(현재창, 임대제외 — 임대영입·복귀는 투기적이라 XI 반영 안 함)
    signings = []
    if tr is not None:
        ins, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        ins = ins[(ins["direction"] == "in") & ~ins["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in ins.iterrows():
            signings.append({"player": str(r.get("player") or ""), "pos": str(r.get("pos") or ""),
                             "line": _canon_line(_pos_line(r.get("pos"))), "fee": str(r.get("fee_text") or ""),
                             "photo": str(r.get("photo") or "") if str(r.get("photo") or "").startswith("http") else "",
                             "used": False})

    # 스쿼드 내부 대체 후보
    squad = _squad_df(team, league)
    squad_pool = []
    if squad is not None:
        sd = squad.copy()
        sd["_ovr"] = sd.apply(_player_ovr, axis=1)
        for _, r in sd.sort_values("_ovr", ascending=False).iterrows():
            squad_pool.append({"player": str(r["player"]), "line": _canon_line(rv3.line_of_row(r)),
                               "ovr": int(r["_ovr"]), "photo": _photo(r)})

    xi_names = {_last(p["player"]) for p in season["placements"]}

    def _pick_replacement(slot_line, want_line=None):
        """이탈 선수 자리 대체자. 이탈 선수의 실제 포지션(want_line) 영입 → 슬롯 라인 영입 →
        슬롯 라인 스쿼드 순. (4-2-3-1 등에서 LW 가 LCM 슬롯=MID 로 잡혀도 윙어 영입이 들어가도록)"""
        slot_line = _canon_line(slot_line)
        targets = []
        if want_line and _canon_line(want_line) not in targets:
            targets.append(_canon_line(want_line))
        if slot_line not in targets:
            targets.append(slot_line)
        for tgt in targets:                       # 영입 우선(이탈 포지션 → 슬롯 라인)
            for s in signings:
                if not s["used"] and s["line"] == tgt:
                    s["used"] = True
                    r = resolve(s["player"])
                    ovr = _player_ovr(r) if r is not None else None
                    photo = s["photo"] or (_photo(r) if r is not None else "")
                    if ovr is None:                # 타 리그 영입(예: Gordon EPL→LaLiga) — 교차리그 projection
                        x_ovr, x_photo = _incoming_ovr(s["player"], league)
                        ovr = x_ovr
                        photo = photo or x_photo
                    return {"player": s["player"], "ovr": ovr, "photo": photo, "src": "signing"}
        for c in squad_pool:                      # 스쿼드 내부 승격(슬롯 라인)
            if c["line"] == slot_line and _last(c["player"]) not in xi_names:
                xi_names.add(_last(c["player"]))
                return {"player": c["player"], "ovr": c["ovr"], "photo": c["photo"], "src": "squad"}
        return {"player": "영입 필요", "ovr": None, "photo": "", "src": "gap"}

    projected, diagnosis = [], []
    for p in season["placements"]:
        key = _last(p["player"])
        if key in departing and p["player"] != "—":
            rep = _pick_replacement(p["kind"], departing[key].get("line"))
            projected.append({**p, "player": rep["player"], "ovr": rep["ovr"], "photo": rep["photo"], "changed": True})
            sev = "핵심" if (p.get("ovr") or 0) >= 80 else "로테이션"
            note = (f"{rep['player']} 승격" if rep["src"] == "squad"
                    else (f"영입 {rep['player']}로 대체" if rep["src"] == "signing" else "대체자 영입 필요"))
            diagnosis.append({"kind": "loss", "severity": sev, "player": p["player"], "slot": p["slot"],
                              "line": p["kind"], "to": departing[key]["club"], "replacement": rep["player"],
                              "note": f"{sev} {p['slot']} 이탈 → {note}", "photo": p.get("photo", "")})
        else:
            projected.append({**p, "changed": False})

    def _signing_ovr(s):
        r = resolve(s["player"])
        ovr = _player_ovr(r) if r is not None else None
        photo = s["photo"] or (_photo(r) if r is not None else "")
        if ovr is None:                        # 타 리그 영입 — 교차리그 projection
            x_ovr, x_photo = _incoming_ovr(s["player"], league)
            ovr = x_ovr
            photo = photo or x_photo
        return ovr, photo

    # 영입이 같은 자리 최약체 주전을 밀어내고 선발 진입(IN) — 이탈이 없어도 스쿼드가 갱신되도록.
    # (예: 코나테→아센시오, 쿠쿠레야→카레라스. 25/26 과 똑같이 안 나오게 하는 트리거)
    for s in signings:
        if s["used"]:
            continue
        sb = _fine_bucket(s["pos"])
        if not sb:
            continue
        cands = [p for p in projected if _fine_bucket(p["slot"]) == sb
                 and not p.get("in") and not p.get("changed") and p["player"] not in ("—", "영입 필요")]
        if not cands:
            continue
        weakest = min(cands, key=lambda p: (p.get("ovr") or 0))
        inc_ovr = weakest.get("ovr") or 0
        s_ovr, s_photo = _signing_ovr(s)
        # OVR 미상(유스·하위리그 영입)이거나 약체 백업이면 선발 교체 안 함(보강으로 남김)
        if s_ovr is None or s_ovr < inc_ovr - 4:
            continue
        s["used"] = True
        displaced = weakest["player"]
        weakest.update({"player": s["player"], "ovr": s_ovr,
                        "photo": s_photo or weakest.get("photo", ""),
                        "changed": True, "in": True, "out": displaced})
        diagnosis.append({"kind": "gain", "severity": "선발 영입", "player": s["player"],
                          "slot": weakest["slot"], "line": weakest["kind"], "fee": s["fee"],
                          "replacement": displaced,
                          "note": f"{displaced} 밀어내고 선발 진입", "photo": s_photo or s["photo"]})

    # 사용되지 않은 영입 = 보강(뎁스)
    line_top = {}
    for p in season["placements"]:
        k = _canon_line(p["kind"])
        if k not in line_top or (p.get("ovr") or 0) > line_top[k][1]:
            line_top[k] = (p["player"], p.get("ovr") or 0)
    for s in signings:
        if s["used"]:
            continue
        rival = line_top.get(s["line"], ("", 0))[0]
        r = resolve(s["player"])
        diagnosis.append({"kind": "gain", "severity": "보강", "player": s["player"], "slot": s["pos"],
                          "line": s["line"], "fee": s["fee"], "replacement": "",
                          "note": (f"기존 {rival} 경쟁/뎁스 보강" if rival else f"{s['line']} 뎁스 보강"),
                          "photo": s["photo"] or (_photo(r) if r is not None else "")})

    def _dsort(d):
        if d["kind"] == "loss":
            return 0 if d.get("severity") == "핵심" else 1
        return 2 if d.get("severity") == "선발 영입" else 3
    diagnosis.sort(key=_dsort)

    return {"team": team, "color": tm.team_color(team),
            "current_label": _data_season_label(), "next_label": next_label,
            "current": season, "projected": {"formation": season["formation"], "placements": projected},
            "diagnosis": diagnosis}


@app.get("/api/health")
def health():
    return {"ok": True, "active_league": ACTIVE_LEAGUE, "leagues": ds.available_leagues()}
