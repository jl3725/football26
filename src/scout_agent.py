"""Ask Scout — 자연어 → 툴 라우팅(OpenAI function-calling) → 결정적 엔진 실행 → 답변+카드.

핵심: LLM은 '어느 엔진을 어떤 파라미터로 부를지' + '결과 요약'만 담당한다.
추천·수치·판단은 전부 우리 결정적 엔진(recommend/fit/similar/managersim/identity)이 낸다
→ LLM이 선수를 지어내지 않음(그동안 지켜온 정직함 유지).

로컬 전용 요소 포함(fit/managersim=Qdrant). OPENAI_API_KEY 없으면 available=False.
"""
from __future__ import annotations

from kg_graph import connect as _neo4j_connect  # noqa: E402  (차단기 포함 Neo4j 연결)

import json
import os
import re
import sys
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from leagues import LEAGUES, SEASON_START  # noqa: E402  (계약 임박 연도 = 이번 시즌 종료 해)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def provider() -> str:
    """답을 만드는 쪽 — gemini(무료 키) > openai(유료, SCOUT_ALLOW_PAID=1 일 때만) > rules(키 없이 규칙 라우터).
    OPENAI_API_KEY 는 사용자 개인 유료 키라 기본 경로로 쓰지 않는다(2026-10-20)."""
    _load_dotenv()
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY") and os.getenv("SCOUT_ALLOW_PAID", "").lower() in {"1", "true", "yes"}:
        return "openai"
    return "rules"


def _gemini_schema(s):
    """OpenAI JSON schema → Gemini Schema(type 대문자, 모르는 키 제거)."""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.upper()
            elif k in ("properties",):
                out[k] = {pk: _gemini_schema(pv) for pk, pv in v.items()}
            elif k in ("items",):
                out[k] = _gemini_schema(v)
            elif k in ("description", "required", "enum"):
                out[k] = v
        return out
    return s


def _gemini_call(body: dict) -> dict:
    import requests  # noqa: PLC0415
    key = os.getenv("GEMINI_API_KEY")
    last = None
    # 2026-10-20 신규 키 확인: gemini-2.5-flash 는 404(신규 사용자 막힘), gemini-flash-latest 는 도구 호출에서 60초+ 무응답,
    # gemini-3.1-flash-lite 는 1~2초에 도구를 정확히 고름 → 경량 우선, 모델당 25초 넘으면 다음 모델
    for model in [m for m in (os.getenv("GEMINI_MODEL"), "gemini-3.1-flash-lite", "gemini-flash-lite-latest",
                              "gemini-3.5-flash") if m]:
        try:
            r = requests.post(_GEMINI_URL.format(model=model), params={"key": key}, json=body, timeout=25)
        except requests.RequestException as e:
            last = f"{model} {type(e).__name__}"
            continue
        if r.status_code == 200:
            return r.json()
        last = f"{model} {r.status_code} {r.text[:120]}"
        if r.status_code not in (404, 429, 500, 503):
            break
    raise RuntimeError(f"Gemini 오류: {last}")


