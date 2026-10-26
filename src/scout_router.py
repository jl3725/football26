"""
Ask Scout 무료 모드 — LLM 없이 질문에서 팀·선수·의도를 찾아 도구를 실행하고, 결과 숫자로 한국어 답을 만든다.

GEMINI_API_KEY(무료 등급)가 있으면 scout_agent 가 Gemini 로 라우팅·요약하고, 없으면 이 규칙 라우터가 맡는다.
유료 OpenAI 는 SCOUT_ALLOW_PAID=1 일 때만(사용자 개인 유료 키 — 기본 경로 금지).

- 이름: 우리 클럽·선수 영문 표기, 한국어 위키 제목·넘겨주기 별칭·팬 애칭(data/names_ko.csv, src/names_ko.py — 모두 자동 수집).
- 의도: 키워드(다음 경기·부상·차출·뉴스·이번 주·비슷한·추천·적합·주장·성향·폼). 팀만 있으면 '지금 상태'.
  폼 낱말(폼·컨디션·흐름·기세·부진·활약·요즘 …)과 선수·팀이 함께면 form — 선수면 최근 5경기 vs 시즌, 팀이면 최근 5경기 흐름.
  대상 없이 '요즘 폼 오른 선수' 는 리그 주간 요약(week) 그대로.
- 답은 도구 결과 값만 인용한다(지어내지 않음).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent

POS = {"6번": "Defensive Midfield", "수미": "Defensive Midfield", "수비형": "Defensive Midfield", "8번": "Central Midfield",
       "중미": "Central Midfield", "10번": "Attacking Midfield", "공미": "Attacking Midfield", "왼쪽 윙": "Left Winger",
       "왼윙": "Left Winger", "좌윙": "Left Winger", "오른쪽 윙": "Right Winger", "오른윙": "Right Winger", "우윙": "Right Winger",
       "윙어": "Left Winger", "센터백": "Centre-Back", "중앙 수비": "Centre-Back", "왼쪽 풀백": "Left-Back",
       "레프트백": "Left-Back", "오른쪽 풀백": "Right-Back", "라이트백": "Right-Back", "스트라이커": "Centre-Forward",
       "9번": "Centre-Forward", "공격수": "Centre-Forward", "골키퍼": "Goalkeeper", "키퍼": "Goalkeeper",
       # 영어 질문(소문자로 대조)
       "defensive mid": "Defensive Midfield", "holding mid": "Defensive Midfield", "central mid": "Central Midfield",
       "attacking mid": "Attacking Midfield", "left wing": "Left Winger", "right wing": "Right Winger",
       "winger": "Left Winger", "centre-back": "Centre-Back", "centre back": "Centre-Back", "center back": "Centre-Back",
       "left-back": "Left-Back", "left back": "Left-Back", "right-back": "Right-Back", "right back": "Right-Back",
       "striker": "Centre-Forward", "centre-forward": "Centre-Forward", "goalkeeper": "Goalkeeper", "keeper": "Goalkeeper"}
INTENTS = [  # (의도, 키워드) — 위에서부터 먼저
    ("news", ("뉴스", "기사", "소식", "news")),
    ("similar", ("비슷한", "유사", "닮은", "같은 스타일", "similar")),
    ("fit", ("맞아", "적합", "어울", "핏", " fit")),
    ("recommend", ("추천", "영입", "보강", "필요한 선수", "살만", "recommend", "sign ")),
    ("lead", ("주장", "영향력", "리더", "캡틴", "captain", "leader", "who leads", "influential")),
    ("week", ("이번 주", "이번주", "요즘", "주간", "폼 오른", "폼 떨어", "급등", "급락", "this week")),
    ("identity", ("어떤 팀", "성향", "영입 스타일", "예산")),
    ("team_now", ("다음 경기", "다음경기", "이길", "승부", "예측", "경기 어때", "부상", "결장", "다친", "a매치", "대표팀",
                  "차출", "소집", "최근 경기", "최근 결과", "지금", "next match", "injur", "predict")),
]
# 폼 질문 낱말 — 선수·팀이 함께 나오면 form(뉴스·추천·적합 같은 앞선 의도는 그대로). P2 ⑦(2026-10-21)
# 한글은 부분 문자열, 영어는 단어 경계 — 'formation'·'information' 의 form, 'Is Saka playing on Saturday?' 의 playing 은 폼이 아니다
FORM_WORDS = ("폼", "컨디션", "흐름", "기세", "부진", "활약", "상승세", "하락세", "잘하고", "잘해", "요즘", "최근 어때")
FORM_RE = re.compile(r"\bform\b|\bhow(?:['’]s| is)(?: [\w'’.-]+){1,3} (?:doing|playing)\b")
# '평점' 은 '어때·요즘·최근' 과 함께일 때만 폼('아스날 평점 높은 선수' 는 폼 질문이 아님)
RATING_WORD, RATING_WITH = "평점", ("어때", "요즘", "최근")
# 부상·이적·다음 경기·포메이션·라인업 낱말이 있으면 폼으로 바꾸지 않고 앞선 의도 그대로('아스날 요즘 부상자' = week)
FORM_BLOCK = ("부상", "결장", "다친", "루머", "이적", "영입", "다음 경기", "다음경기", "포메이션", "라인업", "주말", "예측")
FORM_BLOCK_RE = re.compile(r"\b(?:next|injur|transfer|rumou?r|formation|line-?up|saturday|sunday|predict)")


def _is_form_q(ql: str) -> bool:
    """폼을 묻는 질문인가(소문자 질문). 막는 낱말이 있으면 아니다."""
    if any(w in ql for w in FORM_BLOCK) or FORM_BLOCK_RE.search(ql):
        return False
    return (any(w in ql for w in FORM_WORDS) or bool(FORM_RE.search(ql))
            or (RATING_WORD in ql and any(w in ql for w in RATING_WITH)))
# 더 구체적인 리그가 먼저 — '오스트리아 분데스리가'가 분데스리가로, '덴마크 수페르리가'가 쉬페르리그로 잡히지 않게(첫 일치를 쓴다)
LEAGUE_WORDS = {"AustrianBundesliga": ("오스트리아", "austria"), "Championship": ("챔피언십", "championship", "efl"),
                "DanishSuperliga": ("덴마크", "superliga", "danish"),
                "SuperLig": ("쉬페르", "튀르키예", "터키", "super lig", "süper lig"),
                "SwissSuperLeague": ("스위스", "swiss", "super league"),
                "EPL": ("epl", "프리미어", "premier"), "LaLiga": ("라리가", "la liga", "laliga"),
                "SerieA": ("세리에", "serie a"), "Bundesliga": ("분데스", "bundesliga"),
                "Ligue1": ("리그1", "리그 1", "리그앙", "ligue"), "LigaPortugal": ("포르투갈", "리가 포르투갈"),
                "Eredivisie": ("에레디비시", "eredivisie"), "BelgianProLeague": ("벨기에", "belgian")}


def _norm(s) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", unidecode(str(s or "")).lower()).split())   # ?·!·'s 등 문장부호는 띄어쓰기로


def _dominant(cands: dict[str, list[tuple]], margin: float = 8.0) -> dict[str, tuple]:
    """짧은 별칭(성 하나 등) → 선수 하나. 유일하면 그 선수, 여럿이면 OVR 이 둘째보다 margin 이상 높은 한 명만
    (음바페 → Kylian, 동명이인끼리 비슷하면 별칭을 주지 않음)."""
    out = {}
    for alias, rows in cands.items():
        rows = sorted(set(rows), key=lambda r: -r[3])
        if len(rows) == 1 or rows[0][3] >= rows[1][3] + margin:
            out[alias] = rows[0]
    return out


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
    # 영문 첫 낱말(Bayern·Juventus 처럼 클럽 사이에서 유일할 때만 — Real·Manchester·Borussia 는 여럿이라 제외)
    first: dict[str, list[str]] = {}
    for s in club_league:
        w = _norm(s).split()
        if len(w) > 1 and len(w[0]) >= 4:
            first.setdefault(w[0], []).append(s)
    for w, ss in first.items():
        if len(ss) == 1 and w not in {"club", "real", "sporting", "athletic", "union", "royal"}:
            clubs.append((w, ss[0], club_league[ss[0]]))
    ko = ROOT / "data" / "names_ko.csv"
    kd = pd.read_csv(ko) if ko.exists() else pd.DataFrame(columns=["kind", "league", "name", "squad", "ko"])
    # 한국어 클럽 이름 = 위키 언어 링크 제목 + 그 문서로 넘겨주는 표기 전부(club_alias — '아스날 FC'·'맨시티'·'클럽 브뤼헤',
    # src/names_ko.py 주간 수집). 손으로 쓴 애칭 사전 없이. 첫 낱말 줄임('토트넘')은 클럽 사이에서 겹치지 않을 때만
    full_of: dict[str, set] = {}
    for r in kd[kd["kind"].isin(["club", "club_alias"])].itertuples():
        if r.name not in club_league:
            continue
        full = re.sub(r"\b(FC|F\.C\.?|AFC|CF|SC|KV|KSV|RSC|SK|AC|SSC|AS|OGC|RC|FK|CD|UD|SD|VfB|VfL|TSG)(?=\s|$)", "", str(r.ko)).strip()
        if full:
            full_of.setdefault(full.lower(), set()).add(r.name)
    part_of: dict[str, set] = {}                          # 첫·마지막 낱말 줄임('토트넘'·'뮌헨'·'마르세유')
    for f, names in full_of.items():
        ws = f.split(" ")
        for w in {ws[0], ws[-1]}:
            if len(w) >= 2 and w != f:
                part_of.setdefault(w, set()).update(names)
    # 두 클럽에 걸리는 말은 팀 전력(상위 11명 OVR 평균)이 5 이상 높은 쪽 — '레알'=Real Madrid, '브뤼헤'=Club Brugge,
    # 비슷하면('맨체스터' City·United) 쓰지 않는다. 손으로 정한 애칭 없이 데이터로
    from api.services.player_data import player_frame as _pf_  # noqa: PLC0415
    strength: dict[str, float] = {}
    for lg in LEAGUES:
        f_ = _pf_(lg)
        if f_ is not None and not f_.empty:
            for sq, g in f_.groupby("squad"):
                strength[str(sq)] = float(pd.to_numeric(g["_ovr"], errors="coerce").nlargest(11).mean())
    for alias, names in list(full_of.items()) + [(w, n) for w, n in part_of.items() if w not in full_of]:
        ranked = sorted(names, key=lambda n: -strength.get(n, 0))
        if len(ranked) == 1 or strength.get(ranked[0], 0) >= strength.get(ranked[1], 0) + 5:
            clubs.append((alias, ranked[0], club_league[ranked[0]]))
    for r in kd[kd["kind"] == "club_nick"].itertuples():  # 한국 팬 애칭(Gemini 수집, 다른 클럽과 겹치지 않는 것만)
        if r.name in club_league:
            clubs.append((str(r.ko).lower(), r.name, club_league[r.name]))
    # 선수 — 영문 전체·성(리그 안 유일), 한국어 전체·마지막 낱말(유일)
    from api.services.player_data import player_frame  # noqa: PLC0415
    rows = []
    for lg in LEAGUES:
        f = player_frame(lg)
        if f is None:
            continue
        for p, sq, o in zip(f["player"].astype(str), f["squad"].astype(str), f["_ovr"]):
            rows.append((p, sq, lg, float(o) if o == o else 0.0))
    last: dict[str, list[tuple]] = {}
    for p, sq, lg, o in rows:
        n = _norm(p)
        players.append((n, p, sq, lg, o))
        if n and len(n.split()[-1]) >= 4:
            last.setdefault(n.split()[-1], []).append((p, sq, lg, o))
    for alias, (p, sq, lg, o) in _dominant(last).items():
        players.append((alias, p, sq, lg, o))
    ovr = {(p, sq): o for p, sq, _, o in rows}
    # 한국어 — 위키 언어 링크가 동명이인 문서로 이어진 경우(Mo Salah 두 명 → '모하메드 살라')는 전체 이름도 주지 않는다
    kp = kd[kd["kind"] == "player"]
    who = kp.groupby("ko")[["name", "squad"]].apply(lambda g: len(set(zip(g["name"], g["squad"]))))
    ko_last: dict[str, list[tuple]] = {}
    for r in kp.itertuples():
        if who.get(r.ko, 0) > 1:
            continue
        o = ovr.get((r.name, r.squad), 0.0)
        players.append((str(r.ko).lower(), r.name, r.squad, r.league, o))
        t = str(r.ko).split()[-1]
        if len(t) >= 2:
            ko_last.setdefault(t.lower(), []).append((r.name, r.squad, r.league, o))
    for alias, (p, sq, lg, o) in _dominant(ko_last).items():
        players.append((alias, p, sq, lg, o))
    clubs.sort(key=lambda x: -len(x[0]))
    players.sort(key=lambda x: (-len(x[0]), -x[4]))
    return {"clubs": clubs, "players": players}


def _find(text: str, entries: list, latin: bool) -> list:
    """질문 안에 나온 별칭 — 영문은 단어 경계, 한글은 부분 문자열. 겹치는 자리는 긴 것 하나만."""
    found, used = [], []
    # 영문 대조엔 한글을 빼고 — unidecode 가 한글을 로마자로 바꿔 '맞아'가 'maja'(Josh Maja)로 잡혔다
    t_lat, t_raw = f" {_norm(re.sub(r'[ㄱ-ㅎㅏ-ㅣ가-힣]+', ' ', text))} ", text.lower()
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
    role = next((v for k, v in POS.items() if k in ql), None)
    team_hit = clubs[0] if clubs else None
    lg_word = next((k for k, ws in LEAGUE_WORDS.items() if any(w in ql for w in ws)), None)
    # 폼 — 선수·팀을 짚은 폼 질문만(뉴스·비슷한·추천·적합·주장·성향 의도는 그대로). '아스날 다음 경기' 같은 team_now 낱말이 있으면 team_now
    ours = team and any(w in ql for w in ("우리 팀", "우리팀", "이 팀", "our team", "we "))   # 보고 있는 팀을 가리킴
    if (uniq or team_hit or ours) and intent in (None, "week") and _is_form_q(ql):
        intent = "form"
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
        for k, lab in (("model", "MODEL"), ("fans", "팬 투표"), ("elo", "Elo 기준")):
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


def _say_player_form(r: dict) -> str:
    if not isinstance(r, dict) or r.get("error"):
        return (r or {}).get("error") or "폼 정보를 찾지 못했습니다."
    s, rc = r.get("season") or {}, r.get("recent") or {}
    head = f"{r['player']}({r['squad']}) — {r.get('verdict')}."
    parts = []
    if rc.get("form") is not None:
        sf = s.get("rating_fotmob")
        parts.append(f"최근 {rc.get('n')}경기 평점 평균 {rc.get('avg5_fotmob')}" + (f" / 시즌 {sf:.2f}" if sf else "")
                     + f"(FotMob) · 폼 지수 최근 {rc['form']} / 시즌 {s.get('form')}")
    elif s.get("form") is not None:
        parts.append(f"시즌 폼 지수 {s.get('form')}(최근 출전 적음)")
    parts.append(f"시즌 {s.get('minutes', 0):,}′ {s.get('goals', 0)}골 {s.get('assists', 0)}도움")
    eu = r.get("europe_cups")
    if eu:
        parts.append(f"유럽·컵 평점 {eu['rating_fotmob']}({eu['minutes']}′, FotMob)")
    ms = rc.get("matches") or []
    if ms:
        parts.append("최근 경기: " + ", ".join(
            f"{m['opponent']} {m['rating']}" + (f"(⚽{m['goals']})" if m.get("goals") else "") + (f"(🅰{m['assists']})" if m.get("assists") else "")
            for m in ms[:5] if m.get("rating") is not None))
    if r.get("ovr_change_2w"):
        parts.append(f"OVR {r['ovr']}(2주 {'+' if r['ovr_change_2w'] > 0 else ''}{r['ovr_change_2w']})")
    return head + " " + " · ".join(parts) + "."


def _say_team_form(r: dict) -> str:
    if not isinstance(r, dict) or r.get("error"):
        return (r or {}).get("error") or "팀 흐름을 찾지 못했습니다."
    t = r.get("team")
    parts = []
    rec = r.get("record5")
    if rec and r.get("last5"):
        parts.append(f"최근 {len(r['last5'])}경기 {rec['W']}승 {rec['D']}무 {rec['L']}패(득 {rec['gf']} 실 {rec['ga']}): "
                     + ", ".join(f"{x['opp']} {x['score']}{x['result']}" for x in r["last5"]))
    tb = r.get("table")
    if tb:
        parts.append(f"리그 {tb['rank']}위 {tb['points']}점({tb['played']}경기)")
    el = r.get("elo")
    if el:
        ch = el.get("change_30d")
        parts.append(f"Elo {el['now']}" + (f"(30일 {'+' if ch and ch > 0 else ''}{ch})" if ch is not None else ""))
    hot = r.get("hot") or []
    if hot:
        parts.append("폼 좋은 선수: " + ", ".join(f"{x['player']}({x['recent_form']})" for x in hot))
    cold = r.get("cold") or []
    if cold:
        parts.append("시즌보다 떨어진 선수: " + ", ".join(f"{x['player']}({x['season_form']}→{x['recent_form']})" for x in cold))
    return f"{t} — " + " · ".join(parts) + "." if parts else f"{t}의 최근 흐름을 찾지 못했습니다."


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
                "answer": "팀이나 선수 이름을 넣어 물어봐 주세요. 예: '아스날 다음 경기 어때?', '사카 요즘 폼 어때?', "
                          "'사카 최근 뉴스', '라이스랑 비슷한 선수', '아스날 왼쪽 윙어 추천', '이번 주 EPL 요약', '바르사 주장단'."}
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
    elif intent == "form" and pl:
        it, res = sa._execute("player_form", {"player": pl["name"], "club": pl["squad"]}, pl["league"])
        text = _say_player_form(res)
    elif intent == "form" and tm:
        it, res = sa._execute("team_form", {"team": tm}, lg)
        text = _say_team_form(res)
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
