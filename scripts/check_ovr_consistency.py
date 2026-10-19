"""
OVR 검증 에이전트 — ① 같은 선수의 OVR 이 화면(API)마다 같은가 ② 최종 OVR 은 무엇인가 ③ 지난 기록보다 올랐나·내렸나.

2026-10-19 사용자: "하베르츠가 포메이션엔 83, 선수 프로필엔 84 — 최종 OVR 을 검증하는 에이전트도".
기준값(최종 OVR) = player_frame 의 `_ovr`(rv3.ovr_of_row — 모델 하나). API 함수를 프로세스 안에서 불러
팀마다 선수 OVR 을 모아 기준값과 비교한다(운영 서버에 요청하지 않음).
- 출처: database(선수 카드·DB) · squad(스쿼드·뎁스) · players(선수 목록) · overview(KEY PLAYERS·분포) ·
  lineup(FORMATION 시즌·최근·벤치) · player_detail(선수 프로필, 팀당 상위 N명) · rating_history 기록 경로(player_line) ·
  리크루트 풀(전 리그 후보 현재 OVR, 리그마다 한 팀)
- 변동: data/rating_history_* 의 마지막 기록 대비 ±. 모델 버전이 바뀐 날의 변화는 '모델 변경'으로 따로 센다.
- 결과: --json 경로(기본 data/eval/ovr_audit.json). 불일치가 하나라도 있으면 종료 코드 1(daily_data → watchdog 이슈).

사용: python scripts/check_ovr_consistency.py [--league EPL] [--detail 5] [--json PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def _add(src: dict, name: str, player, ovr) -> None:
    if player and ovr is not None and player not in ("—", "영입 필요"):
        src.setdefault(name, {})[str(player)] = int(ovr)


def team_sources(m, team: str, lg: str, db_rows: list[dict], detail_names: list[str]) -> dict[str, dict[str, int]]:
    """{출처: {선수: OVR}} — 화면마다 내보내는 값."""
    src: dict[str, dict[str, int]] = {}
    for r in db_rows:
        _add(src, "database", r["player"], r["ovr"])
    sq = m.squad(team, lg)
    for line in (sq.get("lines") or {}).values():
        for p in line:
            _add(src, "squad", p.get("player"), p.get("ovr"))
    for b in sq.get("buckets") or []:
        for p in [b.get("starter")] + list(b.get("rotation") or []):
            if p:
                _add(src, "squad_depth", p.get("player"), p.get("ovr"))
    for p in (m.players(team, lg).get("players") or []):
        _add(src, "players", p.get("player"), p.get("ovr"))
    ov = m.overview(team, lg)
    for p in ov.get("stars") or []:
        _add(src, "overview_stars", p["player"], p["ovr"])
    for p in ov.get("squad_ratings") or []:
        _add(src, "overview_squad", p["player"], p["ovr"])
    try:
        lu = m.lineup(team, lg, "league")
    except Exception:  # noqa: BLE001 — 라인업 없는 팀(시즌 초·승격팀)
        lu = {}
    for key in ("season", "recent"):
        for p in ((lu.get(key) or {}).get("placements") or []):
            _add(src, f"lineup_{key}", p.get("player"), p.get("ovr"))
    for p in lu.get("bench") or []:
        _add(src, "lineup_bench", p.get("player"), p.get("ovr"))
    for name in detail_names:
        try:
            _add(src, "player_detail", name, m.player_detail(team, name, lg).get("ovr"))
        except Exception:  # noqa: BLE001
            pass
    return src


def audit_league(m, lg: str, detail_n: int) -> dict:
    import rating_history as rh
    import ratings_v3 as rv3
    pf = m._pf(lg)
    if pf is None or pf.empty:
        return {"league": lg, "teams": 0, "checked": 0, "mismatches": [], "changes": []}
    cur = pf
    if "left_for" in cur.columns:
        cur = cur[cur["left_for"].isna() | (cur["left_for"].astype(str).str.strip() == "")]
    truth = {(str(r["squad"]), str(r["player"])): int(r["_ovr"]) for _, r in cur.iterrows() if r.get("_ovr") == r.get("_ovr")}
    db = json.loads(m.database().body.decode("utf-8"))["players"]
    db_by_team: dict[str, list[dict]] = {}
    for r in db:
        if r["league"] == lg:
            db_by_team.setdefault(r["squad"], []).append(r)
    mism, checked = [], 0
    for team in sorted(cur["squad"].dropna().astype(str).unique()):
        top = cur[cur["squad"] == team].sort_values("_ovr", ascending=False)["player"].astype(str).head(detail_n).tolist()
        for name, vals in team_sources(m, team, lg, db_by_team.get(team, []), top).items():
            for player, v in vals.items():
                t = truth.get((team, player))
                if t is None:
                    continue                    # 기준표 밖(계약 명단만 있는 백업 등) — 따로 계산된 값이라 비교 안 함
                checked += 1
                if v != t:
                    mism.append({"league": lg, "team": team, "player": player, "source": name, "shown": v, "final": t})
    # 기록 경로(rating_history.record → player_line)도 같은 값을 남기는가
    for _, r in cur.iterrows():
        t = truth.get((str(r["squad"]), str(r["player"])))
        if t is None:
            continue
        checked += 1
        v = rv3.player_line(r)["ovr"]
        if v != t:
            mism.append({"league": lg, "team": str(r["squad"]), "player": str(r["player"]), "source": "rating_history",
                         "shown": int(v), "final": t})
    # 마지막 기록 대비 변동(▲▼) — 모델 버전이 바뀐 변화는 따로
    changes = []
    hist = rh.load(lg)
    if not hist.empty:
        last = rh.state_at(hist, "9999-12-31").set_index("pid")
        for _, r in cur.iterrows():
            p = rh.pid(r)
            t = truth.get((str(r["squad"]), str(r["player"])))
            if t is None or p not in last.index:
                continue
            prev = int(last.at[p, "ovr"])
            if prev != t:
                changes.append({"team": str(r["squad"]), "player": str(r["player"]), "from": prev, "to": t, "d": t - prev,
                                "since": str(last.at[p, "date"]),
                                "model_change": str(last.at[p, "model"]) != rv3.MODEL_VERSION})
    changes.sort(key=lambda c: -abs(c["d"]))
    return {"league": lg, "teams": int(cur["squad"].nunique()), "checked": checked, "mismatches": mism, "changes": changes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--detail", type=int, default=5, help="팀당 선수 프로필(player_detail)까지 비교할 상위 인원")
    ap.add_argument("--json", default=str(ROOT / "data" / "eval" / "ovr_audit.json"))
    a = ap.parse_args()
    from api import main as m
    import datastore as ds
    import ratings_v3 as rv3
    leagues = [a.league] if a.league else list(ds.available_leagues())
    res = [audit_league(m, lg, a.detail) for lg in leagues]
    mism = [x for r in res for x in r["mismatches"]]
    # 리크루트 풀(전 리그 후보)의 현재 OVR — 후보가 뛰는 리그 표의 최종 OVR 과 같은가(리그마다 한 팀)
    truth_all = {}
    for lg in ds.available_leagues():
        pf = m._pf(lg)
        if pf is not None:
            truth_all.update({(lg, str(s_), str(p_)): int(o) for s_, p_, o in zip(pf["squad"], pf["player"], pf["_ovr"]) if o == o})
    n_disc = 0
    for lg in leagues:
        pf = m._pf(lg)
        if pf is None or pf.empty:
            continue
        team = str(pf.sort_values("_ovr", ascending=False)["squad"].iloc[0])
        try:
            recs = m.discover(team, league=lg, top=40).get("recommendations") or []
        except Exception:  # noqa: BLE001
            recs = []
        for r in recs:
            t = truth_all.get((r["source_league"], r["squad"], r["player"]))
            if t is None:
                continue
            n_disc += 1
            if r["current_ovr"] != t:
                mism.append({"league": r["source_league"], "team": r["squad"], "player": r["player"],
                             "source": f"recruit_pool({team})", "shown": r["current_ovr"], "final": t})
    out = {"date": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date().isoformat(), "model": rv3.MODEL_VERSION,
           "checked": sum(r["checked"] for r in res) + n_disc, "mismatches": mism,
           "leagues": {r["league"]: {"teams": r["teams"], "checked": r["checked"], "mismatches": len(r["mismatches"]),
                                     "changed": len(r["changes"]), "model_changed": sum(c["model_change"] for c in r["changes"]),
                                     "changes_top": r["changes"][:15]} for r in res}}
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OVR 검증 [{out['model']}] — 비교 {out['checked']}건 · 불일치 {len(mism)}건")
    for r in res:
        up = sum(1 for c in r["changes"] if c["d"] > 0)
        dn = sum(1 for c in r["changes"] if c["d"] < 0)
        print(f"  {r['league']:16} 팀 {r['teams']:2} · 비교 {r['checked']:5} · 불일치 {len(r['mismatches']):3} · "
              f"지난 기록 대비 ▲{up} ▼{dn} (모델 변경분 {sum(c['model_change'] for c in r['changes'])})")
    for x in mism[:30]:
        print(f"    ✗ {x['league']} {x['team']} · {x['player']}: {x['source']} {x['shown']} ≠ 최종 {x['final']}")
    return 1 if mism else 0


if __name__ == "__main__":
    sys.exit(main())