def _answer_gemini(message: str, team: str | None, league: str, history: list | None) -> dict:
    """Gemini 무료 등급 함수 호출 — 1차: 도구 고르기, 2차: 도구 결과로 한국어 브리핑(숫자는 결과 값만)."""
    sys_prompt = _SYSTEM + f"\n가능한 클럽: {', '.join(_clubs())}"
    if team:
        sys_prompt += f"\n현재 팀 컨텍스트: {team} (리그 {league})"
    contents = []
    for h in (history or [])[-6:]:
        text = str(h.get("content") or h.get("text") or "")[:1500]
        if text:
            contents.append({"role": "model" if h.get("role") == "assistant" else "user", "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    decl = [{"name": t["function"]["name"], "description": t["function"]["description"],
             "parameters": _gemini_schema(t["function"]["parameters"])} for t in TOOLS]
    base = {"systemInstruction": {"parts": [{"text": sys_prompt}]}, "tools": [{"functionDeclarations": decl}],
            "generationConfig": {"temperature": 0}}
    r1 = _gemini_call({**base, "contents": contents})
    parts = ((r1.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    call_part = next((p for p in parts if "functionCall" in p), None)     # thoughtSignature 까지 그대로 돌려줘야 함(Gemini 3)
    call = call_part["functionCall"] if call_part else None
    if not call:
        return {"available": True, "engine": "gemini", "intent": None,
                "answer": "".join(p.get("text", "") for p in parts), "result": None}
    args = call.get("args") or {}
    intent, result = _execute(call["name"], args, league)
    resp = {"name": call["name"], "response": {"content": _slim(intent, result)}}
    if call.get("id"):
        resp["id"] = call["id"]
    contents += [{"role": "model", "parts": [call_part]}, {"role": "user", "parts": [{"functionResponse": resp}]}]
    try:
        r2 = _gemini_call({**base, "contents": contents, "generationConfig": {"temperature": 0.2}})
        ans = "".join(p.get("text", "") for p in ((r2.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    except Exception:  # noqa: BLE001
        ans = ""
    out = {"available": True, "engine": "gemini", "intent": intent, "args": args, "answer": ans, "result": result}
    if not ans.strip():                      # 요약이 비면(도구 오류·한도) 규칙 엔진 문장으로
        import scout_router  # noqa: PLC0415
        rb = scout_router.answer(message, team, league)
        out.update({"answer": rb.get("answer", ""), "note": "Gemini 요약이 비어 규칙 기반 문장"})
    return out
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j", os.getenv("NEO4J_PASSWORD", "football26"))

# GraphRAG용 KG 스키마(라이브 introspect 기반). LLM이 이 라벨/관계/속성만 써서 Cypher 작성.
_KG_SCHEMA = """노드:
  Player {name, pos, pos_detail, age, nationality, league, market_value_eur, minutes, goals, assists, ss_rating, contract_until, career_games_missed,
          ovr, form, recent, xg_p90, influence(팀 안 영향력 0~100), captain_rank, injured_now, news_60d(최근 60일 기사 수), active(현재 우리 리그 소속)}
  Club {name, spend_tier, squad_value_eur, net_spend_eur, max_fee_paid_eur, price_ceiling_eur, recruit_profile, recruit_avg_age, europe_coefficient}
  League {key, name, level}  (key: EPL/LaLiga/SerieA/Bundesliga/Ligue1/LigaPortugal/Eredivisie/BelgianProLeague)
  Country {name, fifa_rank, fifa_points}
  Manager {name, formation, appointed, is_new, months_tenure, style_tags, tendency_tags, tac_pressing, tac_control, tac_creativity, tac_attack, tac_aerial, tac_disruption}
  TransferEvent {player, fee_eur, fee_text, window, season}
  Competition {name}  (UEFA Champions League / Europa League / Conference League)
  Role {name} · TacticalSnapshot · Scout · ScoutReport
관계(방향 정확히):
  (Player)-[:PLAYS_FOR]->(Club)
  (Player)-[:TEAMMATE_OF]->(Player)        // 같은 팀 선발 공유
  (Player)-[:REPRESENTS]->(Country)         // 국가대표
  (Player)-[:PLAYED_IN]->(Competition)      // 유럽대항전 출전
  (Player)-[:RUMORED_WITH {probability}]->(Club)   // 이적 루머/링크
  (Club)-[:COMPETES_IN]->(League)
  (Manager)-[:MANAGES]->(Club)
  (Manager)-[:EMPHASIZES]->(Role)
  (TransferEvent)-[:OF]->(Player), (TransferEvent)-[:FROM]->(Club), (TransferEvent)-[:TO]->(Club)
  (League)-[:IN_COUNTRY]->(Country)
  (Player)-[:CAPTAIN_OF {rank, role}]->(Club)          // 주장단(1=주장, 2=부주장 …)
  (Player)-[:MENTIONED_WITH {articles, last}]-(Player) // 최근 60일 같은 기사에 함께 나옴
  (Player)-[:CALLED_UP {squad_for, caps, goals}]->(Country)  // 대표팀 소집(가장 최근 명단)"""

# graph_query Cypher 작성 가이드 + few-shot(정확도↑). 라이브 값 기반.
_CYPHER_TIPS = """graph_query Cypher 팁:
- pos_detail 값: Centre-Back, Right-Back, Left-Back, Defensive Midfield, Central Midfield, Attacking Midfield, Right Winger, Left Winger, Centre-Forward, Second Striker, Goalkeeper.
- Competition.name = 'UEFA Champions League'/'UEFA Europa League'/'UEFA Conference League' → 부분일치 CONTAINS 'Champions'.
- League.key = EPL/LaLiga/SerieA/Bundesliga/Ligue1/LigaPortugal/Eredivisie/BelgianProLeague. contract_until 형식 'YYYY-MM-DD'(계약임박=CONTAINS '{EXPIRY_YEAR}').
- 이름 애매하면 WHERE x.name CONTAINS '...'. ORDER BY 속성엔 WHERE 속성 IS NOT NULL(NULL이 DESC 최상단 오는 것 방지). 반드시 LIMIT.
- 지금 소속 선수만: WHERE p.active = true (떠난 선수 노드는 active=false 로 남음). 골·도움·OVR 은 매주 화요일 기준.
예시:
  [루머] MATCH (p:Player)-[r:RUMORED_WITH]->(c:Club {name:'Arsenal'}) WHERE r.probability IS NOT NULL RETURN p.name, p.pos_detail, r.probability ORDER BY r.probability DESC LIMIT 15
  [챔스 U23 풀백] MATCH (p:Player)-[:PLAYED_IN]->(comp:Competition) WHERE comp.name CONTAINS 'Champions' AND p.age<=23 AND p.pos_detail IN ['Right-Back','Left-Back'] RETURN DISTINCT p.name,p.age,p.pos_detail,p.league,p.ss_rating ORDER BY p.ss_rating DESC LIMIT 15
  [주장단] MATCH (p:Player)-[k:CAPTAIN_OF]->(:Club {name:'Arsenal'}) RETURN p.name, k.role ORDER BY k.rank LIMIT 6
  [영향력] MATCH (p:Player)-[:PLAYS_FOR]->(:Club {name:'Arsenal'}) WHERE p.influence IS NOT NULL RETURN p.name, p.influence ORDER BY p.influence DESC LIMIT 5
  [같이 기사에] MATCH (:Player {name:'Declan Rice'})-[m:MENTIONED_WITH]-(q:Player) RETURN q.name, m.articles ORDER BY m.articles DESC LIMIT 10
  [대표팀 차출] MATCH (p:Player)-[c:CALLED_UP]->(co:Country) MATCH (p)-[:PLAYS_FOR]->(:Club {name:'Arsenal'}) RETURN p.name, co.name, c.caps LIMIT 20
  [이적경로 Ligue1→EPL] MATCH (fr:Club)-[:COMPETES_IN]->(:League {key:'Ligue1'}) MATCH (fr)<-[:FROM]-(t:TransferEvent)-[:TO]->(to:Club)-[:COMPETES_IN]->(:League {key:'EPL'}) MATCH (t)-[:OF]->(p:Player) RETURN p.name,fr.name,to.name,t.fee_text LIMIT 15
  [국대 동료] MATCH (a:Player {name:'Bukayo Saka'})-[:REPRESENTS]->(ctry)<-[:REPRESENTS]-(b:Player) WHERE a<>b RETURN b.name,b.pos_detail,b.league LIMIT 15
  [팀동료 중 루머] MATCH (a:Player {name:'Vitinha'})-[:TEAMMATE_OF]-(b:Player)-[:RUMORED_WITH]->(c:Club) RETURN DISTINCT b.name,c.name LIMIT 15
  [계약임박 CB] MATCH (p:Player) WHERE p.contract_until CONTAINS '{EXPIRY_YEAR}' AND p.pos_detail='Centre-Back' AND p.age<=26 RETURN p.name,p.contract_until,p.league,p.market_value_eur ORDER BY p.market_value_eur DESC LIMIT 15"""

_WRITE_RE = re.compile(r"(?i)(?<![a-z])(create|merge|delete|detach|set|remove|drop|foreach|load\s+csv)(?![a-z])")


def _run_cypher(cypher: str) -> dict:
    """읽기 전용 Cypher 실행(가드레일: 쓰기 차단·LIMIT 주입·타임아웃·READ 모드)."""
    if not cypher or not cypher.strip():
        return {"error": "빈 쿼리"}
    if _WRITE_RE.search(cypher):
        return {"error": "읽기 전용 Cypher만 허용됩니다(쓰기 키워드 감지)"}
    c = cypher.strip().rstrip(";")
    if not re.search(r"(?i)\blimit\b", c):
        c += "\nLIMIT 25"
    try:
        from neo4j import GraphDatabase, Query
        d = _neo4j_connect()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Neo4j 미가동: {str(e)[:60]}"}
    try:
        with d.session(default_access_mode="READ") as s:
            rows = s.run(Query(c, timeout=8.0)).data()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Cypher 오류: {str(e)[:140]}", "cypher": c}
    finally:
        d.close()
    return {"rows": rows[:25], "count": len(rows), "cypher": c}

TOOLS = [
    {"type": "function", "function": {
        "name": "recommend_players",
        "description": "특정 팀의 약한 포지션에 대한 영입 후보를 Qdrant 스타일-핏 기반으로 추천. "
                       "'아스날 6번 추천', '여름 보강 우선순위' 같은 질문. 후속 질문('프랑스 리그에서?', "
                       "'더 젊은 선수로')이면 이전 role/team 을 유지하고 조건만 바꿔 재호출.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명(정확한 데이터 표기)"},
            "role": {"type": "string", "description": "세부 역할(선택, 예: Defensive Midfield, Left Winger, Centre-Back). "
                     "'6번'=Defensive Midfield, '8번'=Central Midfield, '10번'=Attacking Midfield"},
            "leagues": {"type": "array", "items": {"type": "string"},
                        "description": "후보를 특정 소스 리그로 제한(선택). 키: EPL·LaLiga·SerieA·Bundesliga·"
                        "Ligue1·LigaPortugal·Eredivisie·BelgianProLeague. '프랑스 리그'=[\"Ligue1\"], '분데스'=[\"Bundesliga\"], "
                        "'스페인'=[\"LaLiga\"], '이탈리아'=[\"SerieA\"], '포르투갈'=[\"LigaPortugal\"], "
                        "'네덜란드'=[\"Eredivisie\"], '벨기에'=[\"BelgianProLeague\"]"},
            "max_age": {"type": "integer", "description": "최대 나이(선택, '더 젊은' 등)"},
            "max_value": {"type": "integer", "description": "최대 시장가 EUR(선택, '더 싼' 등, 예: 50000000)"}},
            "required": ["team"]}}},
    {"type": "function", "function": {
        "name": "evaluate_fit",
        "description": "특정 선수를 특정 클럽의 특정 역할로 영입할 때의 적합도를 정밀 분해. "
                       "'X를 아스날 CM으로 영입하면?', 'X 이 팀에 맞아?' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "candidate": {"type": "string", "description": "후보 선수명"},
            "club": {"type": "string", "description": "대상 클럽명"},
            "role": {"type": "string", "description": "세부 역할(예: Centre-Back, Central Midfield, Right Winger)"}},
            "required": ["candidate", "club", "role"]}}},
    {"type": "function", "function": {
        "name": "find_similar",
        "description": "특정 선수와 플레이 스타일이 비슷한 선수들을 전 리그에서 찾음. "
                       "'X랑 비슷한 선수', '비슷한데 더 싼 선수' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "player": {"type": "string", "description": "기준 선수명"}}, "required": ["player"]}}},
    {"type": "function", "function": {
        "name": "simulate_manager",
        "description": "특정 클럽에 새 감독이 부임하면 전술·스쿼드 적합도·영입 우선순위가 어떻게 변하는지 시뮬. "
                       "'아스날에 클롭 오면?' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "club": {"type": "string", "description": "대상 클럽명"},
            "manager": {"type": "string", "description": "새 감독명 또는 클럽명(그 클럽 전술 대입)"}},
            "required": ["club", "manager"]}}},
    {"type": "function", "function": {
        "name": "club_identity",
        "description": "클럽의 전술 정체성·영입 성향(유망주형/즉전형)·예산(추정)을 설명. "
                       "'아스날은 어떤 팀?', 'X팀 영입 성향' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명"}}, "required": ["team"]}}},
    # ── 실시간 도구(설계도 3단계) — 경기·부상·뉴스·이번 주. 숫자는 전부 데이터 값(API 함수 그대로) ──
    {"type": "function", "function": {
        "name": "team_now",
        "description": "팀의 '지금' 상태: 다음 경기와 승부 예측(모델·팬 투표·ClubElo), 최근 결과, 현재 부상·결장자와 결장 전력 손실, "
                       "다가오는 A매치 기간 소집 선수. '아스날 다음 경기 어때?', '지금 부상자 누구야?', '이번 주말 이길까?', "
                       "'A매치 차출 누구?' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명"}}, "required": ["team"]}}},
    {"type": "function", "function": {
        "name": "team_leadership",
        "description": "팀 주장단(주장·부주장·N번째 주장)과 팀 안 영향력 상위 선수(실력·출전·완장·볼 관여·폼 가중합 0~100). "
                       "'바르사 주장 누구?', '아스날에서 영향력 큰 선수', '리더가 누구야' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명"}}, "required": ["team"]}}},
    {"type": "function", "function": {
        "name": "player_news",
        "description": "선수가 나온 최근 뉴스 기사(제목·출처·날짜). '사카 최근 뉴스', 'X 요즘 기사 뭐 나와?' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "player": {"type": "string", "description": "선수명(데이터 표기)"},
            "club": {"type": "string", "description": "소속 클럽(선택 — 동명이인 구분)"}}, "required": ["player"]}}},
    {"type": "function", "function": {
        "name": "player_form",
        "description": "선수의 폼: 최근 5경기 평점(전 대회, FotMob, 출전 시간 가중)과 경기별 평점, 최근 폼 지수 vs 시즌 폼 지수(같은 리그·포지션 "
                       "안 순위 45~99)와 상승·하락 판정, 시즌 출전·골·도움·평점, 유럽대회 평점, OVR 과 2주 변화. "
                       "'사카 요즘 폼 어때?', '외데고르 최근 활약', 'X 컨디션 괜찮아?', 'X 부진해?' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "player": {"type": "string", "description": "선수명(데이터 표기)"},
            "club": {"type": "string", "description": "소속 클럽(선택 — 동명이인 구분)"}}, "required": ["player"]}}},
    {"type": "function", "function": {
        "name": "team_form",
        "description": "팀의 최근 흐름: 최근 5경기 결과(전 대회)와 승무패·득실, 리그 순위·승점, 팀 Elo 와 30일 변화, "
                       "최근 폼이 좋은 선수·시즌보다 떨어진 선수. '아스날 요즘 흐름 어때?', '맨시티 최근 기세', 'X팀 폼' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명"}}, "required": ["team"]}}},
    {"type": "function", "function": {
        "name": "league_week",
        "description": "리그의 지난 7일 변화 요약: 폼 지수 급등·급락 선수, 새 부상·복귀, 기사에 많이 나온 선수, 새 이적 루머, "
                       "다가오는 A매치 기간. '이번 주 EPL 어땠어?', '요즘 폼 오른 선수', '이번 주 부상 소식' 같은 질문.",
        "parameters": {"type": "object", "properties": {
            "league": {"type": "string", "description": "리그 키(EPL·LaLiga·SerieA·Bundesliga·Ligue1·LigaPortugal·Eredivisie·"
                       "BelgianProLeague). 없으면 현재 리그"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "graph_query",
        "description": "위 툴로 안 되는 열린 그래프 질문에 read-only Cypher를 직접 작성해 실행. "
                       "특히 **이적 루머/링크**('아스날에 링크나는 선수'=RUMORED_WITH), 관계 traversal"
                       "('국대 동료','팀 동료'), 다중 조건 필터('챔스 뛴 U23 풀백'), 이적 경로"
                       "('PSG→EPL 이적'), 집계('유럽 출전 최다 MF'). 반드시 스키마의 라벨/관계/속성만 사용.",
        "parameters": {"type": "object", "properties": {
            "cypher": {"type": "string", "description": "읽기 전용 Cypher(스키마 준수, 항상 LIMIT). "
                       "예: MATCH (p:Player)-[r:RUMORED_WITH]->(c:Club {name:'Arsenal'}) "
                       "RETURN p.name, p.pos_detail, r.probability ORDER BY r.probability DESC LIMIT 15"}},
            "required": ["cypher"]}}},
]

_SYSTEM = (
    "너는 'Chief Scout' — 축구 스카우팅 AI 어시스턴트다. 사용자의 질문을 적절한 툴로 라우팅한다.\n"
    "규칙:\n"
    "- 선수·수치·추천을 절대 지어내지 마라. 모든 판단은 툴 결과에서만 온다.\n"
    "- 클럽명은 아래 '가능한 클럽' 목록의 정확한 표기를 써라(예: Manchester United→'Manchester Utd').\n"
    "- 답변은 한국어로, 스카우트 브리핑처럼 간결하게. 툴 결과의 근거(팀니즈·유럽검증·시장가·전술적합)를 짚어라.\n"
    "- '우리 팀'/'이 팀'은 현재 보고 있는 팀 컨텍스트를 쓴다.\n"
    "- **'링크/루머/관심/영입설'은 추천이 아니라 RUMORED_WITH 조회다 → graph_query 사용.**\n"
    "- 관계·다중필터·집계·이적경로 질문도 graph_query(read-only Cypher). 구조화 툴이 맞으면 그걸 우선.\n"
    "- **주장·부주장·팀 안 영향력**은 team_leadership(그래프 쿼리보다 우선).\n"
    "- 답에는 툴 결과에 있는 사실·숫자만 쓴다. 결과에 없는 플레이 스타일 설명·평가·추측은 덧붙이지 않는다.\n"
    "- **지금·다음 경기·부상자·A매치 차출**은 team_now, **선수 최근 기사**는 player_news, "
    "**리그 이번 주 변화(폼·부상·루머)**는 league_week. 예측 확률은 그대로 인용하고 출처(모델·팬 투표·ClubElo)를 밝혀라.\n"
    "- **특정 선수의 폼·요즘 활약·컨디션·부진**은 player_form, **특정 팀의 최근 흐름·기세**는 team_form. "
    "verdict(상승세·하락세·유지)와 최근 5경기 평점·폼 지수를 그대로 인용하라(지수는 같은 리그·포지션 안 순위 45~99).\n"
    "- **'왜/이유/근거/설명해줘' 같은 메타 질문은 툴을 절대 호출하지 말고, 직전 답변을 근거로 텍스트로만 설명하라.**\n"
    "- 후속 질문('더 싸게','좁혀줘','~빼고')은 조건을 바꿔 새로 조회. 그 외 후속은 맥락 참고.\n"
    "\nKG 스키마(graph_query용, 이 라벨/관계/속성만 사용):\n" + _KG_SCHEMA + "\n\n"
    + _CYPHER_TIPS.replace("{EXPIRY_YEAR}", str(SEASON_START + 1)) + "\n"
)


def _load_dotenv():
    """프로젝트 루트 .env 에서 env 에 없는 키만 로드(의존성 없이) — 예전엔 OPENAI_API_KEY 가 있으면 통째로 건너뛰어
    GEMINI_API_KEY 를 못 읽었다."""
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not os.getenv(k):
            os.environ[k] = v


def _api():
    return sys.modules.get("api.main") or sys.modules.get("main")


@lru_cache(maxsize=1)
def _clubs() -> list:
    try:
        import club_profile as cp
        sv = cp._squad_value()
        return sorted(sv["club"].astype(str).unique().tolist()) if not sv.empty else []
    except Exception:  # noqa: BLE001
        return []


def _toks(s: str) -> set:
    syn = s.lower().replace("united", "utd").replace("münchen", "munich").replace("munchen", "munich")
    return set(re.findall(r"[a-z]+", syn))


def _resolve_club(name: str) -> str:
    if not name:
        return name
    clubs = _clubs()
    nl = name.lower().strip()
    for c in clubs:
        if c.lower() == nl:
            return c
    for c in clubs:
        if nl in c.lower() or c.lower() in nl:
            return c
    tn = _toks(name)
    best, bs = name, 0
    for c in clubs:
        ov = len(tn & _toks(c))
        if ov > bs:
            bs, best = ov, c
    return best if bs else name


_CLUB_LEAGUE: dict = {}


def _league_of(team: str, default: str) -> str:
    """팀이 뛰는 리그 — 선수 표(api._pf) squad 로 만든 클럽→리그(1시간 캐시). 모르면 default(대화 리그).
    대화 리그를 그대로 쓰면 'EPL 보다가 바르사 흐름' 이 EPL 일정·순위에서 찾아 비었다."""
    import time  # noqa: PLC0415
    api = _api()
    hit = _CLUB_LEAGUE.get("v")
    if not hit or hit[0] < time.time():
        m: dict[str, str] = {}
        for lg in dict.fromkeys([*LEAGUES, *(getattr(api, "_LEAGUE_LEVEL", None) or {})]):
            try:
                f = api._pf(lg)
            except Exception:  # noqa: BLE001
                continue
            if f is not None and "squad" in f.columns:
                for sq in f["squad"].dropna().astype(str).unique():
                    m.setdefault(sq, lg)
        hit = (time.time() + 3600, m)
        if m:
            _CLUB_LEAGUE["v"] = hit
    return hit[1].get(team) or default


def _execute(name: str, args: dict, league: str):
    """LLM이 고른 툴 → 결정적 엔진 함수 실행. (intent, 결과dict) 반환."""
    api = _api()
    if api is None:
        return None, {"error": "api.main 미로드"}
    if name == "recommend_players":
        import transfer_fit as tf  # Qdrant 스타일-핏 발굴(교차리그, 리그 중립)
        return "recommend", tf.discover_fits(
            _resolve_club(args.get("team", "")), args.get("role") or None,
            leagues=args.get("leagues") or None,
            max_age=args.get("max_age") or None, max_value=args.get("max_value") or None)
    if name == "evaluate_fit":
        return "fit", api.fit(args.get("candidate", ""), _resolve_club(args.get("club", "")),
                              args.get("role", ""), "", league)
    if name == "find_similar":
        return "similar", api.similar(args.get("player", ""), True, 0.6, league)
    if name == "simulate_manager":
        return "managersim", api.managersim(_resolve_club(args.get("club", "")), args.get("manager", ""), league)
    if name == "club_identity":
        return "identity", api.identity(_resolve_club(args.get("team", "")), league)
    if name == "graph_query":
        return "graph", _run_cypher(args.get("cypher", ""))
    if name in ("team_now", "team_form", "team_leadership"):     # 대화 리그가 아니라 그 팀의 리그로
        team = _resolve_club(args.get("team", ""))
        tlg = _league_of(team, league)
    if name == "team_now":
        return "team_now", team_now(team, tlg)
    if name == "team_leadership":
        lead = api.network(team, tlg).get("leadership") or {}
        top = sorted((lead.get("influence") or {}).items(), key=lambda x: -x[1])[:6]
        return "lead", {"team": args.get("team"), "captains": [{"name": c["name"], "role": c.get("role_ko"), "rank": c.get("captain_rank")}
                                                              for c in lead.get("captains") or []],
                        "influence_top": [{"name": n, "influence": v} for n, v in top]}
    if name == "player_news":
        return "news", api.news_player(args.get("player", ""), _resolve_club(args.get("club", "")) if args.get("club") else "",
                                       league, 6)
    if name == "league_week":
        lg = args.get("league") or league
        return "week", api.digest(lg if lg in LEAGUES else league)
    if name == "player_form":
        return "pform", player_form(args.get("player", ""), _resolve_club(args.get("club", "")) if args.get("club") else "", league)
    if name == "team_form":
        return "tform", team_form(team, tlg)
    return None, {"error": f"알 수 없는 툴: {name}"}


def team_now(team: str, league: str) -> dict:
    """팀의 지금 — 다음 경기·예측, 최근 결과, 부상·결장, A매치 소집. 모두 API 함수 값 그대로(지어내지 않게)."""
    api = _api()
    out: dict = {"team": team, "league": league}
    try:
        nxt = (api.team_fixtures(team, league).get("next") or [])[:2]
        out["next"] = [{"date": m.get("date"), "kickoff": m.get("kickoff"), "comp": m.get("comp"),
                        "home": m["home"]["team"], "away": m["away"]["team"],
                        "model": {k: (m.get("model") or {}).get(k) for k in ("h", "d", "a", "score", "xg_h", "xg_a")} if m.get("model") else None,
                        "fans": {k: (m.get("fans") or {}).get(k) for k in ("h", "d", "a")} if m.get("fans") else None,
                        "elo": {k: (m.get("elo") or {}).get(k) for k in ("h", "d", "a")} if m.get("elo") else None,
                        "inputs": (m.get("model") or {}).get("inputs")} for m in nxt]
    except Exception as e:  # noqa: BLE001
        out["next_error"] = str(e)[:120]
    try:
        sch = api.schedule(team, league)
        done = [m for m in sch.get("matches", []) if m.get("status") == "completed"][-3:]
        out["recent"] = [{"date": m.get("date"), "opp": m.get("opponent"), "ha": m.get("home_away"), "score": m.get("score"),
                          "result": m.get("result"), "comp": m.get("comp")} for m in done]
    except Exception as e:  # noqa: BLE001
        out["recent_error"] = str(e)[:120]
    try:
        inj = api._injuries_table(league)
        if inj is not None and not inj.empty:
            t = inj[inj["squad"] == team]
            out["injuries"] = [{"player": r.player, "injury": r.injury, "until": r.until, "source": r.source}
                               for r in t.itertuples()][:12]
        out["absence_loss"] = api._absence_loss(league).get(team)
    except Exception as e:  # noqa: BLE001
        out["injury_error"] = str(e)[:120]
    try:
        from api.services import intl as _intl  # noqa: PLC0415
        it = _intl.team_payload(team, league)
        if it.get("window"):
            out["intl"] = {"window": {k: it["window"][k] for k in ("start", "end", "label", "kind")}, "days_to": it["days_to"],
                           "squad_state": it["squad_state"], "summary": it["summary"],
                           "players": [{"player": p["player"], "nation": p["nation"], "far": p["far"],
                                        "fixtures": [f"{f['date']} {'vs' if f['home'] else '@'} {f['opp']}" for f in p["fixtures"]]}
                                       for p in it["players"]][:14]}
    except Exception as e:  # noqa: BLE001
        out["intl_error"] = str(e)[:120]
    return out


# ── 폼(P2 ⑦) — 선수·팀 '요즘 어때'. 값은 선수 표(player_frame)·일정·Elo 그대로(지어내지 않게) ─────────────────
FORM_UP, FORM_DOWN = 10, -10        # 최근 폼 지수 − 시즌 폼 지수(45~99 순위 척도)가 이만큼 벌어져야 상승·하락


def form_word(f) -> str | None:
    """폼 지수 → 화면과 같은 단어(web/lib/meaning.ts formMeaning — 72 = 중간)."""
    if f is None:
        return None
    return "절정" if f >= 90 else "좋음" if f >= 80 else "보통" if f >= 64 else "주춤" if f >= 55 else "부진"


def _form_verdict(recent, season) -> str:
    """수준(최근 5경기 폼 단어) + 방향(시즌보다 10 이상 차이일 때만). 최근 90 · 시즌 96 은 '절정'이지 하락세가 아니다."""
    if recent is None:
        return f"최근 출전 적음(시즌 폼 {form_word(season)})" if season is not None else "최근 출전 적음"
    lv = f"최근 폼 {form_word(recent)}"
    if season is None:
        return lv
    d = recent - season
    return lv + (" · 시즌보다 상승세" if d >= FORM_UP else " · 시즌보다 하락세" if d <= FORM_DOWN else " · 시즌 수준")


def _num(v):
    try:
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def player_form(player: str, club: str, league: str) -> dict:
    """선수 폼 — 최근 5경기(전 대회 FotMob 평점, 출전 시간 가중) vs 시즌 폼(리그 안 순위), 시즌 누적, 유럽 평점, OVR 추이."""
    import scout_router as sr  # noqa: PLC0415
    api = _api()
    hit = None
    if club:   # 동명이인 — 클럽을 주면 그 클럽 선수부터(parse 는 OVR 높은 쪽을 골라 Vitinha·Genoa → PSG 였다)
        key = sr._norm(player)
        for lg in (x for x in dict.fromkeys([league, *LEAGUES]) if x in LEAGUES):
            f = api._pf(lg)
            if f is None or "squad" not in f.columns:
                continue
            same = f[(f["squad"].astype(str) == club) & (f["player"].astype(str).map(sr._norm) == key)]
            if not same.empty:
                hit = {"name": str(same.iloc[0]["player"]), "squad": club, "league": lg}
                break
    hit = hit or (sr.parse(player, club or None, league).get("players") or [None])[0]
    if not hit:
        return {"error": f"선수 '{player}' 를 찾지 못했습니다"}
    lg = hit["league"]
    f = api._pf(lg)
    rows = f[(f["squad"] == hit["squad"]) & (f["player"] == hit["name"])]
    if rows.empty:
        rows = f[f["player"] == hit["name"]]
    if rows.empty:
        return {"error": f"선수 '{hit['name']}' 기록이 없습니다"}
    r = rows.iloc[0]
    rec = api._recent_of(r, lg) or {}
    season_form = api._player_form(r)
    recent_score = rec.get("score")
    tr = api._trend(r, lg)
    out = {"player": str(r["player"]), "squad": str(r["squad"]), "league": lg, "pos": api._pos_label(r),
           "ovr": api._player_ovr(r), "ovr_change_2w": tr.get("ovr_d"), "ovr_last_season": tr.get("ovr_prev"),
           # 평점 척도 — 최근 평균(avg5_fotmob)과 비교할 땐 같은 FotMob 척도의 rating_fotmob 를 쓴다(rating = 두 출처 평균, 척도 다름)
           "season": {"form": season_form, "rating_fotmob": _num(r.get("fm_rating")), "rating_two_sources": _num(r.get("ss_rating")),
                      "minutes": int(_num(r.get("minutes")) or 0), "goals": int(_num(r.get("goals")) or 0),
                      "assists": int(_num(r.get("assists")) or 0)},
           "recent": {"form": recent_score, "n": rec.get("n"), "avg5_fotmob": rec.get("avg5"), "avg3_fotmob": rec.get("avg3"),
                      "matches": [{k: m.get(k) for k in ("date", "comp_code", "opponent", "home_away", "minutes", "rating", "goals", "assists")}
                                  for m in (rec.get("matches") or [])[:5]]},
           "verdict": _form_verdict(recent_score, season_form),
           "note": "폼 지수 = 같은 리그·같은 포지션 안 순위(45~99). 평점 비교는 같은 척도끼리 — 최근 avg5_fotmob ↔ 시즌 rating_fotmob"
                   "(FotMob). rating_two_sources 는 Sofascore·FotMob 평균(다른 척도)이라 최근 평균과 직접 비교하지 않는다"}
    xs, xm = _num(r.get("x_ss_rating")), _num(r.get("x_raw_minutes"))
    if xs and xm:
        from rating_blend import FM_MU, FM_SD, SS_MU, SS_SD  # noqa: PLC0415 — 같은 FotMob 척도로 되돌려 최근 평균과 나란히
        out["europe_cups"] = {"rating_fotmob": round(FM_MU + (xs - SS_MU) * FM_SD / SS_SD, 2), "minutes": int(xm),
                              "comps": r.get("x_comps") if isinstance(r.get("x_comps"), dict) else None}
    return out


def team_form(team: str, league: str) -> dict:
    """팀 흐름 — 최근 5경기(전 대회) 결과·득실, 리그 순위·승점, 팀 Elo 와 30일 변화, 폼 좋은·떨어진 선수."""
    import datetime as dt  # noqa: PLC0415

    import datastore as ds  # noqa: PLC0415
    api = _api()
    out: dict = {"team": team, "league": league}
    try:
        done = [m for m in api.schedule(team, league).get("matches", []) if m.get("status") == "completed"][-5:]
        last = []
        gf = ga = 0
        for m in done:
            try:
                a, b = (int(x) for x in str(m.get("score") or "").split("-")[:2])
            except ValueError:
                a = b = None
            if a is not None:
                gf, ga = gf + a, ga + b          # 일정 score 는 우리 팀 기준(득-실)
            last.append({"date": m.get("date"), "opp": m.get("opponent"), "ha": m.get("home_away"), "score": m.get("score"),
                         "result": m.get("result"), "comp": m.get("comp")})
        out["last5"] = last
        out["record5"] = {"W": sum(x["result"] == "W" for x in last), "D": sum(x["result"] == "D" for x in last),
                          "L": sum(x["result"] == "L" for x in last), "gf": gf, "ga": ga}
    except Exception as e:  # noqa: BLE001
        out["last5_error"] = str(e)[:120]
    try:
        st = ds.read_table("standings", league=league)
        row = st[st["squad"] == team]
        if not row.empty:
            x = row.iloc[0]
            out["table"] = {"rank": int(x["rank"]), "points": int(x["points"]), "played": int(x["played"]), "gd": int(x["gd"])}
    except Exception as e:  # noqa: BLE001
        out["table_error"] = str(e)[:120]
    try:
        now = api._team_elo()
        ago = api._team_elo((dt.date.today() - dt.timedelta(days=30)).isoformat())
        if team in now:
            peers = set(api._pf(league)["squad"])          # 한 번만(예전엔 팀마다 다시 만들었다)
            out["elo"] = {"now": round(now[team]), "change_30d": round(now[team] - ago[team]) if team in ago else None,
                          "league_rank": 1 + sum(1 for t, v in now.items() if v > now[team] and t in peers)}
    except Exception as e:  # noqa: BLE001
        out["elo_error"] = str(e)[:120]
    try:
        f = api._pf(league)
        # 시즌 폼(_form)이 비면 int 변환에서 깨져 hot·cold 가 통째로 사라졌다 → 둘 다 있는 선수만
        t = f[(f["squad"] == team) & (f["minutes"].fillna(0) >= 270) & f["_recent"].notna() & f["_form"].notna()].copy()
        t["_d"] = t["_recent"].astype(float) - t["_form"].astype(float)
        pick = lambda d: [{"player": str(x["player"]), "recent_form": int(x["_recent"]), "season_form": int(x["_form"]),  # noqa: E731
                           "avg5_fotmob": _num(x.get("_recent_avg5"))} for _, x in d.iterrows()]
        out["hot"] = pick(t.sort_values("_recent", ascending=False).head(3))
        out["cold"] = pick(t[t["_d"] <= FORM_DOWN].sort_values("_d").head(3))
    except Exception as e:  # noqa: BLE001
        out["players_error"] = str(e)[:120]
    return out


def _slim(intent: str, r: dict) -> dict:
    """LLM 요약용으로 결과 축약(토큰 절약). 전체 결과는 프론트 카드로 별도 전달."""
    if not isinstance(r, dict):
        return {}
    if r.get("available") is False or r.get("error"):
        return {"unavailable": r.get("reason") or r.get("error")}
    if intent == "recommend":
        return {"target_roles": r.get("target_roles"),
                "picks": [{"player": x["player"], "club": x["squad"], "pos": x["pos"], "ovr": x["ovr"],
                           "style_fit": x.get("style_fit"), "proj": x.get("projected_ovr"),
                           "why": x.get("why_fit"), "cross_league": x.get("cross_league"),
                           "from": x.get("source_league")}
                          for x in (r.get("recommendations") or [])[:6]]}
    if intent == "fit":
        return {k: r.get(k) for k in ("candidate", "target_club", "role", "fit_score",
                                      "signing_type", "risk_level", "components", "notes")} | {
            "tactical": r.get("tactical_detail"), "affordability": r.get("affordability"),
            "similar": (r.get("similar_players") or [])[:3]}
    if intent == "similar":
        return {"player": r.get("player"),
                "results": [{"player": x["player"], "club": x["squad"], "pos": x["pos"],
                             "score": x.get("score")} for x in (r.get("results") or [])[:6]]}
    if intent == "managersim":
        return {k: r.get(k) for k in ("target_club", "new_manager", "vector_changes")} | {
            "misfit": (r.get("squad_misfit") or [])[:4], "priorities": (r.get("priorities") or [])[:3]}
    if intent == "identity":
        return r
    if intent == "graph":
        return {"cypher": r.get("cypher"), "count": r.get("count"),
                "rows": (r.get("rows") or [])[:15], "error": r.get("error")}
    if intent == "news":
        return {"player": r.get("player"), "total": r.get("total"),
                "articles": [{k: a.get(k) for k in ("headline", "source", "published")} for a in (r.get("articles") or [])[:6]]}
    if intent == "week":
        return {k: r.get(k) for k in ("league", "since", "risers", "fallers", "news", "intl")} | {
            "injuries": {k: (r.get("injuries") or {}).get(k) for k in ("n_new", "n_back", "new", "back")},
            "rumors": r.get("rumors")}
    return r


def answer(message: str, team: str | None = None, league: str = "EPL",
           history: list | None = None) -> dict:
    """공급자별 — gemini(무료) · openai(유료 허용 시) · rules(규칙 라우터, src/scout_router.py). LLM 이 실패하면 규칙으로."""
    prov = provider()
    if prov == "rules":
        import scout_router  # noqa: PLC0415
        return scout_router.answer(message, team, league)
    if prov == "gemini":
        try:
            return _answer_gemini(message, team, league, history)
        except Exception as e:  # noqa: BLE001 — 한도·장애면 규칙 라우터로
            import scout_router  # noqa: PLC0415
            out = scout_router.answer(message, team, league)
            out["note"] = f"Gemini 실패({str(e)[:60]}) — 규칙 기반 답"
            return out
    return _answer_openai(message, team, league, history)


def _answer_openai(message: str, team: str | None = None, league: str = "EPL",
                   history: list | None = None) -> dict:
    _load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"available": False, "reason": "OPENAI_API_KEY 미설정 — 서버 환경변수에 키 설정 후 API 재시작"}
    try:
        from openai import OpenAI
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"openai 패키지 없음: {str(e)[:60]}"}

    clubs = _clubs()
    sys_prompt = _SYSTEM + f"\n가능한 클럽: {', '.join(clubs)}"
    if team:
        sys_prompt += f"\n현재 팀 컨텍스트: {team} (리그 {league})"
    msgs = [{"role": "system", "content": sys_prompt}]
    # 대화 메모리(직전 몇 턴) — 후속 질문 맥락 유지
    for h in (history or [])[-6:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        content = str(h.get("content") or h.get("text") or "")[:1500]
        if content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": message})
    client = OpenAI(api_key=key)
    try:
        r1 = client.chat.completions.create(model=MODEL, messages=msgs, tools=TOOLS,
                                            tool_choice="auto", temperature=0)
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": f"OpenAI 오류: {str(e)[:120]}"}

    m = r1.choices[0].message
    if not m.tool_calls:
        return {"available": True, "intent": None, "answer": m.content or "", "result": None}

    tc = m.tool_calls[0]
    try:
        args = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    intent, result = _execute(tc.function.name, args, league)

    # 2차 호출: 결과에 근거한 한국어 브리핑
    msgs.append({"role": "assistant", "content": None, "tool_calls": [
        {"id": tc.id, "type": "function",
         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}]})
    msgs.append({"role": "tool", "tool_call_id": tc.id,
                 "content": json.dumps(_slim(intent, result), ensure_ascii=False)[:4000]})
    ans = ""
    try:
        r2 = client.chat.completions.create(model=MODEL, messages=msgs, temperature=0.3)
        ans = r2.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        ans = ""
    return {"available": True, "intent": intent, "args": args, "answer": ans, "result": result}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("q")
    ap.add_argument("--team", default=None)
    ap.add_argument("--league", default="EPL")
    a = ap.parse_args()
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "api"))
    import main as _  # api.main 로드(단독 실행 시 툴 실행용)  # noqa: F401
    r = answer(a.q, a.team, a.league)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
