"""
FotMob 경기 상세 → 라인업·교체 행(ESPN 라인업 표와 같은 열) — 라이트 리그용.

2026-10-22 1단계 리그 확장: ESPN 은 스위스 리그 26/27 을 아예 다루지 않고(이벤트 0건), 라이트 리그 일정의 경기 id 는 FotMob id 다.
예상 XI·포메이션·대회별 포메이션·라인업 짝(케미)·포지션 역할은 espn_lineups 표(squad·formation·starter·espn_pos·formation_place)를
읽으므로, fetch_fotmob_matches 가 이미 받는 matchDetails 의 lineup 으로 같은 열을 만든다(추가 요청 없음).
- espn_pos: FotMob 은 선수마다 판 위 좌표(verticalLayout: y = 깊이, x = 오른쪽 0 → 왼쪽 1)를 준다. 깊이로 줄을 나누고
  (포메이션 숫자 순 — 수비·미드·공격), 줄 안에서 오른쪽부터 ESPN 토큰(RB·CD-R·CM-L·RF …)을 붙인다 —
  team_analysis.espn_assign_slots 가 ESPN 라인업과 똑같이 슬롯을 정한다.
- 교체: matchFacts 이벤트 Substitution(swap = [들어온 선수, 나간 선수]).
"""
from __future__ import annotations

LINEUP_COLS = ["squad", "date", "opponent", "home_away", "formation", "starter", "jersey", "player", "espn_pos",
               "formation_place", "event_id"]
SUB_COLS = ["event_id", "home_away", "minute", "minute_sec", "player_in", "player_out"]

# 줄 크기 → 오른쪽부터 토큰(ESPN 표기 — team_analysis.ESPN_SLOT_CANDS)
TOKENS = {
    "D": {1: ["CD"], 2: ["CD-R", "CD-L"], 3: ["CD-R", "CD", "CD-L"], 4: ["RB", "CD-R", "CD-L", "LB"],
          5: ["RWB", "CD-R", "CD", "CD-L", "LWB"]},
    "DM": {1: ["DM"], 2: ["DM-R", "DM-L"], 3: ["DM-R", "DM", "DM-L"], 4: ["RM", "DM-R", "DM-L", "LM"],
           5: ["RM", "CM-R", "DM", "CM-L", "LM"]},
    "CM": {1: ["CM"], 2: ["CM-R", "CM-L"], 3: ["CM-R", "CM", "CM-L"], 4: ["RM", "CM-R", "CM-L", "LM"],
           5: ["RM", "CM-R", "CM", "CM-L", "LM"]},
    "AM": {1: ["AM"], 2: ["AM-R", "AM-L"], 3: ["AM-R", "AM", "AM-L"], 4: ["RM", "AM-R", "AM-L", "LM"]},
    "F": {1: ["F"], 2: ["CF-R", "CF-L"], 3: ["RF", "F", "LF"]},
}


def _xy(p: dict) -> tuple[float, float]:
    v = p.get("verticalLayout") or {}
    return float(v.get("y") or 0), float(v.get("x") or 0)


