"""경기 전 예측 기록 — 팬 투표 · 우리 모델 · Elo 기준을 경기 전에 저장하고, 끝나면 결과를 붙인다(2026-10-15).

Elo 기준(elo_*) = 우리 Elo 만으로 낸 승·무·패(src/team_elo.wdl, 그 경기 날 아침 Elo · 무승부 곡선은 지난 시즌으로만 맞춤 —
소급해도 미래 정보 없음). 2026-10-26 전까지 이 칸은 ClubElo 였고(10/25 부터 사이트 차단), 그 값은 clubelo_* 로 옮겨
따로 둔다(성적표에 섞지 않음). elo_ver 가 비어 있는 옛 행은 한 번 옮기고 Elo 기준을 소급해 채운다.

'팬 vs 모델 누가 더 잘 맞히나' 성적표(/api/prediction-league)의 원천: data/predictions_log.csv
  · 다가오는 경기(킥오프 전): 최신 예측으로 덮어쓴다 — 마지막 기록 = 경기 직전에 가장 가까운 예측
  · 이미 끝났는데 기록이 없는 경기(최근 7일): 팬·ClubElo 는 보관분(7일), 모델은 '그 경기 전 데이터만으로' 다시 계산
  · 결과가 나온 경기: 스코어·결과(H/D/A)를 채운다
match_refresh(08:15)·daily_data(13:30)가 돌린다. 팬 투표는 로컬 PC 가 10:30·18:30 에 갱신.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import api.main as api  # noqa: E402
import match_center as mc  # noqa: E402
import predict_model as pm  # noqa: E402

OUT = ROOT / "data" / "predictions_log.csv"
COLS = ["event_id", "date", "kickoff", "comp_code", "home", "away", "home_league", "away_league", "home_logo", "away_logo",
        "model_h", "model_d", "model_a", "model_score", "fans_h", "fans_d", "fans_a", "fans_n",
        "elo_h", "elo_d", "elo_a", "logged_at", "hg", "ag", "result",
        # model_ver: 기록 당시 모델 버전(비어 있으면 v2 시절) · v3r_*: v3 를 '그 경기 전 데이터만으로' 다시 계산한 값(참고, v3 이전 경기)
        "model_ver", "v3r_h", "v3r_d", "v3r_a",
        # elo_ver: Elo 기준 버전(own-v1) · clubelo_*: 예전 ClubElo 기록(10/15~10/24)
        "elo_ver", "clubelo_h", "clubelo_d", "clubelo_a"]
ELO_VER = "own-v1"


def _row(m: dict, now: str) -> dict:
    mo, fa, el = m.get("model") or {}, m.get("fans") or {}, m.get("elo") or {}
    return {"event_id": str(m["event_id"]), "date": m["date"], "kickoff": m.get("kickoff", ""), "comp_code": m["comp_code"],
            "home": m["home"]["team"], "away": m["away"]["team"],
            "home_league": m["home"].get("league") or "", "away_league": m["away"].get("league") or "",
            "home_logo": m["home"].get("logo") or "", "away_logo": m["away"].get("logo") or "",   # 우리 리그 밖 팀은 ESPN 로고
            "model_h": mo.get("h"), "model_d": mo.get("d"), "model_a": mo.get("a"), "model_score": mo.get("score"),
            "fans_h": fa.get("h"), "fans_d": fa.get("d"), "fans_a": fa.get("a"), "fans_n": fa.get("n"),
            "elo_h": el.get("h"), "elo_d": el.get("d"), "elo_a": el.get("a"), "logged_at": now,
            "model_ver": pm.MODEL_VERSION if mo else None, "elo_ver": ELO_VER if el else None}


def _blank(v) -> bool:
    return v is None or v != v or str(v).strip() in ("", "nan")


def migrate_elo(rows: dict) -> tuple[int, int]:
    """옛 행의 elo_*(ClubElo) → clubelo_* 로 옮기고, Elo 기준이 없는 행은 그 경기 날 아침 Elo 로 채운다. (옮김, 채움)"""
    moved = filled = 0
    for r in rows.values():
        if _blank(r.get("elo_ver")) and not _blank(r.get("elo_h")):
            r["clubelo_h"], r["clubelo_d"], r["clubelo_a"] = r.get("elo_h"), r.get("elo_d"), r.get("elo_a")
            r["elo_h"] = r["elo_d"] = r["elo_a"] = None
            moved += 1
        if r.get("elo_ver") != ELO_VER:
            e = api._elo_pred(str(r["home"]), str(r["away"]), str(r["date"])[:10])
            if e:
                r["elo_h"], r["elo_d"], r["elo_a"], r["elo_ver"] = e["h"], e["d"], e["a"], ELO_VER
                filled += 1
    return moved, filled


def main() -> int:
    src = api._fx_sources()
    today = api._today_kst()
    now_utc = dt.datetime.now(dt.timezone.utc)
    now = now_utc.isoformat(timespec="minutes")
    log = pd.read_csv(OUT, dtype={"event_id": str}) if OUT.exists() else pd.DataFrame(columns=COLS)
    rows = {r["event_id"]: r for r in log.to_dict("records")}
    moved, filled = migrate_elo(rows)

    # 1) 다가오는 경기 — 킥오프 전이면 최신 예측으로 덮어쓴다
    up = 0
    for m in mc.matches_from(src["rows"], today, 3):
        if not m.get("event_id"):
            continue
        ko = pd.to_datetime(m.get("kickoff") or None, utc=True, errors="coerce")
        if ko is not pd.NaT and ko == ko and ko <= now_utc:
            continue                                   # 이미 시작 — 경기 전 기록을 덮지 않는다
        m = api._fx_enrich(m, src)
        if not (m.get("model") or m.get("fans") or m.get("elo")):
            continue
        rows[str(m["event_id"])] = {**rows.get(str(m["event_id"]), {}), **_row(m, now)}
        up += 1

    # 2) 최근 7일 끝난 경기 — 기록이 없으면 보관된 팬·Elo + 경기 전 데이터로 다시 계산한 모델로 추가, 결과 채우기
    back = res = 0
    for m in mc.results_from(src["rows"], today, 7):
        eid = str(m.get("event_id") or "")
        if not eid:
            continue
        hg, ag = m["home"]["goals"], m["away"]["goals"]
        if eid not in rows:
            m = api._fx_enrich(m, src)
            m.pop("model", None)
            api._attach_model(m, before=m["date"])     # 결과 누설 없이
            if not m.get("fans"):
                continue                               # 외부 예측(팬 투표)이 없으면 성적표에 넣지 않는다 — Elo 기준은 늘 있어서 기준이 못 된다
            rows[eid] = _row(m, now)
            back += 1
        r = rows[eid]
        if r.get("result") not in ("H", "D", "A"):
            r["hg"], r["ag"] = hg, ag
            r["result"] = "H" if hg > ag else "A" if hg < ag else "D"
            res += 1
    # 3) v3 이전에 기록된 끝난 경기 — v3 를 그 경기 전 데이터만으로 다시 계산해 따로(v3r_*) 남긴다(성적표 '참고' 줄).
    #    부상 결장 명단은 과거분이 없어 빠지고, 팀 OVR 은 지금 값이라 조금 유리할 수 있다(화면에 밝힘)
    rep_n = 0
    for r in rows.values():
        if r.get("result") not in ("H", "D", "A") or str(r.get("model_ver") or "") == pm.MODEL_VERSION:
            continue
        if r.get("v3r_h") == r.get("v3r_h") and r.get("v3r_h") is not None:
            continue
        hl, al = r.get("home_league"), r.get("away_league")
        if not (isinstance(hl, str) and hl and isinstance(al, str) and al):
            continue
        fx = {"home": {"team": r["home"], "league": hl}, "away": {"team": r["away"], "league": al}}
        api._attach_model(fx, before=str(r["date"])[:10])
        mo = fx.get("model")
        if mo:
            r["v3r_h"], r["v3r_d"], r["v3r_a"] = mo["h"], mo["d"], mo["a"]
            rep_n += 1
    out = pd.DataFrame(list(rows.values()), columns=COLS).sort_values(["date", "kickoff"])
    out.to_csv(OUT, index=False)
    print(f"[predictions-log] 예정 갱신 {up} · 지난 경기 추가 {back} · 결과 채움 {res} · v3 재계산 {rep_n} · "
          f"ClubElo 옮김 {moved} · Elo 기준 채움 {filled} · 전체 {len(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
