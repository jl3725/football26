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
