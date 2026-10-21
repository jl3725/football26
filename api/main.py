"""Football26 FastAPI 백엔드.

football.db와 도메인 분석 로직을 팀·선수·이적·스카우팅 JSON API로 노출한다.
데이터 계층은 src/datastore.py를 사용하므로 UI 프레임워크와 무관하게
리그/시즌 좌표로 데이터를 얻는다.

실행:
    .venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000

주의: OVR/레이더 수치는 team_unit_metrics 인덱스를 그대로/근사 매핑한 값.
추후 overview.team_ratings(유저가 튜닝한 공식)를 순수 로직으로 추출해 교체 가능.
"""
from __future__ import annotations

import datetime
import json
import os
import re

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.bootstrap import ROOT  # noqa: E402,F401

import datastore as ds  # noqa: E402
import teammeta as tm  # noqa: E402
import ratings as rt  # noqa: E402
import ratings_v3 as rv3  # noqa: E402  (절대 클래스·폼·POT·신뢰도)
import transfer_adjust as ta  # noqa: E402

# ── 응답 캐시 ──────────────────────────────────────────────────────────────
# 무거운 집계(overview·projection·recommend…)를 요청마다 다시 계산하면 단일 워커가 수 초씩 멈춘다.
# 키에 football.db 수정 시각을 넣어 데이터가 갱신되면 자동 무효화. 프로세스 메모리, 상한 512개.
_MEMO: dict[tuple, tuple[float, object]] = {}
_MEMO_MAX = 512


def _clean_title(v) -> str:
    """RSS 제목의 CDATA 래퍼·공백 정리(이미 저장된 데이터용)."""
    import re as _re
    return _re.sub(r"^<!\[CDATA\[\s*|\s*\]\]>$", "", str(v or "")).strip()


def _db_stamp() -> float:
    try:
        return ds.DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


# 데이터 API 는 football.db 에서만 계산되고 키에 DB 수정 시각(_db_stamp)이 들어가 배포 시 자동 무효화된다 —
# 그래서 무거운 엔드포인트는 TTL 을 6시간으로 길게 둔다(무료 인스턴스에서 첫 호출이 수 초~십여 초).
_MEMO_LOCKS: dict = {}
_MEMO_GUARD = __import__("threading").Lock()


def _memo(ttl: float = 3600.0):
    """메모이즈(ttl 초) — 같은 키는 한 스레드만 계산하고 나머지는 결과를 기다린다.
    Render 무료(0.1 CPU)에서 데우기 스레드와 첫 요청이 같은 리그 전체 계산을 동시에 돌려 Overview 가 30초를 넘겼다(2026-10-15)."""
    import functools
    import threading
    import time as _t

    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            key = (fn.__name__, args, tuple(sorted(kwargs.items())), _db_stamp())
            hit = _MEMO.get(key)
            if hit and hit[0] > _t.monotonic():
                return hit[1]
            with _MEMO_GUARD:
                lock = _MEMO_LOCKS.setdefault(key, threading.Lock())
            with lock:
                hit = _MEMO.get(key)
                now = _t.monotonic()
                if hit and hit[0] > now:
                    return hit[1]
                out = fn(*args, **kwargs)
                if len(_MEMO) >= _MEMO_MAX:
                    for k in [k for k, v in _MEMO.items() if v[0] <= now][:64] or [next(iter(_MEMO))]:
                        _MEMO.pop(k, None)
                        _MEMO_LOCKS.pop(k, None)
                _MEMO[key] = (now + ttl, out)
                return out
        return wrapped
    return deco
from leagues import ACTIVE_LEAGUE, SEASON_START, league_config, data_path  # noqa: E402
from season_context import current_window as _current_window  # noqa: E402
from season_context import season_label as _data_season_label  # noqa: E402
from team_analysis import (  # noqa: E402  (streamlit 비의존)
    espn_assign_slots, slot_xy, slot_kind, formation_slots, display_slot,
)
from api.routers.meta import router as meta_router  # noqa: E402
from api.routers.teams import router as teams_router  # noqa: E402
from api.routers.teams import teams, teams_next  # noqa: E402
from api.routers.world_cup import router as world_cup_router  # noqa: E402
from api.routers.intl import router as intl_router  # noqa: E402
from api.services.player_data import extra_photo_map as _xtra_photo  # noqa: E402
from api.services.player_data import number as _num  # noqa: E402
from api.services.player_data import photo_url as _photo  # noqa: E402
from api.services.player_data import player_frame as _pf  # noqa: E402
from api.services.player_data import resolve_photo as _resolve_photo  # noqa: E402
from player_names import read_lineup_csv  # noqa: E402

app = FastAPI(title="Football Scout API", version="0.2.0")
app.include_router(meta_router)
app.include_router(teams_router)
app.include_router(world_cup_router)
app.include_router(intl_router)
# gzip — 큰 응답(예: database 전리그 766KB) 전송량을 ~5분의 1로 줄여 로딩 단축.
app.add_middleware(GZipMiddleware, minimum_size=1024)
# CORS — 브라우저에서 API에 직접 접근할 origin만 명시한다.
# Vercel rewrite는 same-origin이므로 기본값을 비워도 정상 동작한다.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.middleware("http")
async def _data_version(request, call_next):
    """X-Data-Version = 모델 버전 + DB 빌드 시각 — 브라우저가 오래 들고 있던 캐시(선수 DB)를 배포 뒤 버리게 한다.
    예전엔 배포 전에 연 화면에서 선수 카드만 옛 OVR(하베르츠 84)이고 새로 받은 포메이션은 83이었다(2026-10-19)."""
    resp = await call_next(request)
    if request.url.path.startswith("/api/"):
        resp.headers["X-Data-Version"] = f"{rv3.MODEL_VERSION}.{int(ds._db_mtime())}"
    return resp


MANAGER_JSON = data_path("manager_profiles", "EPL", ext="json")
TEAM_PROFILES_JSON = ROOT / "data" / "team_profiles.json"


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
    """team_unit_metrics 인덱스(0-99) → 체감 OVR 밴드(대략 60-90)."""
    return int(round(55 + float(idx) * 0.36))


def _team_row(table: str, team: str, league: str, key: str = "squad"):
    df = ds.read_table(table, league=league)
    if df is None or key not in df.columns:
        return None
    hit = df[df[key] == team]
    return hit.iloc[0] if not hit.empty else None


def _window_filter(tt, win):
    """이적 DF 를 활성 윈도우로 필터. 해당 윈도우 데이터 없으면 (원본, False)."""
    if tt is None or "season_id" not in tt.columns or "window" not in tt.columns:
        return tt, False
    f = tt[(pd.to_numeric(tt["season_id"], errors="coerce") == win["season_id"])
           & (tt["window"].astype(str) == win["window"])]
    if f.empty:
        return tt, False
    return f, True




def _with_roster(full_df, team: str, league: str):
    """팀 OVR 입력 — 이번 시즌 출전자 + 출전 없는 등록 선수(장기 부상 살리바 등, 지난 시즌 기록으로).
    '가진 전력'이라 부상자도 넣는다(출전 기록이 있는 부상자는 원래 들어가 있었다 — 0분 부상자만 빠졌던 것)."""
    if full_df is None or "squad" not in full_df.columns:
        return full_df
    sq = full_df[full_df["squad"] == team]
    lo = _loans_out(team, league)
    if lo and not sq.empty:
        sq = sq[~sq["player"].map(lambda n: _is_loaned(n, lo))]   # 임대 보낸 선수(Grealish)
    try:
        ex = _roster_extras(team, league, full_df)
    except Exception:  # noqa: BLE001 — 계약 명단이 없는 리그
        ex = []
    if not ex:
        return sq
    ex_df = pd.DataFrame(ex).dropna(axis=1, how="all")   # 빈 열은 concat 이 NaN 으로 채운다(FutureWarning 회피)
    return pd.concat([sq, ex_df], ignore_index=True)


@_memo(ttl=21600)
def _sh_reader(league: str, season: str):
    return ds.read_table("standings", league=league, season=season)


@_memo(ttl=21600)
def _team_record(team: str, league: str) -> dict:
    """{current, past[]} — 이번 시즌과 지난 여러 시즌의 경기당 득점·실점·리그 안 z·순위(src/season_history.py).
    시즌 목록은 SEASON_START 기준으로 자동 — 시즌이 넘어가면 직전 시즌이 '과거'로 들어오고 오래된 시즌은 가중이 줄어든다."""
    import season_history as sh  # noqa: PLC0415
    cur_t = ds.read_table("standings", league=league)
    cur = sh.table_stats(cur_t, team) if cur_t is not None and "squad" in cur_t.columns else None
    tag = sh.season_tag(SEASON_START)
    return {"current": {"season": tag, "label": sh.short(tag), **cur} if cur else None,
            "past": sh.team_record(league, team, _sh_reader)}


@_memo(ttl=21600)
def _team_perf(team: str, league: str) -> dict:
    """팀 실적 0~99(50 = 리그 평균, 1 표준편차 = 20) — rv3.team_ratings 의 라인 실적 보정(±2.5).

    공격 = 경기당 득점, 수비 = 경기당 실점의 리그 안 z. 백분위 지수(defense_output_index)는 상위권이 눌려
    아스날 25/26 최소 실점(0.71)과 맨시티(0.92)가 97·95 로 거의 같았다. 미드필드는 midfield_index(직전 시즌까지).
    이번 시즌(경기 수 g, 비중 g/(g+10)) + 지난 시즌들(직전 1 · 그 전 0.5 · 0.25 …, 그 리그에 있던 시즌만 —
    2026-10-15 사용자: '두 시즌만이 아니라 쌓이는 시즌을 자동으로', '맨시티는 작년에도 실점이 더 많았다')."""
    import season_history as sh  # noqa: PLC0415
    rec = _team_record(team, league)
    cur, past = rec["current"], rec["past"]
    g = cur["played"] if cur else 0
    w = g / (g + 10.0)
    out = {}
    for unit, key in (("attack", "gf_z"), ("defense", "ga_z")):
        c = 50.0 + 20.0 * cur[key] if cur else None
        hz = sh.blended(past, key)
        p = 50.0 + 20.0 * hz if hz is not None else None
        if c is None and p is None:
            continue
        out[unit] = round(w * (c if c is not None else 50.0) + (1 - w) * (p if p is not None else 50.0), 1)
    prev_season = f"{SEASON_START - 1}_{SEASON_START}"
    cur_m = ds.read_table("team_unit_metrics", league=league)
    prev_m = ds.read_table("team_unit_metrics", league=league, season=prev_season)
    col = "midfield_index"
    c = _num(cur_m[cur_m["squad"] == team].iloc[0].get(col), None) if cur_m is not None and team in set(cur_m["squad"]) and col in cur_m.columns else None
    p = _num(prev_m[prev_m["squad"] == team].iloc[0].get(col), None) if prev_m is not None and team in set(prev_m["squad"]) and col in prev_m.columns else None
    if c is not None or p is not None:
        out["midfield"] = round(w * (c if c is not None else 50.0) + (1 - w) * (p if p is not None else 50.0), 1)
    return out


@_memo(ttl=21600)
def _league_units(league: str) -> dict:
    """{클럽: {overall, attack, midfield, defense}} — 같은 리그 안 라인별 순위·클럽 티어·빅매치 전력.

    배포 빌드에서 미리 계산한 data/team_units.json(scripts/precompute_team_units.py)이 지금 DB 와 같으면 그걸 쓴다.
    Render 무료(0.1 CPU)에서 시작할 때마다 8개 리그 전 팀(부상자 포함·임대 판정·여러 시즌 기록)을 계산하느라
    홈(빅매치·결과 띠)과 Overview 가 70초 제한을 넘겼다(2026-10-15). 파일이 없거나 DB 가 바뀌었으면 즉석 계산."""
    from api.services.player_data import same_build  # noqa: PLC0415
    snap = _units_snapshot()
    if (snap.get("season") == SEASON_START and same_build(snap.get("db_mtime"), snap.get("db_size"))
            and league in snap.get("leagues", {})):
        return snap["leagues"][league]
    return _compute_league_units(league)


_UNITS_FILE = ds.DB_PATH.parent / "team_units.json"
_UNITS_SNAP: dict = {}


def _units_snapshot() -> dict:
    if "data" not in _UNITS_SNAP:
        try:
            _UNITS_SNAP["data"] = json.loads(_UNITS_FILE.read_text(encoding="utf-8")) if _UNITS_FILE.exists() else {}
        except (OSError, ValueError):
            _UNITS_SNAP["data"] = {}
    return _UNITS_SNAP["data"]


def _compute_league_units(league: str) -> dict:
    full = _pf(league)
    out: dict = {}
    if full is None or "squad" not in full.columns:
        return out
    for c in full["squad"].dropna().astype(str).unique():
        tr = rv3.team_ratings(_with_roster(full, c, league), c, perf=_team_perf(c, league))
        if tr:
            out[c] = {k: tr[k] for k in ("overall", "attack", "midfield", "defense")}
    return out


def _unit_ranks(team: str, league: str, ovr: dict) -> dict:
    """{라인: {rank, n}} — 표시 값(ovr) 기준, 같은 값은 같은 순위."""
    lu = _league_units(league)
    out = {}
    for k in ("overall", "attack", "midfield", "defense"):
        others = [v[k] for c, v in lu.items() if c != team]
        if ovr.get(k) is None or not others:
            continue
        out[k] = {"rank": 1 + sum(1 for x in others if x > ovr[k]), "n": len(others) + 1}
    return out


def _age_summary(team: str, league: str, full_df) -> dict | None:
    """출전 가중 평균 나이(실제로 뛰는 선수 기준)와 리그 안 순위(1 = 가장 젊다) + 연령대별 출전 비중.
    머릿수 평균은 안 뛰는 유스·백업 GK 에 흔들려 '얼마나 젊은 팀인가'를 잘 못 보여 준다."""
    if full_df is None or "age" not in full_df.columns:
        return None
    f = full_df[["squad", "age", "minutes"]].copy()
    f["age"] = pd.to_numeric(f["age"], errors="coerce")
    f["minutes"] = pd.to_numeric(f["minutes"], errors="coerce").fillna(0)
    f = f[(f["age"] > 0) & (f["minutes"] > 0)]
    if f.empty or team not in set(f["squad"]):
        return None
    w = f.assign(am=f["age"] * f["minutes"]).groupby("squad")[["am", "minutes"]].sum()
    wavg = (w["am"] / w["minutes"]).sort_values()
    t = f[f["squad"] == team]
    tot = float(t["minutes"].sum())
    share = lambda m: round(100.0 * float(t.loc[m, "minutes"].sum()) / tot) if tot else 0  # noqa: E731
    return {"wavg": round(float(wavg[team]), 1), "rank_young": int(list(wavg.index).index(team)) + 1, "n": int(len(wavg)),
            "league_wavg": round(float((w["am"].sum()) / w["minutes"].sum()), 1),
            "u23": share(t["age"] <= 23), "prime": share((t["age"] >= 24) & (t["age"] <= 29)), "vet": share(t["age"] >= 30)}


@app.get("/api/overview/{team}")
@_memo(ttl=21600)
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
            # 실제 최빈 포메이션(리그 라인업) 우선, 위키 값은 '선호'로
            "formation": (_used_formation(team, league) or {}).get("formation") or mgr.get("formation", ""),
            "formation_used": _used_formation(team, league),
            "formation_pref": mgr.get("formation", ""),
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

    def _ix(col, default=None):
        """팀 지표(1~99). 원천 미수집이면 None — 레이더에서 그 축을 뺀다(예전엔 50 으로 채움)."""
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
    base = rv3.team_ratings(_with_roster(full_df, team, league), team, perf=_team_perf(team, league))                       # 이적 전(현재 스쿼드)
    # 이적 보정은 아직 실제 스쿼드·스탯에 반영되지 않은 창일 때만 — 시즌 중 닫힌 창(여름 이적이 이미
    # 데이터에 들어감)에 또 적용하면 영입 선수를 이중 계산한다.
    adjust = win.get("phase") != "in_season" or win.get("is_open")
    if base:
        adj = (rv3.team_ratings(ta.build_adjusted_full(_with_roster(full_df, team, league), tr, win), team, perf=_team_perf(team, league)) or base) if adjust else base
        for k in ("overall", "attack", "midfield", "defense"):
            ovr[k] = adj[k]
            ovr_delta[k] = adj[k] - base[k]
        ovr["top_xi"] = adj.get("top_xi", adj["overall"])
        ovr["perf_adj"] = adj.get("perf_adj") or {}
        ovr["record"] = _team_record(team, league)     # 시즌별 득점·실점(화면: 라인 아래 기록 줄)
        ovr["unit_rank"] = _unit_ranks(team, league, ovr)
        import positions as _ps  # noqa: PLC0415
        _inj = _active_injuries(team, league)
        ovr["units"] = {k: [{**x, "injured": _ps.norm_name(x["player"]) in _inj,
                             "until": (_inj.get(_ps.norm_name(x["player"])) or {}).get("until", "")} for x in v]
                        for k, v in (adj.get("units") or {}).items()}

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
        _lo = _loans_out(team, league)
        if _lo:
            sq = sq[~sq["player"].map(lambda n: _is_loaned(n, _lo))]     # 임대 보낸 선수
        sq["_r"] = pd.to_numeric(sq.get("ss_rating"), errors="coerce").fillna(0)
        sq["_ovr"] = sq.apply(_player_ovr, axis=1)
        # 소표본 유스 인플레 방지 — 출전시간 확보 선수만(부족하면 완화)
        sq_star = sq[pd.to_numeric(sq.get("minutes"), errors="coerce").fillna(0) >= _mm(450, league)]
        if len(sq_star) < 5:
            sq_star = sq
        for _, r in sq_star.sort_values(["_ovr", "_r"], ascending=False).head(5).iterrows():
            prof = _comp_profile(r, usage_idx)
            stars.append({
                "player": r["player"], "pos": _pos_label(r),
                "ovr": _player_ovr(r), "pot": _player_pot(r), "form": _player_form(r),
                "form_recent": _recent_score(r), "recent_avg": _num_or_none(r.get("_recent_avg5")), "recent_n": _num_or_none(r.get("_recent_n")),
                "trend": _trend(r, league),
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
                "line": rv3.line_of_row(r), "photo": _photo(r),
            })
        squad_ratings.sort(key=lambda x: -x["ovr"])
    age_summary = _age_summary(team, league, full_df)

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
    inj_tbl = _injuries_table(league)          # 부상 뒤 실제로 뛴 선수 제외(TM 갱신 지연)
    injuries = []
    if inj_tbl is not None and "squad" in inj_tbl.columns:
        ti = inj_tbl[inj_tbl["squad"].astype(str) == team]
        if "active" in ti.columns:
            ti = ti[ti["active"].astype(str).str.lower().isin({"true", "1", "yes", "y"})]
        for _, r in ti.iterrows():
            injuries.append({
                "player": str(r.get("player") or ""), "injury": str(r.get("injury") or ""),
                "until": str(r.get("until") or "") if pd.notna(r.get("until")) else "", "pos": str(r.get("position") or ""),
                "photo": str(r.get("tm_photo") or "") if str(r.get("tm_photo") or "").startswith("http") else "",
                "source": str(r.get("source") or "transfermarkt"),
            })

    # 팀 리더 (지표별 1위)
    leaders = []
    if full_df is not None:
        sq_all = full_df[full_df["squad"] == team]
        # 90분당 지표는 최소 출전(풀시즌 1200′를 진행률만큼 줄인 값, 최소 180′) — 키패스 1위가 10분 뛴 Dowman 이었다(2026-10-20 점검)
        min_p90 = max(180, _mm(1200, league))           # 시즌 7경기면 약 220′(2.5경기)
        for label, col, kind in [("득점", "goals", "tot"), ("도움", "assists", "tot"),
                                 ("xG/90", "xg_p90", "p90"), ("키패스/90", "key_passes_per90", "p90"),
                                 ("태클/90", "tackles_won_per90_ss", "p90")]:
            if col in sq_all.columns and not sq_all.empty:
                ss = sq_all.copy()
                ss["_v"] = pd.to_numeric(ss[col], errors="coerce").fillna(0)
                if kind == "p90":
                    ss = ss[pd.to_numeric(ss["minutes"], errors="coerce").fillna(0) >= min_p90]
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
        # 사진: 이적 기록의 TM 사진 → 이름으로 찾은 현재 명단(성만 같은 다른 선수일 수 있어 뒤로) → 이적 사진 사전
        ph = v.get("photo") or (_photo(r) if r is not None else "") or _resolve_photo(v["player"], resolve_dep, league)
        departed.append({"player": v["player"], "left_for": v["club"],
                         "pos": v["pos"] or (str(r.get("fl_group") or r.get("pos") or "") if r is not None else ""),
                         "photo": ph if str(ph).startswith("http") else ""})

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
        "radar": [ax for ax in [
            {"axis": "ATT OUT", "value": _ix("attack_output_index")},
            {"axis": "CREATE", "value": _ix("attack_creation_index")},
            {"axis": "CONTROL", "value": _ix("midfield_control_index")},
            {"axis": "PRESS", "value": _ix("pressing_index")},
            {"axis": "DEF OUT", "value": _ix("defense_output_index")},
            {"axis": "SET PC", "value": _ix("set_piece_attack_index")},
        ] if ax["value"] is not None],
        "form": form,
        "manager": manager,
        "snapshot": snapshot,
        "edge": edge,
        "stars": stars,
        "squad_ratings": squad_ratings, "age_summary": age_summary,
        "leaders": leaders,
        # 골·도움·출전이 언제 경기까지 반영됐나 — FotMob 리그 경기 합(경기 20분 뒤) 기준일, 없으면 None(FBref 주간)
        "leaders_asof": _stats_asof(full_df, team),
        "departed": departed,
        "injuries": injuries,
        # TM 은 아직 '부상'이지만 부상 뒤에 실제로 뛰어 복귀로 본 선수(_injury_returns)
        "injury_returns": [{"player": k[1], "date": v["date"], "since": v.get("since")}
                           for k, v in _injury_returns(league).items() if k[0] == team],
        "transfers": {"in": tin, "out": tout},
        "window": win,
        "data_season": _data_season_label(),
    }


