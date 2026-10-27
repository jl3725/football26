"""
SCOUT TAKE — 선수 화면 맨 위 한줄평(평가 한 줄 + 근거 한 줄) + 강점·약점·역할 칩.

2026-10-27 사용자: 주 사용자는 팬, 느낌은 고급 스카우트 리포트 — '쿠냐 87 왜?' 같은 질문에 화면이 바로 답하게.
문장은 AI 가 쓴다(사용자: '룰베이스는 싫다'). 규칙은 쓸 사실(facts)과 관점 힌트(scene)만 고른다 — 숫자·순위·역할·팀 순위는
화면과 같은 값(선수 API 응답)에서만. 무료 Gemini(src/llm.py)가 선수마다 후보 3개를 좋은 순으로 쓰고, 검증(check)을 넘은 첫 후보를
쓴다: 사실에 없는 숫자·영문 이름, '~다/~요' 끝(사용자: '명사체로'), 길이, 보고서 말투, 근거 없는 '가장·최고·1위·정상급'.
검증을 넘은 문장이 없으면 화면엔 문장 없이 칩만(규칙 문장으로 채우지 않는다). 칩은 숫자 그대로라 규칙.

매일(daily_data) 바뀐 선수만 다시 쓴다 — 상황·등급·폼 단계·골·도움·배지·역할이 바뀌었거나 지난 문장의 숫자가 지금과 안 맞을 때.
OVR 높은 선수부터, 하루 호출 상한 안에서. → data/ai/scout_takes.json(데이터 배포본으로 서버에), API 는 읽기만.

    python src/scout_take.py --build [--leagues EPL,LaLiga] [--max-calls 120]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

OUT = ROOT / "data" / "ai" / "scout_takes.json"
PROMPT_VERSION = "9"
DAILY_CALLS = 120         # 하루 호출 상한(무료 키를 번역·Ask Scout·경기 리포트와 나눔) — 한 번에 BATCH_AI 명
BATCH_AI = 6              # 10명 묶음은 시간 초과·빠진 선수가 잦았다(2026-10-27 시험)
RETRY_WAIT = (12,)        # 시간 초과·503 이면 한 번만 쉬고 다시(llm.generate 가 이미 다음 모델로 넘어감)
TIMEOUT = 45
KEEP_DAYS = 60

POS = {"ATT": "공격수", "MID": "미드필더", "DEF": "수비수", "GK": "골키퍼"}
BAND = [(90, "월드클래스"), (86, "엘리트"), (82, "상위 주전급"), (77, "주전급"), (72, "로테이션급"), (65, "스쿼드 자원"), (0, "검증 전")]
FORM = [(90, "절정"), (80, "좋음"), (64, "보통"), (55, "주춤"), (0, "부진")]
BENCH_ROLES = {"로테이션", "백업", "주변 자원", "컵 전용"}
# 역할 이름의 뜻(ratings_v3.role_tag) — AI 가 '주전·유럽 로테이션'을 '주전과 로테이션을 오가는'으로 읽었다(하베르츠 리그 7/8 선발)
ROLE_DESC = {"핵심 주전": "리그와 유럽대항전 모두 주전", "주전·유럽 로테이션": "리그는 주전, 유럽대항전에선 로테이션",
             "리그 주전": "리그 주전", "로테이션": "리그에서 선발과 교체를 오감", "유망주 출전": "어린 선수로 출전 기회를 받는 중",
             "컵 전용": "컵 대회 위주로 출전", "백업": "주로 벤치", "주변 자원": "출전이 거의 없음"}

# 관점 힌트 — AI 에게 '이 선수는 이런 상황'이라고만 알려 준다(문장 틀이 아님)
SCENES = {
    "young": "출전이 적은 어린 유망주 — 평가가 아직 이르다",
    "injury_return": "부상으로 빠진 경기가 많아 출전 시간이 적다 — 출전 수가 아니라 부상·복귀 관점으로",
    "expensive_unproven": "몸값은 비싼데 올 시즌 보여 준 게 적다",
    "few_minutes": "올 시즌 출전 기회 자체가 적다",
    "elite_peak": "리그 정상급 선수가 올 시즌도 폼 절정",
    "elite_steady": "정상급 선수가 올 시즌도 제 몫은 한다",
    "class_slump": "클래스(등급)는 높은데 올 시즌 활약이 이름값에 못 미친다",
    "veteran_rise": "30대 베테랑이 올 시즌 기대 이상",
    "overachiever": "등급보다 올 시즌 활약이 훨씬 좋다",
    "bench_start": "건강한데 리그에선 벤치에서 시작하는 날이 많다",
    "steady_average": "선발로는 꾸준히 나오지만 존재감은 평범하다",
    "good_season": "주전으로 무난 이상의 시즌",
    "struggling": "올 시즌 고전 중",
    "steady": "무난한 시즌",
}

# 말투 예시 — 2026-10-27 사용자가 고른 표현(SCOUT TAKE 캔버스 시안)
EXAMPLES = [
    ("class_slump", "클래스는 확실, 올 시즌은 아직 이름값 부족", "평점 6.81로 리그 공격수 평균 아래 — 몸값(€75M)에 못 미치는 활약이라 OVR −1 반영"),
    ("elite_steady", "올 시즌도 제 몫은 확실히 해 주는 윙어", "4골 — 다만 최근 5경기는 주춤"),
    ("elite_peak", "지금 리그에서 가장 폼이 좋은 미드필더 중 하나", "도움 리그 1위, 평점 7.49 — 중원 배급의 중심"),
    ("steady_average", "꾸준히 선발로 나서지만, 존재감은 평범한 시즌", "평점 6.84로 리그 평균 수준 — 찬스 메이킹은 같은 포지션 하위권"),
    ("bench_start", "리그에선 벤치에서 시작하는 날이 많은 시즌", "최근 5경기는 상승세, 유럽대항전 2경기 선발"),
    ("veteran_rise", "35세에도 녹슬지 않은 클래스, 올 시즌 기대 이상", "도움 리그 1위, 평점 7.22 — 찬스 메이킹 상위 3%"),
    ("young", "16세 유망주 — 1군은 아직 맛보기 단계", "출전이 쌓이면 평가가 빠르게 바뀔 선수"),
    ("expensive_unproven", "비싼 몸값(€75M)만큼의 모습은 아직", "올 시즌 출전이 적고, 지난 시즌 평점도 6.77로 평범"),
]


def _band(v, table):
    return next(w for m, w in table if (v or 0) >= m)


def _part(p: dict, *keys: str) -> float:
    return round(sum(x["value"] for x in p.get("ovr_parts") or [] if x.get("key") in keys), 1)


def _euro_starts(p: dict) -> int:
    return sum(int(c.get("starts") or 0) for c in (p.get("comp_usage") or {}).get("comps") or []
               if str(c.get("key") or "") in ("ucl", "uel", "uecl"))


def _league_apps(p: dict) -> int | None:
    """리그 출전 경기 수 — 시즌 기록(SEASON LOG)에서 리그 경기 중 뛴 것."""
    log = (p.get("season_log") or {}).get("matches") or []
    n = sum(1 for m in log if str(m.get("comp") or "") == "리그" and (m.get("minutes") or 0) > 0)
    return n or None


def chips(p: dict) -> dict:
    """강점·약점(같은 포지션 템플릿 백분위 상·하위 30% + 리그 순위 배지)·역할 — 표본이 모자라면 강점·약점은 비운다."""
    tpl = p.get("template") or {}
    enough = bool(tpl.get("enough", True))
    radar = [r for r in p.get("radar_line") or [] if r.get("value") is not None and not r.get("low")]
    hi = [f"{r['axis']} 상위 {max(1, 100 - int(r['value']))}%" for r in sorted(radar, key=lambda r: -r["value"])[:2] if r["value"] >= 70]
    lo = [f"{r['axis']} 하위 {max(1, int(r['value']))}%" for r in sorted(radar, key=lambda r: r["value"])[:1] if r["value"] <= 30]
    badges = [f"{str(b['label']).removesuffix('왕')} 리그 {'공동 ' if b.get('tie') else ''}{b['rank']}위"   # 라이스 '도움 리그 공동 1위'
              for b in (p.get("badges") or [])[:1]] if (p.get("minutes") or 0) >= 450 else []
    cu = p.get("comp_usage") or {}
    return {"strengths": (hi + badges) if enough else [], "weaks": lo if enough else [], "thin": not enough,
            "role": cu.get("role") or "", "role_evidence": cu.get("role_evidence") or ""}


def facts(p: dict, team_rank: int | None = None, n_teams: int | None = None) -> dict:
    """화면 값(선수 API 응답)에서 문장에 쓸 사실만 — 검증(llm.problems)의 근거. 키 이름은 뜻이 드러나게(문장에 새지 않게)."""
    role = (p.get("comp_usage") or {}).get("role") or ""
    ch = chips(p)
    f = {"포지션": (p.get("template") or {}).get("ko") or POS.get(p.get("line") or "", "선수"), "line": p.get("line"),
         "OVR": p.get("ovr"), "OVR_등급": _band(p.get("ovr"), BAND), "나이": p.get("age"),
         "이번시즌_폼": p.get("form"), "이번시즌_폼_뜻": _band(p.get("form"), FORM) if p.get("form") is not None else None,
         "최근5경기_폼": (p.get("recent") or {}).get("score"),
         "이번시즌_평점": round(float(p["ss_rating"]), 2) if p.get("ss_rating") else None,
         "지난시즌_평점": (p.get("ratings") or {}).get("prev_blend"),
         "리그_골": p.get("goals") or 0, "리그_도움": p.get("assists") or 0, "리그_출전분": int(p.get("minutes") or 0),
         "리그_출전경기": _league_apps(p), "유럽대항전_선발": _euro_starts(p),
         "몸값_백만유로": int(round(p["value_eur"] / 1e6)) if (p.get("value_eur") or 0) >= 1e6 else None,
         "이번시즌_부진으로_OVR에서_뺀_점수": _part(p, "slump", "underperf") or None,
         "역할": role, "역할_뜻": ROLE_DESC.get(role), "팀": p.get("team"), "팀_리그순위": team_rank, "리그_팀수": n_teams,
         "부상_결장_경기": int((p.get("comp_usage") or {}).get("injury_missed") or 0) or None,
         "강점": ch["strengths"], "약점": ch["weaks"]}
    f["배지"] = next((s for s in ch["strengths"] if s.endswith("위")), None)
    claims = []                     # 근거 없는 최상급 표현 막기 — 허용되는 말만(check 가 다시 본다)
    if (f["OVR"] or 0) >= 86:
        claims.append("정상급")
    if (f["이번시즌_폼"] or 0) >= 97 or (f["배지"] or "").endswith(" 1위"):
        claims += ["가장", "최고"]
    if (f["배지"] or "").endswith(" 1위"):
        claims.append("1위")
    f["허용_표현"] = claims
    return {k: v for k, v in f.items() if v not in (None, "", [])}


def scene(f: dict) -> str:
    ovr, form, age = f.get("OVR") or 0, f.get("이번시즌_폼"), f.get("나이") or 0
    mins, cut = f.get("리그_출전분") or 0, f.get("이번시즌_부진으로_OVR에서_뺀_점수") or 0
    if (f.get("부상_결장_경기") or 0) >= 2 and mins < 450:
        return "injury_return"                     # 팀버·기마랑이스·수비멘디가 '로테이션 자원'으로 나왔다(부상)
    if age and age <= 21 and mins < 450:
        return "young"
    if mins < 270:
        if (f.get("유럽대항전_선발") or 0) >= 2:
            return "bench_start"                   # 리그는 벤치 시작이 많아도 유럽대항전엔 선발(에제 리그 210′ · UCL 2선발)
        return "expensive_unproven" if cut <= -0.5 and (f.get("몸값_백만유로") or 0) >= 30 else "few_minutes"
    if form is None:
        return "steady"
    if ovr >= 86 and form >= 90:
        return "elite_peak"
    if age >= 32 and form >= 85:
        return "veteran_rise"
    if ovr >= 86 and form >= 80:
        return "elite_steady"
    if ovr >= 82 and (form < 64 or (cut <= -0.5 and form < 80)):
        return "class_slump"
    if ovr < 82 and form >= 90:
        return "overachiever"
    if f.get("역할") in BENCH_ROLES and age >= 23:
        return "bench_start"
    if form < 55:
        return "struggling"
    return "steady_average" if form < 80 else "good_season"


# ── 검증 ─────────────────────────────────────────────────────────────────────
_END_BAD = re.compile(r"(다|요|니다|죠|네)[.!…]*$")
_STIFF = ("지표", "기록", "수행", "유지하며", "보여준", "보여 준 모습", "수준의", "정상급 유망주", "슬럼프", "_",
          "이번시즌", "출전분", "출전경기", "백만유로")       # 사실 이름이 문장에 샌 것('이번시즌 폼 절정'·'리그 출전분 216분')
# '리그 골 1' — 숫자가 단위 없이 낱말 뒤에 붙은 사실 이름 꼴(평점 7.26 은 자연스러워 뺌)
_LEAK = re.compile(r"(?<![가-힣])(골|도움) \d+(?!\d)(?!\s*(개|골|도움|위|경기|분))")
# 평가 방향 — 폼이 좋은데 '아쉬운 시즌'(브루노 폼 94), 폼이 나쁜데 '절정' 같은 반대 결론
_NEG = ("아쉬", "부진", "부족", "저조", "하락", "고전", "주춤", "흔들")
_POS = ("절정", "맹활약", "펄펄", "최고의 시즌", "압도")
_CLAIM = {"가장": "가장", "최고": "최고", "1위": "1위", "정상급": "정상급", "월드클래스": "정상급"}
L1_MAX, L2_MAX = 26, 55


def _strict_numbers(text: str, f: dict) -> list[str]:
    """단위가 붙은 숫자는 그 사실과 정확히 — llm.problems 는 반올림을 너그럽게 봐서(평점 6.81 ≈ 지난 시즌 7.12 → 7)
    숫자가 낡은 문장('1골'인데 지금 3골)이 통과했다. 소수는 보이는 자릿수까지 같은 사실이 있어야 한다."""
    bad = []
    nums = [v for v in _flat(f) if isinstance(v, (int, float)) and not isinstance(v, bool)]
    texts = " ".join(str(v) for v in _flat(f) if isinstance(v, str))
    ranks = {int(x) for x in re.findall(r"(\d+)위", texts)} | ({f["팀_리그순위"]} if f.get("팀_리그순위") else set())
    rules = [(r"(\d+)\s*골", {f.get("리그_골", 0)}), (r"(\d+)\s*도움|도움\s*(\d+)\s*개", {f.get("리그_도움", 0)}),
             (r"(\d+)\s*경기", {f.get("리그_출전경기"), f.get("유럽대항전_선발"), f.get("부상_결장_경기"), 5}),
             (r"(\d+)\s*위", ranks), (r"(\d+)\s*(?:′|분)", {f.get("리그_출전분")})]
    for pat, ok in rules:
        for m in re.finditer(pat, text):
            v = int(next(g for g in m.groups() if g))
            if v not in ok:
                bad.append(f"'{m.group(0).strip()}' ≠ 사실")
    for m in re.finditer(r"(?<![\d.])(\d+)\.(\d+)", text):
        d = len(m.group(2))
        if not any(abs(round(float(n), d) - float(m.group(0))) < 1e-9 for n in nums):
            bad.append(f"'{m.group(0)}' ≠ 사실")
    return bad


def _flat(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _flat(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _flat(v)
    else:
        yield x


def check(take: dict, f: dict, lines: tuple[str, ...] = ("l1", "l2")) -> list[str]:
    """문제 목록(빈 목록 = 통과): 사실에 없는 숫자·영문 이름, '~다/~요' 끝, 길이, 보고서 말투, 허용 안 된 최상급 표현."""
    import llm  # noqa: PLC0415
    bad: list[str] = []
    text = []
    for k in lines:
        s = str(take.get(k) or "").strip()
        if not s:
            return [f"{k} 빔"]
        n = L1_MAX if k == "l1" else L2_MAX
        if len(s) > n:
            bad.append(f"{k} {len(s)}자(최대 {n})")
        if _END_BAD.search(s):
            bad.append(f"{k} '~다/~요' 끝")
        text.append(s)
    joined = " ".join(text)
    bad += [f"보고서 말투 '{w}'" for w in _STIFF if w in joined]
    if _LEAK.search(joined):
        bad.append(f"사실 이름 꼴 '{_LEAK.search(joined).group(0)}'")
    l1 = str(take.get("l1") or "")
    if "l1" in lines and re.match(r"(리그\s*)?정상급", l1.strip()):
        bad.append("상투적 시작 '리그 정상급'")      # 폼 절정 선수 대부분이 같은 말로 시작했다(2026-10-27 EPL 65명)
    fw = f.get("이번시즌_폼_뜻")
    if "l1" in lines and fw in ("절정", "좋음") and any(w in l1 for w in _NEG):
        bad.append(f"폼 {fw}인데 평가가 부정")
    if "l1" in lines and fw in ("주춤", "부진") and any(w in l1 for w in _POS):
        bad.append(f"폼 {fw}인데 평가가 '절정'")
    src = {k: v for k, v in f.items() if k != "허용_표현"}
    bad += llm.problems(re.sub(r"[12]군", "", joined), src)
    bad += _strict_numbers(joined, src)
    for w, need in _CLAIM.items():
        if w in joined and need not in (f.get("허용_표현") or []):
            bad.append(f"근거 없는 '{w}'")
    return bad


# ── 생성 ─────────────────────────────────────────────────────────────────────
SYSTEM = ("너는 축구 스카우트 리포트의 한국어 카피 에디터다. 주어진 facts 에 있는 사실만 쓴다. "
          "facts 에 없는 숫자·순위·대회·선수·팀 이름을 지어내지 않는다.")
PROMPT = """선수마다 스카우트 한줄평(두 줄)을 서로 다른 관점으로 3개씩 써라. 가장 좋은 것을 맨 앞에 둔다.
JSON 으로만 답하라: {{"<id>": [{{"l1": "...", "l2": "..."}}, {{"l1": "...", "l2": "..."}}, {{"l1": "...", "l2": "..."}}], ...}}
- l1: 팬이 3초 안에 읽는 평가 한 줄 — 26자 이내, 짧고 단정하게. 이번 시즌 활약의 핵심(폼·활약이 기대·이름값 대비 어떤지)을
  말한다. 역할(주전·로테이션)만 다시 말하는 문장은 안 된다. scene_ko 는 관점 힌트 — 그 사실 범위 안에서 자연스럽게.
