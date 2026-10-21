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


# 2군·유스 표시 — 이런 이름은 1군(우리 클럽)으로 절대 묶지 않는다('Manchester City U18'·'RC Lens Espoir'·'Jong Ajax')
_RESERVE_ANY = {"espoir", "espoirs", "futuro", "futures", "reserve", "reserves", "youth", "academy", "primavera",
                "castilla", "juvenil", "atletic", "nextgen"}
_RESERVE_RE = re.compile(r"\b(u ?1[5-9]|u ?2[0-3]|sub \d\d|next gen)\b")


def reserve_marks(name) -> frozenset[str]:
    """이름에 붙은 2군·유스 표시(정규화). 'II'·'B' 는 끝, 'Jong' 은 앞에 올 때만('Willem II Tilburg' 은 1군),
    'Atlético' 는 다른 클럽 이름 뒤에 붙을 때만('Sevilla Atlético' 는 2군, 'Atlético Nacional'·'Atlético' 는 아님)."""
    n = norm(name)
    toks = n.split()
    if not toks:
        return frozenset()
    marks = {t for t in toks if t in _RESERVE_ANY} | {m.group(0).replace(" ", "") for m in _RESERVE_RE.finditer(n)}
    if len(toks) >= 2 and toks[-1] in ("ii", "b", "atletico"):
        marks.add(toks[-1])
    if len(toks) >= 2 and toks[0] == "jong":
        marks.add("jong")
    return frozenset(marks)


def own_reserve(raw, team: str) -> bool:
    """raw(원천 표기)가 team 의 2군·유스인가 — 'Manchester City U18' → Manchester City 는 이적설이 아니라 내부 승격.
    2군을 1군으로 묶지 않게 되면서(make_canon) 이런 행이 '영입 표적'으로 새지 않게 따로 거른다."""
    raw = _s(raw)
    if not raw or not team or not reserve_marks(raw):
        return False
    import squads  # noqa: PLC0415
    import team_names as tnm  # noqa: PLC0415
    if squads.is_own_reserve(raw, team):              # 이적 기록에서 학습한 2군 표 + 끝 표시(U21·II·B …)
        return True
    toks = [t for t in _RESERVE_RE.sub(" ", norm(raw)).split() if t not in _RESERVE_ANY]   # 'RC Lens Espoir'·'Sevilla Atlético'
    if len(toks) >= 2 and toks[-1] in ("ii", "b", "atletico"):
        toks = toks[:-1]
    if len(toks) >= 2 and toks[0] == "jong":
        toks = toks[1:]
    return bool(toks) and tnm.best(" ".join(toks), [team]) == team


def make_canon(club_league: dict[str, str], player_clubs: dict[str, set[str]], tm_rows: list[dict]):
    """원천 클럽 표기 → 우리 클럽(8개 리그 squad) — canon(이름, league_hint=None) → 우리 표기 | None(8개 리그 밖, 원래 이름 유지).

    예전엔 우리 클럽 전체에서 team_names.best(단어 포함 0.9)로 골라 다른 클럽이 묶였다
    ('RCD Espanyol Barcelona'→Barcelona, 'Grêmio … Porto Alegrense'→Porto, 'Atlético Nacional'→Nacional, 2군·유스→1군).
    1) 우리 표기 그대로면 그대로
    2) 학습 — TM 루머 행의 선수가 우리 선수면 그 행의 현 소속 표기를 그 선수의 클럽으로(후보를 그 클럽 하나로만 좁혀
       best 가 받아들일 때만 — 다른 클럽으로 샐 수 없음). 한 표기가 두 클럽으로 학습되면 애매해서 버린다
    3) 리그를 알면(TM target_club 은 리그별 파일) squads.canonical_squad → 그 리그 클럽 안에서만 best
       리그를 모르면 사람이 확인·자동 등록한 별칭표(squads.canonical_squad)에서 한 클럽으로만 풀릴 때
    4) 그 밖은 None. 2군·유스 표시가 붙은 이름은 어느 단계에서도 그 표시가 없는 1군으로 묶지 않는다."""
    import squads  # noqa: PLC0415
    import team_names as tnm  # noqa: PLC0415

    by_league: dict[str, list[str]] = {}
    for c, lg in club_league.items():
        by_league.setdefault(lg, []).append(c)
    pc: dict[str, set[str]] = {}
    for k, v in player_clubs.items():                  # 호출부 정규화가 달라도(build_kg _norm) 같은 키로
        pc.setdefault(norm(k), set()).update(v)

    def ok(raw: str, c) -> bool:
        return bool(c) and c in club_league and not (reserve_marks(raw) - reserve_marks(c))

    seen: dict[str, set[str]] = {}
    for r in tm_rows:
        raw = _s(r.get("current_club"))
        if not raw or raw in club_league:
            continue
        for c in pc.get(norm(r.get("player")), ()):
            if ok(raw, c) and tnm.best(raw, [c]) == c:
                seen.setdefault(raw, set()).add(c)
    learned = {raw: next(iter(cs)) for raw, cs in seen.items() if len(cs) == 1}
    cache: dict[tuple, str | None] = {}

    def canon(name, league_hint: str | None = None) -> str | None:
        n = _s(name)
        key = (n, league_hint)
        if key in cache:
            return cache[key]
        out = None
        if not n:
            pass
        elif n in club_league:
            out = n
        elif n in learned:
            out = learned[n]
        elif league_hint in by_league:
            c = squads.canonical_squad(n, league_hint)
            if c != n and club_league.get(c) == league_hint and ok(n, c):
                out = c
            else:
                b = tnm.best(n, by_league[league_hint])
                out = b if ok(n, b) else None
        else:
            hits = {c for lg in by_league for c in [squads.canonical_squad(n, lg)] if c != n and club_league.get(c) == lg}
            out = next(iter(hits)) if len(hits) == 1 and ok(n, next(iter(hits))) else None
        cache[key] = out
        return out
    return canon


def collect(tm_rows: list[dict], claims: list[dict], canon, rel, today: dt.date) -> dict[tuple[str, str], dict]:
    """원천 → {(선수 norm, 행선지 클럽): 연결}. canon(이름[, 리그]) = 우리 클럽 표기(8개 리그 밖이면 None → 원래 이름).
    tm_rows: {player, target_club, current_club, probability, date, age, pos, value, league(target_club 의 리그)}
    claims : {player, origin, dest, stage, source, journalists, date, link, headline}"""
    out: dict[tuple[str, str], dict] = {}

    def club(n, hint=None) -> str:
        n = str(n or "").strip()
        if not n:
            return ""
        return (canon(n, hint) if hint else canon(n)) or n

    def link(player, frm, to, hint=None) -> dict | None:
        k, to = norm(player), club(to, hint)
        if not k or not to or club(frm) == to or own_reserve(frm, to):   # 같은 클럽이거나 자기 2군·유스 → 연결 아님
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
        lk = link(r.get("player"), r.get("current_club"), r.get("target_club"), _s(r.get("league")) or None)
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