@app.get("/api/identity/{team}")
@_memo(ttl=21600)
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
            "manager": p.get("manager"),
            "formation": (_used_formation(team, league) or {}).get("formation") or p.get("formation"),   # 실제 최빈값 우선
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
def fit(candidate: str, club: str, role: str = "", source_league: str = "",
        league: str = ACTIVE_LEAGUE):
    """Transfer Fit Evaluator — (후보, 대상클럽, 역할) → Fit Score + 전 컴포넌트 분해.

    스타일 벡터는 서버 메모리(transfer_fit._vec_index)라 어디서나 동작한다 — 예전엔 Qdrant 가 없는 운영 서버에서
    available=False(꺼짐)였다(2026-10-19). Neo4j 선례는 있으면 보탠다(best-effort). 온디맨드(버튼)로만 호출.
    """
    import transfer_fit as tf  # noqa: PLC0415
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

    manager 는 감독명(현 클럽 전술로 대체) 또는 클럽명. 스타일 벡터는 서버 메모리(Qdrant 불필요, 2026-10-19).
    """
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


@app.post("/api/scout")
def scout(body: dict, x_scout_token: str = Header(default="")):
    """Ask Scout — 자연어 질문 → OpenAI 툴 라우팅(+GraphRAG) → 엔진 실행 → 답변 + 카드용 결과.

    body: {q, team?, league?, history?}. LLM은 라우팅·요약만, 판단은 엔진/그래프.
    OPENAI_API_KEY 없으면 available=False. SCOUT_TOKEN 설정 시 X-Scout-Token 헤더 필요.
    """
    import scout_agent as sa  # noqa: PLC0415 (지연 import — OpenAI 의존)
    # 토큰은 유료(OpenAI) 경로일 때만 — 무료(규칙 라우터·Gemini 무료 등급)는 누구나(2026-10-20)
    if sa.provider() == "openai":
        need = os.getenv("SCOUT_TOKEN")
        allow_public = os.getenv("SCOUT_ALLOW_PUBLIC", "").lower() in {"1", "true", "yes"}
        if not need and not allow_public:
            return {"available": False, "auth_required": True,
                    "reason": "서버에 SCOUT_TOKEN을 설정해야 Ask Scout(유료 모델)를 사용할 수 있습니다"}
        if need and x_scout_token != need:
            return {"available": False, "auth_required": True,
                    "reason": "Ask Scout 접근 토큰이 필요합니다 (비밀번호 입력)"}
    return sa.answer(str(body.get("q") or ""), body.get("team") or None,
                     body.get("league") or ACTIVE_LEAGUE, body.get("history"))


@app.get("/api/discover/{team}")
@_memo(ttl=21600)
def discover(team: str, role: str = "", leagues: str = "", min_age: int = 0,
             max_age: int = 0, max_value: float = 0, top: int = 24,
             league: str = ACTIVE_LEAGUE):
    """벡터(Qdrant) 스타일-핏 교차리그 발굴 + KG 신호(루머·선례). Recruit 탭·스카우트 공용.

    필터: role(포지션)·leagues(쉼표구분 소스리그)·min_age/max_age·max_value(EUR 상한).
    로컬/호스팅 Qdrant 필요. 미가동 시 available=False degrade. role 없으면 얇은 역할 자동.
    """
    import transfer_fit as tf  # noqa: PLC0415
    lgs = [s for s in leagues.split(",") if s] or None
    # 포지션을 고르지 않으면 니즈 v2(부상·폼·이적 공백) 상위 포지션 — 예전엔 '300분+ 2명 이하' 역할만 봤다
    need_roles, needs_meta = None, []
    try:
        team_ovr_ = _position_needs(team, league)["team_ovr"]
    except Exception:  # noqa: BLE001
        team_ovr_ = None
    if not role:
        try:
            pn = _position_needs(team, league)
            top_n = [x for x in pn["roles"] if x["urgency"] >= 15][:3]
            need_roles = [_ROLE_TM[x["role"]] for x in top_n] or None
            needs_meta = [{"role": x["role"], "label": x["label"], "urgency": x["urgency"], "level": x["level"]} for x in top_n]
        except Exception:  # noqa: BLE001
            need_roles = None
    out = tf.discover_fits(team, role or None, top=top or 24, leagues=lgs,
                           min_age=min_age or None, max_age=max_age or None,
                           max_value=max_value or None, roles=need_roles, team_ovr=team_ovr_)
    # 구단 이적 정책(최근 두 시즌 영입 나이·이적료)과 대조
    try:
        pol = _transfer_policy(team)
    except Exception:  # noqa: BLE001
        pol = None
    team_ovr = team_ovr_ or 80.0
    out["team_ovr"] = team_ovr_
    rivals = _club_rivals(team)                 # 위키 라이벌·더비(같은 리그) — 라이벌 구단 선수는 거래 어려움
    for r in out.get("recommendations") or []:
        r["rival"] = str(r.get("squad") or "") in rivals
        pf_ = _policy_fit(pol, r.get("age"), r.get("value_eur"))
        r["policy_ok"], r["policy_notes"] = pf_["ok"], pf_["notes"]
        # 영입 가능성 — 경쟁 팀(같은 리그 전력 6 이내·위) · 강팀(3 이내·위) 핵심 주전(출전 60%+)은 낮음(recommend 와 같은 기준)
        src = str(r.get("source_league") or league)
        cstr = _club_strength(src).get(str(r.get("squad") or ""), 78)
        key = (r.get("minutes") or 0) >= _mm(2000, src)
        r["realistic"] = not (key and ((src == league and cstr >= team_ovr - 6) or cstr >= team_ovr - 3)) and not r["rival"]
    out["policy"] = pol
    out["needs"] = needs_meta
    return out


def _club_rivals(team: str) -> set[str]:
    """위키 라이벌·더비 섹션에서 자동으로 모은 같은 리그 라이벌(src/club_rivals.py → data/club_rivals.json)."""
    try:
        import club_rivals  # noqa: PLC0415
        return set(club_rivals.load().get(team, []))
    except Exception:  # noqa: BLE001
        return set()


def _window_spend(team: str, league: str) -> list[dict]:
    """최근 이적창별 지출·수입(이번·지난 시즌 TM 이적 기록) — 최신 순."""
    rows = []
    for y in (SEASON_START, SEASON_START - 1):
        t = ds.read_table("transfers", league=league, season=f"{y}_{y + 1}")
        if t is None or t.empty or "squad" not in t.columns:
            continue
        t = t[t["squad"].astype(str) == team]
        for (sid, win), g in t.groupby([t["season_id"].astype(int), t["window"].astype(str)]):
            fee = pd.to_numeric(g["fee_eur"], errors="coerce").fillna(0)
            ins, outs = g["direction"] == "in", g["direction"] == "out"
            rows.append({"season_id": int(sid), "window": win,
                         "label": f"{sid % 100:02d}/{(sid + 1) % 100:02d} {'여름' if win == 'summer' else '겨울'}",
                         "spend": float(fee[ins].sum()), "income": float(fee[outs].sum()),
                         "n_in": int(ins.sum()), "n_out": int(outs.sum())})
    rows = list({(r["season_id"], r["window"]): r for r in rows}.values())
    rows.sort(key=lambda r: (r["season_id"], r["window"] == "winter"), reverse=True)
    return rows


@app.get("/api/workspace/{team}")
def workspace(team: str, players: str = "", league: str = ACTIVE_LEAGUE):
    """TRANSFER WORKSPACE — 예산(최근 두 창 지출·구단 가격 상한·이적 정책) + 라이벌 + 고정 후보(SHORTLIST)의 최신 사실.
    players = JSON [{player, club, league}] — 후보마다 우리 리그 기준 예상 OVR(다른 리그면 리그 수준 보정)·나이·시장가·
    예상 이적료(시장가 ×1.2)와 가격 현실성·계약 남은 개월·출전·골·도움·평점·정책 대조·영입 가능성·라이벌 소속 여부."""
    import json as _json  # noqa: PLC0415

    import club_profile as cp  # noqa: PLC0415
    import positions as ps  # noqa: PLC0415
    import scout_report as sr  # noqa: PLC0415
    pol = None
    try:
        pol = _transfer_policy(team)
    except Exception:  # noqa: BLE001
        pass
    try:
        aff = cp.affordability(team) or {}
    except Exception:  # noqa: BLE001
        aff = {}
    wins = _window_spend(team, league)
    last2 = [w for w in wins if w["n_in"] or w["n_out"]][:2]
    rivals = _club_rivals(team)
    try:
        team_ovr = _position_needs(team, league)["team_ovr"] or 80.0
    except Exception:  # noqa: BLE001
        team_ovr = 80.0
    try:
        want = _json.loads(players) if players else []
    except ValueError:
        want = []
    out = []
    for w in want[:12]:
        name, club, src = str(w.get("player") or ""), str(w.get("club") or ""), str(w.get("league") or league)
        pf = _pf(src)
        row = None
        if pf is not None and "player" in pf.columns:
            cand = pf[pf["player"].astype(str).map(ps.norm_name) == ps.norm_name(name)]
            if len(cand) > 1 and "squad" in cand.columns:
                same = cand[cand["squad"].astype(str) == club]
                cand = same if len(same) else cand
            if len(cand):
                row = cand.sort_values("minutes", ascending=False).iloc[0] if "minutes" in cand.columns else cand.iloc[0]
        if row is None:
            out.append({"player": name, "club": club, "league": src, "found": False})
            continue
        cur = _player_ovr(row)
        proj = cur
        if src != league and cur:
            proj, _p, _r = _project_ovr(cur, src, league, False, row.get("age"), _pos_bucket(row))
        value = _num(row.get("market_value_eur")) or None
        fee = value * 1.2 if value else None
        pr = cp.price_realism(team, fee)
        con = sr.contract(row.get("tm_contract_until"))
        pf_ = _policy_fit(pol, row.get("age"), value)
        cstr = _club_strength(src).get(str(row.get("squad") or club), 78)
        key = _num(row.get("minutes")) >= _mm(2000, src)
        realistic = not (key and ((src == league and cstr >= team_ovr - 6) or cstr >= team_ovr - 3))
        is_rival = str(row.get("squad") or club) in rivals
        out.append({"player": str(row["player"]), "club": str(row.get("squad") or club), "league": src, "found": True,
                    "pos": _pos_label(row), "tm_position": str(row.get("tm_position") or ""), "age": int(_num(row.get("age"))) or None,
                    "photo": _photo(row), "ovr": proj, "current_ovr": cur, "cross_league": src != league,
                    "value_eur": value, "likely_fee_eur": round(fee) if fee else None, "price_verdict": pr.get("verdict"),
                    "contract_until": con["until"], "months_left": con["months_left"], "contract_status": con["status"],
                    "minutes": int(_num(row.get("minutes"))), "goals": int(_num(row.get("goals"))), "assists": int(_num(row.get("assists"))),
                    "rating": _num(row.get("ss_rating")) or None,
                    "policy_ok": pf_["ok"], "policy_notes": pf_["notes"], "realistic": realistic and not is_rival, "rival": is_rival,
                    "logo": tm.team_logo(str(row.get("squad") or club))})
    avg_spend = sum(w["spend"] for w in last2) / len(last2) if last2 else None
    return {"team": team, "team_ovr": team_ovr, "windows": last2, "avg_spend": avg_spend,
            "ceiling_eur": aff.get("price_ceiling_eur"), "spend_tier": aff.get("spend_tier"), "policy": pol,
            "rivals": sorted(rivals), "shortlist": out}


@app.get("/api/squad-graph/{team}")
@_memo(ttl=21600)
def squad_graph_ep(team: str, league: str = ACTIVE_LEAGUE):
    """스쿼드 네트워크 — KG(Neo4j) TEAMMATE_OF 로 '같이 뛴' 관계 그래프. 미가동 시 degrade."""
    import kg_graph  # noqa: PLC0415 (지연 import — Neo4j 의존)
    return kg_graph.squad_graph(team, min_matches=6, edge_limit=32)


def _on_pitch(team: str, league: str) -> tuple[dict[str, dict], int]:
    """경기별 출전 구간 {event_id: {선수: (들어간 분, 나간 분)}}, 경기 수 — 라인업(선발)+교체 기록(리그·컵)."""
    lu, subs = _lineups(league), _subs(league)
    if lu is None or lu.empty:
        return {}, 0
    lu = lu[lu["squad"] == team]
    if lu.empty:
        return {}, 0
    starter = lu["starter"].astype(str).str.lower().isin(["true", "1", "1.0"])
    side = lu.groupby("event_id")["home_away"].first().to_dict()
    sub_in: dict = {}
    sub_out: dict = {}
    if subs is not None and not subs.empty:
        for _, r in subs.iterrows():
            eid = r.get("event_id")
            if side.get(eid) != r.get("home_away"):
                continue
            m = _num(r.get("minute_sec")) / 60 or _num(str(r.get("minute") or "").rstrip("'"))
            pin = str(r.get("player_in") or "").strip()
            pout = re.split(r" because | due to ", str(r.get("player_out") or ""))[0].strip()
            if pin:
                sub_in[(eid, pin)] = m
            if pout:
                sub_out[(eid, pout)] = m
    out: dict[str, dict] = {}
    for (eid, pl), st in zip(zip(lu["event_id"], lu["player"].astype(str)), starter):
        a = 0.0 if st else sub_in.get((eid, pl))
        if a is None:                                     # 벤치에서 안 들어온 선수
            continue
        b = sub_out.get((eid, pl), 90.0)
        if b > a:
            out.setdefault(eid, {})[pl] = (a, b)
    return out, len(out)


@app.get("/api/chemistry/{team}")
@_memo(ttl=21600)
def chemistry_ep(team: str, league: str = ACTIVE_LEAGUE):
    """케미스트리 — 실제로 함께 그라운드에 있던 시간(라인업·교체 기록)으로 최고의 듀오·삼각편대.

    예전엔 KG TEAMMATE_OF '함께 뛴 경기 수 ÷ 최다'라 시즌 초엔 거의 모든 조합이 100 이었다(2026-10).
    한 선수가 카드를 독차지하지 않게 듀오는 선수당 최대 2번. 라인업이 없으면 KG 경기 수로 폴백.
    """
    pf = _pf(league)
    pmap, lmap = {}, {}
    if pf is not None and "player" in pf.columns:
        for _, r in pf[pf["squad"] == team].iterrows():
            pmap[str(r.get("player"))] = _photo(r)
            lmap[str(r.get("player"))] = (rv3.line_of_row(r), str(r.get("pos") or ""))

    def card(name: str, node: dict | None = None) -> dict:
        line, pos = lmap.get(name, ((node or {}).get("line", "MID"), (node or {}).get("pos", "")))
        return {"name": name, "line": line, "pos": pos, "rating": (node or {}).get("rating"), "photo": pmap.get(name, "")}

    def pick_duos(scored: list[tuple[str, str, float, int]]) -> list[tuple]:
        used: dict[str, int] = {}
        picked = []
        for a, b, v, n in sorted(scored, key=lambda x: (-x[2], -x[3])):
            if used.get(a, 0) >= 2 or used.get(b, 0) >= 2:
                continue
            picked.append((a, b, v, n))
            used[a] = used.get(a, 0) + 1
            used[b] = used.get(b, 0) + 1
            if len(picked) == 8:
                break
        return picked

    games, n_games = _on_pitch(team, league)
    if n_games:
        tot: dict[str, float] = {}
        for g in games.values():
            for pl, (a, b) in g.items():
                tot[pl] = tot.get(pl, 0) + (b - a)
        core = [pl for pl, _ in sorted(tot.items(), key=lambda x: -x[1])[:14]]

        def overlap(names) -> tuple[float, int]:
            mins, n = 0.0, 0
            for g in games.values():
                if all(x in g for x in names):
                    o = min(g[x][1] for x in names) - max(g[x][0] for x in names)
                    if o > 0:
                        mins += o
                        n += 1
            return mins, n

        pairs = []
        for i, a in enumerate(core):
            for b in core[i + 1:]:
                m, n = overlap((a, b))
                if n >= 2:
                    pairs.append((a, b, m, n))
        full = n_games * 90
        duos = [{"a": card(a), "b": card(b), "matches": n, "minutes": round(m),
                 "chem": min(100, round(m / full * 100))} for a, b, m, n in pick_duos(pairs)]
        trios = []
        top = core[:9]
        for i, a in enumerate(top):
            for j in range(i + 1, len(top)):
                for c in top[j + 1:]:
                    m, n = overlap((a, top[j], c))
                    if n >= 2:
                        trios.append({"players": [card(a), card(top[j]), card(c)], "score": n, "minutes": round(m)})
        trios.sort(key=lambda t: -t["minutes"])
        seen_lead: set[str] = set()
        trios_div = []
        for t in trios:                                   # 같은 두 사람 조합 반복 방지 — 첫 두 명 기준
            k = "|".join(sorted(p["name"] for p in t["players"][:2]))
            if k in seen_lead:
                continue
            seen_lead.add(k)
            trios_div.append(t)
            if len(trios_div) == 4:
                break
        return {"available": True, "team": team, "basis": "minutes", "games": n_games, "duos": duos, "trios": trios_div}

    import kg_graph  # noqa: PLC0415
    g = kg_graph.squad_graph(team, min_matches=4, edge_limit=300)
    if not g.get("available"):
        return {"available": False, "reason": g.get("reason", ""), "duos": [], "trios": []}
    edges = g.get("edges", [])
    if not edges:
        return {"available": True, "team": team, "duos": [], "trios": []}
    nodes = {n["id"]: n for n in g.get("nodes", [])}
    maxm = max(e["matches"] for e in edges) or 1
    duos = [{"a": card(a, nodes.get(a)), "b": card(b, nodes.get(b)), "matches": n, "chem": round(n / maxm * 100)}
            for a, b, _, n in pick_duos([(e["a"], e["b"], e["matches"], e["matches"]) for e in edges])]
    return {"available": True, "team": team, "basis": "matches", "duos": duos, "trios": []}


@app.get("/api/calendar")
@_memo(ttl=1800)
def calendar(league: str = ACTIVE_LEAGUE):
    """상태바 달력 — 리그 일정·이적시장에서 자동 생성(수기 calendar_events.csv 는 월드컵 같은 특별 이벤트만).

    예전엔 수기 파일만 읽어 '26/27 개막 8/14' 같은 지난 일정이 시즌 내내 남았다.
    """
    today = datetime.date.today()
    iso = today.isoformat()
    events: list[dict] = []

    cal = ds.read_table("calendar_events")
    if cal is not None:
        for _, r in cal.iterrows():
            end = str(r.get("end") or r.get("start") or "")
            if end >= iso:
                events.append({"name": str(r.get("name") or ""), "start": str(r.get("start") or ""),
                               "end": end, "icon": str(r.get("icon") or ""), "kind": str(r.get("kind") or "event")})

    try:
        lname = league_config(league).name
    except KeyError:
        lname = league
    sf = ds.read_table("schedule_full", league=league)
    if sf is not None and "date" in sf.columns:
        sf = sf[sf["date"].astype(str) >= iso]
        code = sf["comp_code"].astype(str)
        nxt_league = sf[code.str.endswith(".1")]["date"].min()
        if isinstance(nxt_league, str):
            events.append({"name": f"{lname} 다음 라운드", "start": nxt_league, "end": nxt_league, "icon": "⚽", "kind": "kickoff"})
        euro = sf[code.str.startswith("uefa.")]
        if not euro.empty:
            d0 = euro["date"].min()
            comp = str(euro[euro["date"] == d0]["comp"].iloc[0])
            events.append({"name": f"{comp} 매치데이", "start": d0, "end": d0, "icon": "⭐", "kind": "kickoff"})
        last = sf[code.str.endswith(".1")]["date"].max()
        if isinstance(last, str) and last != nxt_league:
            events.append({"name": f"{lname} 최종전", "start": last, "end": last, "icon": "🏁", "kind": "kickoff"})

    # 이적시장 — 열려 있으면 그 창, 아니면 다음 창(겨울 1/1~2/3 → 여름 6/14~9/1)
    win = _current_window()
    y = int(win["season_id"])
    windows = [("겨울 이적시장", f"{y + 1}-01-01", f"{y + 1}-02-03"), ("여름 이적시장", f"{y + 1}-06-14", f"{y + 1}-09-01")]
    if win["is_open"]:
        name = "여름 이적시장" if win["window"] == "summer" else "겨울 이적시장"
        end = f"{y}-09-01" if win["window"] == "summer" else f"{y + 1}-02-03"
        start = f"{y}-06-14" if win["window"] == "summer" else f"{y + 1}-01-01"
        events.append({"name": name, "start": start, "end": end, "icon": "🔁", "kind": "window"})
    else:
        for name, start, end in windows:
            if end >= iso:
                events.append({"name": name, "start": start, "end": end, "icon": "🔁", "kind": "window"})
                break

    events.sort(key=lambda e: e["start"])
    return {"events": events}


@app.get("/api/heatmaps/{team}")
@_memo(ttl=21600)
def heatmaps(team: str, league: str = ACTIVE_LEAGUE):
    """팀 선수별 시즌 히트맵(Sofascore) — analytics 포지셔널 히트맵용. norm_key 로 players_full 조인."""
    hm = ds.read_table("player_heatmaps", league=league)
    if hm is None or hm.empty or "norm_key" not in hm.columns:
        return {"available": False, "team": team, "players": []}
    pf = _pf(league)
    if pf is None or pf.empty:
        return {"available": False, "team": team, "players": []}
    tp = pf[pf["squad"].astype(str) == team].copy()
    if tp.empty:
        return {"available": False, "team": team, "players": []}
    tp["_mn"] = pd.to_numeric(tp.get("minutes"), errors="coerce").fillna(0)
    meta = {}
    for _, r in tp.iterrows():
        k = str(r.get("norm_key") or "")
        if k:
            meta[k] = {"player": str(r.get("player") or ""), "pos": str(_pos_profile(r).get("primary") or r.get("pos") or ""),
                       "line": rv3.line_of_row(r),
                       "minutes": int(r["_mn"]), "ovr": _player_ovr(r), "photo": _photo(r)}
    gw = gh = None
    players = []
    for _, r in hm.iterrows():
        k = str(r.get("norm_key") or "")
        if k not in meta:
            continue
        try:
            grid = [int(x) for x in str(r.get("grid") or "").split()]
        except ValueError:
            continue
        if not grid:
            continue
        gw = int(_num(r.get("gw"))) or 12
        gh = int(_num(r.get("gh"))) or 8
        # Sofascore 세로축은 화면과 반대 — 그대로 그리면 '공격 →' 피치에서 오른쪽 윙(Saka·Yamal)이 위(왼쪽)로 갔다.
        # 공격 방향을 오른쪽으로 둘 때 오른쪽 측면이 아래가 되도록 행을 뒤집는다(2026-10-15 사용자 지적).
        if len(grid) == gw * gh:
            grid = [v for row in reversed([grid[i * gw:(i + 1) * gw] for i in range(gh)]) for v in row]
        players.append({**meta[k], "n_points": int(_num(r.get("n_points"))), "grid": grid})
    players.sort(key=lambda p: -p["minutes"])
    players = players[:26]
    # 연결선 — 함께 그라운드에 있던 시간(라인업·교체). 패스 데이터가 아니라 '같이 뛴 시간' 관계.
    links = []
    try:
        import team_network as tn  # noqa: PLC0415
        games, _ = _on_pitch(team, league)
        g = tn.chemistry_graph(games, [p["player"] for p in players], min_edge=90, max_edges=120)
        names = {p["player"] for p in players}
        links = [e for e in g["edges"] if e["a"] in names and e["b"] in names]
    except Exception:  # noqa: BLE001
        links = []
    return {"available": len(players) > 0, "team": team, "gw": gw or 12, "gh": gh or 8, "players": players,
            "links": links, "orientation": "attack-right"}


def _lineups(league: str):
    """espn_lineups(리그) + 컵·유럽 라인업 concat — 스케줄/경기상세용. 리그별 파일."""
    base = ds.read_table("espn_lineups", league=league)
    cup = ds.read_table("espn_lineups_cups", league=league)          # 이름 정규화(player_names) 거침
    if base is None:
        return cup
    if cup is None:
        return base
    return pd.concat([base, cup], ignore_index=True)


def _subs(league: str):
    """espn_subs(리그) + 컵·유럽 교체 concat."""
    base = ds.read_table("espn_subs", league=league)
    cup = ds.read_table("espn_subs_cups", league=league)          # 이름 정규화(player_names) 거침
    if base is None:
        return cup
    if cup is None:
        return base
    return pd.concat([base, cup], ignore_index=True)


def _player_ovr(row) -> int:
    # v3 절대 OVR = 커리어 클래스 (시장가+포지션 공정보정+검증/베테랑, GK 는 선방%/CS%, 빅매치 소량 가산)
    # 라인은 역할(tm_position) 우선, 평점은 표본 수축·리그 보정(_league_level — player_frame 이 붙임).
    # player_frame 이 미리 계산한 `_ovr` 가 있으면 그대로(이적 반영용 가상 행 등은 없어서 계산).
    v = row.get("_ovr")
    if v is not None and v == v:
        return int(v)
    return rv3.ovr_of_row(row)


def _recent_score(row):
    """최근 폼 점수(최근 5경기, 45~99) — player_frame 의 `_recent`(src/recent_form.py). 2경기 미만이면 None."""
    v = row.get("_recent")
    return int(v) if v is not None and v == v else None


def _num_or_none(v):
    v = pd.to_numeric(v, errors="coerce")
    return None if v is None or pd.isna(v) else (int(v) if float(v).is_integer() else round(float(v), 2))


def _player_form(row):
    fm = row.get("_form")                          # player_frame 이 붙인 리그 내 순위 폼(우선)
    if fm is not None and fm == fm:
        return int(fm)
    return rv3.form_rating(
        ss_rating=row.get("ss_rating"), minutes=row.get("minutes"),
        goals=row.get("goals"), assists=row.get("assists"),
        pos_group=rv3.line_of_row(row),
        prev_ss_rating=row.get("prev_ss_rating"), prev_minutes=row.get("prev_minutes"),
    )


def _player_pot(row) -> int:
    return rv3.potential(absolute=_player_ovr(row), age=row.get("age"),
                         value=row.get("market_value_eur"))


# ── 평점 추이(2주 전 대비 · 지난 시즌 대비) — src/rating_history.py ─────────────
@_memo(ttl=3600)
def _trend_base(league: str) -> dict:
    import rating_history as rh  # noqa: PLC0415
    return rh.trend_baseline(league)


@_memo(ttl=21600)
def _prev_season() -> dict:
    import rating_history as rh  # noqa: PLC0415
    return rh.prev_season_ovr()


def _trend(row, league: str, ovr: int | None = None, form: int | None = None) -> dict:
    """{ovr_d, form_d: 2주 전 대비(기록이 2주치 쌓여야 생김), ovr_prev: 지난 시즌 OVR(300분+ 뛴 경우)}."""
    import rating_history as rh  # noqa: PLC0415
    ovr = _player_ovr(row) if ovr is None else ovr
    form = _player_form(row) if form is None else form
    out: dict = {"ovr_d": None, "form_d": None, "ovr_prev": None}
    base = _trend_base(league).get(rh.pid(row))
    if base:
        out["ovr_d"] = ovr - base["ovr"]
        if form is not None and base["form"] is not None:
            out["form_d"] = form - base["form"]
    prev = rh.lookup_prev(_prev_season(), row)
    # 지난 시즌 값이 유망주 검증 보정에 걸렸으면(출전 부족으로 60 쪽으로 깎인 값) 비교하지 않는다
    if prev and prev.get("minutes", 0) >= 300 and not prev.get("gated"):
        out["ovr_prev"] = prev["ovr"]
    return out


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
        idx = {"exact": exact, "last": last, "league": league}
    except (OSError, KeyError, ValueError):
        idx = {"exact": {}, "last": {}, "league": league}   # 사용량 없음 — 역할은 리그 출전만으로
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


@_memo(ttl=3600)
def _inj_missed_league(league: str) -> dict:
    """{(squad, norm_key): 이번 시즌 부상으로 빠진 리그 경기 수, '_played': {squad: 리그 경기 수}} — 역할 판정 분모 보정.
    TM 부상 이력 spells(from~until, 진행 중이면 오늘까지) 안에 열린 팀 리그 경기를 센다."""
    import json as _json  # noqa: PLC0415
    from unidecode import unidecode  # noqa: PLC0415
    out: dict = {"_played": {}}
    sch = ds.read_table("schedule_full", league=league)
    hist = ds.read_table("tm_injury_history", league=league)
    if sch is None or sch.empty:
        return out
    lg = sch[(sch["comp_code"].astype(str).str.endswith(".1")) & (sch["status"].astype(str) == "completed")]
    dates = {sq: sorted(pd.to_datetime(g["date"], errors="coerce").dropna().dt.date) for sq, g in lg.groupby("squad")}
    out["_played"] = {str(sq): len(ds_) for sq, ds_ in dates.items()}
    if hist is None or hist.empty or "spells_json" not in hist.columns:
        return out
    label = f"{SEASON_START % 100:02d}/{(SEASON_START + 1) % 100:02d}"
    today = _today_kst()
    cur = hist[hist["season"].astype(str) == label] if "season" in hist.columns else hist   # 통합 DB 표는 이번 시즌만
    for r in cur.itertuples(index=False):
        try:
            spells = _json.loads(r.spells_json) if isinstance(r.spells_json, str) else []
        except ValueError:
            continue
        md = dates.get(str(r.squad), [])
        n = 0
        for s in spells:
            try:
                a = datetime.datetime.strptime(str(s.get("from")), "%d/%m/%Y").date()
            except ValueError:
                continue
            try:
                b = datetime.datetime.strptime(str(s.get("until")), "%d/%m/%Y").date()
            except ValueError:
                b = today                                # 진행 중
            n += sum(1 for d in md if a <= d <= b)
        if n:
            out[(str(r.squad), unidecode(str(r.player)).lower().strip())] = n
    return out


def _comp_profile(row, usage_idx) -> dict:
    """players_full 행 + comp usage → 역할 + 대회별 상세(선발/출전).

    role/big_match 는 리그분 + 유럽/컵 사용량 기반. comps 는 출전>0 대회만.
    comp usage 없으면(라리가 등) comps=[], 역할은 리그분만으로 폴백.
    """
    u = _usage_for(usage_idx, row.get("squad"), row.get("norm_key")) or {}
    es, ea = _num(u.get("euro_starts")), _num(u.get("euro_apps"))
    cs, ca = _num(u.get("cup_starts")), _num(u.get("cup_apps"))
    lm = _num(row.get("minutes"))
    # 역할 임계값(리그 1800′·유럽 6선발 등)은 풀시즌 기준 — 시즌 초엔 전원 '백업'이 되므로
    # 리그 진행률로 풀시즌 환산해 판정한다(끝난 시즌은 진행률 1.0 → 그대로).
    lg = (usage_idx or {}).get("league")
    scale = 1.0 / _progress(lg) if lg else 1.0
    # 부상으로 빠진 리그 경기는 분모에서 뺀다 — 종아리 부상 6경기 결장한 Doku 가 '백업'으로 나왔다(2026-10-20 점검)
    missed = 0
    if lg:
        inj = _inj_missed_league(lg)
        missed = inj.get((str(row.get("squad")), str(row.get("norm_key") or "")), 0)
        played = inj["_played"].get(str(row.get("squad")), 0)
        if missed and played > missed:
            scale *= played / max(played - missed, min(played, 3))   # 뛸 수 있던 경기가 너무 적으면 과대평가 — 최소 3경기
    role = rv3.role_tag(league_min=min(lm * scale, 3420.0), euro_starts=es * scale, euro_apps=ea * scale,
                        cup_starts=cs * scale, cup_apps=ca * scale, age=row.get("age"))
    comps = []
    for key, label in _COMP_LABELS:
        st, ap = int(_num(u.get(f"{key}_starts"))), int(_num(u.get(f"{key}_apps")))
        if ap > 0:
            comps.append({"key": key, "label": label, "starts": st, "apps": ap})
    parts = [f"리그 {int(lm)}′"] + [f"{c['label']} {c['starts']}선발" for c in comps if c["starts"]] \
        + ([f"부상 결장 {missed}경기 제외"] if missed else [])
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
    # 임대 보낸 선수는 지금 우리 스쿼드가 아니다 — 시즌 초 몇 분 뛰고 떠난 Grealish(City 9분, 사진·나이 없는 행)가
    # 벤치·스쿼드에 남았다(2026-10-15). 'ON LOAN' 목록(_loans_out)으로 따로 보여 준다.
    lo = _loans_out(team, league)
    if lo and not df.empty:
        df = df[~df["player"].map(lambda n: _is_loaned(n, lo))]
    return df


def _is_loaned(name, lo: dict) -> bool:
    """임대 목록에 있는가 — 이적 기록 출처는 (성, 이름 첫 글자), 위키 출처는 전체 이름까지 같아야(동명이인 방지)."""
    v = lo.get(_person_key(name))
    if v is None:
        return False
    if v.get("source") == "transfer":
        return True
    from unidecode import unidecode  # noqa: PLC0415
    nn = lambda s: unidecode(str(s or "")).lower().replace("-", " ").strip()  # noqa: E731
    return nn(name) == nn(v.get("player"))


@_memo(ttl=21600)
def _contracts_all() -> dict:
    """{_person_key: TM 계약 행(dict, league 포함)} — 전 리그 TM 스쿼드 명단. 임대 간 선수의 현재 팀·사진·입단일 찾기용.
    같은 키가 여러 팀이면(동명이인) 모호해서 뺀다."""
    from leagues import LEAGUES  # noqa: PLC0415
    out: dict = {}
    dup: set = set()
    for lg in LEAGUES:
        try:
            ct = ds.read_table("transfermarkt_contracts", league=lg)
        except Exception:  # noqa: BLE001
            ct = None
        if ct is None or "player" not in ct.columns:
            continue
        for r in ct.to_dict("records"):
            k = _person_key(r.get("player"))
            if k in out and out[k].get("squad") != r.get("squad"):
                dup.add(k)
            out[k] = {**r, "league": lg}
    for k in dup:
        out.pop(k, None)
    return out


def _win_order(year, window) -> int:
    return int(_num(year)) * 2 + (1 if str(window).lower().startswith("summer") else 0)


@_memo(ttl=21600)
def _loans_out(team: str, league: str) -> dict:
    """{_person_key: {player, club, photo, pos, nat, source}} — 임대 보낸 선수(계약은 우리, 지금은 다른 팀에서 뛴다).

    1) 이번 시즌 이적 기록 OUT 중 임대(같은 선수의 더 늦은 '임대 종료' IN 이 있으면 복귀한 것)
    2) 위키 스쿼드 'Out on loan' 섹션 — TM 계약 명단에서 다른 팀 소속이면 그 팀이 행선지,
       우리 팀 소속으로 나오면 이미 복귀한 것이라 뺀다. 우리 리그 밖으로 간 선수는 행선지 미상.
    """
    out: dict = {}
    ca = _contracts_all()
    tr = ds.read_table("transfers", league=league)
    if tr is not None and "squad" in tr.columns:
        t = tr[tr["squad"] == team]
        eol = lambda f: str(f or "").lower().startswith("end of loan")  # noqa: E731
        back = {}
        for r in t[(t["direction"] == "in") & t["fee_text"].map(eol)].to_dict("records"):
            back[_person_key(r["player"])] = max(back.get(_person_key(r["player"]), -1), _win_order(r.get("season_id"), r.get("window")))
        for r in t[(t["direction"] == "out") & t["fee_text"].map(_is_loan_move)].to_dict("records"):
            k = _person_key(r["player"])
            if back.get(k, -1) > _win_order(r.get("season_id"), r.get("window")):
                continue
            ph = str(r.get("photo") or "")
            out[k] = {"player": str(r["player"]), "club": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                      "nat": str(r.get("nat") or ""), "photo": ph if ph.startswith("http") else "", "source": "transfer"}
    import difflib  # noqa: PLC0415
    from unidecode import unidecode  # noqa: PLC0415
    _nn = lambda s: unidecode(str(s or "")).lower().replace("-", " ").strip()  # noqa: E731

    def _dup(name) -> bool:   # 표기만 다른 같은 선수('Dastan Satpaev' ↔ 'Satpayev')
        n = _nn(name)
        return any(difflib.SequenceMatcher(None, n, _nn(v["player"])).ratio() >= 0.85 for v in out.values())
    for r in _wiki_squad(team, league):
        if r.get("section") == "loan":
            k = _person_key(r.get("player"))
            if k in out or _dup(r.get("player")):
                continue
            c = ca.get(k)
            if c is not None and str(c.get("squad")) == team:
                continue          # TM 은 우리 팀 소속 — 복귀했거나 위키가 늦음
            ph = str((c or {}).get("tm_photo") or "")
            out[k] = {"player": str(r.get("player") or ""), "club": str((c or {}).get("squad") or ""),
                      "pos": str(r.get("pos") or ""), "nat": str(r.get("nat") or ""),
                      "photo": ph if ph.startswith("http") else "", "source": "wiki"}
    # 위키 1군 표에 있는데 TM 계약 명단상 다른 팀 소속 — 임대 섹션을 따로 두지 않는 위키 표(Man City 등).
    # 팔린 선수(이번 창 이탈)는 위키가 늦게 고친 것이라 뺀다.
    try:
        deps = _departures(team, league, _current_window())
    except Exception:  # noqa: BLE001
        deps = {}
    for r in _wiki_squad(team, league):
        if r.get("section") != "first":
            continue
        k = _person_key(r.get("player"))
        c = ca.get(k)
        if k in out or c is None or str(c.get("squad")) == team or _dep_last(r.get("player")) in deps                 or _dup(r.get("player")):
            continue
        ph = str(c.get("tm_photo") or "")
        out[k] = {"player": str(r.get("player") or ""), "club": str(c.get("squad") or ""),
                  "pos": str(r.get("pos") or ""), "nat": str(r.get("nat") or ""),
                  "photo": ph if ph.startswith("http") else "", "source": "wiki"}
    for k, v in out.items():
        c = ca.get(k)
        if c is not None and not v["photo"]:
            ph = str(c.get("tm_photo") or "")
            v["photo"] = ph if ph.startswith("http") else ""
    return out


def _loan_details(team: str, league: str) -> list[dict]:
    """임대 보낸 선수 + 임대지 이번 시즌 출전·OVR(우리 데이터 안 리그) — 스쿼드 화면 OUT ON LOAN 전용.
    다른 리그 선수 표를 불러와야 해서 _loans_out(Overview·팀 OVR 이 매번 부름)에서 뺐다."""
    ca = _contracts_all()
    out = []
    for k, v0 in _loans_out(team, league).items():
        v = {**v0, "minutes": None, "ovr": None}
        c = ca.get(k)
        if c is not None and str(c.get("squad")) != team:
            try:
                f2 = _pf(c["league"])
                hit = f2[(f2["squad"] == c["squad"]) & (f2["player"].map(_person_key) == k)] if f2 is not None else None
                if hit is not None and not hit.empty:
                    h = hit.iloc[0]
                    v["minutes"] = int(_num(h.get("minutes")))
                    v["ovr"] = _player_ovr(h)
                    v["club"] = v["club"] or str(c["squad"])
                    v["photo"] = v["photo"] or _photo(h)
            except Exception:  # noqa: BLE001
                pass
        out.append(v)
    return out


@_memo(ttl=21600)
def _prev_rows() -> pd.DataFrame:
    """pid(tm id) → 지난 시즌 선수 행(출전 가장 많은 것) — 이번 시즌 출전 없는 스쿼드 선수 보강용."""
    import rating_history as rh  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    season = f"{SEASON_START - 1}_{SEASON_START}"
    frames = []
    for lg in LEAGUES:
        df = _pf(lg, season)
        if df is None or "tm_id" not in df.columns:
            continue
        tid = pd.to_numeric(df["tm_id"], errors="coerce")
        sub = df[tid.notna()].copy()
        sub["_pid"] = "tm" + tid[tid.notna()].astype("int64").astype(str)
        sub["_mn"] = pd.to_numeric(sub.get("minutes"), errors="coerce").fillna(0)
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    # 한 선수가 여러 행(시즌 중 이적)이면 출전이 가장 많은 행. 표 그대로(pid 색인) 두고 필요한 행만 꺼낸다 —
    # 예전엔 전 리그 ~5천 행을 iterrows 로 dict 로 풀어(운영 0.1 CPU 에서 수십 초 · 메모리 수십 MB) 데우기가 길어졌다.
    allp = pd.concat(frames, ignore_index=True).sort_values("_mn", ascending=False).drop_duplicates("_pid")
    return allp.drop(columns=["_mn"]).set_index("_pid")


def _roster_extras(team: str, league: str, df) -> list[dict]:
    """이번 시즌 출전이 없어 players_full 에 없는 스쿼드 선수(TM 스쿼드 명단 = 계약 데이터).

    예전엔 출전자만 보여 백업 GK(케파·메슬리에)·부상 장기 결장(살리바)이 스쿼드에서 빠지고 뎁스 차트가
    'GK 백업 없음'이라고 했다. 포지션·시장가치·직전 평점은 지난 시즌 기록(tm id)에서 가져오고,
    지난 시즌 기록도 없는 선수(유스 등)는 포지션을 몰라 넣지 않는다.
    """
    import league_level  # noqa: PLC0415
    ct = ds.read_table("transfermarkt_contracts", league=league)
    if ct is None or "squad" not in ct.columns:
        return []
    have_tm = {str(int(_num(t))) for t in df.get("tm_id", pd.Series(dtype=float)).dropna()} if df is not None else set()
    have_nk = set(df["norm_key"].astype(str)) if df is not None and "norm_key" in df.columns else set()
    prev = _prev_rows()
    out = []
    for _, r in ct[ct["squad"] == team].iterrows():
        tid = str(int(_num(r.get("tm_id")))) if pd.notna(r.get("tm_id")) else ""
        if (tid and tid in have_tm) or str(r.get("norm_key")) in have_nk:
            continue
        pid = f"tm{tid}" if tid else None
        if pid is None or prev.empty or pid not in prev.index:
            continue
        pr = prev.loc[pid].to_dict()
        row = dict(pr)
        row.update({
            "player": r.get("player"), "squad": team, "norm_key": r.get("norm_key"), "tm_id": r.get("tm_id"),
            "minutes": 0, "goals": 0, "assists": 0, "ss_rating": None,
            "prev_minutes": pr.get("minutes"), "prev_ss_rating": pr.get("ss_rating"),
            "age": (_num(pr.get("age")) + 1) if pr.get("age") is not None else None,
            "tm_photo": r.get("tm_photo") or pr.get("tm_photo"),
            "_ovr": None, "_form": None, "_league_level": league_level.level(league),
            "left_for": None, "_roster_only": True,
        })
        out.append(row)
    return out


@_memo(ttl=21600)
def _role_counts_all() -> dict:
    """전 리그 ESPN 선발 라인업(이번 시즌 1.0 + 지난 시즌 0.5) → {이름: Counter(역할)} — src/positions.py.
    이적생은 전 소속 리그 파일에서 이름으로 찾는다. 6시간 캐시(서버 시작 때 미리 계산)."""
    # player_data.role_counts(이번 시즌)와 같은 계산 — 하나로 써서 두 번 읽지 않고, 빌드 캐시도 같이 쓴다
    from api.services.player_data import role_counts  # noqa: PLC0415
    return role_counts(None)


def _pos_profile(r) -> dict:
    """선수 주포지션·2/3포지션(실제로 선 자리 우선, 부족하면 TM)."""
    import positions as ps  # noqa: PLC0415
    tmp = r.get("tm_position") if hasattr(r, "get") else None
    return ps.profile(ps.lookup(_role_counts_all(), r.get("player")), tmp if isinstance(tmp, str) else None)


def _parse_dmy(s) -> str | None:
    """'24/09/2026' → '2026-09-24'."""
    t = str(s or "").strip()
    if len(t) == 10 and t[2] == "/" and t[5] == "/":
        return f"{t[6:]}-{t[3:5]}-{t[:2]}"
    return None


@_memo(ttl=1800)
def _injury_returns(league: str) -> dict:
    """{(팀, 정규화 이름): {date, since}} — TM 은 '부상'인데 부상 시작일 뒤에 실제로 뛴(선발·교체) 선수.

    Transfermarkt 부상 목록은 갱신이 늦다 — Havertz(9/24 허벅지)가 10/10 선발·10/18 출전 뒤에도 '부상'으로 남아
    신뢰도가 떨어져 보였다(2026-10-19 사용자 지적). 시작일은 TM 부상 이력(spells)의 열린 구간 → 없으면 부상 변경
    감지일. 둘 다 없으면 최근 14일 안 출전만 본다."""
    import positions as ps  # noqa: PLC0415
    inj = ds.read_table("transfermarkt_injuries", league=league)
    if inj is None or inj.empty or "squad" not in inj.columns:
        return {}
    if "active" in inj.columns:
        inj = inj[inj["active"].astype(str).str.lower().isin({"true", "1", "yes", "y"})]
    since: dict = {}
    hist = ds.read_table("tm_injury_history", league=league)
    if hist is not None and not hist.empty and "spells_json" in hist.columns:
        for sq, pl, sj in zip(hist["squad"].astype(str), hist["player"].astype(str), hist["spells_json"]):
            try:
                spells = json.loads(sj) if isinstance(sj, str) and sj.strip() else []
            except ValueError:
                spells = []
            opens = [_parse_dmy(s.get("from")) for s in spells if not str(s.get("until") or "").strip()]
            opens = [d for d in opens if d]
            if opens:
                since[(sq, ps.norm_name(pl))] = max(opens)
    ch = ds.read_table("transfermarkt_injury_changes", league=league)
    if ch is not None and not ch.empty and {"event_type", "run_date"} <= set(ch.columns):
        for sq, pl, ev, d in zip(ch["squad"].astype(str), ch["player"].astype(str), ch["event_type"].astype(str), ch["run_date"].astype(str)):
            if ev.lower().startswith("new"):
                since.setdefault((sq, ps.norm_name(pl)), d[:10])
    seen: dict = {}                                       # (팀, 이름) → 마지막 출전일
    for stem in ("espn_lineups", "espn_lineups_cups"):
        el = ds.read_table(stem, league=league)
        if el is None or el.empty:
            continue
        st = el[pd.to_numeric(el["starter"], errors="coerce") == 1]
        for sq, pl, d in zip(st["squad"].astype(str), st["player"].astype(str), st["date"].astype(str)):
            k = (sq, ps.norm_name(pl))
            seen[k] = max(seen.get(k, ""), d[:10])
    for stem in ("espn_subs", "espn_subs_cups"):
        sb = ds.read_table(stem, league=league)
        if sb is None or sb.empty or "player_in" not in sb.columns or "squad" not in sb.columns:
            continue
        el = ds.read_table(stem.replace("subs", "lineups"), league=league)
        dates = dict(zip(el["event_id"].astype(str), el["date"].astype(str))) if el is not None and not el.empty else {}
        for sq, pl, e in zip(sb["squad"].astype(str), sb["player_in"].astype(str), sb["event_id"].astype(str)):
            d = dates.get(e, "")[:10]
            if d:
                k = (sq, ps.norm_name(pl))
                seen[k] = max(seen.get(k, ""), d)
    recent = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    out = {}
    for sq, pl in zip(inj["squad"].astype(str), inj["player"].astype(str)):
        k = (sq, ps.norm_name(pl))
        last = seen.get(k)
        s0 = since.get(k)
        if last and ((s0 and last > s0) or (not s0 and last >= recent)):
            out[k] = {"date": last, "since": s0}
    return out


_FM_KIND = {"injury": "부상", "suspension": "출장 정지", "in_match": "경기 중 부상 교체"}
_MONTH = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}


def _fm_return_kr(s: str) -> str:
    """FotMob 복귀 예상 → 한국어. 'Early December 2026' → '12월 초 복귀 예상', 'Doubtful' → '출전 불투명'."""
    t = str(s or "").strip()
    low = t.lower()
    if not t:
        return ""
    if low == "doubtful":
        return "출전 불투명"
    if low.replace("-", " ") == "day to day":
        return "단기(경기마다 점검)"
    fixed = {"a few days": "며칠", "a few weeks": "몇 주", "out for season": "시즌 아웃", "unknown": "복귀 시점 미정"}
    if low in fixed:
        return fixed[low]
    import re  # noqa: PLC0415
    g = re.match(r"about (\d+)(?:-(\d+))? (day|week|month)s?$", low)
    if g:
        unit = {"day": "일", "week": "주", "month": "개월"}[g.group(3)]
        return f"약 {g.group(1)}{'~' + g.group(2) if g.group(2) else ''}{unit}"
    if "training" in low:
        return "훈련 복귀"
    w = low.split()
    if len(w) == 3 and w[1] in _MONTH:
        part = {"early": "초", "mid": "중순", "late": "말"}.get(w[0], "")
        return f"{_MONTH[w[1]]}월 {part} 복귀 예상".replace("  ", " ")
    return t


@_memo(ttl=1800)
def _injuries_table(league: str):
    """현재 결장 — Transfermarkt 부상(부상 시작 뒤 실제로 뛴 선수 _injury_returns 는 뺌) + FotMob 결장자.

    TM 은 며칠 늦다 — 에밀리아노 마르티네스(턱 골절로 실려 나감)가 다음 날에도 목록에 없었다(2026-10-19 사용자).
    FotMob 다음 경기 결장 명단·경기 중 부상 교체(src/fetch_fotmob_injuries.py)에서 TM 에 없는 선수를 더한다
    (injury = '부상'·'출장 정지'·'경기 중 부상 교체', until = 복귀 예상, source = fotmob). 원래 표는 그대로 두고 사본."""
    import positions as ps  # noqa: PLC0415
    inj = ds.read_table("transfermarkt_injuries", league=league)
    if inj is not None and not inj.empty and "squad" in inj.columns:
        back = _injury_returns(league)
        if back:
            inj = inj[[(str(s), ps.norm_name(p)) not in back for s, p in zip(inj["squad"], inj["player"])]]
        inj = inj.copy()
        inj["source"] = "transfermarkt"
    fm = ds.read_table("fotmob_injuries", league=league)
    if fm is None or fm.empty or "squad" not in fm.columns:
        return inj
    have = set() if inj is None or inj.empty else {(str(s), ps.norm_name(p)) for s, p in zip(inj["squad"], inj["player"])}
    # TM 행 찾기(복귀일이 빈 TM 행은 FotMob 복귀 예상으로 채운다 — 'Reece James ?' → '1월 중순 복귀 예상')
    tm_row: dict = {}
    if inj is not None and not inj.empty:
        inj = inj.reset_index(drop=True)
        for i, (s_, p_) in enumerate(zip(inj["squad"], inj["player"])):
            w_ = ps.norm_name(p_).split()
            tm_row[(str(s_), ps.norm_name(p_))] = i
            if w_ and len(w_[-1]) >= 4:
                tm_row.setdefault((str(s_), "#" + w_[-1]), i)
    tm_ids = set() if inj is None or inj.empty or "tm_player_id" not in inj.columns else         {(str(s), str(t).split(".")[0]) for s, t in zip(inj["squad"], inj["tm_player_id"]) if pd.notna(t)}
    def sig(p):                                           # 같은 팀 성 — 'Emmanuel'·'Emanuel' Emegha, 'Tino'·'Valentino' Livramento
        w = ps.norm_name(p).split()
        return w[-1] if w and len(w[-1]) >= 4 else ps.norm_name(p)
    sigs = set() if inj is None or inj.empty else {(str(s), sig(p)) for s, p in zip(inj["squad"], inj["player"])}
    pf = _pf(league)
    recs = [] if pf is None else pf.to_dict("records")
    rows_of = {(str(x.get("squad")), str(x.get("player"))): x for x in recs}
    by_fm = {}
    for x in recs:                                        # FotMob id → 선수 표 행(이름 표기가 달라도 같은 사람)
        try:
            if x.get("fm_id") is not None and x.get("fm_id") == x.get("fm_id"):
                by_fm[str(int(x["fm_id"]))] = x
        except (TypeError, ValueError):
            pass
    add = []
    for r in fm.to_dict("records"):
        pr = by_fm.get(str(r.get("fotmob_id") or "").split(".")[0]) or rows_of.get((str(r["squad"]), str(r["player"]))) or {}
        name = str(pr.get("player") or r["player"])
        tid = str(pr.get("tm_id")).split(".")[0] if pr.get("tm_id") is not None and pr.get("tm_id") == pr.get("tm_id") else ""
        key = (str(r["squad"]), ps.norm_name(name))
        if key in have or (str(r["squad"]), ps.norm_name(r["player"])) in have or (tid and (str(r["squad"]), tid) in tm_ids)                 or (str(r["squad"]), sig(name)) in sigs:
            w_ = ps.norm_name(name).split()
            i = tm_row.get(key, tm_row.get((str(r["squad"]), "#" + (w_[-1] if w_ else ""))))
            if i is not None and str(r.get("kind")) != "in_match":
                cur_until = inj.at[i, "until"] if "until" in inj.columns else None
                if cur_until is None or (isinstance(cur_until, float) and cur_until != cur_until) or not str(cur_until).strip():
                    inj.at[i, "until"] = _fm_return_kr(r.get("expected_return"))
            continue
        have.add(key)
        kind = str(r.get("kind") or "injury")
        until = _fm_return_kr(r.get("expected_return")) if kind != "in_match" else             f"{str(r.get('match_date') or '')[5:].replace('-', '/')} {r.get('expected_return') or ''}".strip()
        add.append({"squad": r["squad"], "player": name, "position": pr.get("tm_position") or pr.get("pos") or "",
                    "injury": _FM_KIND.get(kind, kind), "until": until, "market_value_eur": pr.get("market_value_eur"),
                    "tm_player_id": pr.get("tm_id"), "tm_photo": _photo(pr) if pr else "", "last_checked": r.get("fetched"),
                    "active": "true", "source": "fotmob"})
    if not add:
        return inj
    extra = pd.DataFrame(add)
    return extra if inj is None or inj.empty else pd.concat([inj, extra], ignore_index=True)


def _active_injuries(team: str, league: str) -> dict:
    """{정규화 이름: {injury, until}} — 현재 부상(TM, 부상 뒤 실제로 뛴 선수 제외)."""
    import positions as ps  # noqa: PLC0415
    inj = _injuries_table(league)
    out = {}
    if inj is None or "squad" not in inj.columns:
        return out
    ti = inj[inj["squad"].astype(str) == team]
    if "active" in ti.columns:
        ti = ti[ti["active"].astype(str).str.lower().isin({"true", "1", "yes", "y"})]
    for _, r in ti.iterrows():
        out[ps.norm_name(r.get("player"))] = {"injury": str(r.get("injury") or "부상"), "until": str(r.get("until") or "")}
    return out


@app.get("/api/squad/{team}")
def squad(team: str, league: str = ACTIVE_LEAGUE):
    df = _squad_df(team, league)
    if df is None or df.empty:
        raise HTTPException(404, "squad not found")
    extras = _roster_extras(team, league, df)
    if extras:
        df = pd.concat([df, pd.DataFrame(extras).dropna(axis=1, how="all")], ignore_index=True)
    lines: dict[str, list] = {"GK": [], "DEF": [], "MID": [], "ATT": []}
    prof_of = {r["player"]: _pos_profile(r) for _, r in df.iterrows()}   # 주·2·3포지션(src/positions.py)
    for _, r in df.iterrows():
        line = rv3.line_of_row(r)
        _o = _player_ovr(r)
        lines[line].append({
            "player": r["player"],
            "pos": _pos_label(r),
            "age": int(_num(r.get("age"))),
            "minutes": int(_num(r.get("minutes"))),
            "value_eur": _num(r.get("market_value_eur")),
            "ovr": _o,
            "trend": _trend(r, league, ovr=_o),
            "roster_only": bool(r.get("_roster_only") is True),
            "photo": _photo(r),
            "goals": int(_num(r.get("goals"))),
            "assists": int(_num(r.get("assists"))),
            "roles": [x for x in [prof_of[r["player"]]["primary"], *prof_of[r["player"]]["secondary"]] if x],
        })
    for k in lines:
        lines[k].sort(key=lambda x: (-x["ovr"], -x["minutes"]))

    # 포지션별 뎁스 — 역할(GK·LB·CB·RB·DM·CM·AM·LW·RW·ST)마다 주포지션 선수(OVR 순) 다음에 2·3포지션 선수.
    # 예전엔 TM 주포지션 하나라 멀티 포지션 선수(Hincapié LB·CB)가 한 칸에만 있었고 3번째 옵션이 안 보였다.
    import positions as ps  # noqa: PLC0415
    inj = _active_injuries(team, league)
    cards = []
    for _, r in df.iterrows():
        pr = prof_of[r["player"]]
        if not pr.get("primary"):
            continue
        cards.append({"player": r["player"], "ovr": _player_ovr(r), "minutes": int(_num(r.get("minutes"))),
                      "age": int(_num(r.get("age"))), "photo": _photo(r), "primary": pr["primary"],
                      "secondary": pr["secondary"], "injured": ps.norm_name(r["player"]) in inj,
                      "role_starts": pr.get("roles") or {}})
    buckets = []
    first_of: dict[str, str] = {}                         # 선수 → 이미 1st 인 자리(한 선수는 한 자리에서만 1st)
    # 1st 판단은 이번 시즌 리그 선발만(지난 시즌 0.5 가중이 섞인 역할 집계로는 Ødegaard·Eze AM 이 동점이었다) —
    # Overview FORMATION(이번 시즌 리그 XI)과 같은 기준
    try:
        _tl = _team_lineups(team, league, "league")
        cur_roles = ps.role_counts([_tl], [1.0]) if _tl is not None and not _tl.empty else {}
    except Exception:  # noqa: BLE001
        cur_roles = {}
    if cur_roles:                                         # 이번 시즌 선발이 없는 선수는 0(지난 시즌 기록으로 1st 가 되지 않게)
        for c in cards:
            c["role_starts"] = dict(ps.lookup(cur_roles, c["player"]) or {})
    for b in ps.ROLES:
        main = sorted([c for c in cards if c["primary"] == b], key=lambda x: (-x["ovr"], -x["minutes"]))
        alt = sorted([c for c in cards if b in c["secondary"]], key=lambda x: (-x["ovr"], -x["minutes"]))
        opts = [{**c, "kind": "primary"} for c in main] + [{**c, "kind": "secondary"} for c in alt]
        if not opts:
            continue
        # 1st = 쓸 수 있는(부상 아님) 선수 중 그 자리 실제 선발이 많은 순 → 주포지션 → OVR. 다른 자리 1st 는 뒤로
        # (예전엔 OVR 순이라 130분 뛴 Eze 가 AM·LW 두 자리 1st, 2026-10-20 점검). 뎁스 = 2·3번째 옵션 질 + 인원
        opts.sort(key=lambda x: (x["injured"], x["player"] in first_of, -(x["role_starts"].get(b) or 0),
                                 x["kind"] != "primary", -x["ovr"]))
        if not opts[0]["injured"]:
            first_of[opts[0]["player"]] = b
        o2 = opts[1]["ovr"] if len(opts) > 1 else 38
        o3 = opts[2]["ovr"] if len(opts) > 2 else 38
        depth = round(0.55 * o2 + 0.25 * o3 + 0.2 * min(100, len(opts) * 25))
        buckets.append({"pos": b, "count": len(main), "multi": len(alt), "depth": depth,
                        "starter": opts[0], "rotation": opts[1:6]})
    loans = sorted(_loan_details(team, league),
                   key=lambda x: (x["club"] == "", -(x["ovr"] or 0), -(x["minutes"] or 0), x["player"]))
    return {"team": team, "color": tm.team_color(team), "lines": lines, "buckets": buckets, "loans": loans}


@app.get("/api/builder/{team}")
def builder(team: str, league: str = ACTIVE_LEAGUE):
    """Best XI 빌더 — 전체 스쿼드(이번 시즌 출전 없는 선수·부상자 포함)에 주·2·3포지션과 부상 정보를 붙인다.
    예전 빌더는 출전 기록이 있는 선수만 받아 Saliba(부상)·Guimarães 가 빠졌고, 라인(수비/중원/공격)만 보고
    OVR 순으로 채워 Calafiori(LB)가 RB 칸에 들어갔다. 배치는 화면이 역할 적합도 × OVR 최적화로 한다."""
    import positions as ps  # noqa: PLC0415
    df = _squad_df(team, league)
    if df is None or df.empty:
        raise HTTPException(404, "squad not found")
    extras = _roster_extras(team, league, df)
    if extras:
        df = pd.concat([df, pd.DataFrame(extras).dropna(axis=1, how="all")], ignore_index=True)
    inj = _active_injuries(team, league)
    out = []
    for _, r in df.iterrows():
        pr = _pos_profile(r)
        if not pr.get("primary"):
            continue
        out.append({"player": r["player"], "ovr": _player_ovr(r), "photo": _photo(r), "age": int(_num(r.get("age"))),
                    "minutes": int(_num(r.get("minutes"))), "primary": pr["primary"], "secondary": pr["secondary"],
                    "line": ps.LINE_OF[pr["primary"]], "starts": pr["starts"],
                    "injured": inj.get(ps.norm_name(r["player"])), "roster_only": bool(r.get("_roster_only") is True)})
    out.sort(key=lambda x: -x["ovr"])
    # 시작 포메이션 = 실제 리그 최빈값(빌더가 4-3-3 고정으로 시작해 Overview·뎁스와 XI 가 달랐다, 2026-10-20 점검)
    return {"team": team, "color": tm.team_color(team), "players": out,
            "formation": (_used_formation(team, league) or {}).get("formation")}


def _avail_schedule_seasons(league: str) -> list[str]:
    """schedule_full_*.csv 존재하는 시즌(최신 우선) — 리그별."""
    # 데이터 시즌 기준 다음·현재·직전 시즌 (하드코딩 없이 매 시즌 자동)
    cands = [f"{y}_{y + 1}" for y in (SEASON_START + 1, SEASON_START, SEASON_START - 1)]
    return [s for s in cands if data_path("schedule_full", league, s).exists()]


@app.get("/api/schedule/{team}")
def schedule(team: str, league: str = ACTIVE_LEAGUE, season: str = ""):
    """대회 통합 스케줄 — 리그+컵+유럽. season 미지정 시 최신 시즌 기본.
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

    def _txt(v) -> str:
        """NaN 은 빈 문자열 — str(NaN) 이 화면에 'nan' 으로 찍히던 것."""
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)

    import match_center as mc  # noqa: PLC0415
    ids = mc.espn_id_names(_fx_sources()["rows"])   # 컵·유럽 상대 ESPN 이름 → 우리 표기(PSG·Inter·Gent…)
    out = []
    for _, r in ts.iterrows():
        eid = str(r.get("event_id") or "")
        formation = ev_formation.get(eid)
        done = _txt(r.get("status")) == "completed" or bool(_txt(r.get("result")))
        espn_logo = _txt(r.get("opponent_logo"))
        opp, _ = mc.our_opponent(str(r.get("opponent") or ""), espn_logo, ids)
        ko = _txt(r.get("kickoff"))
        t_kst = mc.kst_of(ko, str(r.get("date") or ""))
        out.append({
            "comp": str(r.get("comp") or ""),
            "date": str(r.get("date") or ""),
            "kst": mc.kst_label(t_kst, bool(ko)) if t_kst else None,   # 한국 시각 — 다른 화면(홈·Overview)과 같은 날짜
            "home_away": str(r.get("home_away") or ""),
            "opponent": opp,
            "opp_logo": tm.team_logo(opp) or (espn_logo if espn_logo.startswith("http") else ""),
            # 예정 경기는 원천이 0-0·0·0 으로 채워 둔다 → 결과 칸은 비운다
            "gf": None if (not done or pd.isna(r.get("gf"))) else int(_num(r.get("gf"))),
            "ga": None if (not done or pd.isna(r.get("ga"))) else int(_num(r.get("ga"))),
            "score": _txt(r.get("score")) if done else "",
            "result": _txt(r.get("result")),
            "status": _txt(r.get("status")),
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
            "pos": _pos_label(r),
            "line": rv3.line_of_row(r),
            "age": int(_num(r.get("age"))),
            "nationality": str(r.get("nationality") or ""),
            "value_eur": _num(r.get("market_value_eur")),
            "ovr": int(r["_ovr"]),
            "photo": _photo(r),
            "role": prof["role"], "big_match": prof["big_match"], "comps": prof["comps"],
            "trend": _trend(r, league, ovr=int(r["_ovr"])),
        })
    return {"team": team, "color": tm.team_color(team), "players": out}


