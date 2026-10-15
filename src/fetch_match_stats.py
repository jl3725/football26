"""경기별 팀 기록 — 분석 탭 '경기별 흐름·득실 시간대·리그 백분위' 원천(2026-10-15).

  ESPN 경기 상세(summary): 점유율·슈팅·유효 슈팅·코너·패스·파울·선방·태클·인터셉트 + 득점·퇴장 분
  + 선수 이벤트(골·도움·카드) → data/match_events_<리그>_<시즌>.csv (Player 탭 대회별 골·도움)
     → 끝난 경기(전 대회, schedule_full)마다 한 번만 받는다(증분 — 이미 있는 event_id 는 건너뜀)
  Understat(5대 리그 리그 경기만): xG·npxG·PPDA(압박 강도)·딥 컴플리션·기대 승점 — 매 실행 리그당 한 번 받아 빈칸 채움

출력 data/match_stats_<리그>_<시즌>.csv — 우리 리그 팀 기준 한 경기 한 줄(상대 기록 포함).
ESPN·Understat 모두 GitHub Actions 에서 열린다(scripts/diag_sources.py 진단). 파싱은 경기 리뷰와 같은 match_review.parse.
사용: FB_LEAGUE=EPL python src/fetch_match_stats.py [--max 400]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import match_review as mrv  # noqa: E402
import team_names  # noqa: E402
from leagues import ACTIVE_LEAGUE, SEASON_FBREF, data_path, league_config  # noqa: E402

UA = "Mozilla/5.0 (football26 match-stats)"
UNDERSTAT_LEAGUES = {"EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1"}
STAT_COLS = {   # ESPN 이름 → 우리 컬럼(우리 팀 기준, 상대는 opp_ 접두)
    "possessionPct": "poss", "totalShots": "shots", "shotsOnTarget": "sot", "wonCorners": "corners",
    "passPct": "pass_pct", "foulsCommitted": "fouls", "saves": "saves", "effectiveTackles": "tackles",
    "interceptions": "interceptions", "offsides": "offsides", "blockedShots": "blocked",
}


def _num(v):
    try:
        return float(str(v).replace("%", ""))
    except (TypeError, ValueError):
        return None


def _summary(comp: str, eid: str) -> dict | None:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{comp}/summary?event={eid}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"  ! {eid} {comp}: {type(e).__name__}", flush=True)
            time.sleep(1.5 * (attempt + 1))
    return None


def _min_txt(clock: str) -> str:
    """ESPN "45'+3'" → "45+3", "67'" → "67"."""
    import re  # noqa: PLC0415
    n = re.findall(r"\d+", str(clock or ""))
    return "+".join(n[:2]) if n else ""


def _rows_for(sched_rows: pd.DataFrame, p: dict) -> list[dict]:
    """한 경기 ESPN 파싱 결과 → 이 경기의 우리 팀 행들(홈·원정 둘 다 우리 리그면 두 줄)."""
    out = []
    for r in sched_rows.itertuples(index=False):
        me = "home" if r.home_away == "H" else "away"
        op = "away" if me == "home" else "home"
        row = {"event_id": str(r.event_id), "date": str(r.date)[:10], "kickoff": getattr(r, "kickoff", ""),
               "comp_code": r.comp_code, "squad": r.squad, "opponent": r.opponent, "home_away": r.home_away,
               "gf": p["score"][me], "ga": p["score"][op]}
        row["result"] = "W" if row["gf"] > row["ga"] else "L" if row["gf"] < row["ga"] else "D"
        for name, col in STAT_COLS.items():
            v = p["stats"].get(name) or {}
            a, b = _num(v.get(me)), _num(v.get(op))
            if col == "pass_pct":   # ESPN 은 0.88 같은 비율
                a = round(a * 100, 1) if a is not None and a <= 1 else a
                b = round(b * 100, 1) if b is not None and b <= 1 else b
            row[col], row[f"opp_{col}"] = a, b
        # 패스 성공률은 ESPN 표시값(0.9)이 거칠어 성공/전체 패스로 직접 계산
        ap, tp = p["stats"].get("accuratePasses") or {}, p["stats"].get("totalPasses") or {}
        for side, col in ((me, "pass_pct"), (op, "opp_pass_pct")):
            x, y = _num(ap.get(side)), _num(tp.get(side))
            if x is not None and y:
                row[col] = round(x / y * 100, 1)
        # 득점 분은 '45+3' 형태로 — 정수(48)로 바꾸면 전반 추가시간 골이 후반 48분 골과 섞인다(시간대 분석)
        row["goal_min_for"] = ";".join(_min_txt(g["minute"]) for g in p["goals"] if g["side"] == me)
        row["goal_min_against"] = ";".join(_min_txt(g["minute"]) for g in p["goals"] if g["side"] == op)
        row["red_for"] = sum(1 for c in p["cards"] if c["side"] == me and c["color"] == "red")
        row["red_against"] = sum(1 for c in p["cards"] if c["side"] == op and c["color"] == "red")
        out.append(row)
    return out


def _attach_understat(df: pd.DataFrame, league: str) -> pd.DataFrame:
    """리그 경기에 Understat xG·PPDA 를 붙인다(이미 있는 값은 유지). 실패해도 ESPN 기록은 그대로."""
    if league not in UNDERSTAT_LEAGUES or df.empty:
        return df
    try:
        import soccerdata as sd  # noqa: PLC0415
        u = sd.Understat(leagues=league_config(league).fbref_id, seasons=SEASON_FBREF)
        m = u.read_team_match_stats().reset_index()
    except Exception as e:  # noqa: BLE001
        print(f"  ! Understat 실패: {type(e).__name__}: {str(e)[:100]}", flush=True)
        return df
    ours = sorted(df["squad"].unique())
    name = {t: team_names.best(t, ours) for t in set(m["home_team"]) | set(m["away_team"])}
    us = {}
    for r in m.itertuples(index=False):
        h, a = name.get(r.home_team), name.get(r.away_team)
        d = str(r.date)[:10]
        if h:
            us[(h, a, "H", d)] = (r.home_xg, r.away_xg, r.home_np_xg, r.away_np_xg, r.home_ppda, r.away_ppda,
                                  r.home_deep_completions, r.away_deep_completions, r.home_expected_points)
        if a:
            us[(a, h, "A", d)] = (r.away_xg, r.home_xg, r.away_np_xg, r.home_np_xg, r.away_ppda, r.home_ppda,
                                  r.away_deep_completions, r.home_deep_completions, r.away_expected_points)
    cols = ["xg", "xga", "npxg", "npxga", "ppda", "ppda_opp", "deep", "deep_against", "xpts"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    hit = 0
    for i, r in df[df["comp_code"].astype(str).str.endswith(".1")].iterrows():
        base = pd.Timestamp(r["date"])
        for dd in (0, -1, 1):   # 날짜 기준(UTC↔현지) 하루 차이 허용
            d = (base + pd.Timedelta(days=dd)).date().isoformat()
            v = us.get((r["squad"], r["opponent"], r["home_away"], d)) or us.get((r["squad"], None, r["home_away"], d))
            if v:
                for c, x in zip(cols, v):
                    df.at[i, c] = round(float(x), 3) if x is not None and x == x else None
                hit += 1
                break
    print(f"  · Understat xG 연결 {hit}/{int(df['comp_code'].astype(str).str.endswith('.1').sum())} 리그 경기", flush=True)
    return df


EVENT_COLS = ["event_id", "date", "comp_code", "squad", "minute", "type", "player"]


def _events_for(sched_rows: pd.DataFrame, p: dict) -> list[dict]:
    """선수 이벤트(골·PK·자책·도움·경고·퇴장) — Player 탭 대회별 골·도움(리그·컵·유럽 분리·합산) 원천.
    이벤트가 없는 경기(0-0·카드 없음)도 'none' 한 줄을 남겨 다시 받지 않게 한다."""
    out = []
    for r in sched_rows.itertuples(index=False):
        me = "home" if r.home_away == "H" else "away"
        base = {"event_id": str(r.event_id), "date": str(r.date)[:10], "comp_code": r.comp_code, "squad": r.squad}
        n0 = len(out)
        for g in p["goals"]:
            if g["side"] != me:
                continue
            typ = {"pen": "pen", "og": "og"}.get(g["kind"], "goal")
            out.append({**base, "minute": _min_txt(g["minute"]), "type": typ, "player": g["scorer"]})
            if g.get("assist"):
                out.append({**base, "minute": _min_txt(g["minute"]), "type": "assist", "player": g["assist"]})
        for c in p["cards"]:
            if c["side"] == me:
                out.append({**base, "minute": _min_txt(c["minute"]), "type": c["color"], "player": c["player"]})
        if len(out) == n0:
            out.append({**base, "minute": "", "type": "none", "player": ""})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=400, help="한 번에 새로 받을 경기 수 상한")
    a = ap.parse_args()
    league = ACTIVE_LEAGUE
    sched_p = data_path("schedule_full", league)
    if not sched_p.exists():
        print(f"! {sched_p.name} 없음")
        return 1
    sch = pd.read_csv(sched_p)
    sch = sch[(sch["status"] == "completed") & sch["event_id"].notna()].copy()
    sch["event_id"] = sch["event_id"].astype("int64").astype(str)
    out_p = data_path("match_stats", league)
    old = pd.read_csv(out_p, dtype={"event_id": str}) if out_p.exists() else pd.DataFrame()
    have = set(old["event_id"].astype(str)) if not old.empty else set()
    ev_p = data_path("match_events", league)
    old_ev = pd.read_csv(ev_p, dtype={"event_id": str}) if ev_p.exists() else pd.DataFrame(columns=EVENT_COLS)
    have_ev = set(old_ev["event_id"].astype(str)) if not old_ev.empty else set()
    todo_st = [e for e in sch["event_id"].unique() if e not in have]
    todo_ev = [e for e in sch["event_id"].unique() if e not in have_ev]       # 예전 경기도 이벤트가 없으면 소급
    todo = list(dict.fromkeys(todo_st + todo_ev))[: a.max]
    print(f"[match-stats] {league}: 끝난 경기 {sch['event_id'].nunique()} · 새로 받을 {len(todo)}"
          f"(기록 {len(todo_st)} · 선수 이벤트 {len(todo_ev)})", flush=True)
    rows, evs, fail = [], [], 0
    for k, eid in enumerate(todo, 1):
        srows = sch[sch["event_id"] == eid]
        js = _summary(str(srows.iloc[0]["comp_code"]), eid)
        if not js:
            fail += 1
            continue
        p = mrv.parse(js)
        if p["state"] != "post":
            continue
        if eid not in have:
            rows += _rows_for(srows, p)
        if eid not in have_ev:
            evs += _events_for(srows, p)
        if k % 25 == 0:
            print(f"  … {k}/{len(todo)}", flush=True)
        time.sleep(0.25)
    # 일정에 없는 (경기, 팀) 행은 지운다 — 팀 이름 오매칭(Union SG → Union Berlin)이 고쳐지면 스스로 정리
    valid = set(zip(sch["event_id"].astype(str), sch["squad"].astype(str)))

    def _keep(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        k = [(str(e), str(q)) in valid for e, q in zip(frame["event_id"].astype(str), frame["squad"].astype(str))]
        dropped = len(frame) - sum(k)
        if dropped:
            print(f"  · 일정에 없는 행 {dropped}개 제거", flush=True)
        return frame[k]
    if evs or not old_ev.empty:
        ev = pd.concat([old_ev, pd.DataFrame(evs, columns=EVENT_COLS)], ignore_index=True) if evs else old_ev
        ev = _keep(ev.drop_duplicates()).sort_values(["date", "event_id"])
        ev.to_csv(ev_p, index=False)
        print(f"[OK] {ev_p.name} · {len(ev)}행(새 {len(evs)})", flush=True)
    df = pd.concat([old, pd.DataFrame(rows)], ignore_index=True) if rows else old
    df = _keep(df) if not df.empty else df
    if df.empty:
        print("! 기록 없음 — 저장 안 함")
        return 1 if fail else 0
    df = _attach_understat(df, league)
    df = df.drop_duplicates(["event_id", "squad"], keep="last").sort_values(["squad", "date"])
    df.to_csv(out_p, index=False)
    print(f"[OK] {out_p.name} · {len(df)}행(새 {len(rows)} · 실패 {fail})", flush=True)
    return 1 if fail > max(3, len(todo) // 5) else 0   # 일부 실패는 다음 실행에 다시 받는다


if __name__ == "__main__":
    raise SystemExit(main())
