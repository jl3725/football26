"""
스카우팅 리포트 한 장 — 선수 상세(/api/player)·부상 이력(두 시즌)·현재 결장·계약·시장가치·이적설(TM 루머 + 뉴스 단계·매체 적중률)·
유사 선수를 판단 문장으로 묶는다. 문장은 규칙으로 만든다(숫자는 원자료 그대로, 손으로 쓴 선수 평 없음).

  strengths   리그 경기 기준 같은 포지션 대비 백분위 상위(≥70) 지표 3개 / weaknesses 하위(≤30) 3개
  availability 시즌별 결장 경기·일수·부상 횟수 + 지금 결장 → 위험 low·mid·high
  contract     남은 개월 → expiring(≤12)·short(≤24)·long
  market       지금 가치·1년 변화율·최고점
  verdict      위를 4~6줄 한국어로(역할·강점·약점·폼·가용성·계약·이적설)
"""
from __future__ import annotations

import datetime as dt
import json

LINE_KO = {"GK": "골키퍼", "DEF": "수비수", "MID": "미드필더", "ATT": "공격수"}
STAGE_KO = {"interest": "관심", "talks": "협상", "agreed": "합의", "done": "확정", "denied": "부인"}


def _top_pct(p: float) -> int:
    """백분위 → '상위 n%'(92 → 8)."""
    return max(1, round(100 - p))


def strengths(categories: list[dict], k: int = 3) -> tuple[list[dict], list[dict]]:
    flat = []
    for c in categories or []:
        for m in c.get("metrics") or []:
            if m.get("pct") is None or m.get("low"):          # 시도 10회 미만(표본 부족)은 강약점으로 안 쓴다
                continue
            flat.append({"cat": c.get("name", ""), "label": m.get("label", ""), "pct": float(m["pct"]), "raw": m.get("raw")})
    strong = sorted([x for x in flat if x["pct"] >= 70], key=lambda x: -x["pct"])[:k]
    weak = sorted([x for x in flat if x["pct"] <= 30], key=lambda x: x["pct"])[:k]
    return strong, weak


def availability(seasons: list[dict], current: dict | None) -> dict:
    """seasons = [{season, games_missed, days_out, spells, injuries}](최근 먼저), current = 지금 결장({injury, until}) 또는 None."""
    last = seasons[1] if len(seasons) > 1 else (seasons[0] if seasons else {})
    this = seasons[0] if seasons else {}
    gm_last, gm_this = int(last.get("games_missed") or 0), int(this.get("games_missed") or 0)
    risk = "high" if gm_last >= 15 or gm_this >= 8 else "mid" if gm_last >= 6 or gm_this >= 3 or current else "low"
    return {"seasons": seasons, "current": current, "risk": risk}


