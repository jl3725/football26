"""
Ask Scout 무료 모드 — LLM 없이 질문에서 팀·선수·의도를 찾아 도구를 실행하고, 결과 숫자로 한국어 답을 만든다.

GEMINI_API_KEY(무료 등급)가 있으면 scout_agent 가 Gemini 로 라우팅·요약하고, 없으면 이 규칙 라우터가 맡는다.
유료 OpenAI 는 SCOUT_ALLOW_PAID=1 일 때만(사용자 개인 유료 키 — 기본 경로 금지).

- 이름: 우리 클럽·선수 영문 표기, 한국어 위키 제목(data/names_ko.csv, src/names_ko.py), 클럽 애칭(NICK).
- 의도: 키워드(다음 경기·부상·차출·뉴스·이번 주·비슷한·추천·적합·주장·성향). 팀만 있으면 '지금 상태'.
- 답은 도구 결과 값만 인용한다(지어내지 않음).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent

# 흔한 클럽 애칭·표기 변형(한국어 위키 제목과 다르게 부르는 것) — 클럽 기준 정보라 손으로 둔다
NICK = {
    "아스날": "Arsenal", "맨시티": "Manchester City", "맨유": "Manchester Utd", "토트넘": "Tottenham Hotspur",
    "스퍼스": "Tottenham Hotspur", "뉴캐슬": "Newcastle United", "빌라": "Aston Villa", "팰리스": "Crystal Palace",
    "레알": "Real Madrid", "레알 마드리드": "Real Madrid", "바르사": "Barcelona", "바르셀로나": "Barcelona",
    "아틀레티코": "Atlético Madrid", "아틀레티코 마드리드": "Atlético Madrid", "빌바오": "Athletic Club",
    "뮌헨": "Bayern Munich", "바이에른": "Bayern Munich", "도르트문트": "Dortmund", "레버쿠젠": "Leverkusen",
    "라이프치히": "RB Leipzig", "인테르": "Inter", "인터밀란": "Inter", "인터 밀란": "Inter", "밀란": "Milan",
    "AC밀란": "Milan", "유벤투스": "Juventus", "유베": "Juventus", "나폴리": "Napoli", "로마": "Roma",
    "PSG": "PSG", "파리": "PSG", "파리 생제르맹": "PSG", "마르세유": "Marseille", "리옹": "Lyon", "모나코": "Monaco",
    "벤피카": "Benfica", "포르투": "Porto", "스포르팅": "Sporting CP", "아약스": "Ajax", "페예노르트": "Feyenoord",
    "클뤼프 브뤼허": "Club Brugge", "브뤼허": "Club Brugge",
}
POS = {"6번": "Defensive Midfield", "수미": "Defensive Midfield", "수비형": "Defensive Midfield", "8번": "Central Midfield",
       "중미": "Central Midfield", "10번": "Attacking Midfield", "공미": "Attacking Midfield", "왼쪽 윙": "Left Winger",
       "왼윙": "Left Winger", "좌윙": "Left Winger", "오른쪽 윙": "Right Winger", "오른윙": "Right Winger", "우윙": "Right Winger",
       "윙어": "Left Winger", "센터백": "Centre-Back", "중앙 수비": "Centre-Back", "왼쪽 풀백": "Left-Back",
       "레프트백": "Left-Back", "오른쪽 풀백": "Right-Back", "라이트백": "Right-Back", "스트라이커": "Centre-Forward",
       "9번": "Centre-Forward", "공격수": "Centre-Forward", "골키퍼": "Goalkeeper", "키퍼": "Goalkeeper"}
INTENTS = [  # (의도, 키워드) — 위에서부터 먼저
    ("news", ("뉴스", "기사", "소식", "news")),
    ("similar", ("비슷한", "유사", "닮은", "같은 스타일", "similar")),
    ("fit", ("맞아", "적합", "어울", "핏", " fit")),
    ("recommend", ("추천", "영입", "보강", "필요한 선수", "살만", "recommend", "sign ")),
    ("lead", ("주장", "영향력", "리더", "캡틴", "captain", "leader")),
    ("week", ("이번 주", "이번주", "요즘", "주간", "폼 오른", "폼 떨어", "급등", "급락", "this week")),
    ("identity", ("어떤 팀", "성향", "영입 스타일", "예산")),
    ("team_now", ("다음 경기", "다음경기", "이길", "승부", "예측", "경기 어때", "부상", "결장", "다친", "a매치", "대표팀",
                  "차출", "소집", "최근 경기", "최근 결과", "지금", "next match", "injur", "predict")),
]
LEAGUE_WORDS = {"EPL": ("epl", "프리미어", "premier"), "LaLiga": ("라리가", "la liga", "laliga"),
                "SerieA": ("세리에", "serie a"), "Bundesliga": ("분데스", "bundesliga"),
                "Ligue1": ("리그1", "리그 1", "리그앙", "ligue"), "LigaPortugal": ("포르투갈", "리가 포르투갈"),
                "Eredivisie": ("에레디비시", "eredivisie"), "BelgianProLeague": ("벨기에", "belgian")}


def _norm(s) -> str:
    return " ".join(re.sub(r"[.\-']", " ", unidecode(str(s or "")).lower()).split())


@lru_cache(maxsize=1)
def _index() -> dict:
    """{'clubs': [(별칭, 팀, 리그)], 'players': [(별칭, 선수, 팀, 리그, ovr)]} — 긴 별칭 먼저."""
    from leagues import LEAGUES, data_path  # noqa: PLC0415
    club_league, clubs, players = {}, [], []
    for lg in LEAGUES:
        st = data_path("standings", lg)
        if st.exists():
            for s in pd.read_csv(st)["squad"].astype(str):
                club_league[s] = lg
                clubs.append((s.lower(), s, lg))
    for k, v in NICK.items():
        if v in club_league:
            clubs.append((k.lower(), v, club_league[v]))
    ko = ROOT / "data" / "names_ko.csv"
    kd = pd.read_csv(ko) if ko.exists() else pd.DataFrame(columns=["kind", "league", "name", "squad", "ko"])
    for r in kd[kd["kind"] == "club"].itertuples():
        full = re.sub(r"\b(FC|AFC|CF|SC|KV|KSV|RSC|SK|AC|SSC|AS|OGC|RC|FK|CD|UD|SD|VfB|VfL|TSG)\b", "", str(r.ko)).strip()
        for alias in {full, full.split(" ")[0] if len(full.split(" ")[0]) >= 2 else full}:
            if alias and r.name in club_league:
                clubs.append((alias.lower(), r.name, club_league[r.name]))
    # 선수 — 영문 전체·성(리그 안 유일), 한국어 전체·마지막 낱말(유일)
    from api.services.player_data import player_frame  # noqa: PLC0415
    last_cnt: dict[str, int] = {}
    rows = []
    for lg in LEAGUES:
        f = player_frame(lg)
        if f is None:
            continue
        for p, sq, o in zip(f["player"].astype(str), f["squad"].astype(str), f["_ovr"]):
            rows.append((p, sq, lg, float(o) if o == o else 0.0))
            last = _norm(p).split()[-1] if _norm(p) else ""
            last_cnt[last] = last_cnt.get(last, 0) + 1
    for p, sq, lg, o in rows:
        n = _norm(p)
        players.append((n, p, sq, lg, o))
        last = n.split()[-1] if n else ""
        if len(last) >= 4 and last_cnt.get(last) == 1:
            players.append((last, p, sq, lg, o))
    ovr = {(p, sq): o for p, sq, _, o in rows}
    ko_last: dict[str, int] = {}
    kp = kd[kd["kind"] == "player"]
    for k in kp["ko"].astype(str):
        t = k.split()[-1]
        ko_last[t] = ko_last.get(t, 0) + 1
    for r in kp.itertuples():
        o = ovr.get((r.name, r.squad), 0.0)
        players.append((str(r.ko).lower(), r.name, r.squad, r.league, o))
        t = str(r.ko).split()[-1]
        if len(t) >= 2 and ko_last.get(t) == 1:
            players.append((t.lower(), r.name, r.squad, r.league, o))
    clubs.sort(key=lambda x: -len(x[0]))
    players.sort(key=lambda x: (-len(x[0]), -x[4]))
    return {"clubs": clubs, "players": players}


def _find(text: str, entries: list, latin: bool) -> list:
    """질문 안에 나온 별칭 — 영문은 단어 경계, 한글은 부분 문자열. 겹치는 자리는 긴 것 하나만."""
    found, used = [], []
    t_lat, t_raw = f" {_norm(text)} ", text.lower()
    for e in entries:
        alias = e[0]
        if not alias:
            continue
        hangul = bool(re.search(r"[가-힣]", alias))
        if latin and hangul or (not latin and not hangul):
            continue
        hay = t_raw if hangul else t_lat
        needle = alias if hangul else f" {alias} "
        i = hay.find(needle)
        if i < 0 or any(a <= i < b for a, b in used):
            continue
        used.append((i, i + len(needle)))
        found.append(e)
    return found


def parse(q: str, team: str | None, league: str) -> dict:
    idx = _index()
    clubs = _find(q, idx["clubs"], True) + _find(q, idx["clubs"], False)
    players = _find(q, idx["players"], True) + _find(q, idx["players"], False)
    seen, uniq = set(), []
    for p in players:                                   # 같은 선수(영문·한글로 두 번)는 하나 — 동명이인은 OVR 높은 쪽 먼저
        if (p[1], p[2]) not in seen:
            seen.add((p[1], p[2]))
            uniq.append(p)
    ql = q.lower()
    intent = next((k for k, kws in INTENTS if any(w in ql for w in kws)), None)
    role = next((v for k, v in POS.items() if k in q), None)
    team_hit = clubs[0] if clubs else None
    lg_word = next((k for k, ws in LEAGUE_WORDS.items() if any(w in ql for w in ws)), None)
    return {"intent": intent, "role": role,
            "team": team_hit[1] if team_hit else (None if lg_word and intent == "week" else team),
            "league": team_hit[2] if team_hit else (lg_word or league),
            "players": [{"name": p[1], "squad": p[2], "league": p[3]} for p in uniq[:2]]}


def _pc(v) -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def _say_team_now(r: dict) -> str:
    t = r.get("team")
    lines = []
    for m in (r.get("next") or [])[:1]:
        side = "홈" if m["home"] == t else "원정"
        opp = m["away"] if m["home"] == t else m["home"]
        s = f"다음 경기는 {m.get('date', '')[5:].replace('-', '/')} {opp}전({side}, {m.get('comp') or ''})."
        preds = []
        for k, lab in (("model", "MODEL"), ("fans", "팬 투표"), ("elo", "ClubElo")):
            p = m.get(k)
            if p and p.get("h") is not None:
                preds.append(f"{lab} 홈승 {_pc(p['h'])}·무 {_pc(p['d'])}·원정승 {_pc(p['a'])}")
        if preds:
            s += " 예측 — " + " / ".join(preds) + "."
        lines.append(s)
    rec = r.get("recent") or []
    if rec:
        lines.append("최근 결과: " + ", ".join(f"{x['opp']} {x['score']}({x['result']})" for x in rec[-3:]) + ".")
    inj = r.get("injuries") or []
    if inj:
        lines.append(f"결장 {len(inj)}명: " + ", ".join(f"{x['player']}({x['injury']}{', ' + str(x['until']) if x.get('until') else ''})"
                                                     for x in inj[:5]) + ".")
    it = r.get("intl")
    if it and it.get("summary", {}).get("n"):
        w = it["window"]
        lines.append(f"{w['label']} {w['start'][5:].replace('-', '/')}~{w['end'][5:].replace('-', '/')}"
                     f"(D-{it['days_to']}) 소집 {it['summary']['n']}명"
                     + (f", 유럽 밖 {it['summary']['far']}명" if it["summary"]["far"] else "") + ".")
    return f"{t} — " + " ".join(lines) if lines else f"{t}의 최근 정보를 찾지 못했습니다."


def answer(q: str, team: str | None, league: str) -> dict:
    """규칙 라우팅 → 도구 실행 → 템플릿 답. scout_agent._execute 를 그대로 쓴다(같은 카드)."""
    import scout_agent as sa  # noqa: PLC0415
    p = parse(q, team, league)
    intent, tm, lg, pls = p["intent"], p["team"], p["league"], p["players"]
    pl = pls[0] if pls else None
    if intent is None:
        intent = "news" if (pl and not tm) else ("team_now" if tm else None)
    if intent in ("similar", "news") and not pl:
        intent = "team_now" if tm else None
    if intent is None:
        return {"available": True, "engine": "rules", "intent": None, "result": None,
                "answer": "팀이나 선수 이름을 넣어 물어봐 주세요. 예: '아스날 다음 경기 어때?', '사카 최근 뉴스', "
                          "'라이스랑 비슷한 선수', '아스날 왼쪽 윙어 추천', '이번 주 EPL 요약', '바르사 주장단'."}
    if intent == "similar":
        it, res = sa._execute("find_similar", {"player": pl["name"]}, pl["league"])
        names = ", ".join(f"{x['player']}({x['squad']}, 유사도 {x['score']}%)" for x in (res.get("results") or [])[:5])
        text = f"{pl['name']}와 스타일이 비슷한 선수: {names}." if names else f"{pl['name']}의 유사 선수를 찾지 못했습니다."
    elif intent == "news":
        it, res = sa._execute("player_news", {"player": pl["name"], "club": pl["squad"]}, pl["league"])
        arts = res.get("articles") or []
        text = (f"{pl['name']} 최근 기사 {len(arts)}건: " + " / ".join(f"{a['headline']}({a['source']})" for a in arts[:4])
                if arts else f"{pl['name']}가 나온 최근 기사가 없습니다.")
    elif intent == "fit" and pl and tm:
        it, res = sa._execute("evaluate_fit", {"candidate": pl["name"], "club": tm, "role": p["role"] or ""}, lg)
        text = (f"{pl['name']} → {tm}: 적합도 {res.get('fit_score')} · {res.get('signing_type', '')} · 위험 {res.get('risk_level', '')}"
                if isinstance(res, dict) and res.get("fit_score") is not None else f"{pl['name']}의 {tm} 적합도를 계산하지 못했습니다.")
    elif intent == "recommend" and tm:
        it, res = sa._execute("recommend_players", {"team": tm, "role": p["role"]}, lg)
        recs = (res or {}).get("recommendations") or []
        text = (f"{tm} 보강 후보{' (' + p['role'] + ')' if p['role'] else ''}: "
                + ", ".join(f"{x['player']}({x['squad']}, OVR {x.get('ovr')}→예상 {x.get('projected_ovr')})" for x in recs[:5])
                if recs else f"{tm}의 추천 후보를 찾지 못했습니다.")
    elif intent == "lead" and tm:
        api = sa._api()
        lead = (api.network(tm, lg).get("leadership") or {}) if api else {}
        caps = ", ".join(f"{c['name']}({c['role_ko']})" for c in lead.get("captains") or [])
        top = sorted((lead.get("influence") or {}).items(), key=lambda x: -x[1])[:5]
        it, res = "lead", {"captains": lead.get("captains"), "influence": dict(top)}
        text = (f"{tm} 주장단: {caps or '정보 없음'}. 팀 안 영향력 상위: "
                + ", ".join(f"{n} {v}" for n, v in top) + ". (실력·출전·완장·볼 관여·폼 등 가중합)")
    elif intent == "identity" and tm:
        it, res = sa._execute("club_identity", {"team": tm}, lg)
        rc, bg = (res or {}).get("recruitment") or {}, (res or {}).get("budget") or {}
        text = (f"{tm} 영입 성향: {rc.get('profile', '정보 없음')}(평균 영입 나이 {rc.get('avg_age')})"
                + (f", 예산 {bg.get('spend_tier')} tier" if bg else "") + ".")
    elif intent == "week":
        it, res = sa._execute("league_week", {"league": lg}, lg)
        up = ", ".join(f"{x['player']} +{x['delta']}" for x in (res.get("risers") or [])[:3])
        dn = ", ".join(f"{x['player']} {x['delta']}" for x in (res.get("fallers") or [])[:3])
        inj = res.get("injuries") or {}
        text = (f"{lg} 이번 주 — 폼 상승 {up or '없음'} · 폼 하락 {dn or '없음'} · 새 부상 {inj.get('n_new', 0)}·복귀 "
                f"{inj.get('n_back', 0)} · 새 이적 루머 {(res.get('rumors') or {}).get('n', 0)}건.")
    else:                                               # team_now(기본)
        if not tm:
            return {"available": True, "engine": "rules", "intent": None, "result": None,
                    "answer": "어느 팀 얘기인지 알려 주세요. 예: '아스날 다음 경기 어때?'"}
        it, res = sa._execute("team_now", {"team": tm}, lg)
        text = _say_team_now(res)
    return {"available": True, "engine": "rules", "intent": it, "args": p, "answer": text, "result": res}
