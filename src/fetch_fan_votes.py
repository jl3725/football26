"""
팬 승부 예측 투표 — Sofascore 앱 사용자들의 '누가 이길까?' 투표(홈·무·원정), 양 팀 득점(BTTS), 선제골 팀 투표.

앞으로 10일 안의 경기만(8개 리그 + 챔스·유로파·컨퍼런스). 홈 화면·매치 프리뷰에서 '팬 예측'으로 보여 준다.
로컬 전용 — Sofascore 는 GH 러너에서 막혀 있어(sofascore_client 참고) run_tm_agent.ps1 가 하루 두 번 돌린다.
출력: data/fan_votes.csv (시즌 무관 · 매번 새로 씀)

    python src/fetch_fan_votes.py
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402
from sofascore_client import close, get_json  # noqa: E402
import team_names  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "fan_votes.csv"
DAYS = 10
KST = dt.timezone(dt.timedelta(hours=9))
TOURNAMENTS = {17: "EPL", 8: "LaLiga", 23: "SerieA", 35: "Bundesliga", 34: "Ligue1", 238: "LigaPortugal",
               37: "Eredivisie", 38: "BelgianProLeague", 7: "UCL", 679: "UEL", 17015: "UECL"}


def _our_teams() -> list[str]:
    teams: set[str] = set()
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if p.exists():
            teams |= set(pd.read_csv(p)["squad"].astype(str))
    return sorted(teams)


def _get(path: str, tries: int = 3):
    """연결이 끊기면(Sofascore 가 자주 끊는다) 브라우저를 다시 열어 재시도 — 한 경기 실패가 전체를 멈추지 않게."""
    for i in range(tries):
        try:
            st, d = get_json(path)
        except Exception as e:  # noqa: BLE001
            print(f"[fan_votes] 연결 오류({i + 1}/{tries}) {path}: {type(e).__name__}", flush=True)
            close()
            time.sleep(4 * (i + 1))
            continue
        if st == 200:
            return d
        time.sleep(1.5 * (i + 1))
    return None


def main() -> int:
    ours = _our_teams()
    now = time.time()
    rows = []
    for ut, comp in TOURNAMENTS.items():
        seasons = _get(f"/unique-tournament/{ut}/seasons")
        if not seasons or not seasons.get("seasons"):
            print(f"[fan_votes] {comp}: 시즌 없음")
            continue
        sid = seasons["seasons"][0]["id"]
        events = []
        for page in range(2):
            d = _get(f"/unique-tournament/{ut}/season/{sid}/events/next/{page}")
            events += (d or {}).get("events", [])
            if not d or not d.get("hasNextPage"):
                break
        n = 0
        for e in events:
            ts = e.get("startTimestamp") or 0
            if not (now <= ts <= now + DAYS * 86400):
                continue
            v = _get(f"/event/{e['id']}/votes")
            if not v:
                continue
            vote = v.get("vote") or {}
            btts = v.get("bothTeamsToScoreVote") or {}
            first = v.get("firstTeamToScoreVote") or {}
            hn, an = e["homeTeam"]["name"], e["awayTeam"]["name"]
            rows.append({
                "sofascore_id": e["id"], "comp": comp,
                "date": dt.datetime.fromtimestamp(ts, KST).date().isoformat(),
                "kickoff": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                "home": team_names.best(hn, ours) or hn, "away": team_names.best(an, ours) or an,
                "home_src": hn, "away_src": an,
                "vote_home": int(vote.get("vote1") or 0), "vote_draw": int(vote.get("voteX") or 0), "vote_away": int(vote.get("vote2") or 0),
                "btts_yes": int(btts.get("voteYes") or 0), "btts_no": int(btts.get("voteNo") or 0),
                "first_home": int(first.get("voteHome") or 0), "first_none": int(first.get("voteNoGoal") or 0),
                "first_away": int(first.get("voteAway") or 0),
                "fetched_at": dt.datetime.now(KST).isoformat(timespec="minutes"),
            })
            n += 1
            time.sleep(0.4)
        print(f"[fan_votes] {comp}: {n}경기")
    close()
    if not rows:
        print("[fan_votes] 수집 0건 — 기존 파일 유지")
        return 1
    pd.DataFrame(rows).sort_values(["date", "comp"]).to_csv(OUT, index=False)
    print(f"[OK] {OUT.name} · {len(rows)}경기")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
