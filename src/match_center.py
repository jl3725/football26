"""
매치 센터 — 일정(schedule_full)에서 '다음 경기'와 '이번 주 빅매치'를 골라낸다.

새 수집은 없다: 클라우드 daily_data 가 매일 ESPN 에서 8개 리그 + 유럽대회·국내컵 전 일정을 받고
(fetch_schedule.py, 킥오프 UTC 시각 포함), 여기서는 그 표를 경기 단위로 묶어 한국 시간·순위·폼·전력을
붙이고 빅매치 점수를 매긴다. 순수 계산만 — 데이터 읽기·로고는 API 가 넘겨준다.

빅매치 점수(높을수록 큰 경기) — API 는 35 이상을 빅매치로 쓴다(챔스 가산 30 만으로는 안 됨)
  대회   챔피언스리그 +30 · 유로파 +15 · 컨퍼런스 +6 · 국내컵 −10(강팀끼리가 아니면 묻히게)
  순위   같은 리그 둘 다 2위 안 +40('1위 경쟁') · 4위 안 +25 · 6위 안 +12('상위권 맞대결')
  전력   두 팀 평균 팀 OVR 이 78 을 넘는 만큼 ×2 (두 팀 모두 84+ 면 '강팀 대결')
"""
from __future__ import annotations

import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
_WD = "월화수목금토일"
COMP_LABEL = {"uefa.champions": "챔피언스리그", "uefa.europa": "유로파리그", "uefa.europa.conf": "컨퍼런스리그"}


def kst_of(kickoff: str, date: str) -> dt.datetime | None:
    """UTC ISO('2026-10-18T14:00Z') → 한국 시각. 시각이 없으면(예전 데이터) 날짜만으로 정오 가정."""
    s = str(kickoff or "").strip()
    try:
        if s:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST)
        return dt.datetime.fromisoformat(str(date)[:10]).replace(hour=12, tzinfo=KST)
    except ValueError:
        return None


def kst_label(t: dt.datetime | None, has_time: bool = True) -> str:
    if t is None:
        return ""
    base = f"{t.month}/{t.day}({_WD[t.weekday()]})"
    return f"{base} {t:%H:%M}" if has_time else base


def recent_form(rows, team: str, n: int = 5) -> list[str]:
    """리그 경기 최근 n 결과(W/D/L, 오래된 → 최근)."""
    if rows is None or rows.empty:
        return []
    t = rows[(rows["squad"] == team) & (rows["status"] == "completed")
             & rows["comp_code"].astype(str).str.endswith(".1")]
    return [r for r in t.sort_values("date")["result"].astype(str).tolist() if r in ("W", "D", "L")][-n:]


def big_score(m: dict) -> tuple[int, list[str]]:
    code = str(m.get("comp_code") or "")
    h, a = m["home"], m["away"]
    score, tags = 0, []
    if code == "uefa.champions":          # 대회명은 카드 머리에 있으므로 태그로 반복하지 않는다
        score += 30
    elif code == "uefa.europa":
        score += 15
    elif code == "uefa.europa.conf":
        score += 6
    elif not code.endswith(".1"):
        score -= 10
    hr, ar = h.get("rank"), a.get("rank")
    if hr and ar and h.get("league") == a.get("league"):
        if hr <= 2 and ar <= 2:
            score += 40; tags.append("1위 경쟁")
        elif hr <= 4 and ar <= 4:
            score += 25; tags.append("상위권 맞대결")
        elif hr <= 6 and ar <= 6:
            score += 12; tags.append("상위권 맞대결")
    ho, ao = h.get("ovr"), a.get("ovr")
    if ho and ao:
        s = (ho + ao) / 2
        score += max(0.0, s - 78) * 2
        if min(ho, ao) >= 84:                # 평균이 아니라 둘 다 — 15위 대 2위가 '강팀 대결'로 뜨지 않게
            tags.append("강팀 대결")
    return int(round(score)), tags


def matches_from(rows_by_league: dict, today: dt.date, days: int, team: str | None = None) -> list[dict]:
    """예정 경기 → 경기 단위(중복 제거: 리그 경기는 양 팀 행, 유럽대회는 두 리그 파일에 같은 경기)."""
    end = today + dt.timedelta(days=days)
    seen: dict[str, dict] = {}
    for lg, df in rows_by_league.items():
        if df is None or df.empty:
            continue
        sub = df[df["status"] != "completed"]
        if team:
            sub = sub[sub["squad"] == team]
        for r in sub.itertuples(index=False):
            eid = str(getattr(r, "event_id", "") or "")
            kickoff = getattr(r, "kickoff", "") if hasattr(r, "kickoff") else ""
            kickoff = "" if kickoff != kickoff else kickoff          # NaN
            t = kst_of(kickoff, r.date)
            if t is None or not (today <= t.date() <= end):
                continue
            me = {"team": r.squad, "league": lg}
            opp = {"team": r.opponent, "league": None}
            home, away = (me, opp) if r.home_away == "H" else (opp, me)
            key = eid or f"{t.date()}|{home['team']}|{away['team']}"
            if key in seen:
                # 같은 경기를 상대 쪽 리그 파일에서 또 만나면 그쪽을 우리 표기·리그로 바꿔 끼운다
                # (EPL 파일의 상대는 ESPN 이름 'Paris Saint-Germain', 리그1 파일에선 우리 표기 'PSG')
                side = "home" if r.home_away == "H" else "away"
                seen[key][side] = {"team": r.squad, "league": lg}
                continue
            seen[key] = {"event_id": eid or None, "comp_code": r.comp_code,
                         "comp": COMP_LABEL.get(r.comp_code, r.comp), "kickoff": kickoff,
                         "kst": kst_label(t, bool(kickoff)), "date": t.date().isoformat(),
                         "d_day": (t.date() - today).days, "_t": t, "home": home, "away": away}
    out = sorted(seen.values(), key=lambda m: m["_t"])
    for m in out:
        m.pop("_t", None)
    return out


