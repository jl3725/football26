"""
FotMob 결장자(부상·출장정지) → data/fotmob_injuries_{리그}_{시즌}.csv — Transfermarkt 보다 빠른 부상 명단.

2026-10-19 사용자: "에밀리아노 마르티네스가 턱 골절로 실려 나갔는데 부상자 목록에 없다". TM 부상 목록은 며칠 늦다.
FotMob 은 ① 다음 경기 상세(matchDetails)의 lineup.unavailable 에 결장자·복귀 예상('Early December 2026'·'Doubtful')을,
② 끝난 경기 이벤트에 '부상 교체'(Substitution · injuredPlayerOut)를 바로 올린다.
- ① 팀마다 가장 가까운 다가오는 리그 경기(10일 안) 하나 — 리그당 10경기 안팎 요청.
- ② 최근 4일 안 끝난 경기(리그 + 유럽·국내 컵 — 우리 팀이 낀 것)의 부상 교체 — ①에 아직 없으면 '경기 중 부상 교체'로.
  리그만 보던 때 사카(챔스 바이에른전 10분 부상 교체)가 빠졌다(2026-10-22).
- 매 실행 전체 새로 씀(지금 결장자 스냅숏). 팀 표기는 리그 일정의 FotMob 팀 id → 우리 표기.

사용: python src/fetch_fotmob_injuries.py [--league EPL]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import pandas as pd

from fetch_fotmob_ratings import FOTMOB_ID, _get
from leagues import LEAGUES, SEASON, data_path
import team_names as tn  # noqa: F401
from squads import to_ours

COLS = ["squad", "player", "fotmob_id", "kind", "expected_return", "match_id", "match_date", "fetched"]
AHEAD_DAYS, BACK_DAYS = 10, 4


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


_CUP_CACHE: dict = {}


def _cup_finished(since: str) -> list[dict]:
    """유럽·국내 컵 최근 끝난 경기 — 실행 한 번에 한 번만(리그마다 다시 받지 않게)."""
    if since not in _CUP_CACHE:
        from fetch_fotmob_matches import CUPS, finished  # noqa: PLC0415
        got = []
        for fid in CUPS:
            got += finished(fid, None, since)
            time.sleep(0.3)
        _CUP_CACHE[since] = got
    return _CUP_CACHE[since]


def league_rows(lg: str) -> list[dict]:
    d = _get(f"https://www.fotmob.com/api/data/leagues?id={FOTMOB_ID[lg]}") or {}
    ms = (d.get("fixtures") or {}).get("allMatches") or []
    try:
        ours = list(pd.read_csv(data_path("standings", lg, SEASON))["squad"].astype(str))
    except (FileNotFoundError, KeyError):
        ours = []
    sq: dict[str, str] = {}
    for m in ms:
        for side in ("home", "away"):
            t = m.get(side) or {}
            if str(t.get("id")) not in sq:
                sq[str(t.get("id"))] = to_ours(t.get("name"), lg, ours) or str(t.get("name"))
    now = _now()
    hi, lo = (now + dt.timedelta(days=AHEAD_DAYS)).isoformat()[:19], (now - dt.timedelta(days=BACK_DAYS)).isoformat()[:19]
    # ① 팀마다 가장 가까운 다가오는 경기
    nxt: dict[str, dict] = {}
    for m in sorted(ms, key=lambda x: str((x.get("status") or {}).get("utcTime") or "")):
        st = m.get("status") or {}
        t = str(st.get("utcTime") or "")[:19]
        if st.get("started") or st.get("cancelled") or not t or t > hi:
            continue
        for side in ("home", "away"):
            nxt.setdefault(str((m.get(side) or {}).get("id")), m)
    rows: list[dict] = []
    fetched = now.date().isoformat()
    have: set[tuple[str, str]] = set()
    for mid in {str(m["id"]) for m in nxt.values()}:
        j = _get(f"https://www.fotmob.com/api/data/matchDetails?matchId={mid}") or {}
        lu = (j.get("content") or {}).get("lineup") or {}
        date = str(((j.get("general") or {}).get("matchTimeUTCDate") or ""))[:10]
        for side in ("homeTeam", "awayTeam"):
            t = lu.get(side) or {}
            squad = sq.get(str(t.get("id")), str(t.get("name") or ""))
            for u in t.get("unavailable") or []:
                un = u.get("unavailability") or {}
                rows.append({"squad": squad, "player": u.get("name"), "fotmob_id": str(u.get("id") or ""),
                             "kind": str(un.get("type") or "injury"), "expected_return": str(un.get("expectedReturn") or ""),
                             "match_id": mid, "match_date": date, "fetched": fetched})
                have.add((squad, str(u.get("id"))))
        time.sleep(0.35)
    # ② 최근 끝난 경기의 부상 교체(다음 경기 명단에 아직 없는 선수만) — 리그 + 유럽·컵(우리 팀이 낀 경기)
    recent = list(ms)
    try:
        for m in _cup_finished(lo[:10]):
            if str((m.get("home") or {}).get("id")) in sq or str((m.get("away") or {}).get("id")) in sq:
                recent.append(m)
    except Exception as e:  # noqa: BLE001 — 컵 일정 실패는 리그만으로
        print(f"  [cups] 건너뜀 {type(e).__name__}")
    for m in recent:
        st = m.get("status") or {}
        t = str(st.get("utcTime") or "")[:19]
        if not st.get("finished") or not t or t < lo:
            continue
        j = _get(f"https://www.fotmob.com/api/data/matchDetails?matchId={m['id']}") or {}
        evs = ((((j.get("content") or {}).get("matchFacts") or {}).get("events") or {}).get("events")) or []
        for e in evs:
            if e.get("type") != "Substitution" or not e.get("injuredPlayerOut"):
                continue
            sw = e.get("swap") or []
            if len(sw) < 2:
                continue
            off = sw[1]                                   # swap = [들어간 선수, 나간 선수]
            team_id = str((m.get("home") if e.get("isHome") else m.get("away") or {}).get("id"))
            squad = sq.get(team_id, "")
            if not squad or (squad, str(off.get("id"))) in have:
                continue
            rows.append({"squad": squad, "player": off.get("name"), "fotmob_id": str(off.get("id") or ""),
                         "kind": "in_match", "expected_return": f"{e.get('time')}′ 부상 교체", "match_id": str(m["id"]),
                         "match_date": t[:10], "fetched": fetched})
            have.add((squad, str(off.get("id"))))
        time.sleep(0.35)
    return rows


KIND_KO = {"injury": "부상", "in_match": "경기 중 부상 교체"}
CHANGE_COLS = ["run_date", "event_type", "squad", "player", "old_injury", "new_injury", "old_until", "new_until", "source"]


def injury_changes(prev: pd.DataFrame | None, cur: pd.DataFrame, today: str) -> list[dict]:
    """FotMob 결장 명단에 새로 오른 부상(출장 정지 제외) — TM 부상 변화와 같은 열(source=fotmob).
    부상 신호(홈·Inbox)가 TM 목록 변화만 봐서, TM 이 며칠 늦게 올리는 동안 FotMob 이 이미 '부상·11월 초 복귀'로 표시한 사카가
    안 보였다(2026-10-23 사용자). 복귀는 TM 것만 쓴다 — FotMob '다음 경기 결장'은 경기 사이에 비었다 다시 차서 복귀로 잘못 잡힌다.
    지난 명단이 없으면 아무것도 새로 치지 않는다(기준선)."""
    if prev is None or prev.empty:
        return []
    cur = cur[cur["kind"].isin(list(KIND_KO))]
    seen = {(str(s), str(f).split(".")[0]) for s, f in zip(prev["squad"], prev["fotmob_id"])}
    new = cur[[(str(s), str(f).split(".")[0]) not in seen for s, f in zip(cur["squad"], cur["fotmob_id"])]]
    return [{"run_date": (str(r["match_date"])[:10] if r["kind"] == "in_match" and str(r.get("match_date") or "") else today),
             "event_type": "new_injury", "squad": r["squad"], "player": r["player"], "old_injury": "",
             "new_injury": KIND_KO[r["kind"]], "old_until": "", "new_until": str(r.get("expected_return") or ""),
             "source": "fotmob"} for r in new.to_dict("records")]


def write_changes(lg: str, prev: pd.DataFrame | None, cur: pd.DataFrame) -> int:
    path = data_path("fotmob_injury_changes", lg, SEASON)
    have = pd.read_csv(path) if path.exists() else None
    if have is None:
        # 처음 — 지금 명단은 기준선으로만(언제 다쳤는지 몰라 '오늘 새 부상'으로 찍으면 1월까지 빠지는 오래된 부상도 새것이 된다).
        # 이미 다친 선수는 여러 매체 '부상 보도'가 신호로 잡는다(api _injury_events)
        pd.DataFrame(columns=CHANGE_COLS).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        return 0
    rows = injury_changes(prev, cur, dt.date.today().isoformat())
    if not rows and have is not None:
        return 0
    out = pd.concat([x for x in (have, pd.DataFrame(rows, columns=CHANGE_COLS)) if x is not None], ignore_index=True)
    out = out.drop_duplicates(subset=["event_type", "squad", "player", "new_injury"], keep="first")
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    a = ap.parse_args()
    bad = 0
    for lg in ([a.league] if a.league else [x for x in LEAGUES if x in FOTMOB_ID]):
        try:
            rows = league_rows(lg)
        except Exception as e:  # noqa: BLE001 — 한 리그 실패가 다른 리그를 막지 않게(파일은 그대로 둔다)
            print(f"  {lg:16} 실패: {type(e).__name__}: {e}")
            bad += 1
            continue
        df = pd.DataFrame(rows, columns=COLS).drop_duplicates(subset=["squad", "fotmob_id"])
        out = data_path("fotmob_injuries", lg, SEASON)
        prev = pd.read_csv(out, dtype={"fotmob_id": str}) if out.exists() else None
        df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        try:
            n_new = write_changes(lg, prev, df)
            if n_new:
                print(f"  {lg:16} 새 부상 {n_new}명 -> fotmob_injury_changes")
        except Exception as e:  # noqa: BLE001
            print(f"  {lg:16} 부상 변화 기록 실패 {type(e).__name__}: {e}")
        print(f"  {lg:16} 결장 {len(df)}명(부상 {int((df['kind'] == 'injury').sum())} · 경기 중 부상 교체 "
              f"{int((df['kind'] == 'in_match').sum())} · 그 밖 {int((~df['kind'].isin(['injury', 'in_match'])).sum())}) -> {out.name}")
        time.sleep(0.5)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