def contract(until: str | None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    try:
        d = dt.date.fromisoformat(str(until)[:10])
    except (TypeError, ValueError):
        return {"until": None, "months_left": None, "status": "unknown"}
    months = round((d - today).days / 30.44)
    status = "expiring" if months <= 12 else "short" if months <= 24 else "long"
    return {"until": d.isoformat(), "months_left": months, "status": status}


def market(value_eur: float | None, history: list[dict], today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    hist = sorted([h for h in history or [] if h.get("value_eur")], key=lambda h: str(h.get("date")))
    now = float(value_eur or (hist[-1]["value_eur"] if hist else 0) or 0)
    year_ago = (today - dt.timedelta(days=365)).isoformat()
    base = next((h for h in reversed(hist) if str(h.get("date")) <= year_ago), hist[0] if hist else None)
    chg = round((now - base["value_eur"]) / base["value_eur"] * 100) if base and base["value_eur"] and now else None
    peak = max((h["value_eur"] for h in hist), default=now) if hist else now
    return {"value_eur": now, "change_12m_pct": chg, "peak_eur": max(peak, now), "points": len(hist)}


def _eur(v: float | None) -> str:
    if not v:
        return "-"
    return f"€{v / 1e6:.1f}m" if v >= 1e6 else f"€{v / 1e3:.0f}k"


def verdict(d: dict, strong: list[dict], weak: list[dict], avail: dict, con: dict, mk: dict, talk: list[dict]) -> list[str]:
    """판단 문장 4~6줄 — 숫자는 입력값 그대로."""
    out = []
    line = LINE_KO.get(str(d.get("line") or ""), "선수")
    role = (d.get("comp_usage") or {}).get("role") or ""
    head = f"{role} · " if role else ""
    out.append(f"{head}리그 {int(d.get('minutes') or 0):,}′ {int(d.get('goals') or 0)}골 {int(d.get('assists') or 0)}도움 · OVR {d.get('ovr')}")
    if strong:
        out.append("강점 — " + ", ".join(f"{s['label']}(같은 {line} 상위 {_top_pct(s['pct'])}%)" for s in strong))
    if weak:
        out.append("약점 — " + ", ".join(f"{w['label']}(하위 {max(1, round(w['pct']))}%)" for w in weak))
    rec, form = d.get("recent") or {}, d.get("form")
    if rec.get("score") is not None and form is not None:
        diff = float(rec["score"]) - float(form)
        trend = "상승세" if diff >= 5 else "하락세" if diff <= -5 else "시즌 수준 유지"
        out.append(f"폼 — 최근 {rec.get('n')}경기 {float(rec['score']):.0f} vs 시즌 {float(form):.0f}({trend})"
                   + (f" · 평점 평균 {float(rec['avg5']):.2f}" if rec.get("avg5") else ""))
    seas = avail.get("seasons") or []
    cur = avail.get("current")
    if cur:
        out.append(f"가용성 — 지금 결장({cur.get('injury') or '부상'}{', 복귀 예상 ' + str(cur['until']) if cur.get('until') else ''})")
    elif seas:
        bits = [f"{s['season']} {int(s.get('games_missed') or 0)}경기 결장" for s in seas[:2]]
        tone = {"high": "주의", "mid": "보통", "low": "양호"}[avail["risk"]]
        out.append(f"가용성 — {' · '.join(bits)}({tone})")
    if con.get("months_left") is not None:
        note = {"expiring": "만료 임박 — 이적료 협상력 낮음", "short": "2년 안 만료", "long": "장기 계약"}[con["status"]]
        out.append(f"계약 — {con['until'][:7]}까지({con['months_left']}개월) · {note}"
                   + (f" · 시장가치 {_eur(mk.get('value_eur'))}" if mk.get("value_eur") else "")
                   + (f"(1년 {mk['change_12m_pct']:+d}%)" if mk.get("change_12m_pct") else ""))
    if talk:
        t = talk[0]
        stage = f"{STAGE_KO.get(t.get('stage') or '', '')} 단계" if t.get("stage") else "루머"
        out.append(f"이적설 — {t.get('to_club') or '?'}({stage}, {t.get('source') or 'TM'}) 등 {len(talk)}건")
    return out


def talk_items(tm_rows: list[dict], news_rows: list[dict], track: dict | None = None) -> list[dict]:
    """이적설 — TM 루머(행선지·확률) + 우리 뉴스(이적 단계·매체·적중률). 최신순, 행선지 중복은 단계 높은 것."""
    rank = {"interest": 1, "talks": 2, "agreed": 3, "done": 4, "denied": 0}
    out: dict[str, dict] = {}
    for r in tm_rows:
        k = str(r.get("target_club") or "")
        if not k:
            continue
        out[k] = {"to_club": k, "date": str(r.get("date") or ""), "source": "Transfermarkt", "stage": "",
                  "probability": r.get("probability"), "headline": ""}
    for r in news_rows:
        k = str(r.get("to_club") or "")
        if not k:
            continue
        cur = out.get(k)
        if cur and rank.get(cur.get("stage") or "", -1) > rank.get(r.get("stage") or "", -1):
            continue
        o = (track or {}).get("outlets", {}).get(r.get("source") or "")
        out[k] = {"to_club": k, "date": str(r.get("date") or ""), "source": r.get("source") or "", "stage": r.get("stage") or "",
                  "probability": None, "headline": r.get("headline") or "",
                  "outlet_rate": o["rate"] if o and not o.get("few") else None}
    return sorted(out.values(), key=lambda x: x["date"], reverse=True)


def parse_spells(js: str | None) -> list[dict]:
    try:
        v = json.loads(js or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []
