"""
이적설 지도(NETWORK 탭 RUMOURS 렌즈 · 지식그래프 LINKED_TO) — 선수 → 클럽 '연결' 하나에 원천 여러 개를 모은다.

2026-10-21 사용자: "kg 에 뉴스나 gossip 루머 이런 거 넣어서 관계도를 넓히는 건?" → "이적설 지도 넣고".
원천
  TM 루머    data/transfer_rumors_{리그}_{시즌}.csv — 8개 리그 클럽마다 '이 클럽과 엮인 선수'(현 소속·확률·날짜)
  뉴스 루머  data/news_claims.csv 의 열린 이적시장 건(status=pending) — 기사 단계(관심·협상·합의·확정·부인), 매체·기자
  매체 신뢰  data/news_reliability.csv — 지난 닫힌 시장 적중률(베타 사전분포 score). 모르는 매체는 평균
연결 열기(heat 0~100) = 100·(1 − e^(−합/2)), 합 = Σ 원천 점수 × 최근성(반감기 뉴스 14일·TM 21일)
  TM 1건 = 1 + 확률/100 · 기사 1건 = 단계 가중(관심 1 · 협상 1.6 · 합의 2.4 · 확정 3 · 부인 −0.8) × 매체 신뢰(평균 대비 0.6~1.5)
한 선수에 여러 클럽이 엮이면 서로 '경쟁 구단'(같은 표적을 쫓는 클럽).
"""
from __future__ import annotations

import datetime as dt
import math
import re

from unidecode import unidecode

STAGE_W = {"interest": 1.0, "talks": 1.6, "agreed": 2.4, "done": 3.0, "denied": -0.8}
STAGE_ORDER = ["denied", "rumour", "interest", "talks", "agreed", "done"]
HALF_NEWS, HALF_TM = 14.0, 21.0
MAX_AGE = 120                       # 이보다 오래된 원천은 버린다(지난 시장 얘기)
REL_LO, REL_HI = 0.6, 1.5


def norm(n) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(n or "")).lower()).split())


def _s(v) -> str:
    """CSV 빈칸(NaN)·None → '' — 화면에 'nan' 이 찍히지 않게."""
    return "" if v is None or v != v else str(v).strip()


def parse_date(s) -> dt.date | None:
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def decay(days: float, half: float) -> float:
    return 0.5 ** (max(0.0, days) / half)


def heat(raw: float) -> int:
    return int(round(100 * (1 - math.exp(-max(0.0, raw) / 2))))


def outlet_factor(scores: dict[str, float]):
    """{매체: score} → 매체 → 신뢰 배수(평균 대비, REL_LO~REL_HI). 모르는 매체 1.0."""
    vals = [v for v in scores.values() if v == v]
    mean = sum(vals) / len(vals) if vals else 0.0

    def f(outlet: str) -> float:
        v = scores.get(outlet)
        if v is None or v != v or mean <= 0:
            return 1.0
        return max(REL_LO, min(REL_HI, v / mean))
    return f


def collect(tm_rows: list[dict], claims: list[dict], canon, rel, today: dt.date) -> dict[tuple[str, str], dict]:
    """원천 → {(선수 norm, 행선지 클럽): 연결}. canon(이름) = 우리 클럽 표기(8개 리그 밖이면 None → 원래 이름).
    tm_rows: {player, target_club, current_club, probability, date, age, pos, value}
    claims : {player, origin, dest, stage, source, journalists, date, link, headline}"""
    out: dict[tuple[str, str], dict] = {}

    def club(n) -> str:
        n = str(n or "").strip()
        return (canon(n) or n) if n else ""

    def link(player, frm, to) -> dict | None:
        k, to = norm(player), club(to)
        if not k or not to or club(frm) == to:
            return None
        lk = out.setdefault((k, to), {"player": str(player), "key": k, "from": club(frm), "to": to, "raw": 0.0,
                                      "stage": "rumour", "tm": None, "news": [], "last": None, "info": {}})
        if not lk["from"] and frm:
            lk["from"] = club(frm)
        return lk

    def seen(lk: dict, d: dt.date) -> None:
        if lk["last"] is None or d > lk["last"]:
            lk["last"] = d

    for r in tm_rows:
        d = parse_date(r.get("date")) or today
        age = (today - d).days
        if age > MAX_AGE:
            continue
        lk = link(r.get("player"), r.get("current_club"), r.get("target_club"))
        if lk is None:
            continue
        try:
            p = float(r.get("probability"))
            p = None if p != p else p
        except (TypeError, ValueError):
            p = None
        lk["raw"] += (1.0 + (p or 0) / 100) * decay(age, HALF_TM)
        if lk["tm"] is None or d > parse_date(lk["tm"]["date"]):
            lk["tm"] = {"prob": p, "date": d.isoformat()}
        for f in ("age", "pos", "value"):
            if r.get(f) is not None and r.get(f) == r.get(f):
                lk["info"].setdefault(f, r.get(f))
        seen(lk, d)
    for c in claims:
        d = parse_date(c.get("date"))
        st = str(c.get("stage") or "")
        if d is None or st not in STAGE_W or (today - d).days > MAX_AGE:
            continue
        lk = link(c.get("player"), c.get("origin"), c.get("dest"))
        if lk is None:
            continue
        src = _s(c.get("source"))
        lk["raw"] += STAGE_W[st] * rel(src) * decay((today - d).days, HALF_NEWS)
        lk["news"].append({"outlet": src, "journalists": _s(c.get("journalists")), "stage": st, "date": d.isoformat(),
                           "link": _s(c.get("link")) or None, "headline": _s(c.get("headline")), "trust": round(rel(src), 2)})
        if st != "denied" and STAGE_ORDER.index(st) > STAGE_ORDER.index(lk["stage"]):
            lk["stage"] = st
        elif st == "denied" and lk["stage"] == "rumour" and not lk["tm"]:
            lk["stage"] = "denied"
        seen(lk, d)
    for lk in out.values():
        lk["heat"] = heat(lk["raw"])
        lk["news"].sort(key=lambda x: x["date"], reverse=True)
        lk["outlets"] = sorted({n["outlet"] for n in lk["news"] if n["outlet"]})
        lk["last"] = lk["last"].isoformat() if lk["last"] else None
    return out