- l2: 근거 한 줄 — 55자 이내, '숫자 — 짧은 해석' 꼴. 숫자는 facts 에 있는 것만, 두 가지 이내. 출전 시간·경기 수처럼 매 경기
  바뀌는 숫자보다 평점·골·도움·순위·몸값을 먼저.
- l1 의 평가 방향은 facts.이번시즌_폼_뜻 과 같아야 한다(절정·좋음이면 긍정, 주춤·부진이면 아쉬움). 부상_결장_경기 가 있으면
  출전이 적은 이유는 부상 — '로테이션', '입지' 같은 말로 쓰지 않는다.
- 두 줄 모두 명사형으로 끝낸다(…시즌, …중, …단계, …부족, …반영, …상승세, …선수). '~다', '~요', '~습니다'로 끝내지 않는다.
- 단어를 끼워 맞춘 문장('엘리트급 스트라이커지만 이번 시즌은 평범') 대신 축구 기사에서 쓰는 자연스러운 표현.
- 선수 이름은 쓰지 않는다. facts 의 키 이름을 문장에 쓰지 않는다. '가장', '최고', '1위', '정상급'은 facts.허용_표현 에 있을 때만.
- '지표', '기록', '수행', '유지하며' 같은 보고서 말투는 쓰지 않는다. 포지션은 facts.포지션 그대로.
- 예시 문장을 그대로 베끼지 말고 그 선수 사실에 맞게. '리그 정상급 …'으로 시작하는 상투적인 문장 대신 그 선수만의 강점·숫자·상황으로.