# 선수 상세 지표 — FM 스타일 카테고리 그룹 (아웃필더/골키퍼)
_PL_CATS = [
    ("공격", [("npxG/90", "npxg_p90"), ("슈팅/90", "shots_p90"), ("유효슈팅/90", "sot_per90")]),   # npxG = 기회의 양(결정력 아님)
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
    ("득점왕", "goals"), ("도움왕", "assists"), ("결정력(골−xG)", "_g_minus_xg"), ("키패스/90", "key_passes_per90"),
    ("드리블", "successful_dribbles_per90"), ("태클", "tackles_won_per90_ss"), ("인터셉트", "interceptions_per90_ss"),
    ("공중볼", "aerial_won_pct"), ("평점", "ss_rating"),
]



def _espn_name(ours: str, names) -> str | None:
    """우리 표기 → 그 팀 ESPN 표기 — 'Gabriel Magalhães' ↔ 'Gabriel', 'Martin Ødegaard' ↔ 'Martin Odegaard'."""
    from unidecode import unidecode  # noqa: PLC0415

    def nz(x):
        return " ".join(unidecode(str(x)).lower().replace("-", " ").replace(".", " ").split())
    o = nz(ours)
    ot = o.split()
    if not ot:
        return None
    hits = []
    for n in set(names):
        k = nz(n)
        t = k.split()
        if not t:
            continue
        if k == o:
            return n
        if (t[-1] == ot[-1] and t[0][:1] == ot[0][:1]) or (len(t) == 1 and t[0] in ot) or (len(ot) == 1 and ot[0] in t):
            hits.append(n)
    return hits[0] if len(hits) == 1 else None


@_memo(ttl=21600)
def _fm_match_dates(league: str) -> dict:
    """{('id', fotmob_id) | ('nm', 'squad|player'): {날짜: {r 평점, m 분, g 골, a 도움}}} — SEASON LOG 경기별 기록.
    FotMob 경기별 기록은 선수 헤더의 리그 골·도움·분(season_totals.apply_live_totals)과 같은 원천이라, 두 숫자를
    맞추려고 경기별 분·골·도움도 이걸 우선한다(ESPN 이벤트엔 벨기에 리그·DFB-Pokal 도움이 0건, 2026-10-20 점검)."""
    t = ds.read_table("fotmob_match_ratings", league=league)
    out: dict = {}
    if t is None or t.empty:
        return out
    num = lambda c: pd.to_numeric(t[c], errors="coerce") if c in t.columns else pd.Series(float("nan"), index=t.index)  # noqa: E731
    for fid, sq, pl, d, r, m, g, a in zip(t["fotmob_id"].astype(str).str.replace(r"\.0$", "", regex=True), t["squad"].astype(str),
                                          t["player"].astype(str), t["date"].astype(str), num("rating"), num("minutes"),
                                          num("goals"), num("assists")):
        v = {"r": None if r != r else round(float(r), 2), "m": None if m != m else int(m),
             "g": None if g != g else int(g), "a": None if a != a else int(a)}
        out.setdefault(("id", fid), {})[d[:10]] = v
        out.setdefault(("nm", f"{sq}|{pl}"), {})[d[:10]] = v
    return out


def _season_log(team: str, player: str, league: str, is_gk: bool = False, fm_id=None) -> dict:
    """선수 시즌 기록 — 경기별(대회·상대·결과·출전 분·선발·골·도움·카드) + 대회별 합계 + 전체 합산.
    리그·국내컵·유럽대항전 라인업/교체(ESPN) + 선수 이벤트(data/match_events, src/fetch_match_stats.py).
    예전 Player 탭은 리그 스탯과 컵·유럽 선발 수만 있어 '챔스+리그 합산·분리'가 안 보였다(2026-10-15)."""
    sch = ds.read_table("schedule_full", league=league)
    if sch is None or "squad" not in sch.columns:
        return {"available": False}
    sch = sch[(sch["squad"] == team) & (sch["status"] == "completed") & sch["event_id"].notna()].copy()
    if sch.empty:
        return {"available": False}
    sch["eid"] = pd.to_numeric(sch["event_id"], errors="coerce").astype("Int64").astype(str)
    games, _ = _on_pitch(team, league)
    games = {str(int(float(k))): v for k, v in games.items()}
    lu = _lineups(league)
    listed: dict[str, set] = {}
    if lu is not None and not lu.empty:
        lu = lu[lu["squad"] == team]
        for eid, g in lu.groupby("event_id"):
            listed[str(int(float(eid)))] = set(g["player"].astype(str))
    all_names = {n for g in games.values() for n in g} | {n for v in listed.values() for n in v}
    me = _espn_name(player, all_names)
    ev = ds.read_table("match_events", league=league)
    evs: dict[str, list] = {}
    if ev is not None and not ev.empty:
        ev = ev[ev["squad"] == team]
        ev_names = set(ev["player"].dropna().astype(str))
        me_ev = _espn_name(player, ev_names | ({me} if me else set()))
        for r in ev[ev["player"].astype(str) == (me_ev or "")].itertuples():
            evs.setdefault(str(int(float(r.event_id))), []).append(r.type)
    else:
        ev = None
    # 선수 경기 기록(전 대회 슈팅·유효슈팅·선방·실점 — ESPN, src/fetch_match_stats.py)
    pm: dict[str, dict] = {}
    pmt = ds.read_table("player_match_stats", league=league)
    if pmt is not None and not pmt.empty and me:
        mine = pmt[(pmt["squad"] == team)]
        me_pm = _espn_name(player, set(mine["player"].dropna().astype(str)) | {me})
        for r in mine[mine["player"].astype(str) == (me_pm or "")].to_dict("records"):
            pm[str(r["event_id"]).replace(".0", "")] = r
    pm_events = set(pmt["event_id"].astype(str).str.replace(r"\.0$", "", regex=True)) if pmt is not None and not pmt.empty else set()
    # 경기별 평점(FotMob, 전 대회) — 같은 날짜로 붙인다(ESPN·FotMob 경기 id 가 달라서)
    fmd = _fm_match_dates(league)
    try:
        rt = fmd.get(("id", str(int(fm_id)))) if fm_id is not None and fm_id == fm_id else None
    except (TypeError, ValueError):
        rt = None
    rt = rt or fmd.get(("nm", f"{team}|{player}")) or {}
    rows = []
    ev_ids = set(ev["event_id"].astype(str).str.replace(r"\.0$", "", regex=True)) if ev is not None else set()
    for r in sch.sort_values("date").itertuples():
        e = r.eid
        on = games.get(e, {}).get(me) if me else None
        mins = round(on[1] - on[0]) if on else 0
        t = evs.get(e, [])
        status = "start" if on and on[0] == 0 else "sub" if on else ("bench" if me and me in listed.get(e, set()) else "out")
        goals, assists = t.count("goal") + t.count("pen"), t.count("assist")
        fm = rt.get(str(r.date)[:10]) or {}
        if fm.get("m"):                                  # FotMob 경기별 기록 우선(헤더와 같은 원천)
            mins = fm["m"]
            goals = fm["g"] if fm.get("g") is not None else goals
            assists = fm["a"] if fm.get("a") is not None else assists
            if status in ("bench", "out"):              # ESPN 라인업에서 이름을 못 찾은 경기
                status = "start" if mins >= 60 else "sub"
        rows.append({"date": str(r.date)[:10], "comp": str(r.comp), "comp_code": str(getattr(r, "comp_code", "") or ""),
                     "opponent": str(r.opponent), "home_away": r.home_away, "score": str(r.score or ""), "result": str(r.result or ""),
                     "status": status, "minutes": mins, "goals": goals, "pens": t.count("pen"),
                     "assists": assists, "yellow": t.count("yellow"), "red": t.count("red"),
                     "has_events": e in ev_ids or bool(fm.get("m")),
                     **{k: int(_num((pm.get(e) or {}).get(k))) for k in ("shots", "sot", "saves", "conceded")},
                     "has_stats": e in pm_events, "rating": fm.get("r") if mins > 0 else None})
    by: dict[str, dict] = {}
    for x in rows:
        b = by.setdefault(x["comp"], {"comp": x["comp"], "matches": 0, "apps": 0, "starts": 0, "minutes": 0, "goals": 0,
                                      "assists": 0, "yellow": 0, "red": 0, "shots": 0, "sot": 0, "saves": 0, "conceded": 0})
        b["matches"] += 1
        b["apps"] += 1 if x["minutes"] > 0 else 0
        b["starts"] += 1 if x["status"] == "start" else 0
        for k in ("minutes", "goals", "assists", "yellow", "red", "shots", "sot", "saves", "conceded"):
            b[k] += x[k]
    comps = sorted(by.values(), key=lambda b: (b["comp"] != "리그", -b["matches"]))
    keys = ("matches", "apps", "starts", "minutes", "goals", "assists", "yellow", "red", "shots", "sot", "saves", "conceded")
    tot = {"comp": "합계", **{k: sum(b[k] for b in comps) for k in keys}}
    for b in comps + [tot]:                             # 90분당 — 대회 비교용(출전 270분 미만은 표본 부족)
        rs = [x["rating"] for x in rows if x.get("rating") and (b is tot or x["comp"] == b["comp"])]
        b["rating"] = round(sum(rs) / len(rs), 2) if rs else None   # FotMob 경기 평점 평균(평점 있는 경기)
        b["code"] = next((x["comp_code"] for x in rows if x["comp"] == b["comp"]), "")
        b["g90"] = round(b["goals"] * 90 / b["minutes"], 2) if b["minutes"] >= 270 else None
        b["shots90"] = round(b["shots"] * 90 / b["minutes"], 1) if b["minutes"] >= 270 else None
    return {"available": bool(me), "espn_name": me, "matches": rows, "by_comp": comps, "total": tot, "is_gk": bool(is_gk),
            "events_coverage": round(sum(1 for x in rows if x["has_events"]) / max(1, len(rows)), 2),
            "stats_coverage": round(sum(1 for x in rows if x["has_stats"]) / max(1, len(rows)), 2)}


@app.get("/api/player/{team}/{player}")
@_memo(ttl=21600)
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
    my_line = rv3.line_of_row(row)
    pool = pool[pool.apply(lambda r: rv3.line_of_row(r) == my_line, axis=1)]   # 같은 라인 대비 백분위

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
    # 순위 범위를 밝힌다 — '평점 리그 #3' 이 실제론 '미드필더 450′+ 중 3위'(리그 전체 11위)였다(2026-10-20 점검).
    # 누적(득점·도움)은 리그 전체, 90분당·비율은 같은 라인 + 최소 출전. 동률이면 '공동'
    line_ko = {"ATT": "공격수", "MID": "미드필더", "DEF": "수비수", "GK": "골키퍼"}.get(my_line, "같은 라인")

    def _gxg(df):
        m = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
        return pd.to_numeric(df["goals"], errors="coerce").fillna(0) - pd.to_numeric(df["xg_p90"], errors="coerce") * m / 90
    for label, col in badge_cfg:
        total = col in ("goals", "assists")
        base = full if total else pool
        if col == "_g_minus_xg":
            if not {"goals", "xg_p90", "minutes"} <= set(pool.columns):
                continue
            s, v = _gxg(base).dropna(), float(_gxg(row.to_frame().T).iloc[0]) if pd.notna(row.get("xg_p90")) else float("nan")
        else:
            if col not in base.columns:
                continue
            s = pd.to_numeric(base[col], errors="coerce").dropna()
            try:
                v = float(row.get(col))
            except (TypeError, ValueError):
                continue
        if pd.isna(v) or v <= 0 or s.empty:
            continue
        rank = int((s > v + 1e-9).sum()) + 1
        tie = int((abs(s - v) <= 1e-9).sum()) > 1
        if rank <= 3:
            badges.append({"label": label, "rank": rank, "tie": tie,
                           "scope": "리그" if total else f"{line_ko} {int(min_min)}′+",
                           "medal": "🥇" if rank == 1 else ("🥈" if rank == 2 else "🥉")})
    badges.sort(key=lambda b: b["rank"])

    # 시장가치 추이 (market_value_history — 이름/norm_key 매칭)
    vhist = []
    try:
        mvh = ds.read_table("market_value_history")
        if mvh is not None and not mvh.empty and "player" in mvh.columns:
            from unidecode import unidecode  # noqa: PLC0415
            sub = mvh[mvh["player"].astype(str) == str(row["player"])]
            nk = str(row.get("norm_key") or "")
            if sub.empty and nk:
                sub = mvh[mvh["player"].astype(str).map(lambda x: unidecode(str(x)).lower().strip()) == nk]
            seen_d = set()
            for _, r in sub.sort_values("date").iterrows():
                dt = str(r.get("date") or "")[:10]
                if dt and dt not in seen_d:
                    seen_d.add(dt)
                    vhist.append({"date": dt, "value_eur": _num(r.get("market_value_eur"))})
    except Exception:  # noqa: BLE001
        pass

    return {
        "player": row["player"], "team": team, "color": tm.team_color(team),
        "value_history": vhist, "peers": {"line": my_line, "n": int(len(pool))},
        "pos": _pos_label(row),
        "line": rv3.line_of_row(row),
        "age": int(_num(row.get("age"))), "nationality": str(row.get("nationality") or ""),
        "value_eur": _num(row.get("market_value_eur")), "photo": _photo(row),
        "ovr": _player_ovr(row), "trend": _trend(row, league), "ss_rating": _num(row.get("ss_rating")),
        "minutes": int(_num(row.get("minutes"))), "goals": int(_num(row.get("goals"))),
        "assists": int(_num(row.get("assists"))),
        "contract_until": str(row.get("tm_contract_until") or ""),
        "joined": str(row.get("tm_joined_date") or "")[:10] or None,     # 입단일 — 헤더 '입단 2023-07 · 계약 ~2028-06'
        "is_gk": is_gk, "categories": categories, "radar": radar, "badges": badges,
        "comp_usage": _comp_profile(row, _comp_usage(league)),
        "season_log": _season_log(str(row.get("squad") or team), str(row["player"]), league, is_gk=is_gk, fm_id=row.get("fm_id")),
        # 'OVR 이 어떻게 나왔나' — 단계별 기여(rv3.ovr_parts_of_row)와 평점 출처(Sofascore·FotMob 평균)
        "ovr_parts": rv3.ovr_parts_of_row(row)["parts"],
        "ratings": _rating_sources(row),
        "form": _player_form(row),
        "recent": _recent_of(row, league),
    }


@_memo(ttl=21600)
def _recent_index(league: str) -> dict:
    """선수별 최근 5경기(FotMob 경기별 평점, 전 대회) 색인 — src/recent_form.py."""
    import recent_form as rf  # noqa: PLC0415
    return rf.by_player(rf.recent_rows(ds.read_table("fotmob_match_ratings", league=league)))


def _recent_of(row, league: str) -> dict | None:
    """최근 폼 — 시즌 폼(_form)과 따로 최근 3·5경기(전 대회). score 는 같은 리그·포지션 안 순위 45~99.
    2026-10-19 사용자: '노팅엄전 사카가 못했는데 폼 절정 — 전체 폼과 최근 3·5경기 폼을 나누자'."""
    import recent_form as rf  # noqa: PLC0415
    try:
        g = rf.lookup(_recent_index(league), row.get("fm_id"), row.get("squad"), row.get("player"))
        s, ms = rf.summary(g), rf.match_list(g)
    except Exception:  # noqa: BLE001
        return None
    if not ms or not s:
        return None
    v = row.get("_recent")
    return {"score": int(v) if v is not None and v == v else None, "n": s["n"],
            "avg5": s["avg5"], "avg3": s["avg3"], "matches": ms}   # 평균 = 출전 시간 가중(recent_form.summary)


def _rating_sources(row) -> dict:
    """평점 출처 — 두 출처 평균(모델 입력)과 원래 값(src/rating_blend.py). 없으면 None."""
    import rating_blend as rb  # noqa: PLC0415

    def f(k):
        v = pd.to_numeric(row.get(k), errors="coerce")
        return None if pd.isna(v) or v <= 0 else round(float(v), 2)
    fm = f("fm_rating")
    return {"blend": f("ss_rating"), "sofascore": f("ss_rating_sofa"), "fotmob": fm,
            "fotmob_scaled": round(float(rb.fm_to_ss(fm)), 2) if fm else None,
            "prev_blend": f("prev_ss_rating"), "prev_sofascore": f("prev_ss_rating_sofa"), "prev_fotmob": f("prev_fm_rating"),
            "hist": f("hist_ss_rating"), "prev_minutes": int(_num(row.get("prev_minutes"))) or None}


@_memo(ttl=3600)
def _club_names() -> list[str]:
    """우리 8개 리그 클럽(표준 표기) — 2군 모구단 찾기 후보."""
    out: set[str] = set()
    for lg in ds.available_leagues():
        st = ds.read_table("standings", league=lg)
        if st is not None and "squad" in st.columns:
            out |= set(st["squad"].astype(str))
    return sorted(out)


def _own_reserve_mask(tt, team: str):
    """자기 2군·유스(Club NXT·Barça Atlètic·Arsenal U21)와 오간 행 — 이적이 아니라 내부 승격·강등."""
    import squads as sq  # noqa: PLC0415
    names = _club_names()
    return tt["club"].map(lambda c: sq.is_own_reserve(c, team, names)) if "club" in tt.columns else pd.Series(False, index=tt.index)


