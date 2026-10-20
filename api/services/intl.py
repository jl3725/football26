"""국가대표(INTERNATIONAL) — A매치 기간·소집 명단을 팀 화면과 예측에 잇는다(src/fetch_intl.py 산출물).

- team_payload: 팀의 다음(또는 진행 중) A매치 기간, 그 기간 소집 선수(명단 발표 전이면 지난 기간 명단) + 대표팀 경기
- tournament_absent: 리그가 계속되는 국가대표 대회(아시안컵 등) 기간의 클럽 경기 → 소집 선수를 결장으로(예측 결장 손실)
- returnees: A매치 기간 직후 첫 클럽 경기 — 돌아오는 선수 수·유럽 밖 대표팀 수(예측 화면 참고 표시, 확률엔 안 넣음)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

import api.bootstrap  # noqa: F401
import fetch_intl as fi
import player_registry as preg

DATA = Path(api.bootstrap.ROOT) / "data"
_CACHE: dict[str, tuple[str, object]] = {}   # 파일 이름 → (수정 시각 키, 값)


def _load(name: str):
    p = DATA / name
    if not p.exists():
        return None
    key = f"{name}:{p.stat().st_mtime}"
    hit = _CACHE.get(name)
    if hit and hit[0] == key:
        return hit[1]
    if name.endswith(".json"):
        val = json.loads(p.read_text(encoding="utf-8")).get("windows", [])
    else:
        val = pd.read_csv(p)
    _CACHE[name] = (key, val)  # type: ignore[assignment]
    return val


def windows() -> list[dict]:
    return _load("intl_windows.json") or []


def callups() -> pd.DataFrame:
    c = _load("intl_callups.csv")
    return c if c is not None else pd.DataFrame(columns=["our_squad", "our_league", "our_player", "squad_for"])


def matches() -> pd.DataFrame:
    m = _load("intl_matches.csv")
    return m if m is not None else pd.DataFrame(columns=["date", "home", "away", "comp_code", "state", "hg", "ag"])


def _target(today: dt.date) -> tuple[dict | None, dict | None, str]:
    """(대상 기간: 진행 중 > 다음, 지난 기간, 상태 now·upcoming·none)."""
    t = today.isoformat()
    ws = windows()
    cur = next((w for w in ws if w["start"] <= t <= w["end"]), None)
    nxt = next((w for w in ws if w["start"] > t), None)
    last = next((w for w in reversed(ws) if w["end"] < t), None)
    if cur:
        return cur, last, "now"
    return nxt, last, ("upcoming" if nxt else "none")


def _nation_fixtures(nation: str, w: dict | None) -> list[dict]:
    if not w:
        return []
    m = matches()
    keys = fi.nation_keys(nation)
    m = m[(m["date"] >= w["first_match"]) & (m["date"] <= w["end"])]
    out = []
    for r in m.itertuples():
        hk, ak = preg.norm(r.home), preg.norm(r.away)
        if hk in keys or ak in keys:
            home = hk in keys
            # 그 나라 기준 스코어(우리 - 상대)
            score = None if r.state == "pre" or pd.isna(r.hg) else (
                f"{int(r.hg)}-{int(r.ag)}" if home else f"{int(r.ag)}-{int(r.hg)}")
            out.append({"date": r.date, "opp": r.away if home else r.home, "home": home, "comp": r.comp_code,
                        "score": score})
    return out


def _in(squad_for, lo: str, hi: str) -> bool:
    return isinstance(squad_for, str) and lo <= squad_for <= hi


def team_payload(team: str, league: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    w, last, state = _target(today)
    c = callups()
    c = c[(c["our_squad"] == team) & (c["our_league"] == league)]
    squad_state, rows = "none", c.iloc[0:0]
    if w is not None:
        now_rows = c[c["squad_for"].astype(str) >= w["first_match"]]
        if len(now_rows):
            squad_state, rows = "announced", now_rows
        elif last is not None:
            hi = (dt.date.fromisoformat(last["end"]) + dt.timedelta(days=2)).isoformat()
            prev = c[c["squad_for"].map(lambda x: _in(x, last["start"], hi))]
            if len(prev):
                squad_state, rows = "previous", prev
    players = []
    for r in rows.sort_values(["nation", "caps"], ascending=[True, False]).itertuples():
        conf = r.nation_conf if isinstance(r.nation_conf, str) else ""
        players.append({"player": r.our_player, "nation": r.nation, "conf": conf, "flag": r.flag if isinstance(r.flag, str) else "",
                        "fifa_rank": None if pd.isna(r.fifa_rank) else int(r.fifa_rank),
                        "caps": None if pd.isna(r.caps) else int(r.caps), "goals": None if pd.isna(r.goals) else int(r.goals),
                        "pos": r.pos if isinstance(r.pos, str) else "", "squad_for": r.squad_for,
                        "far": bool(conf) and conf != "UEFA",
                        # 대상 기간 대표팀 경기(명단 발표 전이어도 일정은 나와 있다) · 지난 명단이면 그때 결과도
                        "fixtures": _nation_fixtures(r.nation, w),
                        "last_results": _nation_fixtures(r.nation, last) if squad_state == "previous" else []})
    days_to = (dt.date.fromisoformat(w["start"]) - today).days if w else None
    return {"window": w, "state": state, "days_to": days_to, "last_window": last, "squad_state": squad_state,
            "players": players, "summary": {"n": len(players), "far": sum(p["far"] for p in players),
                                            "nations": len({p["nation"] for p in players})}}


def in_tournament(on: str | None) -> bool:
    return bool(on) and any(w.get("kind") == "tournament" and w["start"] <= on <= w["end"] for w in windows())


def tournament_absent(league: str, on: str | None) -> set[tuple[str, str]]:
    """리그가 계속되는 대표팀 대회 기간의 날짜 on → {(클럽, 정규화 이름)} 소집으로 빠지는 선수.
    나라가 대회 일정을 다 마쳤으면(마지막 경기 + 3일 지남) 돌아온 것으로 본다."""
    if not on:
        return set()
    ws = [w for w in windows() if w.get("kind") == "tournament" and w["start"] <= on <= w["end"]]
    if not ws:
        return set()
    w = ws[0]
    c = callups()
    c = c[(c["our_league"] == league) & c["squad_for"].map(lambda x: _in(x, w["start"], w["end"]))]
    m = matches()
    m = m[(m["date"] >= w["first_match"]) & (m["date"] <= w["end"])]
    out = set()
    for r in c.itertuples():
        keys = fi.nation_keys(r.nation)
        mine = m[[preg.norm(h) in keys or preg.norm(a) in keys for h, a in zip(m["home"], m["away"])]]
        if len(mine) and (mine["state"] == "post").all():
            back = (dt.date.fromisoformat(str(mine["date"].max())) + dt.timedelta(days=3)).isoformat()
            if on > back:
                continue
        import positions as ps  # noqa: PLC0415
        out.add((str(r.our_squad), ps.norm_name(r.our_player)))
    return out


def returnees(team: str, league: str, on: str | None) -> dict | None:
    """on 이 A매치 휴식기 끝난 뒤 7일 안 첫 경기면 {n, far} — 그 기간 소집됐다 돌아오는 선수."""
    if not on:
        return None
    w = next((w for w in windows() if w.get("kind") == "break" and w["end"] < on
              <= (dt.date.fromisoformat(w["end"]) + dt.timedelta(days=7)).isoformat()), None)
    if not w:
        return None
    c = callups()
    c = c[(c["our_squad"] == team) & (c["our_league"] == league)
          & c["squad_for"].map(lambda x: _in(x, w["first_match"], w["end"]))]
    if c.empty:
        return None
    return {"n": int(len(c)), "far": int(sum(isinstance(x, str) and x and x != "UEFA" for x in c["nation_conf"])),
            "window_end": w["end"]}
