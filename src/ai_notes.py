"""
해석 계층(AI 요약) — 규칙 기반 데이터(경기 리뷰·뉴스·WEEKLY DIGEST)를 Gemini 무료 등급(src/llm.py)으로 짧은 한국어 문장으로.

    python src/ai_notes.py match     # 최근 3일 끝난 경기 리포트 3~4문장 → data/ai/match_reports.json (match_refresh)
    python src/ai_notes.py news      # 팀별 최근 48시간 뉴스 1~3줄 → data/ai/news_digest.json (daily_news, 2시간마다)
    python src/ai_notes.py digest    # 리그별 주간 요약 한 문단 → data/ai/digest_text.json (daily_data)

원본이 사실의 근거다: 숫자·영문 이름은 원본에 있는 것만(llm.problems). 경기·주간 요약은 어긋나면 한 번 고쳐 쓰게 하고,
그래도 어긋나면 저장하지 않는다(뉴스 줄은 그 줄만 버림). 키가 없으면 아무것도 안 하고 0으로 끝난다 — 화면은 규칙 기반 그대로.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import llm  # noqa: E402

AI_DIR = ROOT / "data" / "ai"
FILES = {"match": AI_DIR / "match_reports.json", "news": AI_DIR / "news_digest.json", "digest": AI_DIR / "digest_text.json"}
DAILY = {"match": 160, "news": 80, "digest": 30}          # 용도별 하루 호출 상한(무료 키를 번역·Ask Scout 와 나눔)
SYSTEM = ("너는 축구 데이터 서비스의 한국어 에디터다. 주어진 JSON 데이터에 있는 사실만 쓴다. "
          "데이터에 없는 숫자·기록·선수·평가를 지어내지 않는다. 팀·선수 이름은 데이터의 영문 표기 그대로 쓴다.")
_CACHE: dict = {}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _kst_today() -> dt.date:
    return (_now() + dt.timedelta(hours=9)).date()


def _read(kind: str) -> dict:
    p = FILES[kind]
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _write(kind: str, data: dict) -> None:
    p = FILES[kind]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load(kind: str) -> dict:
    """API 용 — 파일이 바뀔 때만 다시 읽는다(배포 때 바뀜)."""
    p = FILES[kind]
    m = p.stat().st_mtime if p.exists() else 0
    hit = _CACHE.get(kind)
    if not hit or hit[0] != m:
        _CACHE[kind] = (m, _read(kind))
    return _CACHE[kind][1]


_FILLER = re.compile(r"(제공되지 않|존재하지 않|확인되지 않|데이터가 없|기록이 없|정보가 없|알 수 없)")


def _clean(text: str) -> str:
    """공백 정리 + '기록은 제공되지 않았다'처럼 빠진 자료를 말하는 문장은 뺀다(빈 칸은 그냥 안 쓰면 됨)."""
    t = " ".join(str(text or "").replace("**", "").replace("\n", " ").split()).strip(' "')
    sents = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(s for s in sents if not _FILLER.search(s)).strip()


def write_checked(prompt: str, facts) -> str | None:
    """한 문단 생성 → 검증 → 어긋나면 한 번 고쳐 쓰기 → 그래도 어긋나면 None."""
    text = _clean(llm.generate(prompt, SYSTEM) or "")
    if not text:
        return None
    bad = llm.problems(text, facts)
    if not bad:
        return text
    fix = (f"{prompt}\n\n방금 쓴 문단:\n{text}\n\n이 표현은 데이터에 없다: {', '.join(dict.fromkeys(bad))}. "
           "데이터에 있는 것만으로 다시 써라.")
    text = _clean(llm.generate(fix, SYSTEM) or "")
    return text if text and not llm.problems(text, facts) else None


# ── ① 경기 리포트 ─────────────────────────────────────────────────────────────
def recent_matches(days: int = 3) -> list[dict]:
    """우리 일정(schedule_full)에서 최근 days 일 끝난 경기 — event_id 하나당 한 번, 최근 순."""
    import datastore as ds  # noqa: PLC0415
    since = (_kst_today() - dt.timedelta(days=days)).isoformat()
    seen: dict = {}
    for lg in ds.available_leagues():
        df = ds.read_table("schedule_full", league=lg)
        if df is None or df.empty or "event_id" not in df.columns:
            continue
        d = df[(df["status"].astype(str) == "completed") & (df["date"].astype(str) >= since) & df["event_id"].notna()]
        for r in d.itertuples(index=False):
            eid = str(r.event_id).split(".")[0]
            seen.setdefault(eid, {"event_id": eid, "comp": str(r.comp_code), "comp_name": str(r.comp),
                                  "date": str(r.date)[:10], "kickoff": str(r.kickoff or "")})
    return sorted(seen.values(), key=lambda m: m["kickoff"] or m["date"], reverse=True)


_KIND = {"pen": "페널티킥", "og": "자책골", "header": "헤더"}


def match_facts(rv: dict, comp_name: str = "") -> dict:
    """/api/review 결과 → 요약에 넘길 사실(필요한 것만, 원본 값 그대로)."""
    h, a = rv["home"]["team"], rv["away"]["team"]
    side = {"home": h, "away": a}
    sc, ht = rv["score"], rv.get("ht")
    return {
        "competition": comp_name, "date": rv.get("date"), "home": h, "away": a,
        "final_score": f"{h} {sc['home']}-{sc['away']} {a}",
        "status": rv.get("detail") or None,      # FT · AET(연장) · FT-Pens(승부차기) — 연장·승부차기는 이 표기가 있을 때만
        "half_time": f"{ht['home']}-{ht['away']}" if isinstance(ht, dict) else None,
        "goals": [{"minute": g["minute"], "team": side[g["side"]], "scorer": g["scorer"], "assist": g["assist"] or None,
                   "type": _KIND.get(g["kind"])} for g in rv.get("goals", [])],
        "red_cards": [{"minute": c["minute"], "team": side[c["side"]], "player": c["player"]}
                      for c in rv.get("cards", []) if c.get("color") == "red"],
        "yellow_cards": {t: sum(1 for c in rv.get("cards", []) if c.get("color") == "yellow" and c["side"] == s)
                         for s, t in side.items()},
        "missed_penalties": [{"minute": p["minute"], "team": side[p["side"]], "player": p["player"], "result": p["result"]}
                             for p in rv.get("pens", [])],
        "stats": {s["label"]: {h: s["h"], a: s["a"], "unit": "%" if s["fmt"] in ("pct", "ratio") else ""}
                  for s in rv.get("stats", [])},
        "player_of_match": rv.get("star") and {**rv["star"], "team": side[rv["star"]["side"]]},
        "pre_match_predictions": [{"source": p["source"], "pick": p["pick"], "probability_pct": round(p["p"] * 100),
                                   "hit": p["hit"]} for p in rv.get("predictions", [])],
        "venue": rv.get("venue") or None, "attendance": rv.get("attendance"),
        "notes": rv.get("lines", []),
    }


MATCH_PROMPT = """아래 경기 데이터로 한국어 경기 리포트를 3~4문장, 한 문단으로 써라.
- 순서: 결과와 의미 → 결정적 장면(득점·퇴장·페널티) → 경기 내용(기록 비교) → 경기 전 예측과의 대조. 날짜로 시작하지 마라.
- 득점 시간은 데이터의 minute 표기 그대로(예: 80'). 전반·후반 몇 분으로 바꾸지 마라.
- 순위·연승·시즌 기록·부상처럼 데이터에 없는 것은 쓰지 마라. notes 는 참고만 하고 그대로 베끼지 마라.
- 비어 있는 항목(기록·예측이 없음)은 언급하지 마라 — '제공되지 않았다' 같은 문장 금지. 쓸 게 적으면 2문장도 된다.
- 마크다운·목록·따옴표 없이 문장만, '~했다' 체.
데이터:
{facts}"""


def run_match(days: int = 3, limit: int = 40) -> int:
    from api.main import match_review_api  # noqa: PLC0415
    store = _read("match")
    reports, fails = store.get("reports", {}), store.get("fails", {})
    recent = recent_matches(days)
    todo = [m for m in recent if m["event_id"] not in reports and fails.get(m["event_id"], 0) < 2]
    made = 0
    for m in todo[:limit]:
        if llm.remaining() <= 0:
            break
        try:
            rv = match_review_api(m["event_id"], m["comp"])
        except Exception as e:  # noqa: BLE001 — ESPN 한 경기 실패는 건너뜀
            print(f"  ! {m['event_id']} 리뷰 실패: {type(e).__name__}")
            continue
        if rv.get("state") != "post":
            continue
        facts = match_facts(rv, m["comp_name"])
        text = write_checked(MATCH_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False)), facts)
        if not text:
            fails[m["event_id"]] = fails.get(m["event_id"], 0) + 1
            print(f"  - {facts['final_score']}: 검증 실패·생성 실패 — 저장 안 함")
            continue
        reports[m["event_id"]] = {"text": text, "date": m["date"], "home": facts["home"], "away": facts["away"],
                                  "at": _now().isoformat(timespec="seconds"), "model": llm.last_model()}
        made += 1
        print(f"  + {facts['final_score']}")
    keep = (_kst_today() - dt.timedelta(days=30)).isoformat()
    reports = {k: v for k, v in reports.items() if v.get("date", "") >= keep}
    _write("match", {"reports": reports, "fails": {k: v for k, v in fails.items() if k in {m["event_id"] for m in recent}}})
    print(f"[ai-match] 새 리포트 {made} · 대상 {len(todo)} · 보관 {len(reports)}")
    return 0


# ── ② 팀 뉴스 하루 요약 ───────────────────────────────────────────────────────
NEWS_PROMPT = """팀별 최근 기사 목록으로 팀마다 '오늘의 뉴스 요약'을 만들어라. JSON 으로만 답하라: {{"팀 이름": ["문장", ...]}}.
- 팀마다 핵심 소식 1~3줄. 한 줄은 70자 이내 한국어 문장. 같은 소식을 다룬 기사는 한 줄로 합쳐라.
- 기사에 있는 사실만. 숫자·선수 이름은 기사 표기 그대로(선수 이름은 영문).
- 하이라이트 영상 안내·광고·다른 팀만의 소식은 빼라. 쓸 만한 소식이 없으면 빈 목록.
- 키는 주어진 팀 이름 그대로.
기사:
{facts}"""


def _news_window(hours: int = 48, per_team: int = 8) -> dict[str, list[dict]]:
    import sqlite3  # noqa: PLC0415

    import pandas as pd  # noqa: PLC0415
    since = (_kst_today() - dt.timedelta(days=max(1, hours // 24))).isoformat()   # first_seen 은 날짜 단위
    old = (_kst_today() - dt.timedelta(days=4)).isoformat()
    con = sqlite3.connect(ROOT / "data" / "news.db")
    try:
        df = pd.read_sql("select link, team, source, headline, headline_ko, descr, published, first_seen from articles "
                         "where first_seen >= ?", con, params=[since])
        try:
            tags = pd.read_sql("select link, squad from article_players", con)
        except Exception:  # noqa: BLE001 — 태깅 전 news.db
            tags = pd.DataFrame(columns=["link", "squad"])
    finally:
        con.close()
    pub = df["published"].astype(str).str[:10]
    df = df[(pub >= old) | ~pub.str.match(r"\d{4}-\d{2}-\d{2}")]       # 오래된 기사가 새로 잡힌 경우 제외
    # 화면(/api/news)과 같은 관련성 기준 — 팀 이름이 원문에 있거나 이 팀 선수 태그가 있는 기사만(src/news_relevance.py)
    import news_relevance as nr  # noqa: PLC0415
    import news_sources  # noqa: PLC0415 — 현지 클럽 표기('Standard Luik')도 그 팀 이름으로
    tagged = set(zip(tags["link"].astype(str), tags["squad"].astype(str)))
    ours = _our_clubs()
    keep = [bool(str(r.team) in ours and nr.relevant({"headline": r.headline, "descr": r.descr, "published": r.published,
                                                     "first_seen": r.first_seen},
                                                    nr.team_terms(str(r.team), tuple(news_sources.cached_local_names(str(r.team)))),
                                                    (str(r.link), str(r.team)) in tagged))
            for r in df.itertuples(index=False)]
    df = df[keep]
    out: dict[str, list[dict]] = {}
    for team, g in df.sort_values("published", ascending=False).groupby("team"):
        out[str(team)] = [{"link": str(r.link), "source": str(r.source or ""), "title": str(r.headline or ""),
                           "title_ko": str(r.headline_ko or ""), "summary": str(r.descr or "")[:240]}
                          for r in g.drop_duplicates("headline").head(per_team).itertuples()]
    return out


def _our_clubs() -> set[str]:
    """지금 8개 리그 소속 클럽 — 강등팀(Burnley·Wolves) 뉴스 요약에 할당량을 쓰지 않게."""
    import pandas as pd  # noqa: PLC0415
    from leagues import LEAGUES, data_path  # noqa: PLC0415
    out: set[str] = set()
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if p.exists():
            out |= set(pd.read_csv(p)["squad"].astype(str))
    return out


def _brief_lines(got, team: str, facts_team) -> tuple[list[str], int]:
    lines = [_clean(x) for x in (got.get(team) or []) if isinstance(x, str) and _clean(x)] if isinstance(got, dict) else []
    ok = [x for x in lines if not llm.problems(x, {"team": team, "articles": facts_team})][:3]
    return ok, len(lines) - len(ok)


def run_news(min_articles: int = 2, regen_h: float = 6, chunk: int = 10) -> int:
    store = _read("news")
    teams = store.get("teams", {})
    win = _news_window()
    now = _now()
    todo = []
    for team, arts in win.items():
        if len(arts) < min_articles:
            continue
        sig = hashlib.sha1("|".join(sorted(a["link"] for a in arts)).encode()).hexdigest()[:12]
        cur = teams.get(team) or {}
        age_h = (now - dt.datetime.fromisoformat(cur["at"])).total_seconds() / 3600 if cur.get("at") else 1e9
        if cur.get("sig") != sig and age_h >= regen_h:
            todo.append((team, sig, arts))
    made = 0
    for i in range(0, len(todo), chunk):
        if llm.remaining() <= 0:
            break
        part = todo[i:i + chunk]
        facts = {t: [{k: a[k] for k in ("source", "title", "title_ko", "summary")} for a in arts] for t, _, arts in part}
        got = llm.generate_json(NEWS_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False)), SYSTEM)
        if not isinstance(got, dict):
            continue
        for team, sig, arts in part:
            ok, dropped = _brief_lines(got, team, facts[team])
            if team not in got and llm.remaining() > 0:      # 묶음 응답에서 빠진 팀 — 혼자 한 번 더(47팀 중 16팀이 빠졌다)
                one = llm.generate_json(NEWS_PROMPT.format(facts=json.dumps({team: facts[team]}, ensure_ascii=False)), SYSTEM)
                ok, dropped = _brief_lines(one, team, facts[team])
            if not ok:
                continue                                       # 빈 결과는 저장하지 않는다 — 다음 실행이 다시 시도
            teams[team] = {"lines": ok, "n": len(arts), "sig": sig, "at": now.isoformat(timespec="seconds"),
                           "dropped": dropped}
            made += 1
    keep = (now - dt.timedelta(days=3)).isoformat()
    teams = {t: v for t, v in teams.items() if v.get("at", "") >= keep}
    _write("news", {"teams": teams})
    print(f"[ai-news] 팀 {made}/{len(todo)} 갱신 · 보관 {len(teams)}")
    return 0


# ── ③ WEEKLY DIGEST 서술 ─────────────────────────────────────────────────────
DIGEST_PROMPT = """아래는 {league} 지난 7일({since}~{until}) 변화 데이터다. 이번 주 흐름을 한국어 3~4문장, 한 문단으로 요약하라.
- 단순 나열보다 '무엇이 눈에 띄는지'를 연결해서. 가장 큰 변화부터.
- form_delta 는 '폼 지수 +N/-N', ovr 는 'OVR N'처럼 데이터 값 그대로. 몸값은 market_value 표기 그대로(예: €40m).
- 데이터의 키 이름(영문 필드명)을 문장에 쓰지 마라. 날짜는 '11월 9일'처럼.
- 데이터에 없는 경기 결과·순위·이유는 쓰지 마라. 마크다운·목록 없이 문장만, '~했다' 체.
데이터:
{facts}"""


def digest_facts(d: dict) -> dict:
    mv = lambda x: {"player": x["player"], "team": x["squad"], "ovr": x["ovr"], "form": x["form"],  # noqa: E731
                    "form_delta": x["delta"], "ovr_delta": x.get("ovr_delta") or 0}
    inj = lambda x: {k: x.get(k) for k in ("player", "squad", "injury", "until", "ovr")}  # noqa: E731
    rum = d.get("rumors") or {}
    return {
        "form_up": [mv(x) for x in d.get("risers", [])], "form_down": [mv(x) for x in d.get("fallers", [])],
        "new_injuries": [inj(x) for x in d.get("injuries", {}).get("new", [])],
        "returned_from_injury": [inj(x) for x in d.get("injuries", {}).get("back", [])],
        "injury_counts": {"new": d.get("injuries", {}).get("n_new", 0), "back": d.get("injuries", {}).get("n_back", 0)},
        "most_in_news": [{"player": x["player"], "team": x["squad"], "articles": x["articles"]} for x in d.get("news", [])],
        "transfer_rumors": {"count": rum.get("n", 0), "busiest_clubs": rum.get("clubs", []),
                            "biggest": [{"player": x["player"], "from": x["from"], "to": x["to"],
                                         "market_value": None if x.get("value_eur") is None else f"€{x['value_eur'] / 1e6:g}m"}
                                        for x in rum.get("top", [])]},
        "international_break": d.get("intl") and {k: d["intl"].get(k) for k in ("label", "start", "end", "days_to")},
    }


def run_digest() -> int:
    from api.main import digest  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    store = _read("digest")
    made = 0
    for lg in LEAGUES:
        if llm.remaining() <= 0:
            break
        try:
            d = digest(league=lg)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {lg} digest 실패: {type(e).__name__}")
            continue
        facts = digest_facts(d)
        if not (facts["form_up"] or facts["form_down"] or facts["new_injuries"] or facts["most_in_news"]):
            continue
        text = write_checked(DIGEST_PROMPT.format(league=lg, since=d["since"], until=d["until"],
                                                  facts=json.dumps(facts, ensure_ascii=False)), facts)
        if text:
            store[lg] = {"text": text, "since": d["since"], "until": d["until"], "at": _now().isoformat(timespec="seconds")}
            made += 1
            print(f"  + {lg}")
        else:
            print(f"  - {lg}: 검증 실패·생성 실패 — 이전 문단 유지")
    _write("digest", store)
    print(f"[ai-digest] {made}개 리그 갱신")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = argv if argv is not None else sys.argv[1:]
    kind = args[0] if args else ""
    if kind not in FILES:
        print(__doc__)
        return 2
    if not llm.available():
        print(f"[ai-{kind}] GEMINI_API_KEY 없음 — 건너뜀(화면은 규칙 기반 문장)")
        return 0
    llm.start(kind, DAILY[kind])
    try:
        return {"match": run_match, "news": run_news, "digest": run_digest}[kind]()
    finally:
        u = llm.finish()
        print(f"[ai-{kind}] 호출 {u['calls']} · 오늘 {u['today']}/{u['daily']} · 모델 {u['model']}"
              + (f" · 실패 {u['errors']}" if u["errors"] else ""))


if __name__ == "__main__":
    raise SystemExit(main())