말투 예시:
{examples}

선수:
{players}"""


def _examples() -> str:
    return "\n".join(f"- [{sc}] l1: {a} / l2: {b}" for sc, a, b in EXAMPLES)


def _pick(cands, f: dict) -> dict | None:
    """후보 중 검증을 넘은 첫 번째(AI 가 좋은 순으로 준다) — 예시 문장을 그대로 베낀 것은 뒤로."""
    ex = {a for _, a, _ in EXAMPLES}
    ok = [{"l1": c["l1"].strip(), "l2": c["l2"].strip()} for c in (cands if isinstance(cands, list) else [cands])
          if isinstance(c, dict) and c.get("l1") and c.get("l2") and not check(c, f)]
    ok.sort(key=lambda c: c["l1"] in ex)
    return ok[0] if ok else None


def write_ai(items: list[tuple[str, dict, str]]) -> dict[str, dict]:
    """[(id, facts, scene)] → {id: take} — 선수마다 후보 3개를 받아 검증을 넘은 것만. 빠진 선수는 혼자 한 번 더."""
    import llm  # noqa: PLC0415
    out: dict[str, dict] = {}

    def ask(part):
        players = [{"id": i, "scene_ko": SCENES[sc], "facts": f} for i, f, sc in part]
        prompt = PROMPT.format(examples=_examples(), players=json.dumps(players, ensure_ascii=False))
        for wait in (0, *RETRY_WAIT):
            if wait:
                time.sleep(wait)
            if llm.remaining() <= 0:
                return None
            got = llm.generate_json(prompt, SYSTEM, temperature=0.6, timeout=TIMEOUT)
            if isinstance(got, dict):
                return got
        return None

    def run(pool: list) -> list:
        """묶음으로 쓰고 못 쓴 선수(빠짐·셋 다 탈락·호출 한도)를 돌려준다."""
        left: list = []
        for n in range(0, len(pool), BATCH_AI):
            if llm.remaining() <= 0:
                return left + pool[n:]
            part = pool[n:n + BATCH_AI]
            got = ask(part) or {}
            for i, f, sc in part:
                t = _pick(got.get(i), f)
                if t:
                    out[i] = t
                else:
                    left.append((i, f, sc))
        return left

    # 못 쓴 선수는 끝에 모아 묶음으로 한 번 더 — 예전엔 한 명씩 다시 보내 120호출에 172명이었다(2026-10-27 CI)
    run(run(items))
    return out


# ── 저장·API ───────────────────────────────────────────────────────────────
_STABLE = ("OVR", "OVR_등급", "이번시즌_폼_뜻", "리그_골", "리그_도움", "배지", "역할", "몸값_백만유로", "지난시즌_평점",
           "이번시즌_부진으로_OVR에서_뺀_점수", "나이")


def sig(f: dict, sc: str) -> str:
    """다시 쓸지 정하는 지문 — 매 경기 바뀌는 출전 시간·평점 소수점은 빼고 상황·등급·폼 단계·골·도움·배지·역할만."""
    core = {k: f.get(k) for k in _STABLE}
    return hashlib.sha1(json.dumps([PROMPT_VERSION, sc, core], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


_TAKES_CACHE: dict = {}


def load() -> dict:
    m = OUT.stat().st_mtime if OUT.exists() else 0
    hit = _TAKES_CACHE.get("t")
    if not hit or hit[0] != m:
        try:
            data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        except (ValueError, OSError):
            data = {}
        _TAKES_CACHE["t"] = (m, data)
    return _TAKES_CACHE["t"][1]


def key_of(league: str, team: str, player: str) -> str:
    return f"{league}|{team}|{player}"


def for_payload(p: dict, league: str, team_rank: int | None = None, n_teams: int | None = None) -> dict:
    """API 용 — 저장된 AI 문장 중 지금 사실로도 맞는 것만(숫자가 낡은 근거 줄은 빼고 평가 줄만). 없으면 칩만.
    규칙 문장은 화면에 내지 않는다(2026-10-27 사용자: '룰베이스는 싫다')."""
    f = facts(p, team_rank, n_teams)
    sc = scene(f)
    hit = (load().get("takes") or {}).get(key_of(league, str(p.get("team")), str(p.get("player"))))
    take: dict = {}
    if hit and not check(hit, f):
        take = {"l1": hit["l1"], "l2": hit["l2"], "src": "ai", "at": hit.get("at")}
    elif hit and not check(hit, f, ("l1",)):
        take = {"l1": hit["l1"], "src": "ai", "at": hit.get("at")}
    return {**take, "scene": sc, **chips(p)}


def team_ranks(league: str) -> tuple[dict, int]:
    """{팀: 리그 순위}, 팀 수 — 공식 순위표(standings)."""
    import datastore as ds  # noqa: PLC0415
    t = ds.read_table("standings", league=league)
    if t is None or t.empty or "rank" not in t.columns:
        return {}, 0
    return {str(s): int(r) for s, r in zip(t["squad"], t["rank"])}, len(t)


def build(leagues: list[str] | None = None, max_calls: int = DAILY_CALLS) -> dict:
    """바뀐 선수만 AI 로 다시 쓴다(OVR 높은 선수부터) → OUT. 요약을 돌려준다."""
    import llm  # noqa: PLC0415
    from api.main import player_detail  # noqa: PLC0415
    from api.services.player_data import player_frame  # noqa: PLC0415
    from leagues import LEAGUES  # noqa: PLC0415
    takes: dict = dict(load().get("takes") or {})
    todo: list[tuple[float, str, dict, str]] = []
    seen = 0
    for lg in leagues or list(LEAGUES):
        df = player_frame(lg)
        if df is None or df.empty:
            continue
        ranks, n = team_ranks(lg)
        for r in df.itertuples():
            lf = getattr(r, "left_for", None)
            if float(getattr(r, "minutes", 0) or 0) <= 0 or (isinstance(lf, str) and lf.strip()):
                continue
            try:
                p = player_detail(str(r.squad), str(r.player), league=lg)
            except Exception:  # noqa: BLE001 — 한 선수 실패가 전체를 멈추지 않게
                continue
            seen += 1
            f = facts(p, ranks.get(str(r.squad)), n or None)
            sc = scene(f)
            k = key_of(lg, str(r.squad), str(r.player))
            old = takes.get(k)
            if old and old.get("sig") == sig(f, sc) and not check(old, f):
                continue
            todo.append((-(p.get("ovr") or 0), k, f, sc))
    todo.sort(key=lambda x: x[0])
    llm.start("scout_take", max_calls)
    made = 0
    if llm.available():
        fs = {k: (f, sc) for _, k, f, sc in todo}
        got = write_ai([(k, f, sc) for _, k, f, sc in todo])
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        for k, t in got.items():
            f, sc = fs[k]
            takes[k] = {**t, "sig": sig(f, sc), "scene": sc, "at": now}
            made += 1
    usage = llm.finish()
    keep = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    takes = {k: v for k, v in takes.items() if v.get("at", "") >= keep}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"version": PROMPT_VERSION, "takes": takes}, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {"players": seen, "todo": len(todo), "written": made, "stored": len(takes), "calls": usage.get("calls"),
               "model": usage.get("model"), "errors": usage.get("errors")}
    print(f"[scout-take] {json.dumps(summary, ensure_ascii=False)}")
    return summary


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--leagues", default="")
    ap.add_argument("--max-calls", type=int, default=DAILY_CALLS)
    a = ap.parse_args(argv)
    if a.build:
        build([x for x in a.leagues.split(",") if x] or None, a.max_calls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
