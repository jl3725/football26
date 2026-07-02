"""2026 FIFA 월드컵 데이터 수집 — ESPN(fifa.world) 무료 API.

한 번의 scoreboard 쿼리로 전 경기(그룹+녹아웃)를 받아 매치·득점왕·조별순위를 만들고,
teams+roster 로 48개국 스쿼드를 받는다. 위키 불필요. EPL 라인업/뉴스에 이미 쓰는 API.

산출 (data/):
  wc_matches.csv  — date, round, group, home/away(+abbr,logo,score), status, completed
  wc_scorers.csv  — player, nation, goals, penalties  (득점왕)
  wc_groups.csv   — group, team, P/W/D/L/GF/GA/GD/Pts (조별 최종순위)
  wc_squads.csv   — nation, player, pos, jersey, age   (팀별 스쿼드)

사용:
    python src/fetch_wc.py
    python src/fetch_wc.py --no-squads          # 스쿼드(48 요청) 건너뜀
    python src/fetch_wc.py --dates 20260601-20260720
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "football26/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def _logo(team: dict) -> str:
    lg = team.get("logo") or ""
    if lg:
        return lg
    logos = team.get("logos") or []
    return logos[0].get("href", "") if logos else ""


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def fetch_scoreboard(dates: str) -> list[dict]:
    d = _get(f"{BASE}/scoreboard?dates={dates}&limit=400")
    return d.get("events", [])


def parse_matches(events: list[dict]):
    """→ (matches, scorers, group_standings)."""
    matches = []
    goals: dict = defaultdict(lambda: {"player": "", "nation": "", "goals": 0, "pens": 0})
    grp: dict = defaultdict(lambda: {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0,
                                     "team": "", "abbr": "", "logo": "", "group": ""})

    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        rnd = e.get("season", {}).get("slug", "")
        note = comp.get("altGameNote") or ""
        gm = re.search(r"Group\s+([A-L])", note)
        group = gm.group(1) if gm else ""
        status = comp.get("status", {}).get("type", {})
        completed = bool(status.get("completed"))
        comps = comp.get("competitors", [])
        home = next((c for c in comps if c.get("homeAway") == "home"), None)
        away = next((c for c in comps if c.get("homeAway") == "away"), None)
        if not home or not away:
            comps = comps + [{}, {}]
            home, away = comps[0], comps[1]
        ht, at = home.get("team", {}), away.get("team", {})

        def _sc(c):
            try:
                return int(c.get("score"))
            except (TypeError, ValueError):
                return None
        hs, as_ = _sc(home), _sc(away)
        matches.append({
            "date": (e.get("date") or "")[:10], "round": rnd, "group": group,
            "home": ht.get("displayName", ""), "home_abbr": ht.get("abbreviation", ""),
            "home_logo": _logo(ht), "home_score": "" if hs is None else hs,
            "away": at.get("displayName", ""), "away_abbr": at.get("abbreviation", ""),
            "away_logo": _logo(at), "away_score": "" if as_ is None else as_,
            "status": status.get("shortDetail") or status.get("description") or "",
            "completed": completed,
        })

        # 득점왕 — 골 상세
        for det in comp.get("details", []):
            if not det.get("scoringPlay") or det.get("ownGoal"):
                continue
            ath = det.get("athletesInvolved") or []
            if not ath:
                continue
            pid = str(ath[0].get("id") or ath[0].get("displayName"))
            tid = str(det.get("team", {}).get("id") or "")
            nation = ht.get("displayName") if tid == str(ht.get("id")) else at.get("displayName")
            g = goals[pid]
            g["player"] = ath[0].get("displayName", "")
            g["nation"] = nation or g["nation"]
            g["goals"] += 1
            if det.get("penaltyKick"):
                g["pens"] += 1

        # 조별 순위 — 그룹스테이지 완료 경기로 집계
        if group and completed and hs is not None and as_ is not None:
            for c, team, gf, ga in ((home, ht, hs, as_), (away, at, as_, hs)):
                key = (group, str(team.get("id")))
                row = grp[key]
                row.update(group=group, team=team.get("displayName", ""),
                           abbr=team.get("abbreviation", ""), logo=_logo(team))
                row["P"] += 1; row["GF"] += gf; row["GA"] += ga
                if gf > ga:
                    row["W"] += 1; row["Pts"] += 3
                elif gf == ga:
                    row["D"] += 1; row["Pts"] += 1
                else:
                    row["L"] += 1

    scorers = sorted(goals.values(), key=lambda x: (-x["goals"], -x["pens"]))
    scorers = [s for s in scorers if s["goals"] > 0]
    groups = []
    for row in grp.values():
        row["GD"] = row["GF"] - row["GA"]
        groups.append(row)
    groups.sort(key=lambda r: (r["group"], -r["Pts"], -r["GD"], -r["GF"]))
    return matches, scorers, groups


def fetch_squads(sleep: float = 0.15) -> list[dict]:
    d = _get(f"{BASE}/teams")
    teams = d.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    out = []
    for i, t in enumerate(teams):
        tm = t.get("team", {})
        tid = tm.get("id")
        nation = tm.get("displayName", "")
        try:
            r = _get(f"{BASE}/teams/{tid}/roster")
        except Exception as exc:
            print(f"    [roster 실패] {nation}: {exc}", file=sys.stderr)
            continue
        for a in r.get("athletes", []):
            pos = (a.get("position") or {}).get("abbreviation", "")
            out.append({
                "nation": nation, "nation_id": tid, "nation_abbr": tm.get("abbreviation", ""),
                "player": a.get("fullName") or a.get("displayName", ""),
                "player_id": a.get("id", ""), "pos": pos, "jersey": a.get("jersey", ""),
                "age": a.get("age", ""),
            })
        if (i + 1) % 12 == 0:
            print(f"    squads {i + 1}/{len(teams)}…")
        time.sleep(sleep)
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", default="20260601-20260720")
    ap.add_argument("--no-squads", action="store_true")
    args = ap.parse_args(argv)

    events = fetch_scoreboard(args.dates)
    if not events:
        print("[wc] scoreboard 비어있음 — 중단", file=sys.stderr)
        return 1
    matches, scorers, groups = parse_matches(events)
    _write(DATA / "wc_matches.csv",
           ["date", "round", "group", "home", "home_abbr", "home_logo", "home_score",
            "away", "away_abbr", "away_logo", "away_score", "status", "completed"], matches)
    _write(DATA / "wc_scorers.csv", ["player", "nation", "goals", "pens"], scorers)
    _write(DATA / "wc_groups.csv",
           ["group", "team", "abbr", "logo", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"], groups)
    print(f"[wc] matches {len(matches)} · scorers {len(scorers)} · group-rows {len(groups)}")

    if not args.no_squads:
        squads = fetch_squads()
        _write(DATA / "wc_squads.csv",
               ["nation", "nation_id", "nation_abbr", "player", "player_id", "pos", "jersey", "age"], squads)
        print(f"[wc] squads {len(squads)} (48개국)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
