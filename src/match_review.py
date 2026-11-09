"""
경기 리뷰(Match Review) — ESPN 경기 상세(summary)로 규칙 기반 리포트를 만든다(유료 AI 없음).

입력: ESPN /summary JSON(keyEvents 득점·카드·페널티, boxscore 팀 기록, gameInfo 경기장·관중)
      + 우리 쪽 맥락(팀 표기·로고·색, 경기 전 팬 투표·Elo 기준 예측).
출력: 헤드라인 · 요약 문장 · 득점 타임라인 · 카드 · 실축 페널티 · 기록 비교 · 스타 플레이어 · 예측 적중.
숫자는 모두 ESPN 원자료 그대로 인용한다(지어내지 않음). 진행 중 경기면 '현재까지' 기준.
"""
from __future__ import annotations

import re

STATS = [  # (ESPN 이름, 화면 라벨, 표시 형식)
    ("possessionPct", "점유율", "pct"), ("totalShots", "슈팅", "int"), ("shotsOnTarget", "유효 슈팅", "int"),
    ("wonCorners", "코너킥", "int"), ("saves", "선방", "int"), ("passPct", "패스 성공률", "ratio"),
    ("foulsCommitted", "파울", "int"), ("offsides", "오프사이드", "int"), ("interceptions", "인터셉트", "int"),
]


