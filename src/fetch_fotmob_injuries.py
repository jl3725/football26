"""
FotMob 결장자(부상·출장정지) → data/fotmob_injuries_{리그}_{시즌}.csv — Transfermarkt 보다 빠른 부상 명단.

2026-10-19 사용자: "에밀리아노 마르티네스가 턱 골절로 실려 나갔는데 부상자 목록에 없다". TM 부상 목록은 며칠 늦다.
FotMob 은 ① 다음 경기 상세(matchDetails)의 lineup.unavailable 에 결장자·복귀 예상('Early December 2026'·'Doubtful')을,
② 끝난 경기 이벤트에 '부상 교체'(Substitution · injuredPlayerOut)를 바로 올린다.
- ① 팀마다 가장 가까운 다가오는 리그 경기(10일 안) 하나 — 리그당 10경기 안팎 요청.
- ② 최근 4일 안 끝난 리그 경기의 부상 교체 — ①에 아직 없으면 '경기 중 부상 교체'로 남긴다.
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
    # ② 최근 끝난 경기의 부상 교체(다음 경기 명단에 아직 없는 선수만)
    for m in ms:
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
        df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        print(f"  {lg:16} 결장 {len(df)}명(부상 {int((df['kind'] == 'injury').sum())} · 경기 중 부상 교체 "
              f"{int((df['kind'] == 'in_match').sum())} · 그 밖 {int((~df['kind'].isin(['injury', 'in_match'])).sum())}) -> {out.name}")
        time.sleep(0.5)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
