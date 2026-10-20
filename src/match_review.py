"""
경기 리뷰(Match Review) — ESPN 경기 상세(summary)로 규칙 기반 리포트를 만든다(유료 AI 없음).

입력: ESPN /summary JSON(keyEvents 득점·카드·페널티, boxscore 팀 기록, gameInfo 경기장·관중)
      + 우리 쪽 맥락(팀 표기·로고·색, 경기 전 팬 투표·ClubElo 예측).
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


def build(p: dict, home: str, away: str, fans: dict | None = None, elo: dict | None = None,
          model: dict | None = None) -> dict:
    """사건·기록 → 화면용 리뷰(한국어 문장)."""
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
        lines.append(f"{name[win]}, {deficit[win]}골 차로 끌려가다 뒤집었다." if deficit[win] >= 2
                     else f"{name[win]}, 선제골을 내주고도 뒤집었다.")
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
    for label, v in (("팬 투표", fans), ("모델", model), ("ClubElo", elo)):
        if not v:
            continue
        pick = max(("h", "d", "a"), key=lambda k: v.get(k) or 0)
        word = {"h": f"{home} 승", "d": "무승부", "a": f"{away} 승"}[pick]
        pred.append({"source": label, "pick": word, "p": round(float(v.get(pick) or 0), 3), "hit": (pick == outcome) and not live})
    if pred and not live:
        hits = [x["source"] for x in pred if x["hit"]]
        miss = [x["source"] for x in pred if not x["hit"]]
        bits = []
        if hits:
            bits.append(f"{'·'.join(hits)} 예측 적중")
        if miss:
            bits.append(f"{'·'.join(miss)} 빗나감")
        lines.append(", ".join(bits) + ".")

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
            "predictions": pred, "venue": p["venue"], "attendance": p["attendance"],
            "ht": ht if p["goals"] else None}