def _int(v) -> int | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else int(f)


def results_from(rows_by_league: dict, today: dt.date, days: int = 3) -> list[dict]:
    """최근 끝난 경기(스코어 포함, 최신순) — matches_from 과 같은 방식으로 경기 단위 중복 제거."""
    start = today - dt.timedelta(days=days)
    seen: dict[str, dict] = {}
    for lg, df in rows_by_league.items():
        if df is None or df.empty:
            continue
        for r in df[df["status"] == "completed"].itertuples(index=False):
            kickoff = getattr(r, "kickoff", "") if hasattr(r, "kickoff") else ""
            kickoff = "" if kickoff != kickoff else kickoff
            t = kst_of(kickoff, r.date)
            if t is None or not (start <= t.date() <= today):
                continue
            gf, ga = _int(getattr(r, "gf", None)), _int(getattr(r, "ga", None))
            if gf is None or ga is None:
                continue
            eid = str(getattr(r, "event_id", "") or "")
            me = {"team": r.squad, "league": lg, "goals": gf}
            opp = {"team": r.opponent, "league": None, "goals": ga}
            home, away = (me, opp) if r.home_away == "H" else (opp, me)
            key = eid or f"{t.date()}|{home['team']}|{away['team']}"
            if key in seen:
                side = "home" if r.home_away == "H" else "away"
                seen[key][side] = me
                continue
            seen[key] = {"event_id": eid or None, "comp_code": r.comp_code,
                         "comp": COMP_LABEL.get(r.comp_code, r.comp), "kickoff": kickoff,
                         "kst": kst_label(t, bool(kickoff)), "date": t.date().isoformat(),
                         "d_day": (t.date() - today).days, "_t": t, "home": home, "away": away}
    out = sorted(seen.values(), key=lambda m: m["_t"], reverse=True)
    for m in out:
        m.pop("_t", None)
    return out


def upset_note(m: dict) -> str:
    """이변이면 한 줄 설명(아니면 빈 문자열) — 순위 8계단 이상 또는 팀 OVR 5 이상 낮은 쪽이 이김."""
    h, a = m["home"], m["away"]
    if h.get("goals") is None or a.get("goals") is None or h["goals"] == a["goals"]:
        return ""
    w, l = (h, a) if h["goals"] > a["goals"] else (a, h)
    if w.get("rank") and l.get("rank") and w.get("league") and w.get("league") == l.get("league") and w["rank"] - l["rank"] >= 8:
        return f"{w['rank']}위가 {l['rank']}위를 꺾음"
    if w.get("ovr") and l.get("ovr") and l["ovr"] - w["ovr"] >= 5:
        return f"전력 {w['ovr']} 팀이 {l['ovr']} 팀을 꺾음"
    return ""


def watch_score(m: dict, n_teams: int) -> tuple[float, list[str]]:
    """같은 리그 경기 중 '주목할 매치' 점수와 이유 — 순위가 붙어 있을수록·걸린 게 클수록 높다.
    (빅매치는 챔스·강팀 위주라 에버튼 5위 대 첼시 6위 같은 리그 안의 승부처가 빠졌다)"""
    h, a = m["home"], m["away"]
    hr, ar = h.get("rank"), a.get("rank")
    if not hr or not ar or h.get("league") != a.get("league"):
        return 0.0, []
    tags: list[str] = []
    s = 0.0
    top, bottom, gap = min(hr, ar), max(hr, ar), abs(hr - ar)
    hp, ap = h.get("points"), a.get("points")
    pts = abs((hp or 0) - (ap or 0)) if hp is not None and ap is not None else None
    if bottom <= 2:
        s += 50; tags.append("1위 경쟁")
    elif bottom <= 4:
        s += 38; tags.append("상위권 맞대결")
    elif bottom <= 7 and gap <= 3:
        s += 30; tags.append("유럽 진출권 경쟁")
    elif n_teams and top >= n_teams - 4:
        s += 26; tags.append("강등권 맞대결")
    elif gap <= 2:
        s += 10; tags.append("중위권 맞대결")
    s += max(0, 3 - gap) * 3
    if pts is not None and pts <= 3:
        s += (3 - pts) * 4
        tags.append("승점 동률" if pts == 0 else f"승점 차 {pts}")
        if 0 < pts < 3:
            tags.append("이기면 순위 역전")
    hw, aw = streak_of(h.get("form") or [], "W"), streak_of(a.get("form") or [], "W")
    if hw >= 2 and aw >= 2:
        s += 6; tags.append("상승세 맞대결")
    elif max(hw, aw) >= 3:
        s += 3; tags.append(f"{h['team'] if hw >= aw else a['team']} {max(hw, aw)}연승")
    if h.get("ovr") and a.get("ovr"):
        s += max(0.0, (h["ovr"] + a["ovr"]) / 2 - 78)
    return s, tags


def streak_of(form: list[str], r: str) -> int:
    n = 0
    for x in reversed(form):
        if x != r:
            break
        n += 1
    return n


def points_path(rows, team: str) -> list[int]:
    """리그 경기 누적 승점(경기 순) — 우승 경쟁 그래프."""
    if rows is None or rows.empty:
        return []
    t = rows[(rows["squad"] == team) & (rows["status"] == "completed")
             & rows["comp_code"].astype(str).str.endswith(".1")].sort_values("date")
    out, acc = [], 0
    for r in t["result"].astype(str):
        acc += 3 if r == "W" else 1 if r == "D" else 0
        out.append(acc)
    return out