def _num(v) -> float:
    try:
        return float(str(v).replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def _minute(clock: str) -> int:
    """'45'+3'' → 48, '90'' → 90 (정렬·전반 판단용)."""
    m = re.findall(r"\d+", str(clock or ""))
    return sum(int(x) for x in m[:2]) if m else 0


def parse(summary: dict, home_espn_id: str | None = None) -> dict:
    """ESPN summary → 사건·기록(우리 표기 붙이기 전)."""
    comp = (summary.get("header", {}).get("competitions") or [{}])[0]
    status = comp.get("status", {}).get("type", {})
    teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    hid = str((teams.get("home") or {}).get("team", {}).get("id") or home_espn_id or "")
    goals, cards, pens = [], [], []
    for e in summary.get("keyEvents", []):
        typ = str(e.get("type", {}).get("text") or "")
        side = "home" if str(e.get("team", {}).get("id") or "") == hid else "away"
        clock = e.get("clock", {}).get("displayValue") or ""
        ps = [p.get("athlete", {}).get("displayName") for p in e.get("participants", [])]
        if typ.startswith("Goal") or typ in ("Penalty - Scored", "Own Goal"):
            kind = "pen" if "Penalty" in typ else "og" if "Own" in typ else "header" if "Header" in typ else ""
            goals.append({"minute": clock, "m": _minute(clock), "side": side, "scorer": ps[0] if ps else "",
                          "assist": ps[1] if len(ps) > 1 and kind != "pen" else "", "kind": kind})
        elif typ in ("Yellow Card", "Red Card", "Second Yellow Card") or "Red Card" in typ:
            cards.append({"minute": clock, "m": _minute(clock), "side": side, "player": ps[0] if ps else "",
                          "color": "yellow" if typ == "Yellow Card" else "red"})
        elif typ.startswith("Penalty") and ("Saved" in typ or "Missed" in typ):
            pens.append({"minute": clock, "m": _minute(clock), "side": side, "player": ps[0] if ps else "",
                         "result": "saved" if "Saved" in typ else "missed"})
    stats = {}
    for t in summary.get("boxscore", {}).get("teams", []):
        side = "home" if str(t.get("team", {}).get("id") or "") == hid else "away"
        for s in t.get("statistics", []):
            stats.setdefault(s.get("name"), {})[side] = s.get("displayValue")
    gi = summary.get("gameInfo", {})
    score = {k: int(_num((teams.get(k) or {}).get("score"))) for k in ("home", "away")}
    return {"state": status.get("state", "pre"), "detail": status.get("shortDetail") or status.get("detail") or "",
            "score": score, "goals": sorted(goals, key=lambda g: g["m"]), "cards": cards, "pens": pens, "stats": stats,
            "venue": (gi.get("venue") or {}).get("fullName", ""), "attendance": gi.get("attendance")}


# FotMob 경기 상세 기록 → ESPN 이름(STATS 키). ESPN 이 없는 리그(스위스 — 2026-11-02 AI 경기 리포트 대상 6경기가 매번
# 'no review' 로 실패)는 FotMob matchDetails 로 같은 꼴을 만든다
_FM_STATS = {"BallPossesion": "possessionPct", "total_shots": "totalShots", "ShotsOnTarget": "shotsOnTarget",
             "corners": "wonCorners", "keeper_saves": "saves", "accurate_passes": "passPct", "fouls": "foulsCommitted",
             "Offsides": "offsides", "interceptions": "interceptions"}


def _fm_minute(e: dict) -> tuple[str, int]:
    t, ov = int(_num(e.get("time"))), int(_num(e.get("overloadTime")))
    return (f"{t}'+{ov}'" if ov else f"{t}'"), t + ov


def parse_fotmob(details: dict) -> dict:
    """FotMob matchDetails → parse() 와 같은 꼴(사건·기록). 득점 쪽은 바뀐 점수(newScore)로 정한다 — 자책골도 득점한 팀 기준."""
    hdr = details.get("header") or {}
    st = hdr.get("status") or {}
    teams = (hdr.get("teams") or []) + [{}, {}]
    state = "post" if st.get("finished") else "in" if st.get("started") and not st.get("cancelled") else "pre"
    if state == "post":
        detail = (st.get("reason") or {}).get("short") or "FT"
    else:
        detail = str((st.get("liveTime") or {}).get("short") or "").replace("\u200e", "").replace("’", "'")
    content = details.get("content") or {}
    mf = content.get("matchFacts") or {}
    goals, cards = [], []
    prev = (0, 0)
    for e in ((mf.get("events") or {}).get("events") or []):
        if e.get("isPenaltyShootoutEvent"):
            continue
        typ = e.get("type")
        minute, m = _fm_minute(e)
        name = str(e.get("nameStr") or (e.get("player") or {}).get("name") or "")
        if typ == "Goal":
            ns = e.get("newScore") or [e.get("homeScore"), e.get("awayScore")]
            cur = (int(_num(ns[0])), int(_num(ns[1]))) if ns and len(ns) == 2 else prev
            side = "home" if cur[0] > prev[0] else "away" if cur[1] > prev[1] else ("home" if e.get("isHome") else "away")
            prev = cur
            desc = str(e.get("goalDescriptionKey") or e.get("goalDescription") or "").lower()
            kind = ("og" if e.get("ownGoal") else "pen" if "penalty" in desc or e.get("suffix") == "Pen"
                    else "header" if "header" in desc else "")
            assist = re.sub(r"^assist by\s+", "", str(e.get("assistStr") or ""), flags=re.I).strip()
            goals.append({"minute": minute, "m": m, "side": side, "scorer": name,
                          "assist": "" if kind == "pen" else assist, "kind": kind})
        elif typ == "Card" and e.get("card"):
            cards.append({"minute": minute, "m": m, "side": "home" if e.get("isHome") else "away", "player": name,
                          "color": "yellow" if e.get("card") == "Yellow" else "red"})
    hid = teams[0].get("id")
    pens = []
    for s in ((content.get("shotmap") or {}).get("shots") or []):      # 실축·선방 페널티(득점한 페널티는 위 득점)
        if s.get("situation") == "Penalty" and s.get("eventType") != "Goal":
            mn = int(_num(s.get("min")))
            pens.append({"minute": f"{mn}'", "m": mn + int(_num(s.get("minAdded"))),
                         "side": "home" if s.get("teamId") == hid else "away", "player": str(s.get("playerName") or ""),
                         "result": "saved" if s.get("eventType") == "AttemptSaved" else "missed"})
    stats: dict = {}
    for grp in ((((content.get("stats") or {}).get("Periods") or {}).get("All") or {}).get("stats") or []):
        for s in grp.get("stats") or []:
            key = _FM_STATS.get(str(s.get("key")))
            vals = s.get("stats") or []
            if not key or key in stats or len(vals) != 2 or vals[0] is None or vals[1] is None:
                continue
            if key == "passPct":          # '298 (79%)' → 0.79(ESPN passPct 와 같은 비율)
                ms = [re.search(r"\((\d+)%\)", str(v)) for v in vals]
                if not all(ms):
                    continue
                vals = [_num(x.group(1)) / 100 for x in ms]
            stats[key] = {"home": vals[0], "away": vals[1]}
    info = mf.get("infoBox") or {}
    return {"state": state, "detail": detail,
            "score": {"home": int(_num(teams[0].get("score"))), "away": int(_num(teams[1].get("score")))},
            "goals": sorted(goals, key=lambda g: g["m"]), "cards": cards, "pens": pens, "stats": stats,
            "venue": (info.get("Stadium") or {}).get("name", ""), "attendance": info.get("Attendance")}


XG_EDGE = 0.4      # xG 차이가 이만큼은 돼야 '내용 우세'


def _context_lines(lines: list[str], ctx: dict, name: dict, win: str | None, lose: str | None) -> list[str]:
    """우리 데이터 맥락 줄 — 이변(맨 앞)·xG 흐름·평점 1위·연승/무승·주요 결장. 이름 바로 뒤 조사는 붙이지 않는다."""
    out = list(lines)
    if ctx.get("shock"):
        out.insert(0, f"이변 — {ctx['shock']}")
    xg = ctx.get("xg") or {}
    if xg.get("home") is not None and xg.get("away") is not None:
        xh, xa = float(xg["home"]), float(xg["away"])
        lead = "home" if xh >= xa + XG_EDGE else "away" if xa >= xh + XG_EDGE else None
        if lead is None:
            word = "내용은 팽팽"
        elif win and lead == win:
            word = f"내용대로 {name[lead]} 우세"
        else:
            word = f"내용은 {name[lead]} 우세"
        out.append(f"xG {xh:.1f}–{xa:.1f} · {word}")
    top = ctx.get("top")
    if top and top.get("rating"):
        out.append(f"평점 1위 {top['player']}({top['team']}) {float(top['rating']):.1f} · FotMob")
    for side in ("home", "away"):
        f = (ctx.get("form") or {}).get(side) or {}
        if f.get("streak"):
            out.append(f"{name[side]} {f['streak']}" + (f" · 리그 {f['rank']}위" if f.get("rank") else ""))
    for side in ("home", "away"):
        miss = (ctx.get("absent") or {}).get(side) or []
        if miss:
            out.append(f"{name[side]} 결장 — {', '.join(miss[:3])}")
    return out


def build(p: dict, home: str, away: str, fans: dict | None = None, elo: dict | None = None,
          model: dict | None = None, ctx: dict | None = None) -> dict:
    """사건·기록 → 화면용 리뷰(한국어 문장). ctx(우리 데이터 — api _review_ctx): shock(이변 한 줄)·xg{home, away}·
    top{player, team, rating}·form{home|away: {streak, rank}}·absent{home|away: [이름]}.
    2026-11-09 사용자 — 요약에 '모델·팬 투표 예측 적중/빗나감' 대신 경기 자체의 중요한 요소를. 예측 적중은 predictions 칸에만."""
    ctx = ctx or {}
    hs, as_ = p["score"]["home"], p["score"]["away"]
    live = p["state"] == "in"
    name = {"home": home, "away": away}
    win = "home" if hs > as_ else "away" if as_ > hs else None
    lose = {"home": "away", "away": "home"}.get(win or "", None)

    # 흐름 — 역전 여부(최대 몇 골 차까지 끌려갔나), 전반 스코어, 결승골
    h = a = 0
    deficit = {"home": 0, "away": 0}
    for g in p["goals"]:
        if g["side"] == "home":
            h += 1
        else:
            a += 1
        deficit["home"] = max(deficit["home"], a - h)
        deficit["away"] = max(deficit["away"], h - a)
    trailed = {s: deficit[s] > 0 for s in deficit}
    first_half = lambda g: g["m"] <= 45 or g["minute"].startswith("45'")  # noqa: E731 — '45'+3'' 은 전반 추가시간
    ht = {s: sum(1 for g in p["goals"] if g["side"] == s and first_half(g)) for s in ("home", "away")}
    decisive = None
    if win:
        n_l = hs if win == "away" else as_
        cnt = 0
        for g in p["goals"]:
            if g["side"] == win:
                cnt += 1
                if cnt == n_l + 1:
                    decisive = g
                    break

    # 헤드라인
    margin = abs(hs - as_)
    if win is None:
        head = f"{home}·{away} {hs}-{as_} 무승부" if not live else f"{home} {hs}-{as_} {away} 진행 중"
    else:
        venue_word = "원정에서" if win == "away" else "홈에서"
        late = bool(decisive and decisive["m"] >= 85 and margin == 1)
        how = ("극장 역전승" if late and trailed[win] else "역전승" if trailed[win] else "극장골 승리" if late
               else "대승" if margin >= 3 else "완승" if margin == 2 else "신승")
        head = (f"{name[win]}, {venue_word} {max(hs, as_)}-{min(hs, as_)} {how}" if not live
                else f"{name[win]} {max(hs, as_)}-{min(hs, as_)} 리드 중 ({p['detail']})")

    # 문장은 팀·선수 이름 바로 뒤에 조사를 붙이지 않는다(외국 이름은 받침을 알 수 없어 'Kane가' 같은 오류가 난다)
    lines: list[str] = []
    other = {"home": "away", "away": "home"}
    # 전반 흐름
    if p["goals"]:
        if ht["home"] != ht["away"] and (ht["home"] + ht["away"]) >= 2:
            lead = "home" if ht["home"] > ht["away"] else "away"
            lines.append(f"전반은 {name[lead]} {max(ht['home'], ht['away'])}-{min(ht['home'], ht['away'])} 리드로 끝났다.")
        elif ht["home"] == ht["away"] == 0 and hs + as_ > 0 and not live:
            lines.append("전반은 0-0, 골은 모두 후반에 나왔다.")
    if win and trailed[win] and not live:
        # 선제골을 넣고도 한때 뒤졌다 뒤집은 경기(취리히 5-3, 2026-11-02)를 '선제골을 내주고도'로 쓰지 않게 첫 골 쪽을 본다
        conceded_first = bool(p["goals"]) and p["goals"][0]["side"] != win
        lines.append(f"{name[win]}, {deficit[win]}골 차로 끌려가다 뒤집었다." if deficit[win] >= 2
                     else f"{name[win]}, 선제골을 내주고도 뒤집었다." if conceded_first
                     else f"{name[win]}, 한때 리드를 내줬지만 다시 뒤집었다.")
    elif win is None and not live:
        for s in ("home", "away"):
            if deficit[s] >= 2:
                lines.append(f"{name[s]}, {deficit[s]}골 차를 따라잡아 승점 1을 챙겼다.")
    if decisive and margin <= 2:   # 대승이면 결승골이 의미 없다
        if decisive["kind"] == "og":   # 자책골이면 득점자는 상대 선수 — '결승골은 72' Travassos'로 보이면 안 된다(2026-10-20 점검)
            lines.append(f"결승골은 {decisive['minute']} {name[other[decisive['side']]]} {decisive['scorer']}의 자책골.")
        else:
            lines.append(f"결승골은 {decisive['minute']} {decisive['scorer']}" + (f"(도움 {decisive['assist']})" if decisive["assist"] else "")
                         + (" 페널티킥" if decisive["kind"] == "pen" else "") + ".")
    # 득점자 묶기(멀티골 강조)
    by: dict[tuple, list] = {}
    for g in p["goals"]:
        if g["kind"] != "og":
            by.setdefault((g["side"], g["scorer"]), []).append(g["minute"])
    for (s, n), ms in by.items():
        if len(ms) >= 2:
            word = "해트트릭" if len(ms) == 3 else f"{len(ms)}골"
            lines.append(f"{word} — {n}({name[s]}) {', '.join(ms)}")
    # 기록 대비 결과 — 진 팀이 슈팅에서 앞섰을 때 유효 슈팅까지 앞섰는지에 따라 문장이 다르다
    st = p["stats"]
    pos = {k: _num(v) for k, v in (st.get("possessionPct") or {}).items()}
    sh = {k: int(_num(v)) for k, v in (st.get("totalShots") or {}).items()}
    sot = {k: int(_num(v)) for k, v in (st.get("shotsOnTarget") or {}).items()}
    if win and sh.get(lose, 0) > sh.get(win, 0):
        more = [f"슈팅 {sh.get(lose, 0)}-{sh.get(win, 0)}"]
        if pos.get(lose, 0) > pos.get(win, 0):
            more.insert(0, f"점유율 {pos.get(lose, 0):.0f}%")
        if sot.get(lose, 0) > sot.get(win, 0):
            more.append(f"유효 슈팅 {sot.get(lose, 0)}-{sot.get(win, 0)}")
            lines.append(f"{name[lose]}, {'·'.join(more)}로 앞서고도 졌다 — {name[win]}의 효율이 빛났다.")
        else:
            lines.append(f"{name[lose]}, {'·'.join(more)}로 앞섰지만 유효 슈팅은 {sot.get(lose, 0)}-{sot.get(win, 0)}로 밀렸다.")
    elif win and sh.get(win, 0) >= sh.get(lose, 0) + 5:
        lines.append(f"슈팅 {sh.get(win, 0)}-{sh.get(lose, 0)} · 유효 슈팅 {sot.get(win, 0)}-{sot.get(lose, 0)}, 내용에서도 {name[win]} 압도.")
    elif win is None and sh:
        lead = max(sh, key=sh.get)
        if sh[lead] >= sh.get(other[lead], 0) + 5:
            lines.append(f"{name[lead]}, 슈팅 {sh[lead]}-{sh.get(other[lead], 0)}로 몰아붙였지만 승부를 내지 못했다.")
    # 결정적 장면
    for pn in p["pens"]:
        lines.append(f"{pn['minute']} {name[pn['side']]} {pn['player']} 페널티킥 " + ("선방에 막힘." if pn["result"] == "saved" else "실축."))
    for c in p["cards"]:
        if c["color"] == "red":
            lines.append(f"{c['minute']} {name[c['side']]} {c['player']} 퇴장.")

    # 예측 적중
    pred = []
    outcome = "h" if win == "home" else "a" if win == "away" else "d"
    for label, v in (("팬 투표", fans), ("모델", model), ("Elo", elo)):
        if not v:
            continue
        pick = max(("h", "d", "a"), key=lambda k: v.get(k) or 0)
        word = {"h": f"{home} 승", "d": "무승부", "a": f"{away} 승"}[pick]
        pred.append({"source": label, "pick": word, "p": round(float(v.get(pick) or 0), 3), "hit": (pick == outcome) and not live})
    if not live:
        lines = _context_lines(lines, ctx, name, win, lose)

    # 스타 플레이어(데이터 기준) — 골 2 + 도움 1 + 승리 팀 1
    pts: dict[tuple, float] = {}
    for g in p["goals"]:
        if g["kind"] != "og":
            pts[(g["side"], g["scorer"])] = pts.get((g["side"], g["scorer"]), 0) + 2
        if g["assist"]:
            pts[(g["side"], g["assist"])] = pts.get((g["side"], g["assist"]), 0) + 1
    star = None
    if pts:
        (s, n), v = max(pts.items(), key=lambda kv: (kv[1] + (1 if kv[0][0] == win else 0), kv[0][0] == win))
        gl = sum(1 for g in p["goals"] if g["scorer"] == n and g["side"] == s and g["kind"] != "og")
        asn = sum(1 for g in p["goals"] if g["assist"] == n and g["side"] == s)
        star = {"player": n, "side": s, "goals": gl, "assists": asn}

    stats = []
    for key, label, fmt in STATS:
        v = st.get(key)
        if not v or "home" not in v or "away" not in v:
            continue
        hv, av = _num(v["home"]), _num(v["away"])
        if fmt == "ratio":
            hv, av = round(hv * 100), round(av * 100)
        stats.append({"key": key, "label": label, "h": hv, "a": av, "fmt": fmt})

    return {"state": p["state"], "detail": p["detail"], "score": p["score"], "headline": head, "lines": lines,
            "goals": p["goals"], "cards": p["cards"], "pens": p["pens"], "stats": stats, "star": star,
            "predictions": pred, "venue": p["venue"], "attendance": p["attendance"], "context": ctx,
            "ht": ht if p["goals"] else None}