def team_map(team: str, links: dict[tuple[str, str], dict], roster: set[str], limit: int = 14) -> dict:
    """한 클럽 기준 — in(이 클럽이 쫓는 선수 + 경쟁 구단) · out(우리 선수에게 엮인 클럽) · competition · outlets.
    roster = 우리 선수 norm 이름(지금 스쿼드)."""
    by_player: dict[str, list[dict]] = {}
    for lk in links.values():
        if lk["heat"] > 0:
            by_player.setdefault(lk["key"], []).append(lk)
    ins, outs = [], []
    for k, ls in by_player.items():
        mine = next((x for x in ls if x["to"] == team), None)
        if mine and k not in roster:
            rivals = sorted((x for x in ls if x["to"] != team), key=lambda x: -x["heat"])
            ins.append({**_pub(mine), "rivals": [{"club": x["to"], "heat": x["heat"], "stage": x["stage"]} for x in rivals[:6]]})
        if k in roster or any(x["from"] == team for x in ls):
            suit = sorted((x for x in ls if x["to"] != team), key=lambda x: -x["heat"])
            if suit:
                outs.append({"player": suit[0]["player"], "key": k, "heat": max(x["heat"] for x in suit),
                             "suitors": [_pub(x) for x in suit[:6]]})
    ins.sort(key=lambda x: -x["heat"])
    outs.sort(key=lambda x: -x["heat"])
    comp: dict[str, dict] = {}
    for x in ins:
        for r in x["rivals"]:
            c = comp.setdefault(r["club"], {"club": r["club"], "players": [], "score": 0})
            c["players"].append(x["player"])
            c["score"] += min(x["heat"], r["heat"])
    outlets: dict[str, dict] = {}
    for x in [*ins, *(s for o in outs for s in o["suitors"])]:
        for n in x["news"]:
            o = outlets.setdefault(n["outlet"], {"outlet": n["outlet"], "n": 0, "trust": n["trust"]})
            o["n"] += 1
    return {"in": ins[:limit], "out": outs[:limit], "n_in": len(ins), "n_out": len(outs),
            "competition": sorted(comp.values(), key=lambda c: (-len(c["players"]), -c["score"]))[:8],
            "outlets": sorted(outlets.values(), key=lambda o: -o["n"])[:10]}


def _pub(lk: dict) -> dict:
    return {"player": lk["player"], "from": lk["from"], "to": lk["to"], "heat": lk["heat"], "stage": lk["stage"],
            "tm": lk["tm"], "news": lk["news"][:4], "n_news": len(lk["news"]), "outlets": lk["outlets"],
            "last": lk["last"], "info": lk["info"]}


STAGE_KO = {"rumour": "루머", "interest": "관심", "talks": "협상", "agreed": "합의", "done": "확정", "denied": "부인"}


def insight(team: str, m: dict) -> dict | None:
    """NETWORK GRAPH INSIGHTS 카드 — 가장 뜨거운 영입설(경쟁 구단 수)과 우리 선수 이적설 수."""
    top = (m.get("in") or [None])[0]
    if not top and not m.get("out"):
        return None
    if top:
        riv = top.get("rivals") or []
        txt = (f"{top['player']}({top['from'] or '?'}) — {STAGE_KO.get(top['stage'], top['stage'])} · 열기 {top['heat']}"
               + (f" · 경쟁 {len(riv)}개 클럽" if riv else ""))
        ev = [f"{top['player']} ─LINKED_TO→ {team}"] + [f"{top['player']} ─LINKED_TO→ {r['club']}" for r in riv[:2]]
        return {"lens": "rumors", "icon": "⇢", "tone": "info", "title": "가장 뜨거운 영입설", "text": txt,
                "big": str(m.get("n_in", 0)), "unit": "명 표적", "who": [top["player"]], "line": txt, "evidence": ev}
    o = m["out"][0]
    txt = f"{o['player']} — " + " · ".join(f"{x['to']}({STAGE_KO.get(x['stage'], x['stage'])})" for x in o["suitors"][:3])
    return {"lens": "rumors", "icon": "⇢", "tone": "warn", "title": "우리 선수 이적설", "text": txt,
            "big": str(m.get("n_out", 0)), "unit": "명 이적설", "who": [o["player"]], "line": txt,
            "evidence": [f"{o['player']} ─LINKED_TO→ {x['to']}" for x in o["suitors"][:3]]}
