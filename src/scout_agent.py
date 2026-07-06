"""Ask Scout — 자연어 → 툴 라우팅(OpenAI function-calling) → 결정적 엔진 실행 → 답변+카드.

핵심: LLM은 '어느 엔진을 어떤 파라미터로 부를지' + '결과 요약'만 담당한다.
추천·수치·판단은 전부 우리 결정적 엔진(recommend/fit/similar/managersim/identity)이 낸다
→ LLM이 선수를 지어내지 않음(그동안 지켜온 정직함 유지).

로컬 전용 요소 포함(fit/managersim=Qdrant). OPENAI_API_KEY 없으면 available=False.
"""
from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TOOLS = [
    {"type": "function", "function": {
        "name": "recommend_players",
        "description": "특정 팀의 약한 포지션에 대한 영입 후보를 Qdrant 스타일-핏 기반으로 전 리그에서 추천. "
                       "'아스날 6번 추천', '우리 팀 여름 보강 우선순위' 같은 질문. role 있으면 그 역할로 좁힘.",
        "parameters": {"type": "object", "properties": {
            "team": {"type": "string", "description": "팀명(정확한 데이터 표기)"},
            "role": {"type": "string", "description": "세부 역할(선택, 예: Defensive Midfield, Centre-Back). "
                     "'6번'=Defensive Midfield, '8번'=Central Midfield, '10번'=Attacking Midfield"}},
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
]

_SYSTEM = (
    "너는 'Chief Scout' — 축구 스카우팅 AI 어시스턴트다. 사용자의 질문을 적절한 툴로 라우팅한다.\n"
    "규칙:\n"
    "- 선수·수치·추천을 절대 지어내지 마라. 모든 판단은 툴 결과에서만 온다. 툴을 반드시 호출하라.\n"
    "- 클럽명은 아래 '가능한 클럽' 목록의 정확한 표기를 써라(예: Manchester United→'Manchester Utd').\n"
    "- 답변은 한국어로, 스카우트 브리핑처럼 간결하게. 툴 결과의 근거(팀니즈·유럽검증·시장가·전술적합)를 짚어라.\n"
    "- '우리 팀'/'이 팀'은 현재 보고 있는 팀 컨텍스트를 쓴다.\n"
)


def _load_dotenv():
    """OPENAI_API_KEY 가 env 에 없으면 프로젝트 루트 .env 에서 로드(의존성 없이)."""
    if os.getenv("OPENAI_API_KEY"):
        return
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


def _execute(name: str, args: dict, league: str):
    """LLM이 고른 툴 → 결정적 엔진 함수 실행. (intent, 결과dict) 반환."""
    api = _api()
    if api is None:
        return None, {"error": "api.main 미로드"}
    if name == "recommend_players":
        import transfer_fit as tf  # Qdrant 스타일-핏 발굴(교차리그, 리그 중립)
        return "recommend", tf.discover_fits(_resolve_club(args.get("team", "")), args.get("role") or None)
    if name == "evaluate_fit":
        return "fit", api.fit(args.get("candidate", ""), _resolve_club(args.get("club", "")),
                              args.get("role", ""), "", league)
    if name == "find_similar":
        return "similar", api.similar(args.get("player", ""), True, 0.6, league)
    if name == "simulate_manager":
        return "managersim", api.managersim(_resolve_club(args.get("club", "")), args.get("manager", ""), league)
    if name == "club_identity":
        return "identity", api.identity(_resolve_club(args.get("team", "")), league)
    return None, {"error": f"알 수 없는 툴: {name}"}


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
    return r


def answer(message: str, team: str | None = None, league: str = "EPL") -> dict:
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
    msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": message}]
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