def tokens(starters: list[dict], formation: str) -> list[str]:
    """선발 11명(FotMob 순서) → ESPN 토큰(같은 순서). 포메이션 숫자와 줄 수가 안 맞으면 깊이로 줄을 나눈다."""
    out = ["SUB"] * len(starters)
    gk = [i for i, p in enumerate(starters) if int(p.get("positionId") or 0) == 11]
    if not gk and starters:
        gk = [min(range(len(starters)), key=lambda i: _xy(starters[i])[0])]
    for i in gk[:1]:
        out[i] = "G"
    rest = sorted((i for i in range(len(starters)) if i not in gk[:1]), key=lambda i: _xy(starters[i]))
    try:
        parts = [int(x) for x in str(formation or "").split("-") if x.strip()]
    except ValueError:
        parts = []
    if sum(parts) != len(rest):                      # 포메이션 정보가 없거나 어긋남 — 같은 깊이끼리 한 줄
        parts, cur, last = [], 0, None
        for i in rest:
            y = round(_xy(starters[i])[0], 2)
            if last is not None and abs(y - last) > 0.05:
                parts.append(cur)
                cur = 0
            cur, last = cur + 1, y
        if cur:
            parts.append(cur)
    lines, k = [], 0
    for n in parts:
        lines.append(rest[k:k + n])
        k += n
    n_lines = len(lines)
    mids = list(range(1, n_lines - 1))
    for li, line in enumerate(lines):
        if li == 0:
            kind = "D"
        elif li == n_lines - 1 and n_lines > 1:
            kind = "F"
        elif len(mids) >= 2 and li == mids[0]:
            kind = "DM"
        elif len(mids) >= 2 and li == mids[-1]:
            kind = "AM"
        else:
            kind = "CM"
        row = sorted(line, key=lambda i: _xy(starters[i])[1])          # 오른쪽(x 작음)부터
        toks = TOKENS[kind].get(len(row)) or TOKENS["CM"].get(len(row)) or ["CM"] * len(row)
        for i, t in zip(row, toks):
            out[i] = t
    return out


def lineup_rows(j: dict, match: dict, sides: dict) -> list[dict]:
    """우리 팀(sides 에 있는 FotMob 팀 id) 쪽 선발·벤치 행."""
    lu = ((j.get("content") or {}).get("lineup")) or {}
    day = str(((match.get("status") or {}).get("utcTime")) or "")[:10]
    names = {str((match.get(s) or {}).get("id")): (match.get(s) or {}).get("name") for s in ("home", "away")}
    rows = []
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team = lu.get(key) or {}
        tid = str(team.get("id") or (match.get(side) or {}).get("id") or "")
        if tid not in sides:
            continue
        squad = sides[tid][1]
        other = str((match.get("away" if side == "home" else "home") or {}).get("id"))
        opp = sides.get(other, (None, names.get(other)))[1]
        starters = team.get("starters") or []
        if len(starters) < 11:
            continue
        form = str(team.get("formation") or "")
        toks = tokens(starters, form)
        order = sorted(range(len(starters)), key=lambda i: (toks[i] != "G", _xy(starters[i])))
        place = {i: n + 1 for n, i in enumerate(order)}
        for i, p in enumerate(starters):
            rows.append({"squad": squad, "date": day, "opponent": opp, "home_away": side, "formation": form,
                         "starter": True, "jersey": p.get("shirtNumber"), "player": p.get("name"), "espn_pos": toks[i],
                         "formation_place": place[i], "event_id": str(match.get("id"))})
        for p in team.get("subs") or []:
            rows.append({"squad": squad, "date": day, "opponent": opp, "home_away": side, "formation": form,
                         "starter": False, "jersey": p.get("shirtNumber"), "player": p.get("name"), "espn_pos": "SUB",
                         "formation_place": None, "event_id": str(match.get("id"))})
    return rows


def sub_rows(j: dict, match: dict, sides: dict) -> list[dict]:
    ev = ((((j.get("content") or {}).get("matchFacts") or {}).get("events") or {}).get("events")) or []
    ids = {"home": str((match.get("home") or {}).get("id")), "away": str((match.get("away") or {}).get("id"))}
    out = []
    for e in ev:
        if e.get("type") != "Substitution":
            continue
        side = "home" if e.get("isHome") else "away"
        if ids[side] not in sides:
            continue
        sw = e.get("swap") or []
        t = e.get("time")
        out.append({"event_id": str(match.get("id")), "home_away": side, "minute": f"{t}'" if t is not None else "",
                    "minute_sec": float(t) * 60 if isinstance(t, (int, float)) else None,
                    "player_in": (sw[0] or {}).get("name") if len(sw) > 0 else "",
                    "player_out": (sw[1] or {}).get("name") if len(sw) > 1 else ""})
    return out
