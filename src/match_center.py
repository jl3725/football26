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
import re

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


_FORM_IDX: dict = {}      # id(rows) → (rows, {팀: [W/D/L …]}) — rows 를 붙잡아 두어 id 가 다른 표에 재사용되지 않게


def _form_index(rows) -> dict:
    """같은 경기 표의 팀별 리그 결과(날짜순) — 한 번 만들어 둔다. 일정 화면이 경기마다 recent_form 을 불러
    표 전체를 수백 번 거르던 것(리그 홈 일정 234번, 2026-10-22 성능 점검). 표는 읽기 전용으로 쓴다."""
    hit = _FORM_IDX.get(id(rows))
    if hit is not None and hit[0] is rows:
        return hit[1]
    t = rows[(rows["status"] == "completed") & rows["comp_code"].astype(str).str.endswith(".1")]
    idx = {sq: [r for r in g["result"].astype(str).tolist() if r in ("W", "D", "L")]
           for sq, g in t.sort_values("date", kind="stable").groupby("squad", sort=False)}
    if len(_FORM_IDX) >= 32:
        _FORM_IDX.clear()
    _FORM_IDX[id(rows)] = (rows, idx)
    return idx


def recent_form(rows, team: str, n: int = 5) -> list[str]:
    """리그 경기 최근 n 결과(W/D/L, 오래된 → 최근)."""
    if rows is None or rows.empty:
        return []
    return _form_index(rows).get(team, [])[-n:]


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
    # 팀 지정이면 그 팀 경기(event_id)를 모든 리그 파일에서 — 상대가 다른 리그면 그쪽 파일 행이 우리 표기·리그로
    # 바꿔 끼운다(바르사 일정의 'Paris Saint-Germain' → PSG·리그1: 순위·OVR·모델 예측이 살아남, 2026-10-20 점검)
    ids = espn_id_names(rows_by_league)
    team_eids: set[str] = set()
    if team:
        for df in rows_by_league.values():
            if df is not None and not df.empty and "event_id" in df.columns:
                team_eids |= {str(e) for e in df.loc[df["squad"] == team, "event_id"].dropna()}
    for lg, df in rows_by_league.items():
        if df is None or df.empty:
            continue
        sub = df[df["status"] != "completed"]
        if team:
            hit = sub["squad"] == team
            if team_eids and "event_id" in sub.columns:
                hit = hit | sub["event_id"].astype(str).isin(team_eids)
            sub = sub[hit]
        for r in sub.itertuples(index=False):
            eid = str(getattr(r, "event_id", "") or "")
            kickoff = getattr(r, "kickoff", "") if hasattr(r, "kickoff") else ""
            kickoff = "" if kickoff != kickoff else kickoff          # NaN
            t = kst_of(kickoff, r.date)
            if t is None or not (today <= t.date() <= end):
                continue
            me = {"team": r.squad, "league": lg}
            on, ol = our_opponent(r.opponent, _opp_logo(r), ids)
            opp = {"team": on, "league": ol, "logo_alt": _opp_logo(r)}
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


def _opp_logo(r) -> str:
    """일정 행의 ESPN 상대 로고(우리 로고 사전에 없는 팀용 대체). 예전 파일엔 컬럼이 없다."""
    v = getattr(r, "opponent_logo", "") if hasattr(r, "opponent_logo") else ""
    return v if isinstance(v, str) and v.startswith("http") else ""


_ESPN_ID = re.compile(r"/(\d+)\.png")


def espn_id_names(rows_by_league: dict) -> dict[str, tuple[str, str]]:
    """ESPN 팀 id → (우리 표기, 리그). 리그 경기 행의 상대는 우리 표기이고 로고 URL 에 ESPN id 가 있다 —
    컵·유럽 경기의 ESPN 이름('Paris Saint-Germain'·'Internazionale'·'KAA Gent')을 손 별칭 없이 우리 클럽에 잇는다."""
    out: dict[str, tuple[str, str]] = {}
    for lg, df in rows_by_league.items():
        if df is None or df.empty or "opponent_logo" not in df.columns:
            continue
        lgr = df[df["comp_code"].astype(str).str.endswith(".1")]
        squads = set(df["squad"].astype(str))
        for opp, logo in zip(lgr["opponent"].astype(str), lgr["opponent_logo"].astype(str)):
            m = _ESPN_ID.search(logo)
            if m and opp in squads:
                out.setdefault(m.group(1), (opp, lg))
    return out


def our_opponent(name: str, logo: str, ids: dict[str, tuple[str, str]]) -> tuple[str, str | None]:
    """일정 행 상대 → (우리 표기 또는 원래 이름, 우리 리그 또는 None)."""
    m = _ESPN_ID.search(str(logo or ""))
    hit = ids.get(m.group(1)) if m else None
    return hit if hit else (name, None)


def results_from(rows_by_league: dict, today: dt.date, days: int = 3) -> list[dict]:
    """최근 끝난 경기(스코어 포함, 최신순) — matches_from 과 같은 방식으로 경기 단위 중복 제거."""
    start = today - dt.timedelta(days=days)
    seen: dict[str, dict] = {}
    ids = espn_id_names(rows_by_league)
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
            on, ol = our_opponent(r.opponent, _opp_logo(r), ids)
            opp = {"team": on, "league": ol, "goals": ga, "logo_alt": _opp_logo(r)}
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


def _pois(lam: float, k: int) -> float:
    import math
    return math.exp(-lam) * lam ** k / math.factorial(k)


def win_prob(h_ovr, a_ovr, h_gdpg: float = 0.0, a_gdpg: float = 0.0) -> dict | None:
    """승·무·패 확률과 예상 득점 — 팀 OVR 차이 + 이번 시즌 경기당 골득실(±2로 자름)로 양 팀 득점 기대값을 잡고
    포아송 분포로 스코어 확률을 더한다. 홈 이점은 기본 득점(홈 1.40 · 원정 1.10)에 들어 있다.
    베팅 시장 배당이 아니라 우리 데이터로 만든 모델 값이다."""
    if not h_ovr or not a_ovr:
        return None
    import math
    clip = lambda v: max(-2.0, min(2.0, float(v or 0.0)))  # noqa: E731
    sgap = 0.05 * (float(h_ovr) - float(a_ovr)) + 0.10 * (clip(h_gdpg) - clip(a_gdpg))
    lh, la = 1.40 * math.exp(sgap / 2), 1.10 * math.exp(-sgap / 2)
    ph = pd_ = pa = 0.0
    for i in range(11):
        for j in range(11):
            q = _pois(lh, i) * _pois(la, j)
            if i > j:
                ph += q
            elif i == j:
                pd_ += q
            else:
                pa += q
    t = ph + pd_ + pa
    return {"h": round(ph / t, 3), "d": round(pd_ / t, 3), "a": round(pa / t, 3), "xg_h": round(lh, 2), "xg_a": round(la, 2)}