def _tf_list(tt, direction, team: str | None = None):
    sub = tt[tt["direction"] == direction].copy()
    if "fee_text" in sub.columns:  # 임대복귀 제외 (원본과 동일)
        sub = sub[~sub["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
    if team and len(sub):          # 2군 승격은 영입이 아니다(바르사 IN 16명 중 8명이 Barça Atlètic, 2026-10-20 점검)
        sub = sub[~_own_reserve_mask(sub, team)]
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
    tin, tout = _tf_list(tt, "in", team), _tf_list(tt, "out", team)
    spend = sum(x["fee_eur"] for x in tin)
    income = sum(x["fee_eur"] for x in tout)
    ins = tt[tt["direction"] == "in"]
    promoted = sorted(set(ins.loc[_own_reserve_mask(ins, team), "player"].astype(str))) if len(ins) else []
    return {
        "team": team, "color": tm.team_color(team),
        "in": tin, "out": tout, "promoted": promoted,
        "window": win, "data_season": _data_season_label(),
        "window_has_data": filtered,
        "summary": {"spend": spend, "income": income, "net": spend - income,
                    "in_count": len(tin), "out_count": len(tout)},
    }


@app.get("/api/news/{team}")
@_memo(ttl=21600)
def news(team: str, league: str = ACTIVE_LEAGUE):
    na = ds.read_table("news_articles", league=league)
    if na is None:
        return {"team": team, "color": tm.team_color(team), "articles": []}
    ta = na[na["team"] == team].copy()
    if "published" in ta.columns:
        ta = ta.sort_values("published", ascending=False)
    today = str(datetime.date.today())
    # 기사에 나온 이 팀 선수(src/news_tags.py — 이름 전체 · 성+클럽)
    tags = ds.read_table("news_players", league=league)
    tagmap: dict = {}
    if tags is not None and not tags.empty:
        for ln, pl in zip(tags.loc[tags["squad"] == team, "link"], tags.loc[tags["squad"] == team, "player"]):
            tagmap.setdefault(str(ln), []).append(str(pl))
    # 관련성·기간 — 팀 이름(정식 이름·구별 낱말)이 원문에 나오거나 이 팀 선수 태그가 있고, 최근 60일(src/news_relevance.py)
    import news_relevance as nr  # noqa: PLC0415
    import news_sources  # noqa: PLC0415
    import news_stories  # noqa: PLC0415
    terms = nr.team_terms(team, (tm.team_fullname(team), *news_sources.cached_local_names(team)))   # 'Standard Luik' 같은 현지 표기
    rows = [r for _, r in ta.iterrows()
            if nr.relevant(r.to_dict(), terms, bool(tagmap.get(str(r.get("link") or ""))))]
    rows = rows[:NEWS_MAX]
    links = [str(r.get("link") or "") for r in rows]
    meta = _news_meta(links)               # 종류·이적 단계·기자(src/news_classify.py)
    every = _news_tags_any_league(links)   # STORY 묶음용 — 다른 리그 선수 태그까지(이적설 대상은 남의 리그 선수가 많다)
    out = []
    for r in rows:
        fs = str(r.get("first_seen") or "")[:10]
        ln = str(r.get("link") or "")
        m = meta.get(ln, {})
        out.append({
            "players": tagmap.get(ln, []),
            "headline": str(r.get("headline_ko") or r.get("headline") or ""),
            "headline_en": str(r.get("headline") or ""),
            "descr": str(r.get("descr_ko") or r.get("descr") or ""),
            "source": str(r.get("source") or ""),
            "via": str(r.get("via") or "") if "via" in r.index and r.get("via") == r.get("via") else "",
            "published": str(r.get("published") or ""),
            "first_seen": fs,
            "image": str(r.get("image") or "") if str(r.get("image") or "").startswith("http") else "",
            "link": ln,
            "is_new": bool(fs and fs >= today),
            "kind": m.get("kind") or "other", "stage": m.get("stage") or "",
            "journalists": [j for j in str(m.get("journalists") or "").split("|") if j],
        })
    recent = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    stories = news_stories.cluster(
        [{**a, "all_players": every.get(a["link"], a["players"])} for a in out
         if (a["published"] or a["first_seen"])[:10] >= recent],
        team_words=set(terms))[:6]
    kinds: dict = {}
    srcs: dict = {}
    for a in out:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
        srcs[a["source"]] = srcs.get(a["source"], 0) + 1
    # 오늘의 요약(AI) — 최근 48시간 기사 1~3줄(src/ai_notes.py news, 2시간마다·검증 통과 줄만). 3일 지나면 내림
    import ai_notes  # noqa: PLC0415
    ai = ai_notes.load("news").get("teams", {}).get(team)
    ai = {"lines": ai["lines"], "at": ai["at"], "n": ai.get("n")} if ai and ai.get("lines") else None
    return {"team": team, "color": tm.team_color(team), "articles": out, "sparse": len(out) < 3, "ai": ai,
            "stories": stories, "kinds": kinds,
            "sources": [{"name": k, "n": v} for k, v in sorted(srcs.items(), key=lambda x: -x[1]) if k],
            "track": _news_track() or None}


NEWS_MAX = 48
_TRACK: dict = {}


def _news_track() -> dict:
    """매체·기자 적중률(src/news_reliability.py → data/news_reliability.csv) — {outlets, journalists, stages, all}.
    stages = 단계별 실제 성사율(지난 닫힌 이적시장), 표본 MIN_N 미만은 few."""
    from leagues import DATA_DIR  # noqa: PLC0415
    p = DATA_DIR / "news_reliability.csv"
    if not p.exists():
        return {}
    key = p.stat().st_mtime
    if _TRACK.get("key") == key:
        return _TRACK["val"]
    r = pd.read_csv(p)
    pick = lambda k: {str(x.name): {"n": int(x.n), "hits": int(x.hits), "rate": float(x.rate), "score": float(x.score),  # noqa: E731
                                    "few": bool(x.few)} for x in r[r["kind"] == k].itertuples()}
    stages: dict = {}
    allr = r[r["kind"] == "all"]
    if len(allr):
        for part in str(allr["by_stage"].iloc[0]).split():
            st, _, frac = part.partition(":")
            h, _, n = frac.partition("/")
            if n.isdigit() and int(n):
                stages[st] = {"hits": int(h), "n": int(n), "rate": round(int(h) / int(n), 3)}
    val = {"outlets": pick("outlet"), "journalists": pick("journalist"), "stages": stages,
           "all": {"n": int(allr["n"].iloc[0]), "hits": int(allr["hits"].iloc[0])} if len(allr) else None}
    _TRACK.update(key=key, val=val)
    return val


def _news_side_table(sql: str, links: list[str]) -> list[tuple]:
    """news_* 보조 테이블을 리그 필터 없이 링크로 읽는다(datastore.read_table 은 league 열로 거른다)."""
    if not links or not ds.DB_PATH.exists():
        return []
    import sqlite3  # noqa: PLC0415
    try:
        c = sqlite3.connect(f"file:{ds.DB_PATH}?mode=ro", uri=True)
        try:
            return c.execute(sql.format(q=",".join("?" * len(links))), links).fetchall()
        finally:
            c.close()
    except sqlite3.Error:   # 분류 전 DB(테이블 없음)
        return []


def _news_meta(links: list[str]) -> dict:
    return {ln: {"kind": k, "stage": s, "journalists": j}
            for ln, k, s, j in _news_side_table("SELECT link, kind, stage, journalists FROM news_meta WHERE link IN ({q})", links)}


def _news_tags_any_league(links: list[str]) -> dict:
    out: dict = {}
    for ln, pl in _news_side_table("SELECT link, player FROM news_players WHERE link IN ({q})", links):
        out.setdefault(str(ln), []).append(str(pl))
    return out


@app.get("/api/news-player/{player}")
@_memo(ttl=3600)
def news_player(player: str, club: str = "", league: str = ACTIVE_LEAGUE, limit: int = 8):
    """선수가 나온 최근 기사(news.db 선수 태그 — 이름 전체, 또는 성 + 같은 기사 속 클럽 이름)."""
    tags, na = ds.read_table("news_players", league=league), ds.read_table("news_articles", league=league)
    if tags is None or na is None or tags.empty:
        return {"player": player, "articles": []}
    t = tags[(tags["player"] == player) & ((tags["squad"] == club) if club else True)]
    if t.empty:
        return {"player": player, "articles": []}
    how = dict(zip(t["link"].astype(str), t["how"].astype(str)))
    a = na[na["link"].astype(str).isin(how)].sort_values(["published", "first_seen"], ascending=False)
    a = a.drop_duplicates("link").head(max(1, min(limit, 20)))
    out = [{"headline": str(r.get("headline_ko") or r.get("headline") or ""), "headline_en": str(r.get("headline") or ""),
            "source": str(r.get("source") or ""), "published": str(r.get("published") or ""), "link": str(r.get("link") or ""),
            "image": str(r.get("image") or "") if str(r.get("image") or "").startswith("http") else "",
            "how": how.get(str(r.get("link") or ""), "")} for _, r in a.iterrows()]
    return {"player": player, "articles": out, "total": int(len(how))}


def _ddmmyyyy(s) -> str:
    """TM 날짜 '19/10/2026' → '2026-10-19'(이미 ISO 면 그대로)."""
    s = str(s or "")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else s[:10]


@app.get("/api/scout-report/{team}/{player}")
@_memo(ttl=21600)
def scout_report(team: str, player: str, league: str = ACTIVE_LEAGUE):
    """스카우팅 리포트 한 장 — 선수 상세 + 강약점(백분위) + 가용성(부상 두 시즌·지금 결장) + 계약·가치 + 이적설(TM 루머·뉴스 단계·
    매체 적중률) + 유사 선수(더 싼 대안 표시) + 판단 문장(src/scout_report.py, 규칙). 숫자는 원자료 그대로."""
    import positions as ps  # noqa: PLC0415
    import scout_report as sr  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    d = player_detail(team, player, league)
    me = ps.norm_name(d["player"])
    enough = d["minutes"] >= (300 if d.get("is_gk") else 450)
    strong, weak = sr.strengths(d.get("categories") or []) if enough else ([], [])
    # 부상 — 이번 시즌(이 클럽) + 지난 시즌(어느 리그든)
    seasons = []
    for sea, label in ((f"{SEASON_START}_{SEASON_START + 1}", f"{SEASON_START % 100:02d}/{(SEASON_START + 1) % 100:02d}"),
                       (f"{SEASON_START - 1}_{SEASON_START}", f"{(SEASON_START - 1) % 100:02d}/{SEASON_START % 100:02d}")):
        hit = None
        for lg in ([league] + [x for x in LEAGUES if x != league]):
            t = ds.read_table("tm_injury_history", league=lg, season=sea)
            if t is None or t.empty:
                continue
            rows = t[t["player"].astype(str).map(ps.norm_name) == me]
            if len(rows):
                hit = rows.sort_values("games_missed", ascending=False).iloc[0]
                break
        if hit is not None:
            spells = sr.parse_spells(hit.get("spells_json"))
            seasons.append({"season": label, "games_missed": int(_num(hit.get("games_missed"))),
                            "days_out": int(_num(hit.get("days_out"))), "spells": int(_num(hit.get("spells"))),
                            "injuries": [str(s.get("injury") or s.get("type") or "") for s in spells][:4]})
    cur = None
    inj = _injuries_table(league)
    if inj is not None and not inj.empty:
        mine = inj[(inj["squad"] == team) & (inj["player"].astype(str).map(ps.norm_name) == me)]
        if len(mine):
            r = mine.iloc[0]
            cur = {"injury": str(r.get("injury") or ""), "until": _ddmmyyyy(r.get("until")), "source": str(r.get("source") or "")}
    avail = sr.availability(seasons, cur)
    con = sr.contract(d.get("contract_until"))
    mk = sr.market(d.get("value_eur"), d.get("value_history") or [])
    # 이적설 — TM 루머(전 리그 표에서 이 선수) + 뉴스 루머 판정표(src/news_reliability.py, 최근 120일)
    tm_rows = []
    for lg in LEAGUES:
        t = ds.read_table("transfer_rumors", league=lg)
        if t is not None and not t.empty and "player" in t.columns:
            for r in t[t["player"].astype(str).map(ps.norm_name) == me].to_dict("records"):
                tm_rows.append({**r, "date": _ddmmyyyy(r.get("date"))})
    news_rows = []
    from leagues import DATA_DIR  # noqa: PLC0415
    cp = DATA_DIR / "news_claims.csv"
    if cp.exists():
        cl = pd.read_csv(cp)
        since = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
        cl = cl[(cl["player"].astype(str).map(ps.norm_name) == me) & (cl["date"].astype(str) >= since)]
        news_rows = [{"to_club": r["dest"], "date": r["date"], "source": r["source"], "stage": r["stage"] if r["stage"] == r["stage"] else "",
                      "headline": r["headline"]} for r in cl.sort_values("date").to_dict("records")]
    track = _news_track()
    talk = sr.talk_items(tm_rows, news_rows, track)[:6]
    try:
        sim = similar(d["player"], league=league).get("results", [])[:6]
    except Exception:  # noqa: BLE001 — 유사 선수 없이도 리포트는 낸다
        sim = []
    for s in sim:
        s["cheaper"] = bool(d.get("value_eur") and s.get("value_eur") and s["value_eur"] < d["value_eur"] * 0.7)
    try:
        news = news_player(d["player"], club=team, league=league, limit=4).get("articles", [])
    except Exception:  # noqa: BLE001
        news = []
    return {"player": d, "strengths": strong, "weaknesses": weak, "enough": enough, "availability": avail,
            "contract": con, "market": mk, "talk": talk, "similar": sim, "news": news,
            "stage_rates": (track or {}).get("stages") or {},
            "verdict": sr.verdict(d, strong, weak, avail, con, mk, talk),
            "generated": datetime.date.today().isoformat()}


@app.get("/api/analytics/{team}")
@_memo(ttl=21600)
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
            _t2 = rv3.team_ratings(_with_roster(full, team, league), team, perf=_team_perf(team, league)) or {}
            ovr = {"overall": _t2.get("overall", v.get("종합 지수", 60)), "form": v.get("시즌 폼", 60),
                   "attack": _t2.get("attack", v.get("공격 지수", 60)), "midfield": _t2.get("midfield", v.get("미드필드 지수", 60)),
                   "defense": _t2.get("defense", v.get("수비 지수", 60)), "set_piece": _u("set_piece_attack_index")}
            radar = [{"axis": ax, "value": _u(col)} for ax, col in [
                ("ATT OUT", "attack_output_index"), ("CREATE", "attack_creation_index"),
                ("CONTROL", "midfield_control_index"), ("PRESS", "pressing_index"),
                ("DEF OUT", "defense_output_index"), ("SET PC", "set_piece_attack_index"),
            ] if _u(col, 0) > 0]   # 빈칸·0 = 소스 미수집(26/27 세트피스 등) → 축 제외(기본값 50 으로 채우지 않음)

    # Match Factor Lab — 지수 상/하위 팩터 + 기여 선수
    factors = _match_factors(team, league, full, um_df)

    # 이적 요약
    tr = ds.read_table("transfers", league=league)
    tf_summary = {"spend": 0.0, "income": 0.0, "in_count": 0, "out_count": 0}
    if tr is not None:
        tt = tr[tr["squad"] == team]
        if len(tt):
            tt = tt[~_own_reserve_mask(tt, team)]          # 2군 승격·강등은 이적이 아님
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

    # 지표는 리그 평균이 50(z 기반) — 강점은 평균 위, 약점은 평균 아래만. 예전엔 낮은 순 3개를 무조건
    # 약점으로 넣어 '공중 장악 62'(평균 이상)도 보강 대상으로 떴다. 약점 카드엔 '기여 선수'를 붙이지 않는다.
    strengths = [{"label": l, "value": v, "line": ln, "players": _contrib(ln)} for l, ln, v in scored[:3] if v > 50]
    weaknesses = [{"label": l, "value": v, "line": ln, "players": []} for l, ln, v in scored[::-1] if v < 50][:3]
    return {"strengths": strengths, "weaknesses": weaknesses}


def _signing_audit(team: str, league: str, full):
    """여름 영입 선수들의 이번 시즌 소화도 평가(출전/기여)."""
    tr = ds.read_table("transfers", league=league)
    if tr is None or full is None:
        return []
    ins = tr[(tr["squad"] == team) & (tr["direction"] == "in")].copy()
    if "window" in ins.columns:
        ins = ins[ins["window"].astype(str).str.lower().str.contains("summer") | (ins["window"].astype(str) == "")]
    # 임대 복귀(End of loan)는 영입이 아니다 — 감사 카드에서 제외
    ins = ins[~ins["fee_text"].astype(str).str.lower().str.startswith("end of loan")]
    # 2군 승격·임대 보낸 선수는 '영입 소화도'가 아니다(Arsenal U21 → Stevenage 임대 Setford 가 빨간 평가로 남았다)
    if len(ins):
        ins = ins[~_own_reserve_mask(ins, team)]
    gone = set(_loans_out(team, league))
    ins = ins[~ins["player"].map(lambda n: _person_key(n) in gone)]
    core, rot = _mm(1500, league), _mm(600, league)       # 시즌 진행률만큼 축소한 기준
    import positions as ps  # noqa: PLC0415

    def _keys(n) -> list:
        """출처마다 이름 순서·악센트가 달라('Han-beom Lee' vs 'Lee Han-beom', 'Chérif' vs 'Cherif') 여러 키로 맞춘다."""
        t = ps.norm_name(n).split()
        return [" ".join(t), " ".join(sorted(t)), _person_key(n)]
    fmap: dict = {}
    for _, r in full[full["squad"] == team].iterrows():
        for k in _keys(r["player"]):
            fmap.setdefault(k, r)
    out = []
    for _, r in ins.iterrows():
        name = str(r.get("player") or "")
        pf = next((fmap[k] for k in _keys(name) if k in fmap), None)
        mins = int(_num(pf.get("minutes"))) if pf is not None else 0
        goals = int(_num(pf.get("goals"))) if pf is not None else 0
        assists = int(_num(pf.get("assists"))) if pf is not None else 0
        if mins >= core:
            verdict, tone = "핵심 전력화", "good"
        elif mins >= rot:
            verdict, tone = "로테이션 정착", "ok"
        elif mins > 0:
            verdict, tone = "적응 중", "low"
        elif "keeper" in str(r.get("pos") or "").lower() or str(r.get("pos") or "").upper() == "GK":
            verdict, tone = "백업 골키퍼", "low"              # 주전 GK 가 있으면 0분이 정상
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


@_memo(ttl=3600)
def _used_formation(team: str, league: str) -> dict | None:
    """이번 시즌 리그 경기에서 실제로 가장 많이 쓴 포메이션(ESPN 라인업) — {'formation','n','total'}.
    위키의 감독 '선호' 포메이션(아스날 4-3-3)과 실제(7경기 모두 4-2-3-1)가 달랐다(2026-10-20 점검)."""
    el = ds.read_table("espn_lineups", league=league)
    if el is None or el.empty or "formation" not in el.columns:
        return None
    g = el[el["squad"] == team].drop_duplicates("event_id")
    f = g["formation"].dropna().astype(str)
    f = f[f.str.match(r"^\d(-\d)+$")]
    if f.empty:
        return None
    top = f.value_counts()
    return {"formation": str(top.index[0]), "n": int(top.iloc[0]), "total": int(len(f))}


def _manager_evo(team: str, league: str = "EPL"):
    """감독 전술 진화 — 현재 vs 이전(감독 교체 시)."""
    mp = _managers(league).get(team)
    if not mp:
        return None
    import re as _re2

    def _ko(v) -> str:
        """화면엔 한국어만 — 25/26 수기 영어 라벨('Control + high press')·대기 문구
        ('Pending tactical profile')는 숨기고, 위키에서 자동 수집·번역한 전술 요약(tactics_ko)을 쓴다."""
        t = str(v or "").strip()
        return t if _re2.search(r"[가-힣]", t) else ""

    evo = {
        "name": mp.get("name", ""), "style": _ko(mp.get("style")),
        "formation": (_used_formation(team, league) or {}).get("formation") or mp.get("formation", ""),
        "formation_pref": mp.get("formation", ""), "focus": _ko(mp.get("focus")),
        "tactics": _ko(mp.get("tactics_ko")),
        "appointed": mp.get("appointed", ""),
    }
    if mp.get("previous_name"):
        evo["previous"] = {
            "name": mp.get("previous_name", ""), "style": _ko(mp.get("previous_style")),
            "formation": mp.get("previous_formation", ""),
        }
    return evo


@_memo(ttl=21600)
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


def _person_key(n) -> tuple[str, str]:
    """(성, 이름 첫 글자) — 악센트·대소문자 무시. 성만 쓰면 Wesley Fofana·David Datro Fofana 를 한 사람으로 봤다."""
    from unidecode import unidecode  # noqa: PLC0415
    t = unidecode(str(n or "")).lower().replace("-", " ").split()
    return (t[-1], t[0][:1]) if t else ("", "")


def _gone_keys(team: str, league: str) -> set[tuple[str, str]]:
    """이번(최근) 이적창에 팀을 떠난 선수 — 시즌 초 몇 경기 뛰고 이적한 선수(Everton Ndiaye 등)를
    현재 베스트 XI·벤치에서 뺄 때 쓴다(2026-10 전 팀 점검: scripts/audit_team_pages.py)."""
    try:
        return {_person_key(v["player"]) for v in _departures(team, league, _current_window()).values()}
    except Exception:  # noqa: BLE001
        return set()


def _comp_kind(code) -> str:
    c = str(code or "")
    return "euro" if c.startswith("uefa.") else "league" if c.endswith(".1") else "cup"


def _team_lineups(team: str, league: str, comp: str = "league"):
    """팀 선발 라인업 — comp: league · euro(유럽대항전) · cup(국내컵) · all · 대회 코드 하나(uefa.champions 등).
    컵·유럽은 espn_lineups_cups 를 일정의 대회 코드로 나눈다(_code). 예전 FORMATION 은 리그 전용이었다
    (2026-10-19 사용자: '챔스·컵 스쿼드도 보고 싶다' → 같은 날 '리그·챔스·컵 각각 따로').
    _code: 리그 경기는 'league', 그 밖은 ESPN 대회 코드. _comp: 일정의 대회 이름(한글)."""
    frames = []
    if comp in ("league", "all"):
        el = ds.read_table("espn_lineups", league=league)
        if el is not None and not el.empty:
            frames.append(el.assign(_kind="league", _code="league", _comp="리그"))
    if comp != "league":
        cl = ds.read_table("espn_lineups_cups", league=league)
        sch = ds.read_table("schedule_full", league=league)
        if cl is not None and not cl.empty and sch is not None and "comp_code" in sch.columns:
            code = {str(e).replace(".0", ""): str(c) for e, c in zip(sch["event_id"], sch["comp_code"]) if pd.notna(e)}
            name = {str(c): str(n) for c, n in zip(sch["comp_code"], sch.get("comp", sch["comp_code"]))}
            eid = cl["event_id"].astype(str).str.replace(r"\.0$", "", regex=True)
            cl = cl.assign(_code=eid.map(code).fillna("cup"))
            cl = cl.assign(_kind=cl["_code"].map(_comp_kind), _comp=cl["_code"].map(name).fillna(""))
            cl = cl[cl["_kind"] != "league"]
            if comp in ("euro", "cup"):
                cl = cl[cl["_kind"] == comp]
            elif comp != "all":
                cl = cl[cl["_code"] == comp]
            frames.append(cl)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    return df[(df["squad"] == team) & (pd.to_numeric(df["starter"], errors="coerce") == 1)].copy()


def _placements(team: str, league: str, last_n: int | None = None, exclude: set | None = None, comp: str = "league"):
    df = _team_lineups(team, league, comp)
    if df is None:
        return None
    if df.empty:
        return None
    df["date"] = df["date"].astype(str)
    matches = sorted(df["event_id"].unique(), key=lambda e: df[df["event_id"] == e]["date"].iloc[0])
    if last_n:
        matches = matches[-last_n:]
    sub = df[df["event_id"].isin(matches)]
    fm = sub.groupby("event_id")["formation"].first().mode()
    formation = str(fm.iloc[0]) if not fm.empty else "4-3-3"
    import positions as _ps_  # noqa: PLC0415
    _norm_inj = _ps_.norm_name
    _inj_now = set(_active_injuries(team, league) or {})          # 지금 결장(부상) — 배치 선수에 ✚

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
    # 칸마다 '그 칸 최다 출전'을 따로 고르면 두 칸을 번갈아 선 선수(Man City Anderson RDM·LDM)가 두 번 들어가고
    # 다른 주전(Enzo)이 벤치로 밀렸다 → (칸, 선수, 횟수)를 많은 순으로 한 사람 한 칸씩 배정(2026-10-15).
    # 4-1-2-1-2 처럼 같은 이름의 칸(CM 두 개)이 있으면 그 수만큼 서로 다른 선수.
    from collections import Counter  # noqa: PLC0415
    need = Counter(formation_slots(formation))
    pick: dict[str, list[str]] = {}
    used: set[str] = set()
    trip = sorted(((v, s, p) for s, c in slot_counts.items() for p, v in c.items()
                   if not exclude or _person_key(p) not in exclude), key=lambda t: (-t[0], t[1], t[2]))
    for _v, s, p in trip:
        if p in used or len(pick.get(s, [])) >= need.get(s, 0):
            continue
        pick.setdefault(s, []).append(p)
        used.add(p)
    # 그래도 빈 칸은 이 포메이션에서 선발이 가장 많은 남은 선수로(Elche·Cercle 처럼 후보가 다른 칸에 다 배정된 경우)
    tot: dict[str, int] = {}
    for c in slot_counts.values():
        for p, v in c.items():
            tot[p] = tot.get(p, 0) + v
    spare = [p for p, _ in sorted(tot.items(), key=lambda x: -x[1])
             if p not in used and (not exclude or _person_key(p) not in exclude)]
    for s, n in need.items():
        while len(pick.get(s, [])) < n and spare:
            p = spare.pop(0)
            pick.setdefault(s, []).append(p)
            used.add(p)
    placements = []
    extras = None
    for slot in formation_slots(formation):
        player = pick[slot].pop(0) if pick.get(slot) else None
        x, y = slot_xy(slot, formation)
        row = resolve(player) if player else None
        if player and row is None:
            # 이번 시즌 리그 출전이 없는 컵·유럽 선발(백업 GK 케파 등) — 계약 명단 + 지난 시즌 기록으로 OVR·사진
            if extras is None:
                try:
                    extras = {_person_key(r["player"]): r for r in _roster_extras(team, league, _pf(league))}
                except Exception:  # noqa: BLE001
                    extras = {}
            row = extras.get(_person_key(player))
        placements.append({
            "slot": display_slot(slot, formation),
            "player": player or "—",
            "x": round(float(x), 1), "y": round(float(y), 1),
            "kind": slot_kind(slot),
            "ovr": _player_ovr(row) if row is not None else None,
            "photo": (_photo(row) if row is not None else "") or (_resolve_photo(player, resolve, league) if player else ""),
            # 지금 부상 중이면 표시 — 시즌 XI 의 Tzolis(~10/30)가 표시 없이 선발로 보여 다음 경기 XI 로 오해됐다
            "injured": bool(player) and _norm_inj(player) in _inj_now,
        })
    return {"formation": formation, "placements": placements, "matches": len(matches)}


@app.get("/api/lineup/{team}")
@_memo(ttl=21600)
def lineup(team: str, league: str = ACTIVE_LEAGUE, comp: str = "league"):
    """FORMATION — comp: league(기본) · euro · cup · all · last(가장 최근 한 경기, 전 대회)."""
    gone = _gone_keys(team, league) | {k for k, v in _loans_out(team, league).items() if v.get("source") == "transfer"}   # 떠난·임대 간 선수는 현재 XI·벤치에서 제외
    allt = _team_lineups(team, league, "all")
    codes = set(allt["_code"].astype(str)) if allt is not None and not allt.empty else set()
    comp = comp if comp in ("league", "euro", "cup", "all", "last") or comp in codes else "league"
    src_comp = "all" if comp == "last" else comp
    if comp == "last":
        season = _placements(team, league, last_n=1, comp="all")            # 그 경기 그대로(떠난 선수 제외 안 함)
        recent = None
    else:
        season = _placements(team, league, exclude=gone, comp=src_comp)
        recent = _placements(team, league, last_n=5, exclude=gone, comp=src_comp)
    if season is None and comp == "league":
        raise HTTPException(404, "lineup data not found")
    # 대회별로 선발 기록이 있는 경기 수(화면 토글은 있는 것만) — comps: 묶음(리그·유럽·컵), comp_list: 대회 하나하나
    comps, comp_list = {}, []
    if allt is not None and not allt.empty:
        comps = {k: int(v) for k, v in allt.groupby("_kind")["event_id"].nunique().items()}
        order = {"league": 0, "euro": 1, "cup": 2}
        g = allt.groupby(["_code", "_kind", "_comp"])["event_id"].nunique().reset_index()
        g = g.assign(_o=g["_kind"].map(order)).sort_values(["_o", "event_id"], ascending=[True, False])
        comp_list = [{"key": str(r["_code"]), "kind": str(r["_kind"]), "name": str(r["_comp"]), "n": int(r["event_id"])}
                     for _, r in g.iterrows()]
    if season is None:
        season = {"formation": None, "placements": [], "matches": 0}

    # 벤치 — 시즌 XI 에 없는 스쿼드 선수(OVR 순 상위 8)
    xi_names = {p["player"] for p in season["placements"]}
    bench = []
    df = _squad_df(team, league)
    if df is not None:
        df = df[~df["player"].map(lambda n: _person_key(n) in gone)].copy()
        df["_ovr"] = df.apply(_player_ovr, axis=1)
        for _, r in df[~df["player"].isin(xi_names)].sort_values("_ovr", ascending=False).head(8).iterrows():
            bench.append({"player": r["player"], "pos": str(r.get("fl_group") or r.get("pos") or ""),
                          "ovr": int(r["_ovr"]), "photo": _photo(r)})
    # 마지막으로 반영된 경기(고른 대회) — 라인업은 경기 다음 날 아침 수집이라 '어느 경기까지인지'를 화면에 밝힌다
    last = None
    el = _team_lineups(team, league, src_comp)
    if el is not None and not el.empty:
        full_el = pd.concat([x for x in (ds.read_table("espn_lineups", league=league), ds.read_table("espn_lineups_cups", league=league)) if x is not None], ignore_index=True)
        mine = el
        if not mine.empty:
            row = mine.assign(_d=mine["date"].astype(str)).sort_values("_d").iloc[-1]
            eid = str(row["event_id"]).replace(".0", "")
            opp = full_el[(full_el["event_id"].astype(str).str.replace(".0", "", regex=False) == eid) & (full_el["squad"] != team)]
            last = {"date": str(row["date"])[:10],
                    "opponent": str(opp["squad"].iloc[0]) if not opp.empty else str(row.get("opponent") or ""),
                    "home_away": str(row.get("home_away") or ""), "kind": str(row.get("_kind") or "league"),
                    "code": str(row.get("_code") or "league"), "comp": str(row.get("_comp") or "")}
    return {"team": team, "color": tm.team_color(team), "season": season, "recent": recent, "bench": bench,
            "last_match": last, "comp": comp, "comps": comps, "comp_list": comp_list}


# 유사 선수 엔진 — 임베딩은 최초 1회 빌드 후 캐시(요청마다 재계산 방지)
_SIM = None
_PROGRESS: dict[str, float] = {}




def _progress(league: str) -> float:
    """리그 진행률(0~1) — 순위표 최다 경기수 / 시즌 총 경기수. 시즌 끝난 데이터는 1.0."""
    if league not in _PROGRESS:
        st = ds.read_table("standings", league=league)
        played = 0.0
        if st is not None and "played" in st.columns:
            played = float(pd.to_numeric(st["played"], errors="coerce").max() or 0)
        try:
            total = float(league_config(league).games_per_team)
        except KeyError:
            total = 38.0
        _PROGRESS[league] = max(0.05, min(1.0, played / total)) if played > 0 else 1.0
    return _PROGRESS[league]


def _mm(full: float, league: str = ACTIVE_LEAGUE) -> float:
    """풀시즌 기준 출전시간 임계값을 리그 진행률만큼 축소 — 시즌 초 '표본 부족' 일괄 탈락 방지.
    끝난 시즌(진행률 1.0)은 기존 임계값 그대로."""
    return max(90.0, full * _progress(league))


def _sim_engine():
    global _SIM
    if _SIM is None:
        from similar_players import load_players, build_embeddings
        df = load_players(min_minutes=int(_mm(900, "EPL")))
        _SIM = (df, build_embeddings(df))
    return _SIM


@app.get("/api/similar/{player}")
def similar(player: str, same_position: bool = True, alpha: float = 0.6, league: str = ACTIVE_LEAGUE):
    from similar_players import find_similar
    try:
        df, emb = _sim_engine()
        res = find_similar(df, emb, player, top=60, same_position=same_position, alpha=alpha)
    except Exception:  # noqa: BLE001
        return {"player": player, "results": []}
    # 실제 포지션(RW·LW·AM…)으로 거른다 — 엔진의 'WING_AM' 그룹은 윙어와 공격형 미드를 한데 묶어, 사카(RW) 유사 1위가
    # 만잠비(AM)였다(2026-10-19 사용자). 같은 포지션 먼저, 모자라면 인접 포지션(점수 ×0.9)
    _ADJ = {"RW": ("LW",), "LW": ("RW",), "AM": ("CM", "RW", "LW"), "CM": ("DM", "AM"), "DM": ("CM",),
            "LB": ("RB",), "RB": ("LB",), "CB": (), "ST": (), "GK": ()}
    me = df[df["player"] == player]
    if not me.empty and not res.empty:
        tb = _pos_bucket(me.iloc[0])
        # find_similar 결과엔 tm_position 이 없어(fl_group 만) 엔진 원본 표에서 선수별 포지션을 가져온다
        bk_of = {(str(p), str(s)): _pos_bucket(r) for p, s, r in zip(df["player"], df["squad"], df.to_dict("records"))}
        res = res.assign(_bk=[bk_of.get((str(p), str(s)), "") for p, s in zip(res["player"], res["squad"])])
        same = res[res["_bk"] == tb]
        if len(same) < 6:
            adj = res[res["_bk"].isin(_ADJ.get(tb, ()))].assign(score=lambda x: pd.to_numeric(x["score"], errors="coerce") * 0.9)
            same = pd.concat([same, adj]).sort_values("score", ascending=False)
        res = same.head(6)
    else:
        res = res.head(6)
    out = []
    for _, r in res.iterrows():
        out.append({
            "player": str(r.get("player") or ""), "squad": str(r.get("squad") or ""),
            "pos": str(r.get("_bk") or r.get("fl_group") or r.get("pos") or ""), "age": int(_num(r.get("age"))),
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


def _pos_label(row) -> str:
    """화면 표시용 세부 포지션(CB·DM·RW…). FBref 대분류 'MF'·'FW,MF' 로는 사카·라이스가 다 'MF' 였다.
    역할 정보(tm_position·fl_group)가 없으면 FBref 값 그대로."""
    if any(pd.notna(row.get(c)) and str(row.get(c)).strip() for c in ("tm_position", "fl_group")):
        return _pos_bucket(row)
    return str(row.get("pos") or "")


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
    lu = _league_units(league)                     # 라인 순위와 같은 계산 재사용(리그 전체를 두 번 계산하던 것)
    full = _pf(league)
    squads = [str(c) for c in full["squad"].dropna().unique()] if full is not None else list(lu)
    m: dict[str, float] = {c: (lu[c]["overall"] if c in lu else 75) for c in squads}
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


# 리그 레벨(교차 이적 projection·평점 리그 보정 공용). EPL 기준 100 — src/league_level.py
import league_level as _ll  # noqa: E402

_LEAGUE_LEVEL = _ll.levels()


def _project_ovr(base: int, source: str, target: str, big_match: bool, age, bucket: str) -> tuple[int, str, str]:
    """타 리그 → 우리 리그 이적 시 예상 OVR + (검증근거, 적응리스크 노트).

    기본 OVR(그 리그 실력)은 그대로 두고, '오면 얼마나 통할까'만 보정:
      - 리그 계수(더 센 리그로 갈수록 감점, 약한 리그로 가도 인플레 없음)
      - 유럽(UCL/UEL) 검증 → 완화   - 나이·포지션 적응 리스크(공격수 템포↑, 수비/GK 이식 잘됨)
    """
    if source == target:
        return base, "", ""
    # OVR 은 이미 리그 수준을 담은 절대 척도(평점 리그 보정·최종 레벨 보정·시장가치)라 리그 비율만큼 다시 깎으면 이중 할인이다.
    # 2026-10-19 검증: 이번 시즌 리그를 옮긴 41명 — 실제 OVR 변화 평균 +1.4 인데 예전 환산(OVR × 레벨 비율, 공격수 −1,
    # 유럽 +1.5)은 −2.2 로 예측(오차 4.3 vs 환산 안 함 2.0). 크바라츠헬리아 87 → 80. 사용자 지적('우리 리그 적용해서 너무 낮아짐').
    # → 더 센 리그로 갈 때만 레벨 차 × 0.1 의 작은 적응 할인 + 30세 이상 −1. 적응 위험은 글로만(점수 아님).
    lvl_s, lvl_t = _LEAGUE_LEVEL.get(source, 96.0), _LEAGUE_LEVEL.get(target, 100.0)
    adj = (min(lvl_s, lvl_t) - lvl_t) * 0.1           # ≤0 · 벨기에 → EPL −1.2, 라리가 → EPL −0.5
    risk, notes = 0.0, []
    if _num(age) >= 30:
        risk += 1.0; notes.append("노쇠 적응")
    if bucket in ("LW", "RW", "ST", "AM") and lvl_s < lvl_t - 3:
        notes.append("템포·피지컬 적응")
    proj = int(round(base + adj - risk))
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
              "LigaPortugal": "포르투갈 리그", "Eredivisie": "에레디비시",
              "BelgianProLeague": "벨기에 리그"}


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


@_memo(ttl=21600)
def _rec_pool(league: str):
    """추천 후보 풀용 리그 표 — 출전·세부 포지션·OVR·이탈 여부. 팀과 무관해 리그별로 한 번만 만든다
    (예전엔 추천 1회마다 8개 리그 3,500명을 다시 준비). 공유 캐시라 호출부는 고쳐 쓰지 않는다."""
    df = _pf(league)
    if df is None:
        return None
    df["_mn"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["_bucket"] = df.apply(_pos_bucket, axis=1)
    if "_ovr" not in df.columns:
        df["_ovr"] = df.apply(_player_ovr, axis=1)
    df["_left"] = (df["left_for"].notna() & (df["left_for"].astype(str).str.strip() != "")) \
        if "left_for" in df.columns else False
    return df


@app.get("/api/recommend/{team}")
@_memo(ttl=21600)
def recommend(team: str, league: str = ACTIVE_LEAGUE):
    """보강 후보 — 포메이션 전 포지션에서 '얇은 세부 포지션(CB/RB/DM…)' 을 가려내고,
    각 포지션마다 팀 티어에 맞는 현실적 후보를 **전 리그(교차리그 projection)** 에서 추천."""
    full = _pf(league)
    if full is None:
        return {"team": team, "weakest": None, "recommendations": [], "lost_targets": [], "addressed": False}

    nd = _compute_needs(team, league)
    trr = rv3.team_ratings(_with_roster(full, team, league), team, perf=_team_perf(team, league)) or {}
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
    # 니즈 v2(부상·폼·이적 공백·나이) 상위 포지션이 있으면 그걸 쓴다 — 아스날 좌윙 공백을 '수비'로 보던 문제
    try:
        pn_roles = [x["role"] for x in _position_needs(team, league)["roles"] if x["urgency"] >= 15][:4]
        if pn_roles:
            weak_buckets = pn_roles
    except Exception:  # noqa: BLE001
        pass
    policy = _transfer_policy(team)
    addressed = bool({_LINE_OF_BUCKET[b] for b in weak_buckets} & signed_lines)

    tout = _transferred_out(league)

    import numpy as _np

    def _pct_in(s, v):
        """s = 정렬된 numpy 배열(_dist). v 보다 작은 비율(%)."""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0
        if v != v or len(s) == 0:
            return 0
        return int(round(_np.searchsorted(s, v, side="left") / len(s) * 100))

    # 2) 후보 풀 — 같은 리그 + 데이터 있는 모든 타 리그(EPL·LaLiga·SerieA·…). 리그별 준비는 캐시(_rec_pool)
    pool = _rec_pool(league)
    pool = pool[pool["squad"] != team].copy()
    pool["_left"] = pool["_left"] | pool.apply(
        lambda r: (str(r.get("squad") or ""), str(r.get("norm_key"))) in tout, axis=1)
    src_meta = {league: {"pool": pool, "usage": _comp_usage(league),
                         "club": _club_strength(league), "resolve": _players_lookup(league)}}
    for olg in ds.available_leagues():
        if olg == league:
            continue
        op = _rec_pool(olg)
        if op is None or "player" not in op.columns:
            continue
        src_meta[olg] = {"pool": op, "usage": _comp_usage(olg),
                         "club": _club_strength(olg), "resolve": _players_lookup(olg)}

    _dist_cache: dict = {}

    def _dist(src, bk, col):
        key = (src, bk, col)
        if key not in _dist_cache:
            p = src_meta[src]["pool"]
            sub = p[p["_bucket"] == bk]
            vals = (pd.to_numeric(sub.get(col), errors="coerce").dropna().to_numpy(dtype=float)
                    if col and col in sub.columns else _np.array([], dtype=float))
            _dist_cache[key] = _np.sort(vals)
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
        # 핵심 주전(출전 60%+)은 경쟁 팀끼리 팔지 않는다 — 아스날에 홀란·반다이크·팔머 추천 방지(2026-10-19 사용자)
        #   같은 리그: 우리보다 전력 6 이내·위 팀 · 다른 리그: 우리와 비슷하거나 강한 팀(3 이내)
        key = _num(r.get("minutes")) >= _mm(2000, src)
        if ok and key and ((src == league and cstr >= team_ovr - 6) or cstr >= team_ovr - 3):
            ok, why = False, "경쟁 팀 핵심 주전" if src == league else "강팀 핵심 주전"
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
            sub = p[(p["_bucket"] == bk) & (~p["_left"]) & (p["_mn"] >= _mm(600, src))] \
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
            elif (not ok) and proj >= team_ovr - 2 and pl_name not in seen_long and len(longshots) < 12:
                seen_long.add(pl_name); longshots.append(t)
    picked.sort(key=lambda x: -x[4])
    # 드림 타깃 = 수준(예상 OVR) + 이 팀이 그 자리에 쓰는 스타일과의 유사도(transfer_fit 서버 메모리 벡터).
    # 예전엔 OVR 순으로만 골라 '브루노가 아스날 스타일에 맞나?'에 답하지 못했다(2026-10-19 사용자)
    import transfer_fit as tf  # noqa: PLC0415
    _style: dict = {}
    for t in longshots:
        try:
            _style[t[0]["player"]] = tf.team_style_fit(t[0]["player"], t[1], _ROLE_TM.get(t[12], ""), team)
        except Exception:  # noqa: BLE001
            _style[t[0]["player"]] = None
    longshots = [t for t in longshots if (_style.get(t[0]["player"]) or 0) >= 45] or longshots
    longshots.sort(key=lambda x: -(0.6 * x[4] + 0.4 * (_style.get(x[0]["player"]) or 0)))

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
        pfit = _policy_fit(policy, age, val)
        if pfit["ok"]:
            why_fit.append("구단 이적 정책(나이·이적료)에 맞음")
        why_risk += pfit["notes"]
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
            "why_fit": why_fit, "why_risk": why_risk, "confidence": conf, "policy_ok": pfit["ok"],
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
            "current_ovr": base, "reason": t[8], "style_fit": _style.get(r["player"]),
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

    inj = _injuries_table(league)
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



# ── 포지션 니즈 v2(스카우트 데스크·리크루트 풀·드림 타깃 공용) ──────────────────────────────
# 2026-10-19 사용자: "아스날은 마르티넬리·트로사르가 나가고 촐리스 한 명만 사서 좌윙이 얇은데 '수비가 약하다'고 한다.
# 부상·폼·이적 평가·이적 정책까지 시즌 중에 유기적으로 바뀌어야 한다". 예전 니즈는 GK·수비·미드·공격 4줄 단위라
# 좌윙 3명 이탈이 '공격'(사카·하베르츠…) 안에 묻혔고, 같은 줄에 영입이 하나라도 있으면 '해결'로 봤다.
_ROLE_EN = {"GK": "GK", "LB": "LB", "CB": "CB", "RB": "RB", "DM": "DM", "CM": "CM", "AM": "AM",
            "LW": "LW", "RW": "RW", "ST": "ST"}
_ROLE_TM = {"GK": "Goalkeeper", "LB": "Left-Back", "CB": "Centre-Back", "RB": "Right-Back", "DM": "Defensive Midfield",
            "CM": "Central Midfield", "AM": "Attacking Midfield", "LW": "Left Winger", "RW": "Right Winger",
            "ST": "Centre-Forward"}
_MK_DAY = {"초": 5, "중순": 15, "말": 25}


def _weeks_out(until, today=None) -> float:
    """부상 복귀까지 남은 주 — TM 'dd/mm/yyyy' · FotMob 한국어('12월 초 복귀 예상'·'약 1~2주'·'출전 불투명'). 모르면 4주."""
    import re  # noqa: PLC0415
    today = today or _today_kst()
    t = str(until or "").strip()
    if not t or t.lower() == "nan":
        return 4.0
    g = re.match(r"(\d{2})/(\d{2})/(\d{4})$", t)
    if g:
        return max(0.0, (datetime.date(int(g.group(3)), int(g.group(2)), int(g.group(1))) - today).days / 7)
    g = re.match(r"(\d{1,2})월 (초|중순|말)", t)
    if g:
        mo = int(g.group(1))
        y = today.year + (1 if mo < today.month - 1 else 0)
        return max(0.0, (datetime.date(y, mo, _MK_DAY[g.group(2)]) - today).days / 7)
    g = re.match(r"약 (\d+)(?:~(\d+))?(일|주|개월)", t)
    if g:
        a = (int(g.group(1)) + int(g.group(2) or g.group(1))) / 2
        return a / 7 if g.group(3) == "일" else a * 4.3 if g.group(3) == "개월" else a
    if "시즌 아웃" in t:
        return 30.0
    if any(k in t for k in ("불투명", "며칠", "단기", "훈련 복귀")):
        return 0.5
    return 3.0 if "몇 주" in t else 4.0


@_memo(ttl=21600)
def _prev_frame(league: str):
    """지난 시즌 선수 표 — 떠난 선수(우리 리그 밖으로 간 마르티넬리 등)의 OVR 을 그 팀 시절 값으로."""
    try:
        return _pf(league, f"{SEASON_START - 1}_{SEASON_START}")
    except Exception:  # noqa: BLE001
        return None


@_memo(ttl=1800)
def _position_needs(team: str, league: str) -> dict:
    """포지션(GK·LB·CB·RB·DM·CM·AM·LW·RW·ST)마다 시급도 0~100 — 다섯 요소를 점수로 더한다.

    ① 뎁스: 포메이션 수요(베스트 XI) + 백업(수요의 절반, 최소 1)만큼 '팀 수준 옵션'(OVR ≥ 팀 OVR − 7, 2·3포지션은 0.5명)이 있나
    ② 지금 가용: 부상 때문에 이 자리 최선 조합(수요 인원) 평균 OVR 이 얼마나 떨어졌나(6주+ 장기 부상은 가산)
    ③ 이번 창 순증감: 나간 주요 선수(OVR ≥ 팀 OVR − 9, 지난 시즌 값) − 들어온 주요 선수 = 대체 안 된 자리
    ④ 주전 폼: 주전의 LAST 5 폼(src/recent_form.py)이 60 미만
    ⑤ 나이·계약: 31세+ 주전에 젊은 후계 없음 · 주전 계약 내년까지
    시급 50+ · 보강 필요 30+ · 관찰 15+ · 충분. ①②③(장기 부상·대체 안 됨)은 '1월 창', ④⑤만이면 '여름 창'."""
    import math  # noqa: PLC0415
    import positions as ps  # noqa: PLC0415
    full = _pf(league)
    df = _squad_df(team, league)
    if full is None or df is None or df.empty:
        return {"team": team, "team_ovr": None, "roles": []}
    ex = _roster_extras(team, league, df)
    if ex:
        df = pd.concat([df, pd.DataFrame(ex).dropna(axis=1, how="all")], ignore_index=True)
    tr_ = rv3.team_ratings(_with_roster(full, team, league), team, perf=_team_perf(team, league)) or {}
    team_ovr = float(tr_.get("overall", 78))
    inj = _active_injuries(team, league)
    today = _today_kst()
    cards = []
    for _, r in df.iterrows():
        pr = _pos_profile(r)
        if not pr.get("primary"):
            continue
        nk = ps.norm_name(r["player"])
        rec, frm = r.get("_recent"), r.get("_form")
        cards.append({"player": str(r["player"]), "ovr": int(_player_ovr(r)), "age": int(_num(r.get("age"))),
                      "primary": pr["primary"], "secondary": list(pr["secondary"]), "photo": _photo(r),
                      "injured": nk in inj, "until": (inj.get(nk) or {}).get("until", ""),
                      "out_w": round(_weeks_out((inj.get(nk) or {}).get("until"), today), 1) if nk in inj else 0.0,
                      "recent": int(rec) if rec is not None and rec == rec else None,
                      "form": int(frm) if frm is not None and frm == frm else None,
                      "contract": str(r.get("tm_contract_until") or "")[:4],
                      "joined": str(r.get("tm_joined_date") or "")[:10]})
    demand = _formation_bucket_needs(team, league) or {}
    # 이번 창 이동(임대 제외) — 떠난 선수 OVR 은 지난 시즌 이 팀 시절 값(없으면 이적료 기준점)
    moves: dict = {}
    trt = ds.read_table("transfers", league=league)
    prev = _prev_frame(league)
    if trt is not None and "squad" in trt.columns:
        tt, _wf = _window_filter(trt[trt["squad"] == team].copy(), _current_window())
        tt = tt[~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
        for _, r in tt.iterrows():
            b = _pos_bucket({"tm_position": r.get("pos")})
            name, d_ = str(r.get("player") or ""), str(r.get("direction"))
            ovr = None
            src = full if d_ == "in" else prev
            if src is not None:
                hit = src[(src["squad"] == team) & (src["player"] == name)] if d_ == "in" else src[src["player"] == name]
                if not hit.empty:
                    ovr = int(_player_ovr(hit.iloc[0]))
            if ovr is None and _num(r.get("fee_eur")):
                ovr = int(round(rv3.value_ovr(_num(r.get("fee_eur"))) or 0)) or None
            ph = str(r.get("photo") or "")
            moves.setdefault(b, {"in": [], "out": []}).setdefault(d_, []).append(
                {"player": name, "ovr": ovr, "fee": str(r.get("fee_text") or ""), "age": int(_num(r.get("age"))) or None,
                 "photo": ph if ph.startswith("http") and "default" not in ph else ""})
    lvl_opt = team_ovr - 7
    roles = []
    for b in ps.ROLES:
        d = int(demand.get(b, 0))
        prim = [c for c in cards if c["primary"] == b]
        sec = [c for c in cards if b in c["secondary"]]
        need_n = d + max(1, math.ceil(d * 0.5)) if d else 1
        # GK 백업은 거의 뛰지 않아 기준을 낮추고(팀 OVR − 15), 노쇠는 34세부터(골키퍼 전성기가 늦다)
        opt_cut = lvl_opt - 8 if b == "GK" else lvl_opt
        old_age = 34 if b == "GK" else 31
        options = sum(1 for c in prim if c["ovr"] >= opt_cut) + 0.5 * sum(1 for c in sec if c["ovr"] >= opt_cut)
        # 중앙 미드필더는 DM·CM·AM 을 서로 오간다 — 같은 계열 주포지션 선수도 0.5명(AM 은 CM 만). 예전엔 아스날 AM 이
        # '뎁스 1.5/2'로 니즈에 올라 드림 타깃에 브루노가 나왔다(2026-10-19 사용자: 라이스·기마랑이스·외데고르·수비멘디로 충분)
        fam = {"DM": ("CM",), "CM": ("DM", "AM"), "AM": ("CM",)}.get(b, ())
        options += 0.5 * sum(1 for c in cards if c["primary"] in fam and b not in c["secondary"] and c["ovr"] >= opt_cut)
        reasons, pts, jan = [], 0.0, False
        sig: dict = {"depth": {"have": round(options, 1), "need": need_n}}
        short = max(0.0, need_n - options)
        if short > 0 and d:
            pts += min(50, 35 * short)
            reasons.append(f"뎁스 {options:g}/{need_n}명 — 팀 수준(OVR {opt_cut:.0f}+) 옵션 부족")
            jan = True
        if d:
            fill = lvl_opt - 8
            best = (sorted([c["ovr"] for c in prim] + [c["ovr"] - 2 for c in sec], reverse=True) + [fill] * d)[:d]
            now = (sorted([c["ovr"] for c in prim if c["out_w"] < 1] + [c["ovr"] - 2 for c in sec if c["out_w"] < 1],
                          reverse=True) + [fill] * d)[:d]
            drop = sum(best) / d - sum(now) / d
            long_out = [c for c in prim + sec if c["out_w"] >= 6]
            if drop >= 2:
                sig["injury"] = {"drop": round(drop, 1), "players": [{"player": c["player"], "weeks": c["out_w"], "photo": c["photo"]}
                                                                    for c in prim + sec if c["injured"]]}
                pts += min(40, 5 * drop + (10 if long_out else 0))
                hurt = [f"{c['player'].split()[-1]} {c['out_w']:.0f}주" for c in prim + sec if c["injured"]]
                reasons.append(f"부상으로 이 자리 전력 −{drop:.0f}" + (f" ({', '.join(hurt)})" if hurt else ""))
                jan = jan or bool(long_out)
        mv = moves.get(b, {"in": [], "out": []})
        mv.setdefault("in", [])
        mv.setdefault("out", [])
        q_out = [x for x in mv["out"] if (x["ovr"] or 0) >= team_ovr - 9]
        q_in = [x for x in mv["in"] if (x["ovr"] or 0) >= team_ovr - 9]
        unrep = len(q_out) - len(q_in)
        if unrep > 0:
            sig["unreplaced"] = unrep
            pts += min(40, 20 * unrep)
            jan = True
            reasons.append(f"이번 창 주요 선수 {len(q_out)}명 나감 · {len(q_in)}명 영입 — 대체 안 된 자리 {unrep}")
        starters = sorted([c for c in prim if c["out_w"] < 1], key=lambda c: -c["ovr"])[:max(1, d)]
        cold = [c for c in starters if c["recent"] is not None and c["recent"] < 60]
        if cold and d:
            sig["cold"] = [{"player": c["player"], "recent": c["recent"], "photo": c["photo"]} for c in cold]
            pts += min(24, 12 * len(cold))
            reasons.append("주전 최근 폼 저조: " + ", ".join(f"{c['player'].split()[-1]} LAST 5 {c['recent']}" for c in cold))
        old = [c for c in starters if c["age"] >= old_age]
        young = [c for c in prim if c["age"] and c["age"] <= 23 and c["ovr"] >= lvl_opt]
        if old and not young and d:
            sig["aging"] = [{"player": c["player"], "age": c["age"]} for c in old]
            pts += 10
            reasons.append("주전 " + ", ".join(f"{c['player'].split()[-1]} {c['age']}세" for c in old) + " · 젊은 후계 없음")
        # 올해 이후 만료만, 이번 여름 새로 온 선수는 제외 — TM 계약일이 전 소속 값으로 남아 'Torp ~2024'·
        # 'Rushworth ~2026'(€25.7M 영입)이 근거로 나왔다(2026-10-20 점검)
        season_start = f"{SEASON_START}-07-01"
        exp = [c for c in starters if c["contract"] and str(today.year) <= c["contract"] <= str(today.year + 1)
               and not (c.get("joined") and c["joined"] >= season_start)]
        if exp and d:
            sig["contract"] = [{"player": c["player"], "until": c["contract"]} for c in exp]
            pts += 8
            reasons.append("주전 계약 " + ", ".join(f"{c['player'].split()[-1]} ~{c['contract']}" for c in exp))
        pts = min(100.0, pts)
        level = "urgent" if pts >= 50 else "need" if pts >= 30 else "watch" if pts >= 15 else "ok"
        verdict = ""
        if q_out or q_in:
            verdict = "대체 안 됨" if unrep > 0 else ("업그레이드" if q_in and q_out and
                                                    max(x["ovr"] or 0 for x in q_in) > max(x["ovr"] or 0 for x in q_out)
                                                    else "보강" if q_in else "")
        depth = sorted(prim, key=lambda c: (c["injured"], -c["ovr"])) + sorted(sec, key=lambda c: (c["injured"], -c["ovr"]))
        roles.append({"role": b, "label": _BUCKET_LABEL.get(b, b), "demand": d, "urgency": int(round(pts)),
                      "level": level, "when": "1월 창" if jan else "여름 창", "reasons": reasons, "signals": sig,
                      "options": round(options, 1), "need_n": need_n,
                      "depth": [{"player": c["player"], "ovr": c["ovr"], "kind": "primary" if c in prim else "secondary",
                                 "injured": c["injured"], "until": c["until"], "recent": c["recent"], "age": c["age"],
                                 "photo": c["photo"]} for c in depth[:6]],
                      "window": {"out": mv["out"], "in": mv["in"], "verdict": verdict}})
    roles.sort(key=lambda x: (-x["urgency"], x["role"]))
    return {"team": team, "team_ovr": round(team_ovr, 1), "roles": roles}


@_memo(ttl=21600)
def _transfer_policy(team: str) -> dict | None:
    """구단 이적 정책(최근 두 시즌 영입, 임대 제외) — 나이·이적료·출신 리그. 추천 후보를 이 기준과 대조한다."""
    import team_names as tn_  # noqa: PLC0415
    rows = []
    leagues = list(ds.available_leagues())
    clubs_of: dict = {}
    for se in (f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"):
        for lg in leagues:
            st = ds.read_table("standings", league=lg, season=se)
            if st is not None and "squad" in st.columns:
                for t in st["squad"].astype(str):
                    clubs_of.setdefault(t, lg)
            t_ = ds.read_table("transfers", league=lg, season=se)
            if t_ is not None and "squad" in t_.columns:
                rows.append(t_[(t_["squad"] == team) & (t_["direction"] == "in")].assign(_lg=lg, _season=se))
    if not rows:
        return None
    # 같은 이적이 두 시즌 파일에 모두 실릴 때가 있다(창 기준 season_id·window 로 한 번만)
    t = pd.concat(rows, ignore_index=True)
    t = t.drop_duplicates(subset=[c for c in ("player", "season_id", "window") if c in t.columns])
    t = t[~t["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
    if len(t):
        # 2군 승격은 영입 정책이 아니다 — 브뤼헤 Club NXT 승격이 섞여 정책이 '17~22세 U23 83%'로 왜곡됐다(2026-10-20 점검)
        t = t[~_own_reserve_mask(t, team)]
    if t.empty:
        return None
    home = t["_lg"].iloc[0]
    names = list(clubs_of)

    def src_league(club):
        c = str(club or "")
        hit = clubs_of.get(c) or clubs_of.get(tn_.best(c, names) or "")
        return hit or "기타"
    t = t.assign(_src=t["club"].map(src_league), _age=pd.to_numeric(t["age"], errors="coerce"),
                 _fee=pd.to_numeric(t["fee_eur"], errors="coerce"))
    paid = t[t["_fee"] > 0]
    ages = t["_age"].dropna()
    src = t["_src"].value_counts()
    return {"team": team, "n": int(len(t)), "seasons": 2,
            "age_med": round(float(ages.median()), 1) if len(ages) else None,
            "age_lo": int(ages.quantile(0.25)) if len(ages) else None, "age_hi": int(ages.quantile(0.75)) if len(ages) else None,
            "u23_share": round(float((ages <= 23).mean()), 2) if len(ages) else None,
            "fee_med": float(paid["_fee"].median()) if len(paid) else None,
            "fee_max": float(paid["_fee"].max()) if len(paid) else None,
            "paid_share": round(len(paid) / len(t), 2),
            "domestic_share": round(float((t["_src"] == home).mean()), 2),
            "sources": [{"league": k, "n": int(v)} for k, v in src.head(4).items()],
            "big": [{"player": r["player"], "fee": float(r["_fee"]), "age": None if r["_age"] != r["_age"] else int(r["_age"]),
                     "from": str(r.get("club") or "")} for _, r in paid.sort_values("_fee", ascending=False).head(3).iterrows()]}


def _policy_fit(policy: dict | None, age, value_eur) -> dict:
    """후보 ↔ 구단 정책: 나이(최근 영입 25~75% 구간 ±1세) · 이적료(시장가 × 1.2 ≤ 최고 이적료 × 1.15)."""
    if not policy:
        return {"ok": None, "notes": []}
    notes, ok = [], True
    if age and policy.get("age_lo") is not None:
        if age < policy["age_lo"] - 1 or age > policy["age_hi"] + 1:
            ok = False
            notes.append(f"나이 {age}세 — 최근 영입 {policy['age_lo']}~{policy['age_hi']}세 밖")
    if value_eur and policy.get("fee_max"):
        if value_eur * 1.2 > policy["fee_max"] * 1.15:
            ok = False
            notes.append(f"예상 이적료 €{value_eur * 1.2 / 1e6:.0f}M — 최고 지출 €{policy['fee_max'] / 1e6:.0f}M 초과")
    return {"ok": ok, "notes": notes}


@app.get("/api/needs/{team}")
def needs(team: str, league: str = ACTIVE_LEAGUE):
    """스카우트 데스크 — 예전 라인 단위 니즈(needs) + 포지션 니즈 v2(positions) + 이적 정책(policy)."""
    out = _compute_needs(team, league)
    try:
        pn = _position_needs(team, league)
        out["positions"], out["team_ovr"] = pn["roles"], pn["team_ovr"]
    except Exception as e:  # noqa: BLE001
        out["positions"], out["positions_error"] = [], f"{type(e).__name__}: {str(e)[:120]}"
    try:
        out["policy"] = _transfer_policy(team)
    except Exception:  # noqa: BLE001
        out["policy"] = None
    return out


_DB_CACHE: dict = {"key": None, "body": None}


def _db_mtime() -> float:
    """football.db 수정시각 — 캐시 무효화 키(재빌드되면 자동 갱신)."""
    try:
        return os.path.getmtime(ds.DB_PATH)
    except OSError:
        return 0.0


@app.get("/api/names-ko")
@_memo(ttl=21600)
def names_ko():
    """한글 이름 사전(data/names_ko.csv — 위키 언어 링크, src/names_ko.py 주간 갱신) → 전역 검색의 한글 검색.
    {'players': {'Declan Rice|Arsenal': '데클런 라이스'}, 'clubs': {'Arsenal': '아스널 FC'}}. 같은 한글 제목이 여러 선수면 뺀다."""
    p = ds.DB_PATH.parent / "names_ko.csv"
    if not p.exists():
        return {"players": {}, "clubs": {}}
    kd = pd.read_csv(p, dtype=str).fillna("")
    pl = kd[kd["kind"] == "player"]
    dup = pl.groupby("ko")["name"].transform("nunique") > 1          # Mo Salah 두 명 → '모하메드 살라' 같은 잘못된 링크
    players = {f"{r.name}|{r.squad}": r.ko for r in pl[~dup].itertuples()}
    clubs = {r.name: r.ko for r in kd[kd["kind"] == "club"].itertuples()}
    return {"players": players, "clubs": clubs}


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


def _wiki_squad(team: str, league: str) -> list[dict]:
    """위키백과 스쿼드 표 — 주장단(1~4)·등번호·국적 코드(src/fetch_wiki_squads.py, 8개 리그)."""
    w = ds.read_table("wiki_squads", league=league)
    if w is None or "squad" not in w.columns:
        return []
    out = []
    for _, r in w[w["squad"].astype(str) == team].iterrows():
        rk = pd.to_numeric(r.get("role_rank"), errors="coerce")
        no = pd.to_numeric(r.get("no"), errors="coerce")
        out.append({"player": str(r.get("player")), "section": str(r.get("section") or "first"),
                    "no": None if pd.isna(no) else int(no), "nat": str(r.get("nat") or "").strip(),
                    "pos": str(r.get("pos") or "").strip(), "rank": None if pd.isna(rk) else int(rk)})
    return out


_GLOBAL_CSV: dict = {}


def _global_csv(name: str) -> pd.DataFrame | None:
    """시즌·리그 구분 없는 원천(data/wc_squads.csv · fifa_ranking.csv) — 수정 시각 기준 캐시."""
    p = ROOT / "data" / f"{name}.csv"
    if not p.exists():
        return None
    key = (name, p.stat().st_mtime)
    if key not in _GLOBAL_CSV:
        _GLOBAL_CSV.clear() if len(_GLOBAL_CSV) > 8 else None
        _GLOBAL_CSV[key] = pd.read_csv(p)
    return _GLOBAL_CSV[key]


_NAT_ALIAS = {"korea, south": "korea republic", "south korea": "korea republic", "usa": "usa",
              "united states": "usa", "turkey": "turkiye", "iran": "ir iran", "ivory coast": "cote d'ivoire",
              "czech republic": "czechia", "cape verde": "cabo verde", "dr congo": "congo dr",
              "congo, dem. rep.": "congo dr", "china": "china pr", "north macedonia": "north macedonia",
              "bosnia-herzegovina": "bosnia and herzegovina", "curacao": "curacao", "the gambia": "gambia"}


_PREV_PAIRS: dict = {}


def _prev_lineup_pairs() -> tuple[dict, dict]:
    """지난 시즌 8개 리그(+컵) ESPN 선발 → 클럽별 함께 선발 수(전 소속 동료 그래프). DB 수정 시각 기준 캐시."""
    import team_network as tn  # noqa: PLC0415
    from leagues import DATA_DIR  # noqa: PLC0415
    key = (SEASON_START, ds._db_mtime())
    if key not in _PREV_PAIRS:
        frames = []
        for path in sorted(DATA_DIR.glob(f"espn_lineups*_{SEASON_START - 1}_{SEASON_START}.csv")):
            try:
                frames.append(read_lineup_csv(path, ["squad", "event_id", "starter", "player"]))   # 이름 정규화
            except (ValueError, OSError):
                continue
        _PREV_PAIRS.clear()
        _PREV_PAIRS[key] = tn.lineup_pairs(frames)
    return _PREV_PAIRS[key]


def _manager_careers() -> dict:
    """data/manager_careers.json(src/fetch_manager_careers.py)."""
    p = ROOT / "data" / "manager_careers.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@app.get("/api/network/{team}")
@_memo(ttl=21600)
def network(team: str, league: str = ACTIVE_LEAGUE):
    """팀 지식그래프 — LEADERSHIP · CHEMISTRY · ORIGINS · NATIONS · LINKS 렌즈 + 근거 인사이트.

    그래프 DB 없이 원천 CSV 로 같은 관계(PLAYS_FOR·TEAMMATE_OF·REPRESENTS·TransferEvent·RUMORED_WITH)를 엮는다
    — 운영 Neo4j(AuraDB 무료)가 잠들어도 항상 동작(src/team_network.py).
    """
    import team_names as tnm  # noqa: PLC0415
    import team_network as tn  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    from unidecode import unidecode  # noqa: PLC0415

    today = datetime.date.today()
    pf = _pf(league)
    if pf is None or "squad" not in pf.columns:
        return {"available": False, "reason": "선수 데이터 없음"}
    gone = _gone_keys(team, league)
    loans = _loans_out(team, league)
    rows = pf[pf["squad"] == team]
    rows = rows[[_person_key(p) not in gone and not _is_loaned(p, loans) for p in rows["player"]]]
    if rows.empty:
        return {"available": False, "reason": "선수 데이터 없음"}
    inj = _active_injuries(team, league)
    wiki = [w for w in _wiki_squad(team, league) if w["section"] == "first" and not _is_loaned(w["player"], loans)
            and _person_key(w["player"]) not in gone]
    # 입단일·사진 — TM 계약 명단(이 팀). players_full 에 tm_joined_date 가 없는 선수(출전 없는 1군·이름 표기 차이)가
    # '입단일 미상'(이니셜 아바타)으로 몰렸다(2026-10-15 사용자 지적, Man City JG·KP).
    _ct = ds.read_table("transfermarkt_contracts", league=league)
    _ct_rows = _ct[_ct["squad"] == team].to_dict("records") if _ct is not None and "squad" in _ct.columns else []

    def _tok(n) -> frozenset:   # 어순 무관('Kim Min-jae' ↔ 'Min-jae Kim')
        return frozenset(unidecode(str(n or "")).lower().replace("-", " ").split())
    ct_by: dict = {}
    for c in _ct_rows:
        if pd.notna(c.get("tm_id")):
            ct_by[("tm", str(int(_num(c["tm_id"]))))] = c
        ct_by.setdefault(_tok(c["player"]), c)
        ct_by.setdefault(_person_key(c["player"]), c)
        try:                                              # 레지스트리 기준 표기('Alfon González' → 'Alfon')
            import player_names as _pn  # noqa: PLC0415
            ct_by.setdefault(_tok(_pn.canon(c["player"], team, league)), c)
        except Exception:  # noqa: BLE001
            pass

    def ct_of(name, tm_id=None):
        if tm_id is not None and pd.notna(tm_id) and _num(tm_id) > 0:
            hit = ct_by.get(("tm", str(int(_num(tm_id)))))
            if hit is not None:
                return hit
        return ct_by.get(_tok(name)) or ct_by.get(_person_key(name))
    wiki_idx = tn.NameIndex([w["player"] for w in wiki])
    wiki_by = {w["player"]: w for w in wiki}

    # 국가(FIFA 랭킹·국기) · 월드컵 명단
    fifa = _global_csv("fifa_ranking")
    f_name, f_code = {}, {}
    if fifa is not None:
        for _, r in fifa.iterrows():
            rec = {"name": str(r["team"]), "code": str(r.get("code") or ""), "flag": str(r.get("flag") or ""),
                   "rank": int(r["rank"]) if pd.notna(r.get("rank")) else None}
            f_name[unidecode(str(r["team"])).lower()] = rec
            f_code[str(r.get("code") or "").upper()] = rec

    def nation_of(nat_name, code) -> dict | None:
        k = unidecode(str(nat_name or "")).lower().strip()
        rec = f_name.get(_NAT_ALIAS.get(k, k)) or (f_code.get(str(code or "").upper()) if code else None)
        if rec:
            return rec
        return {"name": str(nat_name), "code": str(code or ""), "flag": "", "rank": None} if nat_name else None

    wc = _global_csv("wc_squads")
    wc_idx = tn.NameIndex(wc["player"].astype(str).tolist()) if wc is not None else None

    # 최근 두 시즌 이적 기록(이 팀)
    trs = []
    for season in (f"{SEASON_START - 1}_{SEASON_START}", None):
        t = ds.read_table("transfers", league=league, season=season)
        if t is not None and "squad" in t.columns:
            trs.append(t[t["squad"] == team])
    tr = pd.concat(trs, ignore_index=True) if trs else pd.DataFrame()
    if not tr.empty:                                     # 리그에 따라 두 시즌 파일이 같은 내용(복사본)이다
        tr = tr.drop_duplicates(subset=[c for c in ("player", "direction", "club", "season_id", "window") if c in tr.columns])
    tin: dict = {}
    if not tr.empty:
        for _, r in tr[tr["direction"] == "in"].sort_values("season_id").iterrows():
            tin[_person_key(r["player"])] = r.to_dict()          # 가장 최근 영입 기록이 남게

    games, n_games = _on_pitch(team, league)
    chem = tn.chemistry_graph(games, rows["player"].astype(str).tolist())

    def pos_label(r) -> str:
        p = _pos_profile(r)
        return str(p.get("primary") or r.get("pos") or "")

    players, seen_wiki = [], set()
    for _, r in rows.iterrows():
        nm = str(r["player"])
        wname = wiki_idx.find(nm)
        w = wiki_by.get(wname) if wname else None
        if w:
            seen_wiki.add(w["player"])
        injury = inj.get(" ".join(unidecode(nm).lower().replace("-", " ").split()))
        age = pd.to_numeric(r.get("age"), errors="coerce")
        mn = pd.to_numeric(r.get("minutes"), errors="coerce")
        p = {"name": nm, "photo": _photo(r), "line": rv3.line_of_row(r), "pos": pos_label(r),
             "ovr": _player_ovr(r), "age": None if pd.isna(age) else int(age),
             "minutes": 0 if pd.isna(mn) else int(mn), "joined": str(r.get("tm_joined_date") or "")[:10] or None,
             "prev_squad": r.get("prev_squad") if isinstance(r.get("prev_squad"), str) else None,
             "no": w["no"] if w else None, "captain_rank": w["rank"] if w else None,
             "injured": bool(injury), "injury": (injury or {}).get("injury"),
             "wc": bool(wc_idx and wc_idx.find(nm)),
             "nation": nation_of(r.get("nationality"), w["nat"] if w else None),
             # 영향력 재료(src/team_network.leadership) — 시즌 폼, 볼 관여(90분당 파이널 서드 패스·키패스)
             "form": _num(r.get("_form"), None), "ft90": _num(r.get("final_third_passes_per90"), None),
             "kp90": _num(r.get("key_passes_per90"), None)}
        c = ct_of(nm, r.get("tm_id"))
        if c is not None:
            p["joined"] = p["joined"] or (str(c.get("joined_date") or "")[:10] or None)
            if not p["photo"] and str(c.get("tm_photo") or "").startswith("http"):
                p["photo"] = str(c["tm_photo"])
        p["origin"] = tn.acquisition(p, tin.get(_person_key(nm)), team, today)
        players.append(p)
    _LINE = {"GK": "GK", "DF": "DEF", "MF": "MID", "FW": "ATT"}
    for w in wiki:                                       # 아직 출전 기록 없는 1군(부상·백업 GK 등)
        if w["player"] in seen_wiki:
            continue
        # TM 스쿼드 명단에도 없는 위키 1군(유스 등록·늦은 위키)은 뺀다 — 입단일·사진·나이 모두 미상이라
        # '입단일 미상'만 늘렸다(Genk 30명). 주장단은 남긴다.
        if _ct_rows and ct_of(w["player"]) is None and not w["rank"]:
            continue
        injury = inj.get(" ".join(unidecode(w["player"]).lower().replace("-", " ").split()))
        p = {"name": w["player"], "photo": _resolve_photo(w["player"], lambda _n: None, league),
             "line": _LINE.get(w["pos"], "MID"), "pos": w["pos"], "ovr": None, "age": None, "minutes": 0,
             "joined": None, "prev_squad": None, "no": w["no"], "captain_rank": w["rank"],
             "injured": bool(injury), "injury": (injury or {}).get("injury"),
             "wc": bool(wc_idx and wc_idx.find(w["player"])), "nation": nation_of(None, w["nat"]), "unplayed": True}
        c = ct_of(w["player"])
        if c is not None:
            p["joined"] = str(c.get("joined_date") or "")[:10] or None
            if not p["photo"] and str(c.get("tm_photo") or "").startswith("http"):
                p["photo"] = str(c["tm_photo"])
        p["origin"] = tn.acquisition(p, tin.get(_person_key(w["player"])), team, today)
        players.append(p)
    for p in players:
        p["tenure"] = tn._years_since(p.get("joined"), today)
        if p["tenure"] is not None:
            p["tenure"] = round(p["tenure"], 1)

    lead = tn.leadership(players, chem, today)

    # 클럽 관계망 — 우리 8개 리그 클럽 이름으로 맞추고, 그 밖은 원래 표기
    club_league: dict[str, str] = {}
    alumni = []
    loc_rows: dict[str, dict] = {}
    for lg in LEAGUES:
        f = _pf(lg)
        if f is None or "squad" not in f.columns:
            continue
        for sq in f["squad"].dropna().astype(str).unique():
            club_league[sq] = lg
        for _, r in f.sort_values("minutes", ascending=False).iterrows():   # 같은 이름은 출전 많은 쪽
            loc_rows.setdefault(str(r["player"]), {"name": str(r["player"]), "club": str(r["squad"]), "league": lg,
                                                    "photo": _photo(r), "ovr": _player_ovr(r)})
        if "prev_squad" in f.columns and "tm_id" in f.columns:
            a = f[(f["prev_squad"] == team) & (f["squad"] != team) & f["tm_id"].notna()]
            for _, r in a.iterrows():
                alumni.append({"player": str(r["player"]), "club": str(r["squad"]), "photo": _photo(r),
                               "ovr": _player_ovr(r)})
    all_clubs = list(club_league)
    _canon_cache: dict = {}

    def canon(name: str):
        if name not in _canon_cache:
            _canon_cache[name] = name if name in club_league else tnm.best(name, all_clubs)
        return _canon_cache[name]

    rumors = []
    ru = ds.read_table("transfer_rumors", league=league)
    if ru is not None and "target_club" in ru.columns:
        for _, r in ru.iterrows():
            tgt, cur = str(r.get("target_club") or ""), str(r.get("current_club") or "")
            prob = pd.to_numeric(r.get("probability"), errors="coerce")
            rec = {"player": str(r.get("player")), "prob": None if pd.isna(prob) else float(prob)}
            if canon(tgt) == team and cur:
                rumors.append({**rec, "club": cur, "direction": "in"})
            elif canon(cur) == team and tgt:
                rumors.append({**rec, "club": tgt, "direction": "out"})
    tr_rows = [{"player": str(r["player"]), "club": str(r.get("club") or ""), "direction": r.get("direction"),
                "fee_text": r.get("fee_text") if isinstance(r.get("fee_text"), str) else None,
                "photo": r.get("photo") if isinstance(r.get("photo"), str) and "default" not in str(r.get("photo")) else "",
                "window": f"{r.get('season_id')} {r.get('window')}"} for _, r in tr.iterrows()] if not tr.empty else []
    lk = tn.links(team, tr_rows, alumni, rumors, canon, tm.team_logo, lambda c: club_league.get(c))
    orig = tn.origins(players, lambda c: club_league.get(canon(c) or ""))
    nat = tn.nations(players)
    chm = chemistry_ep(team, league)
    ins = tn.insights(team, lead, chem, chm.get("duos", []), orig, nat, lk, players)

    loc_idx = tn.NameIndex(list(loc_rows))

    def locate(name):
        k = loc_idx.find(name)
        return loc_rows.get(k) if k else None

    # 대표팀 동료 — 우리 선수가 든 2026 월드컵 명단의 나머지가 어느 클럽에
    our_nat: dict[str, list[str]] = {}
    wc_rows = []
    if wc is not None:
        wc_nat = {str(r["player"]): str(r["nation"]) for _, r in wc.iterrows()}
        wc_rows = [{"nation": str(r["nation"]), "player": str(r["player"]), "pos": str(r.get("pos") or "")}
                   for _, r in wc.iterrows()]
        for p in players:
            k = wc_idx.find(p["name"]) if wc_idx else None
            if k and k in wc_nat:
                our_nat.setdefault(wc_nat[k], []).append(p["name"])
    nat_web = tn.national_web(team, our_nat, wc_rows, locate)
    for nname, w in nat_web.items():
        rec = nation_of(nname, None) or {}
        w["flag"], w["rank"], w["fifa_name"] = rec.get("flag", ""), rec.get("rank"), rec.get("name", nname)
        for c in w["clubs"]:
            c["logo"] = tm.team_logo(c["club"]) if c["club"] != "OTHER" else ""

    # 전 소속 동료 — 지난 시즌 8개 리그 라인업(함께 선발 5경기+)
    pairs, pnames = _prev_lineup_pairs()
    ti = tn.ties(team, players, pairs, pnames, locate)
    for c in ti["clubs"]:
        c["logo"] = tm.team_logo(c["club"])

    # 감독 커리어 그래프
    mg = {"available": False}
    try:
        careers = _manager_careers()
        current: dict = {}
        mine_prof = None
        for lg2 in LEAGUES:
            mp = data_path("manager_profiles", lg2, ext="json")
            if not mp.exists():
                continue
            for t2, m in json.loads(mp.read_text(encoding="utf-8")).items():
                if isinstance(m, dict) and m.get("name"):
                    current[m["name"]] = {"team": t2, "league": lg2, "photo": m.get("photo_url") or "",
                                          "logo": tm.team_logo(t2)}
                    if t2 == team and lg2 == league:
                        mine_prof = m
        if mine_prof:
            mg = tn.manager_graph(team, {"name": mine_prof["name"], "photo": mine_prof.get("photo_url") or "",
                                         "nationality": mine_prof.get("nationality"),
                                         "appointed": mine_prof.get("appointed")},
                                  careers, current, canon, tm.team_logo, players, SEASON_START)
    except (OSError, ValueError):
        pass
    ins += tn.insights_extra(team, nat_web, ti, mg)
    return {"available": True, "team": team, "league": league, "color": tm.team_color(team), "logo": tm.team_logo(team),
            "games": n_games, "players": players, "leadership": lead,
            "chemistry": {"nodes": chem["nodes"], "edges": chem["edges"], "duos": chm.get("duos", []),
                          "trios": chm.get("trios", [])},
            "origins": orig, "nations": nat, "links": lk, "insights": ins,
            "national": nat_web, "ties": ti, "manager": mg,
            "sources": {"captains": "wikipedia" if any(w["rank"] for w in wiki) else None}}


def _stats_asof(pf, team: str | None = None) -> str | None:
    """선수 표의 골·도움 기준일(src/season_totals.py `_stats_asof` 의 최댓값)."""
    if pf is None or "_stats_asof" not in pf.columns:
        return None
    s = pf if team is None else pf[pf["squad"] == team]
    v = s["_stats_asof"].dropna().astype(str)
    return v.max() if len(v) else None


def tn_role_ko(rank: int) -> str:
    return {1: "주장", 2: "부주장"}.get(rank, f"{rank}번째 주장")


@app.get("/api/captains/{team}")
@_memo(ttl=21600)
def captains(team: str, league: str = ACTIVE_LEAGUE):
    """주장단 — 위키백과 스쿼드 표(8개 리그, 주장·부주장·3·4번째) 우선, 없으면 EPL 공식 주장 + (c) 기록 부주장."""
    from unidecode import unidecode
    def _key(nm):
        t = unidecode(str(nm)).lower().split()
        return t[-1] if t else str(nm).lower()

    resolve = _players_lookup(league)
    wiki = sorted([w for w in _wiki_squad(team, league) if w["rank"]], key=lambda w: w["rank"])
    if wiki:
        inj = _active_injuries(team, league)
        out = []
        for w in wiki[:5]:
            r = resolve(w["player"])
            if r is not None and str(r.get("squad")) != team:
                r = None
            nm = str(r["player"]) if r is not None else w["player"]
            out.append({"name": nm, "photo": _photo(r) if r is not None else _resolve_photo(nm, lambda _n: None, league),
                        "ovr": _player_ovr(r) if r is not None else None,
                        "pos": str(w["pos"] or (r.get("pos") if r is not None else "")), "no": w["no"],
                        "role": tn_role_ko(w["rank"]),
                        "rank": w["rank"], "is_main": w["rank"] == 1,
                        "injured": " ".join(unidecode(nm).lower().replace("-", " ").split()) in inj})
        return {"team": team, "color": tm.team_color(team), "captains": out, "source": "wikipedia"}
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
@_memo(ttl=900)
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

    # 재계약(1~2년 남음)은 주전(팀별 출전 상위 11명)만 — '2028-06-30 · 1년 8개월 남음'이 팀마다 6~8개 반복됐다(2026-10-20 점검)
    _pf_k = _pf(league)
    key11: set = set()
    if _pf_k is not None and not _pf_k.empty:
        _m = _pf_k.assign(_mn=pd.to_numeric(_pf_k["minutes"], errors="coerce").fillna(0))
        for _sq, g in _m.groupby("squad"):
            key11 |= {(str(_sq), _nk(n)) for n in g.sort_values("_mn", ascending=False)["player"].head(11)}
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
            # 날짜 칸은 비운다 — 만료일이 '사건 날짜'처럼 보였다. 만료일은 설명에 '만료 2028-06-30'으로
            if 0 <= days <= 365:
                add("", sq, "contract", "bad", "📄", str(r.get("player") or ""),
                    "계약 만료 임박", f"만료 {cu[:10]} · {_fmt_remaining(days)}", photo=_cph)
            elif 365 < days <= 730 and (sq, _nk(r.get("player"))) in key11:
                add("", sq, "resign", "warn", "✍️", str(r.get("player") or ""),
                    "재계약 대상(주전)", f"만료 {cu[:10]} · {_fmt_remaining(days)}", photo=_cph)

    # 5. 시장가치 급등/급락 (market-value agent 델타)
    mv = ds.read_table("market_value_changes", league=league)
    if mv is not None and not mv.empty:
        # 같은 날 같은 팀 갱신이 3명 이상이면 한 장으로 묶는다(TM 정기 갱신 하루에 10건이 목록을 덮었다)
        mvt = mv[mv["squad"].astype(str).map(tfilter)].copy()
        mvt["_d"] = pd.to_numeric(mvt["delta"], errors="coerce").fillna(0)
        for (sq, rd), g in mvt.groupby([mvt["squad"].astype(str), mvt["run_date"].astype(str)]):
            if len(g) >= 3:
                ups, downs = int((g["_d"] >= 0).sum()), int((g["_d"] < 0).sum())
                top = g.reindex(g["_d"].abs().sort_values(ascending=False).index).head(3)
                add(rd, sq, "value", "info", "💹", "", f"시장가치 갱신 {len(g)}명",
                    f"상승 {ups} · 하락 {downs} — " + ", ".join(
                        f"{str(r['player']).split()[-1]} {'+' if r['_d'] >= 0 else '-'}€{abs(r['_d']) / 1e6:.1f}M" for _, r in top.iterrows()))
                continue
            for _, r in g.iterrows():
                delta = _num(r.get("delta"))
                pct = _num(r.get("pct"))
                up = delta >= 0
                add(rd, sq, "value", "good" if up else "bad",
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


def _recent_load(team: str, league: str, today, days: int = 14) -> list[tuple[str, int]]:
    """최근 days 일 출전 분 합(FotMob 경기별 기록, 전 대회) 상위 — 270′ 이상만. [(선수, 분)]"""
    t = ds.read_table("fotmob_match_ratings", league=league)
    if t is None or t.empty:
        return []
    since = (today - datetime.timedelta(days=days)).isoformat()
    m = t[(t["squad"].astype(str) == team) & (t["date"].astype(str).str[:10] >= since)]
    if m.empty:
        return []
    tot = pd.to_numeric(m["minutes"], errors="coerce").fillna(0).groupby(m["player"].astype(str)).sum().sort_values(ascending=False)
    return [(str(n), int(v)) for n, v in tot.items() if v >= 270]


@app.get("/api/this-week/{team}")
@_memo(ttl=900)
def this_week(team: str, league: str = ACTIVE_LEAGUE):
    """THIS WEEK(감독용, Overview 맨 위) — 7일 안 경기(전 대회) · 우리·다음 상대 결장 · 결장 반영 예상 XI(최근 3경기 최빈 XI 에서
    빠진 자리를 같은 세부 포지션 최고 OVR 로) · 로테이션 부담(14일 출전 분·연속 풀타임, FotMob 경기별) · 다가오는 A매치 차출.
    계산은 src/this_week.py."""
    import positions as ps  # noqa: PLC0415
    import this_week as tw  # noqa: PLC0415
    from api.services import intl as _intl  # noqa: PLC0415
    today = _today_kst()
    try:
        nxt = team_fixtures(team, league, 6).get("next", [])
    except Exception:  # noqa: BLE001
        nxt = []
    week = [m for m in nxt if (m.get("d_day") if m.get("d_day") is not None else 99) <= 7] or nxt[:1]

    sq = _squad_df(team, league)
    ovr_of, photo_of, own_bucket, pool = {}, {}, {}, []
    gone = _gone_keys(team, league) | {k for k, v in _loans_out(team, league).items() if v.get("source") == "transfer"}
    if sq is not None:
        for _, r in sq.iterrows():
            k = ps.norm_name(r["player"])
            if _person_key(r["player"]) in gone:                  # 이번 창에 떠난·임대 간 선수(_placements 와 같은 키)
                continue
            o = _player_ovr(r)
            ovr_of[k], photo_of[k] = o, _photo(r)
            b = _fine_bucket(r.get("tm_position") or "") or _fine_bucket(r.get("pos") or "")
            own_bucket[k] = b
            pool.append({"player": str(r["player"]), "ovr": o, "bucket": b, "line": _canon_line(rv3.line_of_row(r)),
                         "photo": _photo(r)})
    absent = dict(_active_injuries(team, league))
    first = week[0] if week else None
    if first:   # 리그가 계속되는 대표팀 대회(아시안컵 등) 기간이면 소집 선수도 결장
        for club, k in _intl.tournament_absent(league, first.get("date")):
            if club == team:
                absent.setdefault(k, {"injury": "대표팀 차출", "until": ""})

    # 최근 3경기 최빈 선발(전 대회) — 5경기면 '최근 2경기 선발 제외'(Inbox) 선수가 남아 어긋났다(2026-10-21 브뤼헤 이한범)
    base = (_placements(team, league, last_n=3, exclude=gone, comp="all") or _placements(team, league, last_n=5, exclude=gone, comp="all")
            or _placements(team, league, exclude=gone))
    xi, changes = ([], [])
    if base and base.get("placements"):
        xi, changes = tw.pick_xi(base["placements"], absent, pool, ps.norm_name, own_bucket, _fine_bucket)
    starters = {ps.norm_name(p["player"]) for p in (base or {}).get("placements", [])}

    def _abs_list(tbl: dict, ovr_map: dict, photo_map: dict, xi_keys: set) -> list[dict]:
        out = []
        for k, v in tbl.items():
            out.append({"player": k.title(), "injury": v.get("injury") or "결장", "until": _ddmmyyyy(v.get("until")) if "/" in str(v.get("until") or "") else str(v.get("until") or ""),
                        "ovr": ovr_map.get(k), "photo": photo_map.get(k, ""), "starter": k in xi_keys})
        return sorted(out, key=lambda x: (not x["starter"], -(x["ovr"] or 0)))

    # 이름 원래 표기(정규화 키 → 스쿼드 표기)
    real = {ps.norm_name(p["player"]): p["player"] for p in pool}
    ours = [{**a, "player": real.get(ps.norm_name(a["player"]), a["player"])} for a in _abs_list(absent, ovr_of, photo_of, starters)]

    opp = None
    if first:
        me_home = first["home"]["team"] == team
        side = first["away"] if me_home else first["home"]
        opp = {"team": side["team"], "league": side.get("league"), "logo": side.get("logo", ""), "rank": side.get("rank"),
               "absences": [], "covered": bool(side.get("league"))}
        if side.get("league"):
            try:
                osq = _squad_df(side["team"], side["league"])
                o_ovr, o_photo, o_real = {}, {}, {}
                if osq is not None:
                    for _, r in osq.iterrows():
                        k = ps.norm_name(r["player"])
                        o_ovr[k], o_photo[k], o_real[k] = _player_ovr(r), _photo(r), str(r["player"])
                obase = _placements(side["team"], side["league"], last_n=5, comp="all")
                o_start = {ps.norm_name(p["player"]) for p in (obase or {}).get("placements", [])}
                opp["absences"] = [{**a, "player": o_real.get(ps.norm_name(a["player"]), a["player"])}
                                   for a in _abs_list(_active_injuries(side["team"], side["league"]), o_ovr, o_photo, o_start)]
            except Exception:  # noqa: BLE001 — 상대 정보는 보조
                pass

    # 로테이션 부담 — 14일 출전 분(270′+) · 최근부터 연속 풀타임
    load = _recent_load(team, league, today, 14)
    fm = ds.read_table("fotmob_match_ratings", league=league)
    streaks, games14 = {}, 0
    if fm is not None and not fm.empty:
        mine = fm[fm["squad"].astype(str) == team]
        since = (today - datetime.timedelta(days=14)).isoformat()
        games14 = int(mine.loc[mine["date"].astype(str).str[:10] >= since, "date"].astype(str).str[:10].nunique())
        for name, g in mine.groupby(mine["player"].astype(str)):
            streaks[name] = tw.full_streak(g[["date", "minutes"]].to_dict("records"))
    rot = tw.rotation(load, streaks, ovr_of, ps.norm_name)

    # 다가오는 A매치(14일 안) — 우리 소집 선수 수
    intl_info = None
    try:
        ip = _intl.team_payload(team, league, today)
        if ip.get("window") and ip.get("days_to") is not None and ip["days_to"] <= 14 and ip["players"]:
            intl_info = {"label": ip["window"]["label"], "days_to": ip["days_to"], "kind": ip["window"].get("kind"),
                         "n": len(ip["players"]), "squad_state": ip.get("squad_state"),
                         "players": [p["player"] for p in ip["players"]][:6]}
    except Exception:  # noqa: BLE001
        pass
    return {"team": team, "today": today.isoformat(), "week": week, "congestion": len([m for m in week if m.get("d_day", 99) <= 7]),
            "absences": ours, "opponent": opp,
            "xi": {"formation": (base or {}).get("formation"), "placements": xi, "changes": changes,
                   "basis": "최근 3경기 최빈 선발(전 대회)"},
            "rotation": rot[:6], "games14": games14, "intl": intl_info}


# 인박스 분류 — 기존 신호 type → (분류, 기본 중요도)
_INBOX_CAT = {"injury_new": ("injury", 70), "injury_return": ("injury", 45), "manager": ("manager", 60),
              "value": ("value", 40), "risk": ("squad", 45), "youth": ("squad", 28), "veteran": ("squad", 25),
              "contract": ("contract", 42), "resign": ("contract", 28)}


@app.get("/api/inbox/{team}")
@_memo(ttl=900)
def inbox(team: str, league: str = ACTIVE_LEAGUE):
    """팀 인박스 — 자동 감지 신호(부상·감독·계약·시장가치·유망주) + 경기 브리핑(다음·지난 경기·일정 과밀)
    + 팀 폼(연승·연패·결정력·막판 실점) + 선수 폼(OVR 2주 변화) + 선발 제외 감지. 중요도(prio) 상위 3건 = 브리핑.
    예전 인박스는 6가지 신호를 분류만 해 '지금 무엇이 중요한지'가 안 보였다(2026-10-15 사용자 요청)."""
    import positions as ps  # noqa: PLC0415
    today = _today_kst()
    msgs: list[dict] = []

    def add(cat, typ, tone, icon, title, detail, prio, date="", player="", photo="", action=None):
        msgs.append({"id": f"{typ}|{player}|{title}|{date}", "cat": cat, "type": typ, "tone": tone, "icon": icon,
                     "title": title, "detail": detail, "prio": int(prio), "date": str(date or ""),
                     "player": player, "photo": photo if str(photo).startswith("http") else "", "action": action})

    # 1) 기존 자동 감지 신호
    base = signals(team=team, league=league, limit=400)
    sq_df = _squad_df(team, league)
    ovr_of = {}
    if sq_df is not None:
        for _, r in sq_df.iterrows():
            ovr_of[ps.norm_name(r["player"])] = _player_ovr(r)
    top_ovr = sorted(ovr_of.values(), reverse=True)
    key_cut = top_ovr[10] if len(top_ovr) > 10 else 0          # 상위 11명 = 핵심

    # 주장단 — 주장이 결장하면 완장을 누가 차는지(위키 스쿼드 표 주장 순위 + 현재 부상)
    try:
        caps = captains(team, league).get("captains", [])
        if caps and caps[0].get("is_main") and caps[0].get("injured"):
            nxt = next((c for c in caps[1:] if not c.get("injured")), None)
            add("squad", "armband", "warn", "©", "완장 이동",
                f"주장 {caps[0]['name']} 결장 — " + (f"완장은 {nxt['role']} {nxt['name']}" if nxt else "다음 주장단도 결장"),
                78, player=caps[0]["name"], photo=caps[0].get("photo", ""),
                action={"kind": "player", "name": (nxt or caps[0])["name"]})
    except Exception:  # noqa: BLE001 — 주장 정보는 보조
        pass
    for s in base["signals"]:
        cat, pr = _INBOX_CAT.get(s["type"], ("squad", 25))
        key = ovr_of.get(ps.norm_name(s.get("player"))) or 0
        if s["type"] == "injury_new" and key >= key_cut:
            pr, s = 85, {**s, "title": "핵심 선수 부상"}
        if s["type"] == "manager":
            try:
                pr = 90 if (today - datetime.date.fromisoformat(s["date"][:10])).days <= 14 else 40
            except ValueError:
                pass
        if s.get("date"):
            try:
                age = (today - datetime.date.fromisoformat(s["date"][:10])).days
                if 0 <= age <= 3:
                    pr += 8                                       # 최근 일
                elif age > 21 and cat in ("injury", "value"):
                    pr -= 15
            except ValueError:
                pass
        add(cat, s["type"], s["tone"], s["icon"], s["title"], s["detail"], pr, s.get("date"), s.get("player", ""), s.get("photo", ""),
            {"kind": "player", "name": s["player"]} if s.get("player") else None)

    inj = _active_injuries(team, league)

    # 2) 경기 브리핑 — 다음 경기 · 지난 경기 · 일정 과밀
    try:
        nxt = team_fixtures(team, league, 4)["next"]
    except Exception:  # noqa: BLE001
        nxt = []
    if nxt:
        m = nxt[0]
        me, op = (m["home"], m["away"]) if m["home"]["team"] == team else (m["away"], m["home"])
        side = "h" if m["home"]["team"] == team else "a"
        bits = []
        if m.get("model"):
            bits.append(f"모델 승 {round(m['model'][side] * 100)}%")
        if m.get("fans"):
            bits.append(f"팬 승 {round(m['fans'][side] * 100)}%")
        if inj:
            names = sorted(inj, key=lambda k: -(ovr_of.get(k) or 0))[:3]
            bits.append(f"결장 {len(inj)}명({', '.join(n.split()[-1].title() for n in names)})")
        rk = f" ({op['rank']}위)" if op.get("rank") else ""
        dd = m["d_day"]
        add("match", "match_next", "info", "⚽", f"다음 경기 {'오늘' if dd <= 0 else f'D-{dd}'} · vs {op['team']}{rk}",
            " · ".join(bits) or m.get("kst", ""), 75 if dd <= 2 else 55, m["date"], action={"kind": "match", "fixture": m})
        # 일정 과밀 — 다음 경기들 중 연속 3경기가 8일 안(예: 10/19·10/22·10/24)
        for i in range(len(nxt) - 2):
            span = nxt[i + 2]["d_day"] - nxt[i]["d_day"]
            if span <= 7 and nxt[i]["d_day"] <= 10:
                trio = nxt[i:i + 3]
                detail = " · ".join(f"{x['date'][5:].replace('-', '/')} {x['away']['team'] if x['home']['team'] == team else x['home']['team']}" for x in trio)
                # 누가 부담이 큰지 — 최근 14일 출전 분(FotMob 경기별, 전 대회) 상위 3명
                load = _recent_load(team, league, today, 14)
                if load:
                    detail += " — 부담 큰 선수(14일): " + " · ".join(f"{n.split()[-1]} {m}′" for n, m in load[:3])
                add("match", "congestion", "warn", "🗓️", f"{span + 1}일 동안 3경기 — 로테이션 필요", detail, 62, trio[0]["date"])
                break
    try:
        ts = team_season(team, league)
    except Exception:  # noqa: BLE001
        ts = None
    if ts and ts.get("recent"):
        r = ts["recent"][0]
        home = r["home"]["team"] == team
        gf, ga = (r["home"]["goals"], r["away"]["goals"]) if home else (r["away"]["goals"], r["home"]["goals"])
        op = r["away"]["team"] if home else r["home"]["team"]
        res = "승" if gf > ga else "패" if gf < ga else "무"
        ago = (today - datetime.date.fromisoformat(r["date"])).days
        add("match", "match_last", "good" if res == "승" else "bad" if res == "패" else "info", "📋",
            f"지난 경기 {gf}-{ga} {res} · vs {op}", f"{r['comp']} · {r['kst']} — 눌러서 경기 리뷰",
            58 if ago <= 2 else 35, r["date"], action={"kind": "match", "fixture": r})
        # 연승·연패(전 대회 최근 5)
        seq = []
        for x in ts["recent"]:
            h = x["home"]["team"] == team
            a_, b_ = (x["home"]["goals"], x["away"]["goals"]) if h else (x["away"]["goals"], x["home"]["goals"])
            seq.append("W" if a_ > b_ else "L" if a_ < b_ else "D")
        run = 0
        for v in seq:
            if v != seq[0]:
                break
            run += 1
        if seq and seq[0] == "W" and run >= 3:
            add("form", "streak", "good", "🔥", f"{run}연승 중", f"전 대회 최근 {len(seq)}경기 {''.join(seq)}", 50 + run * 3, r["date"])
        elif seq and seq[0] == "L" and run >= 2:
            add("form", "streak", "bad", "🧊", f"{run}연패", f"전 대회 최근 {len(seq)}경기 {''.join(seq)} — 반등 필요", 72 + run * 3, r["date"])

    # 3) 팀 폼 — 결정력(실제 득점 − xG) · 막판 실점
    try:
        tt = team_trends(team, league)
    except Exception:  # noqa: BLE001
        tt = None
    if tt and tt.get("available"):
        xs = [m for m in tt["matches"] if m.get("xg") is not None]
        if len(xs) >= 4:
            diff = sum(m["gf"] for m in xs) - sum(m["xg"] for m in xs)
            if abs(diff) >= 2.5:
                add("form", "finishing", "good" if diff > 0 else "bad", "🎯" if diff > 0 else "🥅",
                    "결정력 호조 — 기대보다 많이 넣는 중" if diff > 0 else "결정력 부진 — 기회 대비 득점이 적음",
                    f"리그 {len(xs)}경기 득점 {sum(m['gf'] for m in xs)} · xG {sum(m['xg'] for m in xs):.1f} ({diff:+.1f})", 52)
        tm_ = tt.get("timing") or {}
        conc = tm_.get("conceded") or []
        if sum(conc) >= 4 and conc[-1] / sum(conc) >= 0.4:
            add("form", "late_goals", "warn", "⏱️", "막판 실점 주의", f"실점 {sum(conc)} 중 {conc[-1]}골이 76분 이후 — 교체·체력 관리", 55)

    # 4) 선수 폼 — OVR 2주 변화(기록이 2주 쌓여야 생김)
    if sq_df is not None:
        moves = []
        for _, r in sq_df.iterrows():
            d = (_trend(r, league) or {}).get("ovr_d")
            if d is not None and abs(d) >= 3 and _num(r.get("minutes")) >= 180:
                moves.append((d, r))
        for d, r in sorted(moves, key=lambda x: -abs(x[0]))[:5]:
            up = d > 0
            add("form", "player_form", "good" if up else "bad", "📈" if up else "📉", "폼 상승" if up else "폼 하락",
                f"OVR {_player_ovr(r)} ({d:+d}, 2주 전 대비)", 48 if up else 56, "", r["player"], _photo(r),
                {"kind": "player", "name": r["player"]})

    # 5) 선발 제외 감지 — 시즌 선발 60%+ 였는데 최근 2경기 선발에 없음(부상 아님)
    try:
        el = ds.read_table("espn_lineups", league=league)
        cups = ds.read_table("espn_lineups_cups", league=league)
        lu = pd.concat([x for x in (el, cups) if x is not None], ignore_index=True)
        lu = lu[(lu["squad"] == team) & (pd.to_numeric(lu["starter"], errors="coerce") == 1)]
        games = sorted(lu.groupby("event_id")["date"].first().items(), key=lambda kv: str(kv[1]))
        if len(games) >= 5:
            last2 = {e for e, _ in games[-2:]}
            earlier = [e for e, _ in games[:-2]]
            starts = lu[lu["event_id"].isin(earlier)].groupby("player").size()
            recent = set(lu[lu["event_id"].isin(last2)]["player"])
            for name, n in starts.items():
                if n / len(earlier) >= 0.6 and name not in recent and ps.norm_name(name) not in inj:
                    add("squad", "lineup_drop", "warn", "🪑", "최근 2경기 선발 제외",
                        f"앞선 {len(earlier)}경기 중 {n}경기 선발 → 최근 2경기 벤치·명단 외 (부상 기록 없음)", 60, "", name,
                        "", {"kind": "player", "name": name})
    except Exception:  # noqa: BLE001
        pass

    def _dkey(x):   # 같은 중요도면 최근 날짜 먼저(날짜 없는 항목은 뒤)
        try:
            return -int(str(x["date"]).replace("-", "")[:8])
        except ValueError:
            return 0
    msgs.sort(key=lambda x: (-x["prio"], _dkey(x)))
    counts: dict[str, int] = {}
    for x in msgs:
        counts[x["cat"]] = counts.get(x["cat"], 0) + 1
    # OPPONENT WATCH — 다음 3경기 상대의 부상·감독 소식(최근 30일). 예전 LEAGUE WIRE 는 우리 팀 소식을 반복하고
    # 석 달 전 항목이 섞였다(2026-10-20 점검). 상대 소식이 없으면 리그 소식(우리 팀 제외, 30일)으로 대신한다
    cutoff = (today - datetime.timedelta(days=30)).isoformat()
    fresh = lambda s: (not s.get("date")) or str(s["date"])[:10] >= cutoff  # noqa: E731
    opp_events, opponents = [], []
    for m in nxt[:3]:
        op = m["away"] if m["home"]["team"] == team else m["home"]
        if not op.get("league") or op["team"] in opponents:
            continue
        opponents.append(op["team"])
        try:
            for s in signals(team=op["team"], league=op["league"], limit=40)["signals"]:
                if s["type"] in ("injury_new", "injury_return", "manager") and fresh(s):
                    opp_events.append({**s, "vs": f"{m['date'][5:].replace('-', '/')} 상대"})
        except Exception:  # noqa: BLE001 — 상대 리그 데이터가 없으면 건너뜀
            continue
    lg_events = opp_events[:24] or [s for s in signals(team="", league=league, limit=80)["signals"]
                                     if s["type"] in ("injury_new", "injury_return", "manager", "value", "risk")
                                     and s.get("team") != team and fresh(s)][:24]
    return {"team": team, "briefing": msgs[:3], "messages": msgs, "counts": counts, "league_events": lg_events,
            "opponents": opponents if opp_events else [], "generated": today.isoformat()}


@app.get("/api/home")
@_memo(ttl=1800)
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
                "title": _clean_title(r.get("title_ko") or r.get("title_en")),
                "title_en": _clean_title(r.get("title_en")),
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


_HUB_LEAGUES = ("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague")   # 통합 대시보드 대상 — UI 지원 리그
_HUB_CACHE: dict = {"key": None, "body": None}


_HUB_FILE = ds.DB_PATH.parent / "home_all.json"


# ── 홈 리그 집중 보드(득점왕 레이스 · 시즌 베스트 XI · 부상 타격) — _compute_hub_body 가 리그마다 부른다 ──
def _ss_map(lg: str) -> dict:
    """Sofascore 시즌 기록(xG·xA·키패스 …) — (팀, 정규화 이름) → 행."""
    from unidecode import unidecode  # noqa: PLC0415
    t = ds.read_table("players_sofascore_stats", league=lg)
    if t is None or t.empty:
        return {}
    return {(str(r.get("squad")), unidecode(str(r.get("player"))).lower().strip()): r for _, r in t.iterrows()}


def _golden_boot(p, lg: str, n: int = 6) -> list[dict]:
    """득점 순(동률은 도움 → 적은 출전시간). 90분당 득점·xG(기대 득점)도 함께."""
    q = p[p["_g"] > 0].copy()
    if q.empty:
        return []
    q["_a"] = pd.to_numeric(q.get("assists"), errors="coerce").fillna(0)
    from unidecode import unidecode  # noqa: PLC0415
    ssm = _ss_map(lg)
    out = []
    for _, r in q.sort_values(["_g", "_a", "_mn"], ascending=[False, False, True]).head(n).iterrows():
        sq = str(r.get("squad") or "")
        g, mn = int(r["_g"]), int(r["_mn"])
        out.append({"player": str(r["player"]), "club": sq, "club_logo": tm.team_logo(sq), "goals": g,
                    "assists": int(r["_a"]), "minutes": mn, "mpg": round(mn / g) if g else None,
                    "ovr": _player_ovr(r), "photo": _photo(r), "league": lg})
        ss = ssm.get((sq, unidecode(str(r["player"])).lower().strip()))
        if ss is not None:
            out[-1]["xg"] = round(_num(ss.get("expectedGoals")), 2)
            out[-1]["shots"] = int(_num(ss.get("totalShots")))
    return out


# 시즌 베스트 XI 포메이션 후보 — (자리, 라인, x, y, {역할: 적합도}). 세로 경기장, x·y 0~100(components/Pitch.tsx).
# 예전엔 4-3-3 고정이라 홀란·주앙 페드로처럼 스트라이커 둘이 다 잘해도 한 명만 들어갔다(2026-10-19 사용자 요청).
_BACK4 = [("LB", "DEF", 11, 71, {"LB": 1.0, "RB": 0.85, "CB": 0.7, "LW": 0.75}),
          ("LCB", "DEF", 37, 77, {"CB": 1.0, "DM": 0.8, "LB": 0.8, "RB": 0.8}),
          ("RCB", "DEF", 63, 77, {"CB": 1.0, "DM": 0.8, "LB": 0.8, "RB": 0.8}),
          ("RB", "DEF", 89, 71, {"RB": 1.0, "LB": 0.85, "CB": 0.7, "RW": 0.75})]
# 스리백 가운데는 골키퍼와 겹치지 않게 조금 위로(79 면 이름이 GK 사진에 가렸다)
_BACK3 = [("LCB", "DEF", 26, 72, {"CB": 1.0, "LB": 0.82, "DM": 0.8}), ("CB", "DEF", 50, 74, {"CB": 1.0, "DM": 0.8}),
          ("RCB", "DEF", 74, 72, {"CB": 1.0, "RB": 0.82, "DM": 0.8})]
_GK1 = [("GK", "GK", 50, 93, {"GK": 1.0})]
_CM = {"CM": 1.0, "DM": 0.93, "AM": 0.92}
_DM = {"DM": 1.0, "CM": 0.93, "CB": 0.78, "AM": 0.8}
_ST = {"ST": 1.0, "LW": 0.8, "RW": 0.8, "AM": 0.8}
_LW = {"LW": 1.0, "RW": 0.88, "AM": 0.85, "ST": 0.82}
_RW = {"RW": 1.0, "LW": 0.88, "AM": 0.85, "ST": 0.82}
_TOTS_FORMS: dict[str, tuple[float, list]] = {   # 포메이션: (익숙함 가점, 자리들) — 비슷하면 흔한 형태
    "4-3-3": (0.0, [("ST", "FWD", 50, 10, _ST), ("LW", "FWD", 17, 18, _LW), ("RW", "FWD", 83, 18, _RW),
                    ("LCM", "MID", 27, 44, _CM), ("CM", "MID", 50, 50, _DM), ("RCM", "MID", 73, 44, _CM)] + _BACK4 + _GK1),
    "4-2-3-1": (0.0, [("ST", "FWD", 50, 10, _ST), ("LAM", "MID", 18, 27, _LW),
                      ("CAM", "MID", 50, 30, {"AM": 1.0, "CM": 0.9, "LW": 0.85, "RW": 0.85, "ST": 0.82}),
                      ("RAM", "MID", 82, 27, _RW), ("LDM", "MID", 36, 52, _DM), ("RDM", "MID", 64, 52, _DM)] + _BACK4 + _GK1),
    "4-4-2": (-0.3, [("LST", "FWD", 38, 12, _ST), ("RST", "FWD", 62, 12, _ST),
                     ("LM", "MID", 12, 38, {"LW": 1.0, "CM": 0.85, "AM": 0.85, "LB": 0.75}),
                     ("LCM", "MID", 37, 48, _CM), ("RCM", "MID", 63, 48, _CM),
                     ("RM", "MID", 88, 38, {"RW": 1.0, "CM": 0.85, "AM": 0.85, "RB": 0.75})] + _BACK4 + _GK1),
    "3-5-2": (-0.4, [("LST", "FWD", 38, 12, _ST), ("RST", "FWD", 62, 12, _ST),
                     ("LWB", "MID", 10, 44, {"LB": 1.0, "LW": 0.85, "RB": 0.8}), ("LCM", "MID", 32, 47, _CM),
                     ("CM", "MID", 50, 55, _DM), ("RCM", "MID", 68, 47, _CM),
                     ("RWB", "MID", 90, 44, {"RB": 1.0, "RW": 0.85, "LB": 0.8})] + _BACK3 + _GK1),
    "3-4-3": (-0.4, [("ST", "FWD", 50, 10, _ST), ("LW", "FWD", 18, 18, _LW), ("RW", "FWD", 82, 18, _RW),
                     ("LWB", "MID", 10, 46, {"LB": 1.0, "LW": 0.85, "RB": 0.8}), ("LCM", "MID", 37, 51, _CM),
                     ("RCM", "MID", 63, 51, _CM), ("RWB", "MID", 90, 46, {"RB": 1.0, "RW": 0.85, "LB": 0.8})] + _BACK3 + _GK1),
}
_OFF_POS_PENALTY = 6.0   # 적합도 1 → 0.8 이면 평점 z −1.2 — 3.0 이면 풀백 자리에 센터백 넷이 들어갔다
# 평점 비교 기준 그룹 — 공격형 미드·윙어는 공격수 평균(6.81±0.23)으로. 미드 평균(6.87±0.21)으로 보면 z 가 부풀어
# 4-2-3-1 의 공격형 미드 셋이 스트라이커(홀란)를 밀어냈다
_ROLE_GROUP = {"GK": "GK", "CB": "DEF", "LB": "DEF", "RB": "DEF", "DM": "MID", "CM": "MID",
               "AM": "ATT", "LW": "ATT", "RW": "ATT", "ST": "ATT"}


def _team_of_season(p, lg: str) -> dict:
    """시즌 지금까지 베스트 XI — {formation, xi[], subs[]}.

    평점(Sofascore 시즌 평균)을 포지션 평균 대비 z 로 바꿔(공격수 평점이 원래 높은 것 보정) 포메이션 후보마다
    자리 적합도(실제로 선 자리 우선, 아니면 TM)를 곱한 점수로 채우고, 합이 가장 큰 포메이션을 고른다.
    남은 상위 선수(GK 1 + 필드 6, 라인 골고루)는 교체 명단. 최소 출전 = 팀 경기의 절반."""
    st = ds.read_table("standings", league=lg)
    games = int(pd.to_numeric(st["played"], errors="coerce").max()) if st is not None and "played" in st.columns and len(st) else 0
    min_mn = max(270.0, 0.5 * games * 90)
    q = p[(p["_mn"] >= min_mn) & (p["_ss"] > 0)].copy()
    if q.empty:
        return {"formation": None, "xi": [], "subs": []}
    cands = []
    for idx, r in q.iterrows():
        prof = _pos_profile(r)
        ln = _ROLE_GROUP.get(prof.get("primary") or "", rv3.line_of_row(r))
        z = (float(r["_ss"]) - rv3._F_MEAN.get(ln, 6.85)) / rv3._F_SD.get(ln, 0.21)
        roles = {}
        if prof.get("primary"):
            roles[prof["primary"]] = 1.0
        for s_ in prof.get("secondary") or []:
            roles.setdefault(s_, 0.93)
        if not roles:
            roles = {{"GK": "GK", "DEF": "CB", "MID": "CM", "ATT": "ST"}[ln]: 0.9}
        cands.append({"i": idx, "r": r, "z": z, "roles": roles, "line": ln})

    def fit(c, accept: dict) -> float:
        return max((accept.get(role, 0.0) * w for role, w in c["roles"].items()), default=0.0)

    def assign(slots):
        pairs = []
        for si, (_s, _k, _x, _y, acc) in enumerate(slots):
            for ci, c in enumerate(cands):
                f = fit(c, acc)
                if f >= 0.7:
                    pairs.append((c["z"] - (1.0 - f) * _OFF_POS_PENALTY, si, ci))
        pairs.sort(key=lambda t: -t[0])
        took_s, took_c, pick = set(), set(), {}
        for sc, si, ci in pairs:
            if si in took_s or ci in took_c:
                continue
            took_s.add(si); took_c.add(ci); pick[si] = (ci, sc)
        return pick

    best = None
    for name, (bonus, slots) in _TOTS_FORMS.items():
        pick = assign(slots)
        if len(pick) < len(slots):
            continue
        total = sum(sc for _ci, sc in pick.values()) + bonus
        if best is None or total > best[0]:
            best = (total, name, slots, pick)
    if best is None:
        return {"formation": None, "xi": [], "subs": []}
    _total, formation, slots, pick = best

    def row_out(c) -> dict:
        r = c["r"]
        sq = str(r.get("squad") or "")
        prim = max(c["roles"], key=c["roles"].get)
        return {"player": str(r["player"]), "club": sq, "club_logo": tm.team_logo(sq), "rating": round(float(r["_ss"]), 2),
                "ovr": _player_ovr(r), "photo": _photo(r), "minutes": int(r["_mn"]), "goals": int(_num(r.get("goals"))),
                "assists": int(_num(r.get("assists"))), "pos": str(r.get("tm_position") or ""), "role": prim}
    xi = []
    for si, (slot, kind, x, y, _acc) in enumerate(slots):
        ci, _sc = pick[si]
        xi.append({"slot": slot, "kind": kind, "x": x, "y": y, **row_out(cands[ci])})
    used = {ci for ci, _ in pick.values()}
    rest = sorted((c for ci, c in enumerate(cands) if ci not in used), key=lambda c: -c["z"])
    subs, need = [], {"GK": 1, "DEF": 2, "MID": 2, "ATT": 2}
    for c in rest:                                   # 라인별 최소 인원 먼저(GK 1 · 수비 2 · 미드 2 · 공격 2)
        if need.get(c["line"], 0) > 0:
            subs.append(c); need[c["line"]] -= 1
    subs = sorted(subs, key=lambda c: ({"GK": 0, "DEF": 1, "MID": 2, "ATT": 3}[c["line"]], -c["z"]))[:7]
    return {"formation": formation, "xi": xi, "subs": [row_out(c) for c in subs]}


def _injury_impact(p, cur_inj, lg: str) -> list[dict]:
    """부상으로 잃은 전력 — 팀 베스트 XI 평균 강함(rv3.team_ratings 와 같은 식) 전체 vs 부상자 뺀 것.
    이번 시즌 출전 기록이 있는 선수만 계산에 들어간다(시즌 내내 빠진 선수는 '지금 전력'에 원래 없음)."""
    if cur_inj is None or cur_inj.empty or "squad" not in cur_inj.columns:
        return []
    inj = cur_inj.copy()
    if "active" in inj.columns:
        inj = inj[inj["active"].astype(str).str.lower().isin(["true", "1", "yes"])]
    ids = {str(int(float(x))) for x in inj.get("tm_player_id", pd.Series(dtype=float)).dropna()}
    from unidecode import unidecode  # noqa: PLC0415
    names = {unidecode(str(x)).lower().strip() for x in inj["player"]}

    def strength(r):
        pl = rv3.player_line(r)
        return pl["ovr"] if pl["form"] is None else 0.55 * pl["ovr"] + 0.45 * pl["form"]

    out = []
    for sq, grp in p.groupby("squad"):
        n_all = int((inj["squad"] == sq).sum())
        if not n_all:
            continue
        hurt_idx = {i for i, r in grp.iterrows()
                    if (str(r.get("tm_id")).split(".")[0] in ids) or unidecode(str(r["player"])).lower().strip() in names}
        hurt = [grp.loc[i] for i in hurt_idx]
        st = [(strength(r), i) for i, r in grp.iterrows()]
        top = sorted((x for x, _ in st), reverse=True)[:11]
        rest = sorted((x for x, i in st if i not in hurt_idx), reverse=True)[:11]
        if not top or not rest:
            continue
        loss = sum(top) / len(top) - sum(rest) / len(rest)
        key = [str(r["player"]) for r in sorted(hurt, key=lambda r: -_player_ovr(r))[:3]]
        out.append({"team": str(sq), "logo": tm.team_logo(str(sq)), "league": lg, "n": n_all,
                    "loss": round(loss, 1), "key": key, "ovr": round(sum(top) / len(top))})
    return [x for x in out if x["loss"] > 0 or x["n"] >= 4]


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
    # 홈 상단 요약 — 아래 목록들은 리그별 상위 몇 건만 담으므로 전체 수치는 따로 센다
    summary = {"spend_eur": 0.0, "signings": 0, "manager_changes": 0, "injured": 0}
    prospect_c, veteran_c, value_c = [], [], []      # 유망주 U21 · 베테랑 32+ · 저평가 가성비
    mover_c = []                                     # 선수 동향 — OVR 변화(2주 전 또는 지난 시즌 대비)
    golden_boot, tots, injury_impact = {}, {}, []    # 리그별 득점왕 레이스 · 시즌 베스트 XI · 부상으로 잃은 전력
    tots_meta: dict = {}                             # 리그별 베스트 XI 포메이션 · 교체 명단
    squad2league: dict[str, str] = {}                # 시장가치 급등의 리그 매핑용
    for lg in leagues:
        lname = _lname(lg)
        tr = ds.read_table("transfers", league=lg)
        if tr is not None and "squad" in tr.columns:
            tt, _wf = _window_filter(tr.copy(), win)
            tt = tt[(tt["direction"] == "in")
                    & ~tt["fee_text"].astype(str).str.lower().str.contains("loan", na=False)].copy()
            tt["_fee"] = tt["fee_eur"].map(lambda v: _num(v, 0.0))
            summary["spend_eur"] += float(tt["_fee"].sum())
            summary["signings"] += int(len(tt))
            # 리그당 6건으로 먼저 자르면 EPL 7~9위(€87~95M, 기마랑이스 등)가 빠지고 타 리그 €50M 이 들어갔다
            # → 리그 구분 없이 이적료 순 상위 12건(아래 deals.sort 후 [:12])이 되게 넉넉히 담는다
            for _, r in tt.sort_values("_fee", ascending=False).head(12).iterrows():
                sq, ph = str(r.get("squad") or ""), str(r.get("photo") or "")
                deals.append({"player": str(r.get("player") or ""), "to": sq, "to_logo": tm.team_logo(sq),
                              "from": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                              "fee_eur": _num(r.get("fee_eur"), 0.0), "fee_text": str(r.get("fee_text") or ""),
                              "photo": ph if ph.startswith("http") else "", "league": lg, "league_name": lname})
        bz = ds.read_table("transfer_buzz", league=lg)
        if bz is not None:
            for _, r in bz.head(10).iterrows():
                buzz.append({"title": _clean_title(r.get("title_ko") or r.get("title_en")),
                             "source": str(r.get("source") or ""), "tier": str(r.get("tier") or "rumor"),
                             "link": str(r.get("link") or ""), "published": str(r.get("published") or ""),
                             "league": lg, "league_name": lname})
        mc = ds.read_table("manager_changes", league=lg)
        mgrs = _managers(lg)
        if mc is not None and "team" in mc.columns:
            # 승인된 교체만(감지만 된 'Fulham → TBD' 같은 행 제외), 날짜는 실제 부임일 — 감지일(10.19)이 부임일처럼 보였다
            if "accepted" in mc.columns:
                mc = mc[mc["accepted"].astype(str).str.lower().isin(("true", "1", "1.0"))]
            summary["manager_changes"] += int(len(mc))
            summary["manager_changes_inseason"] = summary.get("manager_changes_inseason", 0) + int(
                (mc["change_type"].astype(str) != "season").sum() if "change_type" in mc.columns else 0)
            for _, r in mc.iterrows():
                t = str(r.get("team") or "")
                prof = mgrs.get(t, {})
                ph = str(prof.get("photo_url") or "")
                when = ""
                for c in ("official_change_date", "new_appointed"):
                    d = pd.to_datetime(str(r.get(c) or ""), errors="coerce", dayfirst=True)
                    if pd.notna(d):
                        when = d.date().isoformat()
                        break
                summer = str(r.get("change_type") or "") == "season"
                changes.append({"team": t, "logo": tm.team_logo(t),
                                "previous": str(r.get("previous_manager") or ""),
                                "current": str(r.get("detected_manager") or ""),
                                "photo": ph if ph.startswith("http") else "",
                                "changed_at": when, "when_label": when or ("여름" if summer else ""),
                                "in_season": not summer,
                                "league": lg, "league_name": lname})
        st = ds.read_table("standings", league=lg)
        table = []
        if st is not None and "rank" in st.columns:
            for _sq in st.get("squad", pd.Series(dtype=str)).astype(str):
                squad2league.setdefault(_sq, lg)
            for _, r in st.sort_values("rank").head(6).iterrows():
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
            for _, r in p[p["_mn"] >= _mm(900, lg)].sort_values("_ss", ascending=False).head(6).iterrows():
                form_c.append((r, lg))
            for _, r in p.sort_values("_g", ascending=False).head(6).iterrows():
                goal_c.append((r, lg))
            p["_age"] = pd.to_numeric(p.get("age"), errors="coerce").fillna(0)
            p["_mv"] = pd.to_numeric(p.get("market_value_eur"), errors="coerce").fillna(0)
            for _, r in p[(p["_age"] > 0) & (p["_age"] <= 21) & (p["_mn"] >= _mm(450, lg))].sort_values("_ss", ascending=False).head(6).iterrows():
                prospect_c.append((r, lg))          # 유망주 원석
            for _, r in p[(p["_age"] >= 32) & (p["_mn"] >= _mm(900, lg))].sort_values("_ss", ascending=False).head(6).iterrows():
                veteran_c.append((r, lg))           # 베테랑 32+
            vp = p[(p["_ss"] >= 6.9) & (p["_mn"] >= _mm(900, lg)) & (p["_mv"] > 0)].copy()
            vp["_ratio"] = vp["_ss"] / (vp["_mv"] / 1e6 + 3.0)   # 평점 대비 저가일수록↑
            for _, r in vp.sort_values("_ratio", ascending=False).head(6).iterrows():
                value_c.append((r, lg))             # 저평가 가성비
            if "tm_contract_until" in p.columns:
                cu = pd.to_datetime(p["tm_contract_until"], errors="coerce")
                dd = (cu - pd.Timestamp(today)).dt.days
                exp = p[(dd >= 0) & (dd <= 400)].copy()
                exp["_mv"] = pd.to_numeric(exp.get("market_value_eur"), errors="coerce").fillna(0)
                for _, r in exp.sort_values("_mv", ascending=False).head(6).iterrows():
                    contract_c.append((r, lg))
            # 무엇이 바뀌었나 — 기록이 2주치 쌓이면 '2주 전 대비', 그 전엔 '지난 시즌 대비'(300분+ 뛴 선수만)
            for _, r in p[p["_mn"] >= max(360.0, _mm(600, lg))].iterrows():
                # 골키퍼 OVR 은 선방률 표본에 크게 흔들려 시즌 초엔 ±10 이 흔하다 → 900분(10경기)부터
                if rv3.line_of_row(r) == "GK" and r["_mn"] < 900:
                    continue
                o = _player_ovr(r)
                t_ = _trend(r, lg, ovr=o)
                if t_["ovr_d"]:
                    mover_c.append((r, lg, "2w", int(t_["ovr_d"]), o, o - int(t_["ovr_d"])))
                elif t_["ovr_prev"] is not None and o != t_["ovr_prev"]:
                    mover_c.append((r, lg, "season", o - int(t_["ovr_prev"]), o, int(t_["ovr_prev"])))

        cur_inj = _injuries_table(lg)
        summary["injured"] += 0 if cur_inj is None else int(len(cur_inj))
        if pf is not None and "player" in pf.columns:
            golden_boot[lg] = _golden_boot(p, lg)
            _t = _team_of_season(p, lg)
            tots[lg] = _t["xi"]
            tots_meta[lg] = {"formation": _t["formation"], "subs": _t["subs"]}
            injury_impact += _injury_impact(p, cur_inj, lg)
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

    def _pcard(r, lg, **extra):
        d = {"player": r["player"], "club": str(r.get("squad") or ""),
             "club_logo": tm.team_logo(str(r.get("squad") or "")), "ovr": _player_ovr(r),
             "pos": str(r.get("fl_group") or r.get("pos") or ""), "age": int(_num(r.get("age"))),
             "photo": _photo(r), "league": lg, "league_name": _lname(lg)}
        d.update(extra)
        return d

    # 선수 스포트라이트 — 전부 리그별 인터리브(빅리그 독식 방지, 전 리그 노출)
    form_c.sort(key=lambda t: -t[0]["_ss"])
    hot_form = _interleave([_pcard(r, lg, rating=round(_num(r.get("ss_rating")), 2)) for r, lg in form_c], 12)
    goal_c.sort(key=lambda t: (-_num(t[0].get("goals")), -_num(t[0].get("assists"))))
    goal_leaders = _interleave([_pcard(r, lg, goals=int(_num(r.get("goals"))), assists=int(_num(r.get("assists")))) for r, lg in goal_c], 12)
    prospect_c.sort(key=lambda t: -t[0]["_ss"])
    prospects = _interleave([_pcard(r, lg, rating=round(_num(r.get("ss_rating")), 2)) for r, lg in prospect_c], 12)
    veteran_c.sort(key=lambda t: -t[0]["_ss"])
    veterans = _interleave([_pcard(r, lg, rating=round(_num(r.get("ss_rating")), 2)) for r, lg in veteran_c], 12)
    value_c.sort(key=lambda t: -t[0]["_ratio"])
    value_picks = _interleave([_pcard(r, lg, rating=round(_num(r.get("ss_rating")), 2), value_eur=_num(r.get("market_value_eur"))) for r, lg in value_c], 12)
    contract_c.sort(key=lambda t: -_num(t[0].get("market_value_eur")))
    contracts_out = _interleave([_pcard(r, lg, until=str(r.get("tm_contract_until") or "")[:10], value_eur=_num(r.get("market_value_eur"))) for r, lg in contract_c], 12)

    # 무엇이 바뀌었나 — 2주 기록이 하나라도 있으면 그 기준만, 아니면 지난 시즌 대비
    basis = "2w" if any(t[2] == "2w" for t in mover_c) else "season"
    mv = [t for t in mover_c if t[2] == basis]

    def _mcard(t):
        r, lg, b, d, o, prev = t
        return _pcard(r, lg, delta=d, ovr_prev=prev, basis=b, rating=round(_num(r.get("ss_rating")), 2),
                      minutes=int(_num(r.get("minutes"))))
    movers_up = _interleave([_mcard(t) for t in sorted((t for t in mv if t[3] > 0), key=lambda t: (-t[3], -t[4]))], 12)
    movers_down = _interleave([_mcard(t) for t in sorted((t for t in mv if t[3] < 0), key=lambda t: (t[3], -t[4]))], 12)

    # 시장가치 급등 — market_value_history 델타(최초 vs 최신 스냅샷). 스냅샷 누적될수록 정확.
    risers = []
    try:
        mvh = ds.read_table("market_value_history")
        if mvh is not None and not mvh.empty and "player" in mvh.columns:
            m = mvh.copy()
            m["_v"] = pd.to_numeric(m["market_value_eur"], errors="coerce")
            m = m.dropna(subset=["_v"]).sort_values("date")
            rows = []
            for player, grp in m.groupby("player"):
                if len(grp) < 2:
                    continue
                first, last = float(grp.iloc[0]["_v"]), float(grp.iloc[-1]["_v"])
                sq = str(grp.iloc[-1]["squad"]); lg = squad2league.get(sq)
                if not lg or first <= 0 or last <= first:
                    continue
                rows.append({"player": str(player), "club": sq, "club_logo": tm.team_logo(sq),
                             "value_eur": last, "delta_eur": last - first,
                             "pct": round((last - first) / first * 100),
                             # 예전엔 비워 둬서 '시장가치 급등' 탭 사진이 전부 빠졌다(Dowman 등)
                             "photo": _resolve_photo(str(player), _players_lookup(lg), lg),
                             "league": lg, "league_name": _lname(lg)})
            rows.sort(key=lambda x: -x["pct"])
            risers = _interleave(rows, 12)
    except Exception:  # noqa: BLE001
        pass

    result = {"window": win, "leagues": [{"key": lg, "name": _lname(lg)} for lg in leagues],
              "top_deals": deals[:12], "buzz": _interleave(buzz, 18),
              "manager_changes": _interleave(sorted(changes, key=lambda c: (0 if c.get("in_season") else 1,           # 시즌 중 교체 먼저, 최근 순
                                                            -int((c.get("changed_at") or "0").replace("-", "") or 0))), 12),
              "snapshots": snaps,
              "injuries": _interleave(injuries, 12), "hot_form": hot_form,
              "goal_leaders": goal_leaders, "prospects": prospects, "veterans": veterans,
              "value_picks": value_picks, "risers": risers, "contracts": contracts_out, "summary": summary,
              "movers_up": movers_up, "movers_down": movers_down, "movers_basis": basis,
              "golden_boot": golden_boot, "tots": tots, "tots_meta": tots_meta,
              "injury_impact": sorted(injury_impact, key=lambda x: (-x["loss"], -x["n"]))[:10],
              # 스냅샷 생성 시각 — scripts/watchdog.py 가 운영 홈이 멈췄는지 본다
              "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    return json.dumps(result, ensure_ascii=False).encode("utf-8")


def _hub_body() -> bytes:
    """메모리(DB-mtime) 캐시 → 디스크 프리컴퓨트(배포본) → 즉석 계산 순."""
    key = _db_mtime()
    if _HUB_CACHE["body"] is not None and _HUB_CACHE["key"] == key:
        return _HUB_CACHE["body"]
    try:
        # 디스크 프리컴퓨트(배포본)가 있으면 서빙. 시작 시 build_db 로 db mtime 이 갱신돼
        # 캐시가 '오래됨'으로 보여도 즉석계산(OOM/타임아웃) 대신 커밋된 스냅샷을 우선.
        if _HUB_FILE.exists():
            body = _HUB_FILE.read_bytes()
            _HUB_CACHE.update(key=key, body=body)
            return body
    except OSError:
        pass
    body = _compute_hub_body()                    # 폴백: 파일 없을 때만 즉석 계산(느림)
    _HUB_CACHE.update(key=key, body=body)
    try:
        _HUB_FILE.write_bytes(body)
    except OSError:
        pass
    return body


# ── 매치 센터(다음 경기 · 이번 주 빅매치) — src/match_center.py ─────────────────
@_memo(ttl=1800)
def _fx_sources() -> dict:
    """리그별 일정(schedule_full)과 팀 → (순위, 승점, 리그) — 매치 센터 공용."""
    rows, ranks = {}, {}
    for lg in ds.available_leagues():
        rows[lg] = ds.read_table("schedule_full", league=lg)
        st = ds.read_table("standings", league=lg)
        if st is not None and "squad" in st.columns:
            for _, r in st.iterrows():
                pl = _num(r.get("played")) or 0
                ranks[str(r["squad"])] = (int(_num(r.get("rank"))), int(_num(r.get("points"))), lg,
                                          (_num(r.get("gd")) / pl) if pl else 0.0)
    return {"rows": rows, "ranks": ranks}


def _fx_enrich(m: dict, src: dict) -> dict:
    import match_center as mc  # noqa: PLC0415
    for side in ("home", "away"):
        t = m[side]
        rk = src["ranks"].get(t["team"])
        lg = t.get("league") or (rk[2] if rk else None)
        t["league"] = lg
        t["rank"], t["points"] = (rk[0], rk[1]) if rk else (None, None)
        t["logo"] = tm.team_logo(t["team"]) or t.pop("logo_alt", "") or ""   # 사전에 없으면 ESPN 일정의 상대 로고
        t.pop("logo_alt", None)
        t["color"] = tm.team_color(t["team"])
        t["ovr"] = _club_strength(lg).get(t["team"]) if lg else None
        t["form"] = mc.recent_form(src["rows"].get(lg), t["team"]) if lg else []
    m["big"], m["tags"] = mc.big_score(m)
    gd = lambda t: (src["ranks"].get(t["team"]) or (0, 0, None, 0.0))[3]  # noqa: E731
    m["prob"] = mc.win_prob(m["home"].get("ovr"), m["away"].get("ovr"), gd(m["home"]), gd(m["away"]))
    _attach_predictions(m)
    _attach_model(m)
    return m


@_memo(ttl=1800)
def _predictions() -> dict:
    """외부 예측 — data/fan_votes.csv(Sofascore 팬 투표, 로컬 하루 2회) · data/clubelo_fixtures.csv(ClubElo, 클라우드 매일).
    (날짜, 홈, 원정) 키. 없으면 빈 dict."""
    out: dict = {"fans": {}, "elo": {}}
    base = ds.DB_PATH.parent
    try:
        fv = pd.read_csv(base / "fan_votes.csv")
        for _, r in fv.iterrows():
            out["fans"][(str(r["date"]), str(r["home"]), str(r["away"]))] = r.to_dict()
    except (OSError, ValueError, KeyError):
        pass
    try:
        ce = pd.read_csv(base / "clubelo_fixtures.csv")
        for _, r in ce.iterrows():
            out["elo"][(str(r["date"]), str(r["home"]), str(r["away"]))] = r.to_dict()
    except (OSError, ValueError, KeyError):
        pass
    return out


def _pred_lookup(table: dict, date: str, h: str, a: str):
    """(날짜, 홈, 원정) 정확히 → 없으면 같은 날 경기 중 두 팀 이름이 가장 비슷한 것(우리 리그 밖 상대는 표기가 달라서)."""
    hit = table.get((date, h, a))
    if hit is not None:
        return hit
    import team_names  # noqa: PLC0415
    best, best_s = None, 0.0
    for (d, hh, aa), row in table.items():
        if d != date:
            continue
        sc = min(team_names.score(h, hh), team_names.score(a, aa))
        if sc > best_s:
            best, best_s = row, sc
    return best if best_s >= 0.6 else None


def _attach_predictions(m: dict) -> None:
    """경기에 팬 투표(fans)·ClubElo(elo) — 날짜는 하루 어긋남(시간대) 허용."""
    pr = _predictions()
    h, a = m["home"]["team"], m["away"]["team"]
    d0 = datetime.date.fromisoformat(m["date"])
    for k in (0, -1, 1):
        day = (d0 + datetime.timedelta(days=k)).isoformat()
        f = _pred_lookup(pr["fans"], day, h, a)
        if f and "fans" not in m:
            n = int(f["vote_home"]) + int(f["vote_draw"]) + int(f["vote_away"])
            if n >= 30:
                bt = int(f["btts_yes"]) + int(f["btts_no"])
                fs = int(f["first_home"]) + int(f["first_none"]) + int(f["first_away"])
                m["fans"] = {"h": round(int(f["vote_home"]) / n, 3), "d": round(int(f["vote_draw"]) / n, 3),
                             "a": round(int(f["vote_away"]) / n, 3), "n": n,
                             "btts": round(int(f["btts_yes"]) / bt, 3) if bt >= 20 else None,
                             "first_h": round(int(f["first_home"]) / fs, 3) if fs >= 20 else None,
                             "first_a": round(int(f["first_away"]) / fs, 3) if fs >= 20 else None}
        e = _pred_lookup(pr["elo"], day, h, a)
        if e and "elo" not in m:
            m["elo"] = {"h": float(e["p_home"]), "d": float(e["p_draw"]), "a": float(e["p_away"])}


_MODEL_CACHE: dict = {}


def _model_state(league: str, before: str | None = None):
    """우리 예측 모델 v2 상태(src/predict_model.py) — 끝난 리그 경기(match_stats) + 팀 OVR, 30분 캐시.
    before(YYYY-MM-DD)가 있으면 그 날짜 전 경기만 — 끝난 경기 리뷰에서 '경기 전 예측'을 정직하게 다시 계산할 때."""
    import time as _t
    import predict_model as pm  # noqa: PLC0415
    key = (league, before)
    hit = _MODEL_CACHE.get(key)
    if hit and _t.time() < hit[0]:
        return hit[1]
    mt = pm.league_matches(ds.read_table("match_stats", league=league))
    if before:
        mt = mt[mt["date"] < before]
    st = pm.build_state(mt, _club_strength(league), asof=before or _today_kst().isoformat())   # 최근 경기에 무게(tau)
    _MODEL_CACHE[key] = (_t.time() + 1800, st)
    return st


@_memo(ttl=3600)
def _team_elo(before: str | None = None) -> dict:
    """{팀: Elo} — 지난 시즌부터 전 리그·컵·유럽 결과로 직접 계산(src/team_elo.py). before 면 그날 아침 값."""
    import league_level  # noqa: PLC0415
    import team_elo as te  # noqa: PLC0415
    frames = []
    for se in (f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"):
        fr = {lg: ds.read_table("schedule_full", league=lg, season=se) for lg in ds.available_leagues()}
        frames.append(te.matches_from({k: v for k, v in fr.items() if v is not None}))
    ms = pd.concat(frames, ignore_index=True).drop_duplicates("event_id").sort_values(["date", "event_id"])
    if before:
        ms = ms[ms["date"] < before]
    elo, _ = te.run(ms, {lg: te.league_base(league_level.level(lg)) for lg in ds.available_leagues()})
    return elo


@_memo(ttl=1800)
def _absence_loss(league: str, on: str | None = None) -> dict:
    """{팀: 결장 전력 손실} — 베스트 11 평균 OVR − 결장자(부상·출장정지, _injuries_table) 뺀 베스트 11 평균.
    예측 모델 v3 입력(src/predict_model.py b_av). 백테스트와 같은 '전 포지션 상위 11명' 기준.
    on(경기 날짜)이 리그가 계속되는 국가대표 대회(아시안컵 등) 기간이면 그 대회 소집 선수도 결장(api/services/intl)."""
    import positions as ps  # noqa: PLC0415
    from api.services import intl as _intl  # noqa: PLC0415
    pf, inj = _pf(league), _injuries_table(league)
    out: dict = {}
    if pf is None or pf.empty:
        return out
    hurt = set() if inj is None or inj.empty else {(str(s), ps.norm_name(p)) for s, p in zip(inj["squad"], inj["player"])}
    try:
        hurt |= _intl.tournament_absent(league, on)
    except Exception:  # noqa: BLE001
        pass
    if not hurt:
        return out
    for sq, g in pf.groupby("squad"):
        vals = [(float(o), (str(sq), ps.norm_name(p)) in hurt) for p, o in zip(g["player"], g["_ovr"]) if o == o]
        top = sorted((v for v, _ in vals), reverse=True)[:11]
        rest = sorted((v for v, h in vals if not h), reverse=True)[:11]
        if top and rest:
            out[str(sq)] = round(max(0.0, sum(top) / len(top) - sum(rest) / len(rest)), 2)
    return out


def _attach_model(m: dict, before: str | None = None) -> None:
    """경기에 우리 모델 예측(model: 승무패·예상 득점·예상 스코어·BTTS·2.5골+). 우리 리그 밖 팀이 끼면 생략.
    v3 입력: 최근 경기 가중(상태) · 팀 Elo 차 · 결장 전력 손실(부상·출장정지 — 지난 경기 리뷰(before)엔 그때 명단이 없어 뺌)."""
    import predict_model as pm  # noqa: PLC0415
    hl, al = m["home"].get("league"), m["away"].get("league")
    if not hl or not al:
        return
    try:
        sh = _model_state(hl, before)
        sa = sh if al == hl else _model_state(al, before)
        h, a = m["home"]["team"], m["away"]["team"]
        extra: dict = {}
        try:
            elo = _team_elo(before)
            if h in elo and a in elo:
                extra["elo_d"] = round(elo[h] - elo[a], 1)
                extra["elo_h"], extra["elo_a"] = round(elo[h]), round(elo[a])
        except Exception:  # noqa: BLE001
            pass
        if not before:
            on = str(m.get("date") or "")[:10] or None
            try:
                from api.services import intl as _intl  # noqa: PLC0415
                t_on = on if _intl.in_tournament(on) else None   # 날짜는 대표팀 대회 기간만 — 나머지는 리그 캐시 하나
                extra["miss_h"] = _absence_loss(hl, t_on).get(h, 0.0)
                extra["miss_a"] = _absence_loss(al, t_on).get(a, 0.0)
            except Exception:  # noqa: BLE001
                pass
            try:   # A매치 휴식기 직후 첫 경기 — 돌아오는 대표 선수(유럽 밖 장거리 포함). 참고 표시만, 확률엔 안 넣음
                from api.services import intl as _intl  # noqa: PLC0415
                for side, team, lg in (("h", h, hl), ("a", a, al)):
                    rt = _intl.returnees(team, lg, on)
                    if rt:
                        extra[f"intl_{side}"], extra[f"intl_far_{side}"] = rt["n"], rt["far"]
            except Exception:  # noqa: BLE001
                pass
        r = pm.predict(sh, h, None if sa is sh else sa, a, extra=extra)
        if r:
            m["model"] = r
    except Exception:  # noqa: BLE001
        pass


def _today_kst() -> datetime.date:
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()


BIG_MIN = 35   # 빅매치 기준 — 챔스 가산(30)만으로는 넘지 못하게(LASK 대 리버풀 같은 경기 제외)


@app.get("/api/fixtures")
@_memo(ttl=1800)
def fixtures(days: int = 7, limit: int = 6, league: str = ""):
    """다가오는 경기 — 빅매치(점수 30+ 상위)·오늘 경기·(리그 지정 시) 그 리그 팀이 뛰는 전 경기(유럽대회 포함).
    일정은 daily_data 가 매일 갱신하고, 순위·폼·D-day 는 요청 시 계산(30분 캐시)이라 따로 돌릴 배치가 없다."""
    import match_center as mc  # noqa: PLC0415
    src = _fx_sources()
    ms = [_fx_enrich(m, src) for m in mc.matches_from(src["rows"], _today_kst(), days)]
    if league:
        ms = [m for m in ms if league in (m["home"].get("league"), m["away"].get("league"))]
    big = sorted([m for m in ms if m["big"] >= BIG_MIN], key=lambda m: (-m["big"], m["date"]))[:limit]
    out = {"days": days, "count": len(ms), "big": big, "today": [m for m in ms if m["d_day"] == 0][:12]}
    if league:
        out["matches"] = ms[:80]
    return out


def _league_pending(rows, today) -> dict:
    """{event_id: {home, away}} — 결과 파일에 아직 없는 최근 3일~내일 리그 경기(잠정 순위 계산 재료)."""
    pending: dict = {}
    if rows is not None and not rows.empty and "event_id" in rows.columns:
        lo, hi = (today - datetime.timedelta(days=3)).isoformat(), (today + datetime.timedelta(days=1)).isoformat()
        pr = rows[(rows["status"] != "completed") & rows["comp_code"].astype(str).str.endswith(".1")
                  & (rows["date"].astype(str).str[:10] >= lo) & (rows["date"].astype(str).str[:10] <= hi)]
        for r in pr.itertuples(index=False):
            e = pending.setdefault(str(r.event_id), {})
            e["home" if r.home_away == "H" else "away"] = str(r.squad)
    return {k: v for k, v in pending.items() if "home" in v and "away" in v}


@app.get("/api/standings-live")
@_memo(ttl=900)
def standings_live(league: str = ACTIVE_LEAGUE):
    """잠정 순위 재료(가벼움) — 공식 순위표 + 아직 결과가 없는 최근·오늘 리그 경기.

    화면의 모든 순위 표시(왼쪽 사이드바 · 팀 헤더 · 경기 카드)가 web/lib/standings.tsx 한 곳에서 라이브 스코어를
    더해 같은 잠정 순위를 본다. 예전엔 몇몇 카드만 라이브였고 사이드바는 다음 날 아침까지 그대로였다(2026-10-19 사용자)."""
    import match_center as mc  # noqa: PLC0415
    st = ds.read_table("standings", league=league)
    if st is None or st.empty:
        return {"league": league, "table": [], "pending": {}}
    rows = _fx_sources()["rows"].get(league)
    table = []
    for _, r in st.sort_values("rank").iterrows():
        sq = str(r["squad"])
        table.append({"rank": int(_num(r.get("rank"))), "team": sq, "logo": tm.team_logo(sq), "played": int(_num(r.get("played"))),
                      "won": int(_num(r.get("won"))), "drawn": int(_num(r.get("drawn"))), "lost": int(_num(r.get("lost"))),
                      "gf": int(_num(r.get("gf"))), "ga": int(_num(r.get("ga"))), "gd": int(_num(r.get("gd"))),
                      "points": int(_num(r.get("points"))), "form": mc.recent_form(rows, sq)})
    return {"league": league, "table": table, "pending": _league_pending(rows, _today_kst())}


@_memo(ttl=3600)
def _team_xg_pg(league: str) -> dict[str, float]:
    """팀 경기당 xG 한 곳 — 리그 경기 Understat 경기별 xG(5대 리그, match_stats) 평균, 없으면 Sofascore 선수 xG 합 ÷ 경기 수.
    예전엔 Overview(Sofascore 1.71)와 Analytics(Understat 1.81)가 다른 값을 보였다(2026-10-20 점검)."""
    out: dict[str, float] = {}
    st = ds.read_table("standings", league=league)
    played = {} if st is None else {str(s): _num(p) for s, p in zip(st["squad"], st["played"])}
    ms = ds.read_table("match_stats", league=league)
    if ms is not None and not ms.empty and "xg" in ms.columns:
        lg = ms[ms["comp_code"].astype(str).str.endswith(".1")].copy()
        lg["xg"] = pd.to_numeric(lg["xg"], errors="coerce")
        for sq, g in lg.groupby("squad"):
            x = g["xg"].dropna()
            if len(x) and len(x) >= max(1, played.get(str(sq), 0) - 1):   # 리그 경기 거의 전부에 xG 가 있을 때만
                out[str(sq)] = round(float(x.mean()), 2)
    t = ds.read_table("players_sofascore_stats", league=league)
    if t is not None and not t.empty and "expectedGoals" in t.columns:
        sums = pd.to_numeric(t["expectedGoals"], errors="coerce").groupby(t["squad"]).sum()
        for sq, v in sums.items():
            if str(sq) not in out and played.get(str(sq)):
                out[str(sq)] = round(float(v) / played[str(sq)], 2)
    return out


@app.get("/api/league-lab/{league}")
@_memo(ttl=21600)
def league_lab(league: str):
    """리그 분석 랩(홈 LEAGUE FOCUS) — Sofascore 시즌 기록 기반, 분석가가 보는 지표:
    playmakers(도움·xA·빅찬스·키패스) · finishing(골 vs xG) · creating(도움 vs xA) ·
    ball_winners(태클·인터셉트·볼 회수 /90) · team_style(경기당 xG vs 경기당 실점)."""
    t = ds.read_table("players_sofascore_stats", league=league)
    xg_one = _team_xg_pg(league)                          # 팀 경기당 xG 한 곳(Understat 우선)
    st = ds.read_table("standings", league=league)
    if t is None or t.empty:
        return {"league": league, "playmakers": [], "finishing": [], "creating": [], "ball_winners": [], "team_style": []}
    t = t.copy()
    for c in ("goals", "expectedGoals", "assists", "expectedAssists", "bigChancesCreated", "keyPasses", "minutesPlayed",
              "tacklesWon", "interceptions", "ballRecovery", "totalShots"):
        t[c] = pd.to_numeric(t.get(c), errors="coerce").fillna(0)
    look = _players_lookup(league)

    def card(r, **extra):
        sq = str(r.get("squad") or "")
        d = {"player": str(r["player"]), "club": sq, "club_logo": tm.team_logo(sq),
             "photo": _resolve_photo(str(r["player"]), look, league), "minutes": int(r["minutesPlayed"])}
        d.update(extra)
        return d

    pm = t[(t["assists"] > 0) | (t["expectedAssists"] >= 0.5)].sort_values(
        ["assists", "expectedAssists", "bigChancesCreated"], ascending=False).head(6)
    playmakers = [card(r, assists=int(r["assists"]), xa=round(r["expectedAssists"], 2), bcc=int(r["bigChancesCreated"]),
                       kp=int(r["keyPasses"])) for _, r in pm.iterrows()]
    fin = t[t["expectedGoals"] >= 0.6].sort_values("expectedGoals", ascending=False).head(28)
    finishing = [{"player": str(r["player"]), "club": str(r["squad"]), "goals": int(r["goals"]),
                  "xg": round(r["expectedGoals"], 2), "shots": int(r["totalShots"])} for _, r in fin.iterrows()]
    cre = t[t["expectedAssists"] >= 0.4].sort_values("expectedAssists", ascending=False).head(28)
    creating = [{"player": str(r["player"]), "club": str(r["squad"]), "assists": int(r["assists"]),
                 "xa": round(r["expectedAssists"], 2), "kp": int(r["keyPasses"])} for _, r in cre.iterrows()]
    mn_min = max(270.0, _mm(600, league))
    # 골키퍼는 볼 회수가 많아 섞이면 순위가 틀어진다(선방 기록이 있으면 GK)
    bw = t[(t["minutesPlayed"] >= mn_min) & (pd.to_numeric(t.get("saves"), errors="coerce").fillna(0) == 0)].copy()
    per = lambda c: bw[c] * 90 / bw["minutesPlayed"]  # noqa: E731
    bw["_t"], bw["_i"], bw["_r"] = per("tacklesWon"), per("interceptions"), per("ballRecovery")
    bw["_s"] = bw["_t"] + bw["_i"] + 0.5 * bw["_r"]
    ball_winners = [card(r, tackles=round(r["_t"], 1), inter=round(r["_i"], 1), recov=round(r["_r"], 1),
                         score=round(r["_s"], 1)) for _, r in bw.sort_values("_s", ascending=False).head(6).iterrows()]
    team_style = []
    if st is not None and not st.empty:
        xg_by = t.groupby("squad")["expectedGoals"].sum()
        for _, r in st.iterrows():
            sq, pl = str(r["squad"]), _num(r.get("played"))
            if not pl:
                continue
            team_style.append({"team": sq, "logo": tm.team_logo(sq), "rank": int(_num(r.get("rank"))),
                               "xg_pg": xg_one.get(sq, round(float(xg_by.get(sq, 0.0)) / pl, 2)),
                               "gf_pg": round(_num(r.get("gf")) / pl, 2), "ga_pg": round(_num(r.get("ga")) / pl, 2)})
    # ── 리그 홈·LEAGUE FOCUS 공용: 전체 순위표 · 우승 경쟁 · 베스트 XI · 득점왕 · 부상 타격 · 전력 대비 · 결과 · 주목할 매치 ──
    import match_center as mc  # noqa: PLC0415
    src = _fx_sources()
    rows = src["rows"].get(league)
    pf = _pf(league)
    pp = None
    if pf is not None and "player" in pf.columns:
        pp = pf.copy()
        if "left_for" in pp.columns:
            pp = pp[pp["left_for"].isna() | (pp["left_for"].astype(str).str.strip() == "")]
        pp["_mn"] = pd.to_numeric(pp.get("minutes"), errors="coerce").fillna(0)
        pp["_ss"] = pd.to_numeric(pp.get("ss_rating"), errors="coerce").fillna(0)
        pp["_g"] = pd.to_numeric(pp.get("goals"), errors="coerce").fillna(0)
    table, race, gaps = [], [], []
    if st is not None and not st.empty:
        st = st.sort_values("rank")
        strength = _club_strength(league)
        str_rank = {t_: i + 1 for i, (t_, _) in enumerate(sorted(strength.items(), key=lambda kv: -kv[1]))}
        xg_by = t.groupby("squad")["expectedGoals"].sum()
        mgrs = _managers(league)
        n = len(st)
        for _, r in st.iterrows():
            sq, pl = str(r["squad"]), _num(r.get("played"))
            row = {"rank": int(_num(r.get("rank"))), "team": sq, "logo": tm.team_logo(sq), "played": int(pl),
                   "won": int(_num(r.get("won"))), "drawn": int(_num(r.get("drawn"))), "lost": int(_num(r.get("lost"))),
                   "gf": int(_num(r.get("gf"))), "ga": int(_num(r.get("ga"))), "gd": int(_num(r.get("gd"))),
                   "points": int(_num(r.get("points"))), "form": mc.recent_form(rows, sq),
                   "xg_pg": xg_one.get(sq, round(float(xg_by.get(sq, 0.0)) / pl, 2)) if pl else None,
                   "ovr": round(float(strength[sq])) if sq in strength else None, "str_rank": str_rank.get(sq),
                   "manager": str((mgrs.get(sq) or {}).get("name") or "")}
            table.append(row)
            if row["str_rank"]:
                g = row["str_rank"] - row["rank"]
                gaps.append({"team": sq, "logo": row["logo"], "league": league, "rank": row["rank"], "str_rank": row["str_rank"],
                             "gap": g, "ovr": row["ovr"], "points": row["points"], "n": n, "manager": row["manager"],
                             "hot_seat": -g >= 6 and row["rank"] > n / 2})
        for row in table[:4]:
            race.append({"team": row["team"], "logo": row["logo"], "color": tm.team_color(row["team"]),
                         "points": mc.points_path(rows, row["team"]), "rank": row["rank"]})
    over = sorted([g for g in gaps if g["gap"] >= 2], key=lambda g: (-g["gap"], g["rank"]))[:8]
    under = sorted([g for g in gaps if g["gap"] <= -2], key=lambda g: (g["gap"], -g["rank"]))[:8]
    today = _today_kst()
    results = []
    # 전 리그 파일로 묶어야 상대 팀도 우리 표기가 된다(ESPN 'Paris Saint-Germain' → 'PSG') — 그중 이 리그 팀 경기만
    for m in mc.results_from(src["rows"], today, 7):
        if league not in (m["home"].get("league"), m["away"].get("league")):
            continue
        m = _fx_enrich(m, src)
        m["upset"] = mc.upset_note(m)
        results.append(m)
    watch = []
    n_teams = 0 if st is None else len(st)
    for m in mc.matches_from({league: rows}, today, 7):
        if not str(m["comp_code"]).endswith(".1"):
            continue
        m = _fx_enrich(m, src)
        sc, why = mc.watch_score(m, n_teams)
        if sc >= 15:
            watch.append({**m, "watch": round(sc), "why": why, "league": league})
    watch.sort(key=lambda m: -m["watch"])
    pending = _league_pending(rows, today)
    cur_inj = _injuries_table(league)
    return {"league": league, "pending": pending, "playmakers": playmakers, "finishing": finishing, "creating": creating,
            "ball_winners": ball_winners, "team_style": team_style,
            "table": table, "race": race, "over": over, "under": under, "results": results[:20], "watch": watch[:3],
            **(lambda t: {"tots": t["xi"], "tots_formation": t["formation"], "tots_subs": t["subs"]})(
                _team_of_season(pp, league) if pp is not None else {"formation": None, "xi": [], "subs": []}),
            "golden_boot": _golden_boot(pp, league) if pp is not None else [],
            "injury_impact": sorted(_injury_impact(pp, cur_inj, league), key=lambda x: (-x["loss"], -x["n"]))[:8] if pp is not None else []}


_REVIEW_CACHE: dict = {}


@app.get("/api/review/{event_id}")
def match_review_api(event_id: str, comp: str = ""):
    """경기 리뷰(Match Review) — ESPN 경기 상세로 규칙 기반 리포트(src/match_review.py). 유료 AI 없음.
    종료 경기는 하루, 진행 중은 1분 캐시. 우리 일정에 있으면 우리 표기·로고·예측(팬 투표·ClubElo)을 붙이고,
    없으면(유럽대회 상대끼리 등) comp 로 ESPN 표기 그대로."""
    import json as _json
    import time as _t
    import urllib.request
    import match_review as mrv  # noqa: PLC0415
    hit = _REVIEW_CACHE.get(event_id)
    if hit and _t.time() < hit[0]:
        return _with_ai_report(hit[1])
    src = _fx_sources()
    home = away = lg_h = lg_a = date = None
    for lg, df in src["rows"].items():
        if df is None or df.empty or "event_id" not in df.columns:
            continue
        sub = df[df["event_id"].astype(str) == str(event_id)]
        for r in sub.itertuples(index=False):
            comp = comp or str(r.comp_code)
            date = str(r.date)[:10]
            if r.home_away == "H":
                home, lg_h = str(r.squad), lg
                away = away or str(r.opponent)
            else:
                away, lg_a = str(r.squad), lg
                home = home or str(r.opponent)
    if not comp:
        raise HTTPException(status_code=404, detail="unknown event")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{comp}/summary?event={event_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (football26)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"espn {type(e).__name__}") from e
    p = mrv.parse(data)
    cps = {c.get("homeAway"): c for c in ((data.get("header", {}).get("competitions") or [{}])[0].get("competitors", []))}
    # 일정 밖 경기는 ESPN 이름 — 결과 띠(scoreboard shortDisplayName)와 같은 짧은 이름을 먼저
    _nm = lambda side: next((t.get(k) for t in [(cps.get(side) or {}).get("team", {})]  # noqa: E731
                             for k in ("shortDisplayName", "displayName", "name") if t.get(k)), "")
    home = home or _nm("home")
    away = away or _nm("away")
    date = date or str(((data.get("header", {}).get("competitions") or [{}])[0].get("date") or ""))[:10]
    m = {"date": date or _today_kst().isoformat(), "home": {"team": home, "league": lg_h}, "away": {"team": away, "league": lg_a}}
    try:
        _attach_predictions(m)
        _attach_model(m, before=m["date"])   # 그 경기 전 데이터만으로 다시 계산한 모델 예측(결과 누설 없음)
    except Exception:  # noqa: BLE001
        pass
    rv = mrv.build(p, home, away, m.get("fans"), m.get("elo"), m.get("model"))
    logo = lambda t, side: tm.team_logo(t) or ((cps.get(side) or {}).get("team", {}).get("logo") or "")  # noqa: E731
    rv.update({"event_id": event_id, "comp": comp, "date": date,
               "home": {"team": home, "league": lg_h, "logo": logo(home, "home"), "color": tm.team_color(home)},
               "away": {"team": away, "league": lg_a, "logo": logo(away, "away"), "color": tm.team_color(away)}})
    _REVIEW_CACHE[event_id] = (_t.time() + (86400 if p["state"] == "post" else 60), rv)
    return _with_ai_report(rv)


def _with_ai_report(rv: dict) -> dict:
    """종료 경기면 AI 경기 리포트(src/ai_notes.py match — 배치에서 만들고 숫자·이름 검증을 통과한 것만)를 붙인다."""
    import ai_notes  # noqa: PLC0415
    rep = ai_notes.load("match").get("reports", {}).get(str(rv.get("event_id"))) if rv.get("state") == "post" else None
    return {**rv, "ai": {"text": rep["text"], "at": rep.get("at")} if rep else None}


@app.get("/api/digest")
@_memo(ttl=1800)
def digest(league: str = ACTIVE_LEAGUE, days: int = 7):
    """WEEKLY DIGEST — 지난 days 일 리그 변화 요약(설계도 3단계 '주간 스카우팅 다이제스트'). 규칙 기반·무료, 숫자는 데이터 값만.
    리그 홈의 결과·일정·리뷰·이적 속보와 겹치지 않게 '이번 주에 바뀐 것'만: OVR ▲▼ · 부상 변동 · 뉴스 언급 · 루머 · A매치 기간."""
    import positions as ps  # noqa: PLC0415
    import rating_history as rh  # noqa: PLC0415
    today = _today_kst()
    since = (today - datetime.timedelta(days=days)).isoformat()
    pf = _pf(league)
    ovr = {} if pf is None else {(str(s_), ps.norm_name(p_)): (None if o != o else int(round(o)))
                                 for s_, p_, o in zip(pf["squad"], pf["player"], pf["_ovr"])}
    # 폼 변화는 주전급만(시즌 270분+) — 몇 분 뛴 선수의 폼 지수는 한 경기로 크게 흔들린다
    regular = set() if pf is None else {(str(s_), ps.norm_name(p_)) for s_, p_, mi in zip(pf["squad"], pf["player"], pf["minutes"])
                                        if mi == mi and mi >= 270}
    out: dict = {"league": league, "since": since, "until": today.isoformat()}

    # 1) 폼 ▲▼ — 평점 추이 기록(변경분 저장: 날짜 D 값 = D 이전 마지막 기록)의 폼 지수 변화. OVR 은 시즌 단위라 한 주엔
    #    거의 안 움직여(10/14~19 EPL 0명) 폼으로 본다 — OVR 이 바뀐 선수는 그 변화도 함께. 기록이 days 보다 짧으면 첫 기록부터
    hist = rh.load(league)
    movers: list = []
    if not hist.empty:
        first = str(hist["date"].min())
        base_day = max(since, first)
        nxt_day = (datetime.date.fromisoformat(base_day) + datetime.timedelta(days=1)).isoformat()   # state_at(D) = D 전날까지
        now_s, then_s = rh.state_at(hist, (today + datetime.timedelta(days=1)).isoformat()), rh.state_at(hist, nxt_day)
        then = {str(r.pid): (int(r.ovr), None if r.form != r.form else int(r.form)) for r in then_s.itertuples()}
        for r in now_s.itertuples():
            b = then.get(str(r.pid))
            if b is None or r.form != r.form or b[1] is None or (str(r.squad), ps.norm_name(r.player)) not in regular:
                continue
            df, do = int(r.form) - b[1], int(r.ovr) - b[0]
            if abs(df) >= 5 or do:
                movers.append({"player": r.player, "squad": r.squad, "ovr": int(r.ovr), "ovr_delta": do,
                               "form": int(r.form), "delta": df})
        out["form_since"] = base_day
    movers.sort(key=lambda x: (-x["delta"], -x["ovr"]))
    out["risers"] = [m for m in movers if m["delta"] > 0][:5]
    out["fallers"] = sorted([m for m in movers if m["delta"] < 0], key=lambda x: (x["delta"], -x["ovr"]))[:5]

    # 2) 부상 변동 — 새 부상(OVR 높은 순) · 복귀
    ic = ds.read_table("transfermarkt_injury_changes", league=league)
    new_inj, back = [], []
    if ic is not None and not ic.empty:
        w = ic[ic["run_date"].astype(str) >= since]
        for r in w.itertuples():
            item = {"player": r.player, "squad": r.squad, "date": str(r.run_date),
                    "ovr": ovr.get((str(r.squad), ps.norm_name(r.player))),
                    "injury": (r.new_injury if isinstance(r.new_injury, str) else r.old_injury) or "",
                    "until": r.new_until if isinstance(r.new_until, str) else None}
            if r.event_type == "new_injury":
                new_inj.append(item)
            elif r.event_type == "recovered_or_removed":
                back.append(item)
    key = lambda x: -(x["ovr"] or 0)  # noqa: E731
    out["injuries"] = {"new": sorted(new_inj, key=key)[:6], "back": sorted(back, key=key)[:6],
                       "n_new": len(new_inj), "n_back": len(back)}

    # 3) 뉴스 언급 — 이번 주 기사(처음 수집일 기준)에 가장 많이 나온 선수(뉴스 선수 태그)
    tags, na = ds.read_table("news_players", league=league), ds.read_table("news_articles", league=league)
    buzz = []
    if tags is not None and na is not None and not tags.empty:
        recent = set(na.loc[na["first_seen"].astype(str) >= since, "link"].astype(str))
        t = tags[tags["link"].astype(str).isin(recent)].drop_duplicates(["link", "player", "squad"])
        for (pl, sq), n in t.groupby(["player", "squad"]).size().sort_values(ascending=False).head(6).items():
            buzz.append({"player": pl, "squad": sq, "articles": int(n), "ovr": ovr.get((str(sq), ps.norm_name(pl)))})
    out["news"] = buzz

    # 4) 루머 — 이번 주 새로 잡힌 이적 루머(TM). 많이 엮인 클럽 · 몸값 큰 대상
    ru = ds.read_table("transfer_rumors", league=league)
    rum = {"n": 0, "clubs": [], "top": []}
    if ru is not None and not ru.empty and "date" in ru.columns:
        d = pd.to_datetime(ru["date"].astype(str), format="%d/%m/%Y", errors="coerce")
        w = ru[d >= pd.Timestamp(since)].copy()
        if len(w):
            w["mv"] = pd.to_numeric(w["market_value_eur"], errors="coerce")
            rum = {"n": int(len(w)),
                   "clubs": [{"club": c, "n": int(n)} for c, n in w.groupby("target_club").size().sort_values(ascending=False).head(4).items()],
                   "top": [{"player": r.player, "from": r.current_club, "to": r.target_club,
                            "value_eur": None if r.mv != r.mv else float(r.mv)}
                           for r in w.sort_values("mv", ascending=False).head(4).itertuples()]}
    out["rumors"] = rum

    # 5) 다가오는 A매치 기간(3주 안)
    try:
        from api.services import intl as _intl  # noqa: PLC0415
        nxt = next((w for w in _intl.windows() if w["start"] >= today.isoformat()), None)
        if nxt and (datetime.date.fromisoformat(nxt["start"]) - today).days <= 21:
            out["intl"] = {**nxt, "days_to": (datetime.date.fromisoformat(nxt["start"]) - today).days}
    except Exception:  # noqa: BLE001
        pass

    # 6) 서술 한 문단(AI) — 위 데이터로 daily_data 가 만든 것(src/ai_notes.py digest, 검증 통과분). 이틀 넘은 건 내림
    import ai_notes  # noqa: PLC0415
    s = ai_notes.load("digest").get(league)
    out["summary"] = ({"text": s["text"], "at": s["at"], "until": s["until"]}
                      if s and s.get("until", "") >= (today - datetime.timedelta(days=2)).isoformat() else None)
    return out


@app.get("/api/hub/pulse")
@_memo(ttl=1800)
def hub_pulse(days_back: int = 3, days: int = 7):
    """홈 '지금' 정보(요청 시 계산·30분 캐시 — 일정·결과는 daily_data 가 매일 갱신):
    results = 최근 경기 결과(이변 표시), watch = 리그별 주목할 매치(같은 리그 순위 승부처),
    race = 리그별 상위 4팀 누적 승점, table_gap = 팀 전력(OVR) 순위 대비 실제 순위(기대 이상·이하, 감독 압박)."""
    import match_center as mc  # noqa: PLC0415
    src = _fx_sources()
    today = _today_kst()
    leagues = [lg for lg in _HUB_LEAGUES if lg in set(ds.available_leagues())]

    results = []
    for m in mc.results_from(src["rows"], today, days_back):
        m = _fx_enrich(m, src)
        m["upset"] = mc.upset_note(m)
        results.append(m)
    results.sort(key=lambda m: (m["date"], bool(m["upset"]), m["big"]), reverse=True)

    watch = []
    upcoming = [_fx_enrich(m, src) for m in mc.matches_from(src["rows"], today, days)]
    for lg in leagues:
        st = ds.read_table("standings", league=lg)
        n_teams = 0 if st is None else int(len(st))
        best = None
        for m in upcoming:
            if not str(m["comp_code"]).endswith(".1") or m["home"].get("league") != lg:
                continue
            sc, why = mc.watch_score(m, n_teams)
            if sc >= 20 and (best is None or sc > best[0]):
                best = (sc, why, m)
        if best:
            watch.append({**best[2], "watch": round(best[0]), "why": best[1], "league": lg})
    watch.sort(key=lambda m: -m["watch"])

    race, gaps = [], []
    for lg in leagues:
        st = ds.read_table("standings", league=lg)
        if st is None or "rank" not in st.columns or st.empty:
            continue
        st = st.sort_values("rank")
        rows = src["rows"].get(lg)
        teams = []
        for _, r in st.head(4).iterrows():
            t = str(r["squad"])
            teams.append({"team": t, "logo": tm.team_logo(t), "color": tm.team_color(t),
                          "points": mc.points_path(rows, t), "rank": int(_num(r.get("rank")))})
        race.append({"league": lg, "teams": teams})
        strength = _club_strength(lg)
        by_str = sorted(strength.items(), key=lambda kv: -kv[1])
        str_rank = {t: i + 1 for i, (t, _) in enumerate(by_str)}
        mgrs = _managers(lg)
        n = len(st)
        for _, r in st.iterrows():
            t = str(r["squad"])
            if t not in str_rank:
                continue
            rk, srk = int(_num(r.get("rank"))), str_rank[t]
            mg = mgrs.get(t) or {}
            gaps.append({"team": t, "logo": tm.team_logo(t), "league": lg, "rank": rk, "str_rank": srk,
                         "gap": srk - rk, "ovr": round(float(strength[t])), "points": int(_num(r.get("points"))),
                         "n": n, "manager": str(mg.get("name") or ""),
                         "hot_seat": (rk - srk) >= 6 and rk > n / 2})
    over = sorted([g for g in gaps if g["gap"] >= 3], key=lambda g: (-g["gap"], g["rank"]))[:10]
    under = sorted([g for g in gaps if g["gap"] <= -3], key=lambda g: (g["gap"], -g["rank"]))[:10]
    return {"results": results[:30], "watch": watch, "race": race, "over": over, "under": under}


@app.get("/api/fixtures/{team}")
@_memo(ttl=1800)
def team_fixtures(team: str, league: str = ACTIVE_LEAGUE, n: int = 3):
    """팀의 다음 경기들(전 대회) — Overview '다음 경기' 카드."""
    import match_center as mc  # noqa: PLC0415
    src = _fx_sources()
    ms = mc.matches_from(src["rows"], _today_kst(), 75, team=team)[:n]   # 전 리그 — 다른 리그 상대도 우리 표기로
    return {"team": team, "next": [_fx_enrich(m, src) for m in ms]}


# 팀 시즌 프로필 축 — (지수 컬럼, 영어, 한글, 근거 숫자 종류). 값은 리그 안 상대 지수(50=리그 평균, 시즌 초 표본 보정)
_PROFILE_AXES = [
    ("attack_output_index", "ATTACK OUTPUT", "공격 출력", "gf"),
    ("attack_creation_index", "CHANCE CREATION", "찬스 창출", ""),
    ("midfield_control_index", "CONTROL", "중원 장악", ""),
    ("pressing_index", "PRESSING", "전방 압박", ""),
    ("defense_output_index", "DEFENSIVE OUTPUT", "실점 억제", "ga"),
    ("set_piece_attack_index", "SET PIECES", "세트피스", "sp"),
]


def _live_inputs(team: str, league: str, src: dict, today) -> dict:
    """화면 실시간 반영 재료 — 공식 결과(매일 아침) 전에 라이브 스코어(/live-scores, ESPN 30초)로 덮어쓸 경기.

    table·pending: 리그 순위표와 아직 결과가 없는 최근·오늘 리그 경기(league_lab 과 같은 값, 잠정 순위 계산용).
    team_pending: 이 팀의 미반영 경기(전 대회, 3일 전~내일) — LAST 5·승점 흐름 맨 앞에 'LIVE 67'·FT(잠정)'.
    예전엔 팀 화면 순위·승점·LAST 5 가 다음 날 아침 갱신까지 그대로였다(2026-10-19 사용자 지적)."""
    import match_center as mc  # noqa: PLC0415
    try:
        lab = league_lab(league)
    except Exception:  # noqa: BLE001
        lab = {}
    pend = []
    for x in mc.matches_from(src["rows"], today - datetime.timedelta(days=3), 4, team=team):
        x = _fx_enrich(x, src)
        x.pop("_t", None)
        pend.append(x)
    return {"table": lab.get("table") or [], "pending": lab.get("pending") or {}, "team_pending": pend}


@app.get("/api/team-season/{team}")
@_memo(ttl=1800)
def team_season(team: str, league: str = ACTIVE_LEAGUE):
    """팀 화면 'SEASON SNAPSHOT' — 순위·승점 흐름(1위·4위 비교)·최근 5경기(전 대회, 리뷰 연결)·
    시즌 프로필(지표별 리그 순위 + 근거 숫자). 레이더 숫자만으론 '2위 팀 공격 43?' 같은 오해가 생겨 순위·근거를 함께 준다."""
    import match_center as mc  # noqa: PLC0415
    src = _fx_sources()
    rows = src["rows"].get(league)
    st = ds.read_table("standings", league=league)
    n = 0 if st is None else len(st)
    me = None if st is None else st[st["squad"] == team]
    stand = None if me is None or me.empty else me.iloc[0]

    def _path_of(t):
        return {"team": t, "path": mc.points_path(rows, t), "logo": tm.team_logo(t), "color": tm.team_color(t)}
    path = _path_of(team)
    refs = []
    if st is not None and not st.empty:
        srt = st.sort_values("rank")
        for rk, label in ((1, "1위"), (4, "4위")):
            r = srt[srt["rank"] == rk]
            if not r.empty and str(r.iloc[0]["squad"]) != team:
                refs.append({**_path_of(str(r.iloc[0]["squad"])), "label": label})

    # 최근 5경기(전 대회) — 상대 리그 파일로 묶어야 상대도 우리 표기
    today = _today_kst()
    recent = []
    for m in mc.results_from(src["rows"], today, 75):
        if team not in (m["home"]["team"], m["away"]["team"]):
            continue
        m = _fx_enrich(m, src)
        m["upset"] = mc.upset_note(m)
        recent.append(m)
        if len(recent) >= 5:
            break

    # 시즌 프로필 — 리그 안 순위와 근거 숫자 + 지난 시즌 같은 지표(같은 리그였을 때) 대비 ▲▼
    profile = []
    um = ds.read_table("team_unit_metrics", league=league)
    sb = _team_row("statbunker_team_stats", team, league)
    prev_season = f"{SEASON_START - 1}_{SEASON_START}"
    um_p = ds.read_table("team_unit_metrics", league=league, season=prev_season)
    row_p = um_p[um_p["squad"] == team].iloc[0] if um_p is not None and team in set(um_p["squad"]) else None
    st_p = ds.read_table("standings", league=league, season=prev_season)
    stand_p = st_p[st_p["squad"] == team].iloc[0] if st_p is not None and team in set(st_p["squad"]) else None
    sb_p = None
    try:
        _sbp = ds.read_table("statbunker_team_stats", league=league, season=prev_season)
        sb_p = _sbp[_sbp["squad"] == team].iloc[0] if _sbp is not None and team in set(_sbp["squad"]) else None
    except Exception:  # noqa: BLE001
        sb_p = None
    # 근거 숫자(경기당 득점·실점)에는 그 숫자 자체의 리그 순위를 — 지수 순위(옆 칸)와 섞여 '1.57 = 5위 / 7위'로
    # 둘로 보였다(2026-10-20 점검). 순위는 SQUAD STRENGTH 의 '26/27 1.57 5위'와 같은 계산(경기당 값, 동률은 같은 순위)
    raw_rank: dict[str, int] = {}
    st_all = ds.read_table("standings", league=league)
    if st_all is not None and stand is not None and not st_all.empty:
        pl_ = pd.to_numeric(st_all["played"], errors="coerce").replace(0, pd.NA)
        gfp = pd.to_numeric(st_all["gf"], errors="coerce") / pl_
        gap = pd.to_numeric(st_all["ga"], errors="coerce") / pl_
        me_gf = float(_num(stand["gf"])) / max(1, int(_num(stand["played"])))
        me_ga = float(_num(stand["ga"])) / max(1, int(_num(stand["played"])))
        raw_rank = {"gf": int((gfp.round(4) > round(me_gf, 4)).sum()) + 1, "ga": int((gap.round(4) < round(me_ga, 4)).sum()) + 1}
    if um is not None and team in set(um["squad"]):
        row = um[um["squad"] == team].iloc[0]
        g = int(_num(stand["played"])) if stand is not None else 0
        for col, en, kr, hint_kind in _PROFILE_AXES:
            if col not in um.columns or pd.isna(row.get(col)) or _num(row.get(col)) <= 0:
                continue
            vals = pd.to_numeric(um[col], errors="coerce")
            val = int(_num(row[col]))
            rank = int((vals > val).sum()) + 1
            hint = ""
            if hint_kind == "gf" and stand is not None and g:
                hint = f"경기당 득점 {int(stand['gf']) / g:.2f}" + (f"(기록 {raw_rank['gf']}위)" if raw_rank else "")
            elif hint_kind == "ga" and stand is not None and g:
                hint = f"경기당 실점 {int(stand['ga']) / g:.2f}" + (f"(기록 {raw_rank['ga']}위)" if raw_rank else "")
            elif hint_kind == "sp" and sb is not None and pd.notna(sb.get("non_penalty_set_piece_goals")):
                hint = f"세트피스 득점 {int(_num(sb.get('non_penalty_set_piece_goals')))}골"
            prev = prev_rank = None
            prev_hint = ""
            if row_p is not None and col in um_p.columns and pd.notna(row_p.get(col)) and _num(row_p.get(col)) > 0:
                prev = int(_num(row_p[col]))
                prev_rank = int((pd.to_numeric(um_p[col], errors="coerce") > prev).sum()) + 1
                gp = int(_num(stand_p["played"])) if stand_p is not None else 0
                if hint_kind == "gf" and gp:
                    prev_hint = f"경기당 득점 {int(_num(stand_p['gf'])) / gp:.2f}"
                elif hint_kind == "ga" and gp:
                    prev_hint = f"경기당 실점 {int(_num(stand_p['ga'])) / gp:.2f}"
                elif hint_kind == "sp" and sb_p is not None and pd.notna(sb_p.get("non_penalty_set_piece_goals")):
                    prev_hint = f"세트피스 득점 {int(_num(sb_p.get('non_penalty_set_piece_goals')))}골"
            profile.append({"key": col, "en": en, "kr": kr, "value": val, "rank": rank,
                            "n": int(vals.notna().sum()), "hint": hint,
                            "prev": prev, "prev_rank": prev_rank, "prev_hint": prev_hint})

    # 득점 구성 — 오픈플레이·세트피스·PK(StatBunker, EPL·라리가·세리에A) 이번 시즌 vs 지난 시즌
    def _mix(r):
        if r is None or pd.isna(r.get("goals_statbunker")):
            return None
        sp = sum(_num(r.get(c)) for c in ("corner_goals", "free_kick_goals", "direct_free_kick_goals", "throw_in_goals"))
        pen = _num(r.get("penalty_goals_type"))
        op = _num(r.get("open_play_goals")) + _num(r.get("cross_goals")) + _num(r.get("other_goals"))
        return {"total": int(op + sp + pen), "open": int(op), "set_piece": int(sp), "pen": int(pen),
                "corner": int(_num(r.get("corner_goals"))), "games": int(_num(r.get("matches_statbunker")))}
    goal_mix = {"cur": _mix(sb), "prev": _mix(sb_p)} if sb is not None else None

    # 리그 표의 경기당 xG·전력 순위(리그 랩 6시간 캐시 재사용)
    xg_pg = str_rank = xg_rank = xg_avg = None
    try:
        tbl = league_lab(league).get("table") or []
        lab_row = next((r for r in tbl if r.get("team") == team), None)
        if lab_row:
            xg_pg, str_rank = lab_row.get("xg_pg"), lab_row.get("str_rank")
            xs = [r.get("xg_pg") for r in tbl if r.get("xg_pg") is not None]
            if xg_pg is not None and xs:                 # 경기당 xG 리그 순위·평균 — 숫자만으론 좋은지 몰랐다
                xg_rank = 1 + sum(1 for x in xs if x > xg_pg)
                xg_avg = round(sum(xs) / len(xs), 2)
    except Exception:  # noqa: BLE001
        pass

    return {
        "team": team, "league": league, "n": n,
        "standing": None if stand is None else {k: int(_num(stand[k])) for k in
                                                 ("rank", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points")},
        "xg_pg": xg_pg, "str_rank": str_rank, "xg_rank": xg_rank, "xg_avg": xg_avg,
        "path": path, "refs": refs, "recent": recent, "profile": profile, "goal_mix": goal_mix,
        **_live_inputs(team, league, src, today),
    }


@app.get("/api/prediction-league")
@_memo(ttl=1800)
def prediction_league():
    """예측 성적표 — 팬 투표 vs 우리 모델 vs ClubElo(data/predictions_log.csv, scripts/log_predictions.py).
    sources: 출처별 적중률·브라이어(낮을수록 좋음)·로그손실, h2h: 팬·모델이 둘 다 있던 경기만 맞대결,
    recent: 최근 끝난 경기 12개(각 출처의 픽·결과), split: 다가오는 경기 중 팬과 모델의 픽이 갈린 경기."""
    import math as _m
    p = data_path("predictions_log", season="x").parent / "predictions_log.csv"
    if not p.exists():
        return {"available": False, "sources": [], "h2h": None, "recent": [], "split": []}
    df = pd.read_csv(p, dtype={"event_id": str})
    keys = (("fans", "FANS", "팬 투표"), ("model", "MODEL", "우리 모델"), ("elo", "CLUBELO", "ClubElo"))

    def probs(r, k):
        v = [r.get(f"{k}_{x}") for x in ("h", "d", "a")]
        return None if any(x is None or x != x for x in v) else {"H": float(v[0]), "D": float(v[1]), "A": float(v[2])}

    done = df[df["result"].isin(["H", "D", "A"])].to_dict("records")

    def score(rows, k):
        n = hit = br = ll = 0
        for r in rows:
            pr = probs(r, k)
            if not pr:
                continue
            n += 1
            hit += max(pr, key=pr.get) == r["result"]
            br += sum((pr[o] - (o == r["result"])) ** 2 for o in pr)
            ll += -_m.log(max(1e-6, pr[r["result"]]))
        return {"n": n, "acc": round(hit / n, 3) if n else None, "brier": round(br / n, 3) if n else None,
                "logloss": round(ll / n, 3) if n else None, "hits": hit}

    def _logo_of(r, side):   # 사전 → 기록 시 저장한 로고(ESPN, 우리 리그 밖 팀)
        v = r.get(f"{side}_logo")
        return tm.team_logo(r[side]) or (v if isinstance(v, str) else "") or ""

    sources = [{"key": k, "en": en, "kr": kr, **score(done, k)} for k, en, kr in keys]
    both = [r for r in done if probs(r, "fans") and probs(r, "model")]
    h2h = {"n": len(both), "fans": score(both, "fans"), "model": score(both, "model")} if both else None
    # 세 출처 맞대결 — 셋 다 예측한 같은 경기만(출처마다 경기 수가 달라 전체 적중률은 공정 비교가 아니다, 2026-10-19 사용자).
    # 순위는 적중률 → 브라이어. v3: 모델 v3 로 본 같은 경기(v3 이전 경기는 '그 경기 전 데이터로 다시 계산'한 v3r_*, 참고)
    common_rows = [r for r in done if all(probs(r, k) for k, *_ in keys)]
    common = None
    if common_rows:
        sc = {k: score(common_rows, k) for k, *_ in keys}
        v3rows = []
        for r in common_rows:
            if str(r.get("model_ver") or "") == "v3":
                v3rows.append(r)
            elif probs(r, "v3r"):
                v3rows.append({**r, "model_h": r["v3r_h"], "model_d": r["v3r_d"], "model_a": r["v3r_a"]})
        v3 = score(v3rows, "model") if v3rows else None
        rank = sorted(sc, key=lambda k: (-(sc[k]["acc"] or 0), sc[k]["brier"] or 9))
        common = {"n": len(common_rows), "scores": sc, "rank": rank, "v3": v3,
                  "v3_live": sum(1 for r in common_rows if str(r.get("model_ver") or "") == "v3")}
    vers = df["model_ver"].fillna("v2").value_counts().to_dict() if "model_ver" in df.columns else {"v2": len(df)}
    v3_since = (str(df[df["model_ver"] == "v3"]["date"].min()) if "model_ver" in df.columns and (df["model_ver"] == "v3").any() else None)

    def pick(r, k):
        pr = probs(r, k)
        return None if not pr else {"pick": max(pr, key=pr.get), "p": round(max(pr.values()), 3)}
    recent = [{"event_id": r["event_id"], "date": r["date"], "home": r["home"], "away": r["away"],
               "home_logo": _logo_of(r, "home"), "away_logo": _logo_of(r, "away"),
               "hg": int(r["hg"]), "ag": int(r["ag"]), "result": r["result"],
               **{k: pick(r, k) for k, *_ in keys}} for r in sorted(done, key=lambda r: (r["date"], str(r.get("kickoff"))), reverse=True)[:12]]
    today = _today_kst().isoformat()
    split = []
    # 승자 예상이 다른 경기 + 같더라도 팬이 고른 결과의 확률이 20%p 이상 다른 경기(Betis–Feyenoord 팬 81% vs 모델 41%).
    # 예전엔 픽이 다를 때만 담아 이번 주 칸이 비었다(2026-10-20 점검)
    for r in df[(df["result"].isna()) & (df["date"].astype(str) >= today)].to_dict("records"):
        f, mo = probs(r, "fans"), probs(r, "model")
        if not (f and mo):
            continue
        fk = max(f, key=f.get)
        differ = fk != max(mo, key=mo.get)
        gap = abs(f[fk] - mo[fk])
        if differ or gap >= 0.20:
            split.append({"event_id": r["event_id"], "date": r["date"], "home": r["home"], "away": r["away"],
                          "home_logo": _logo_of(r, "home"), "away_logo": _logo_of(r, "away"),
                          "fans": pick(r, "fans"), "model": pick(r, "model"), "gap": round(gap, 3),
                          "kind": "pick" if differ else "confidence", "model_on_fan_pick": round(mo[fk], 3)})
    split.sort(key=lambda x: (x["kind"] != "pick", -x["gap"]))
    return {"available": True, "since": str(df["date"].min()), "sources": sources, "h2h": h2h, "recent": recent,
            "split": split[:6], "common": common, "model_versions": {k: int(v) for k, v in vers.items()}, "v3_since": v3_since}


# 분석 탭 '리그 백분위' 지표 — (컬럼 또는 계산 키, 영어, 한글, 높을수록 좋은가, 표시 형식)
_TREND_METRICS = [
    ("gf", "GOALS", "경기당 득점", True, "f2"), ("ga", "CONCEDED", "경기당 실점", False, "f2"),
    ("xg", "xG", "경기당 기대 득점", True, "f2"), ("xga", "xGA", "경기당 기대 실점", False, "f2"),
    ("shots", "SHOTS", "경기당 슈팅", True, "f1"), ("opp_shots", "SHOTS CONCEDED", "경기당 허용 슈팅", False, "f1"),
    ("sot", "ON TARGET", "경기당 유효 슈팅", True, "f1"), ("poss", "POSSESSION", "점유율", True, "pct"),
    ("pass_pct", "PASS ACCURACY", "패스 성공률", True, "pct"), ("ppda", "PPDA", "압박 강도(낮을수록 강함)", False, "f1"),
    ("deep", "DEEP COMPLETIONS", "상대 박스 근처 패스 성공", True, "f1"), ("corners", "CORNERS", "경기당 코너킥", True, "f1"),
]
_TIME_BUCKETS = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90)]


def _bucket_of(tok: str) -> int | None:
    """'45+3' → 31-45 칸, '90+5' → 76-90 칸, '67' → 61-75 칸."""
    try:
        base = int(str(tok).split("+")[0])
    except (TypeError, ValueError):
        return None
    for i, (lo, hi) in enumerate(_TIME_BUCKETS):
        if lo <= base <= hi:
            return i
    return len(_TIME_BUCKETS) - 1 if base > 90 else None


@app.get("/api/team-trends/{team}")
@_memo(ttl=3600)
def team_trends(team: str, league: str = ACTIVE_LEAGUE):
    """분석 탭 — 경기별 흐름(xG·슈팅·결과), 득실 시간대(15분 단위), 리그 백분위(리그 경기 기준 경기당 평균).
    원천: data/match_stats(ESPN 경기 상세 + 5대 리그 Understat xG·PPDA, src/fetch_match_stats.py)."""
    ms = ds.read_table("match_stats", league=league)
    if ms is None or ms.empty or team not in set(ms["squad"]):
        return {"team": team, "league": league, "available": False, "matches": [], "timing": None, "percentiles": [], "has_xg": False}
    ms = ms.copy()
    ms["event_id"] = ms["event_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    mine = ms[ms["squad"] == team].sort_values("date")

    def _f(v):
        x = _num(v, None)
        return None if x is None or x != x else round(float(x), 3)
    matches = []
    for r in mine.itertuples(index=False):
        matches.append({"event_id": r.event_id, "date": str(r.date)[:10], "comp_code": r.comp_code,
                        "opponent": r.opponent, "opp_logo": tm.team_logo(r.opponent) or "", "home_away": r.home_away,
                        "gf": int(_num(r.gf)), "ga": int(_num(r.ga)), "result": r.result,
                        "xg": _f(getattr(r, "xg", None)), "xga": _f(getattr(r, "xga", None)),
                        "shots": _f(r.shots), "opp_shots": _f(r.opp_shots), "sot": _f(r.sot), "opp_sot": _f(r.opp_sot),
                        "poss": _f(r.poss), "ppda": _f(getattr(r, "ppda", None)), "xpts": _f(getattr(r, "xpts", None))})

    # 득실 시간대(전 대회)
    scored, conceded = [0] * len(_TIME_BUCKETS), [0] * len(_TIME_BUCKETS)
    for col, arr in (("goal_min_for", scored), ("goal_min_against", conceded)):
        for v in mine[col].dropna().astype(str):
            for tok in v.split(";"):
                b = _bucket_of(tok.strip())
                if b is not None:
                    arr[b] += 1
    timing = {"buckets": [f"{lo}-{hi}" for lo, hi in _TIME_BUCKETS], "scored": scored, "conceded": conceded,
              "games": int(len(mine))}

    # 리그 백분위 — 리그 경기만, 팀별 경기당 평균
    lg = ms[ms["comp_code"].astype(str).str.endswith(".1")]
    pcts = []
    if not lg.empty and team in set(lg["squad"]):
        agg = lg.groupby("squad").agg({c: "mean" for c, *_ in _TREND_METRICS if c in lg.columns})
        n_games = int((lg["squad"] == team).sum())
        for col, en, kr, high, fmt in _TREND_METRICS:
            if col not in agg.columns:
                continue
            s = pd.to_numeric(agg[col], errors="coerce").dropna()
            if team not in s.index or len(s) < 5:
                continue
            v = float(s[team])
            better = (s < v).sum() if high else (s > v).sum()
            ties = (s == v).sum() - 1
            pct = round((better + 0.5 * ties) / (len(s) - 1) * 100) if len(s) > 1 else 50
            rank = int((s > v).sum() + 1) if high else int((s < v).sum() + 1)
            pcts.append({"key": col, "en": en, "kr": kr, "value": round(v, 2), "fmt": fmt, "pct": int(pct),
                         "rank": rank, "n": int(len(s)), "high_good": high, "league_avg": round(float(s.mean()), 2)})
        timing["league_games"] = n_games
    return {"team": team, "league": league, "available": True, "matches": matches, "timing": timing,
            "percentiles": pcts, "has_xg": any(m["xg"] is not None for m in matches)}


@app.on_event("startup")
def _warm_up() -> None:
    """서버가 뜨자마자 백그라운드에서 공용 계산을 미리 데운다.

    Render 무료 인스턴스는 잠들었다 깨거나 배포될 때마다 메모리 캐시가 비어, 첫 방문자의 화면이
    수십 초 걸렸다(2026-10-14: Overview 첫 호출 33초). 리그별 선수 표·지난 시즌 OVR·평점 추이 기준값·
    홈 스냅샷만 데우면 이후 요청은 0.2~1초. 응답(헬스체크)을 막지 않게 데몬 스레드로.
    """
    import threading

    def run():
        import time as _t
        t0 = _t.monotonic()
        try:
            _role_counts_all()                 # 포지션 프로필(전 리그 라인업 집계)
            for lg in ds.available_leagues():
                _pf(lg)
                _trend_base(lg)
                _rec_pool(lg)
                _players_lookup(lg)
                _club_strength(lg)
            _prev_season()
            _hub_body()
            hub_pulse()              # 홈 결과 띠·주목할 매치·우승 경쟁(로컬 0.9초 → 운영 수 초라 미리)
            for lg in _HUB_LEAGUES:
                league_lab(lg)       # 홈 LEAGUE FOCUS 분석 랩
            print(f"[warm-up] 완료 {_t.monotonic() - t0:.1f}s", flush=True)
        except Exception as e:  # noqa: BLE001 — 데우기는 실패해도 서비스엔 영향 없음
            print(f"[warm-up] 건너뜀: {type(e).__name__}: {e}", flush=True)

    threading.Thread(target=run, name="warm-up", daemon=True).start()


@app.get("/api/home/all")
def home_all():
    return Response(content=_hub_body(), media_type="application/json")


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
    import re as _re  # noqa: PLC0415
    t = str(s or "").upper()
    toks = set(_re.split(r"[^A-Z]+", t))
    if toks & {"GK"} or "KEEPER" in t:
        return "GK"
    if toks & {"LWB", "LB"} or "LEFT-BACK" in t or "LEFT BACK" in t:
        return "LB"
    if toks & {"RWB", "RB"} or "RIGHT-BACK" in t or "RIGHT BACK" in t:
        return "RB"
    if toks & {"CB", "LCB", "RCB"} or "CENTRE-BACK" in t or "CENTER-BACK" in t or "CENTRE BACK" in t:
        return "CB"
    # 공격수를 윙보다 먼저 — 예전엔 'Centre-FoRWard' 안의 'RW' 때문에 모든 센터포워드가 윙(W)이 됐다
    if toks & {"ST", "CF", "SS"} or "STRIKER" in t or "FORWARD" in t:
        return "ST"
    if toks & {"RW", "LW", "RM", "LM"} or "WING" in t or "LEFT MIDFIELD" in t or "RIGHT MIDFIELD" in t:
        return "W"
    if toks & {"DM", "CM", "AM", "CDM", "CAM", "LCM", "RCM", "LDM", "RDM"} or "MID" in t:
        return "CM"
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
        tw, _wf = _window_filter(tr[tr["squad"] == team].copy(), win)
        # 같은 창에서 다시 영입된 선수는 이탈이 아니다 — 임대 종료(out) 후 완전 영입(in)이 함께 기록된다
        # (예: Hincapié 'End of loan → Leverkusen' + '€40m ← Leverkusen' 이 '떠난 선수'와 벤치에 동시에 나왔다)
        # 단, 임대 복귀(in, End of loan) 뒤 완전 이적(out)한 선수(Kiwior → Porto)는 실제로 떠난 것이라 남긴다.
        eol = lambda f: str(f or "").lower().startswith("end of loan")  # noqa: E731
        ins = tw[tw["direction"] == "in"]
        signed = {_dep_last(p) for p, f in zip(ins["player"], ins["fee_text"]) if not eol(f)}
        tt = tw[(tw["direction"] == "out") & ~tw["fee_text"].map(_is_loan_move)]
        tt = tt[~(tt["fee_text"].map(eol) & tt["player"].map(_dep_last).isin(signed))]
        for _, r in tt.iterrows():
            ph = str(r.get("photo") or "")
            dep[_dep_last(r.get("player"))] = {"player": str(r.get("player") or ""),
                "club": str(r.get("club") or ""), "pos": str(r.get("pos") or ""),
                "photo": ph if ph.startswith("http") else ""}   # 이적 기록의 TM 사진(떠난 선수는 현재 명단에 없다)
    full = _pf(league)
    if full is not None and "left_for" in full.columns:
        lf = full[(full["squad"] == team) & full["left_for"].notna()
                  & (full["left_for"].astype(str).str.strip() != "")]
        for _, r in lf.iterrows():
            dep.setdefault(_dep_last(r.get("player")), {"player": str(r["player"]),
                "club": str(r.get("left_for") or ""),
                "pos": str(r.get("tm_position") or r.get("fl_group") or r.get("pos") or ""), "photo": _photo(r)})
    return dep


@app.get("/api/projection/{team}")
@_memo(ttl=21600)
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
            "current_label": _data_season_label(), "next_label": next_label, "phase": win.get("phase"),
            "current": season, "projected": {"formation": season["formation"], "placements": projected},
            "diagnosis": diagnosis}
