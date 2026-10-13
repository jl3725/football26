"""
한국어 번역 — 뉴스 헤드라인·요약, 이적 소문 제목, 감독 소개 공용. 기본 경로는 전부 무료.

공급자 순서(TRANSLATE_PROVIDER=auto, 기본)
  1. Gemini 무료 등급 — GEMINI_API_KEY 가 있을 때. 50건씩 JSON 으로 묶어 1회 요청.
     모델마다 무료 한도가 따로라, 일 한도 소진(429)·미지원(404)이면 다음 모델로 넘어간다.
  2. 구글 무료 번역(translate.googleapis.com gtx) — 여러 줄을 한 요청(~3,500자)에 묶는다.
     429 를 받으면 10분간 쓰지 않는다.
  OpenAI 는 유료라 기본 경로에 없다. TRANSLATE_PROVIDER=openai 로 명시했을 때만 쓴다.
  그 밖의 값: gemini · google(해당 공급자만), none(번역 안 함).

번역에 실패한 항목은 None 을 돌려준다. 호출부는 원문을 번역 칸에 넣지 말고 비워 둬서
다음 실행(백필)에서 다시 시도하게 해야 한다.

배경: 2026-09-13 이후 구글 무료 번역이 막혔고, 수집기가 실패 시 원문을 번역 칸에 넣어
8,317건이 '번역 완료'처럼 보였다. 또 2시간마다 이미 저장된 기사까지 전부(실행당 ~3,000건)
한 줄씩 다시 요청해 제한을 스스로 불렀다 — 호출부는 새 항목만, 묶어서 넘긴다.

사용:
    from translate import translate_many, STATS
    kos = translate_many(["Arsenal close in on ...", "El Getafe cierra ..."])   # [str | None, ...]
    print(STATS)   # 공급자별 번역 건수
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import requests

MAX_CHARS = 600          # 항목당 상한(요약이 긴 경우)
STATS: Counter = Counter()   # {"gemini": n, "google": n, "failed": n} — 실행 요약용

_SYSTEM = (
    "You translate football (soccer) news into natural Korean, as a Korean sports desk would write it. "
    "Use the conventional Korean spellings for clubs, players and coaches, "
    "keep numbers, scores and fees exact, and do not add or omit information. "
    "Input is JSON {\"items\": [...]}; reply with JSON {\"t\": [...]} with exactly the same number of "
    "strings in the same order. If an item is already Korean, return it unchanged."
)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"}


def _load_env() -> None:
    """로컬 실행 편의 — 저장소 .env 의 키를 기본값으로(이미 있으면 유지)."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _clean(text: str, max_chars: int) -> str:
    text = re.sub(r"&nbsp;|\s+", " ", text).strip()
    return text[:max_chars]


# ── 1. Gemini 무료 등급 ─────────────────────────────────────────────────────────
GEMINI_BATCH = 50
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GEMINI_GAP = float(os.getenv("GEMINI_MIN_INTERVAL", "6"))   # 무료 등급 분당 한도 여유(초)
_gemini_dead: set[str] = set()       # 이번 실행에서 한도 소진·미지원인 모델
_gemini_last = 0.0


def _gemini_models() -> list[str]:
    pref = os.getenv("GEMINI_MODEL", "")
    models = [pref] if pref else []
    models += ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-flash-lite-latest"]
    return [m for i, m in enumerate(models) if m and m not in models[:i] and m not in _gemini_dead]


def _gemini_batch(texts: list[str]) -> list[str | None] | None:
    """한 배치를 Gemini 로. 실패 시 None(배치 전체) — 다음 공급자로 넘어간다."""
    global _gemini_last
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    payload = json.dumps({"items": texts}, ensure_ascii=False)
    for model in _gemini_models():
        cfg: dict = {"temperature": 0, "responseMimeType": "application/json",
                     "responseSchema": {"type": "OBJECT", "required": ["t"],
                                        "properties": {"t": {"type": "ARRAY", "items": {"type": "STRING"}}}}}
        if model == "gemini-2.5-flash":
            cfg["thinkingConfig"] = {"thinkingBudget": 0}     # 번역엔 사고 과정 불필요(한도·시간 절약)
        body = {"systemInstruction": {"parts": [{"text": _SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": payload}]}],
                "generationConfig": cfg}
        for attempt in range(3):
            wait = _GEMINI_GAP - (time.monotonic() - _gemini_last)
            if wait > 0:
                time.sleep(wait)
            _gemini_last = time.monotonic()
            try:
                r = requests.post(_GEMINI_URL.format(model=model), json=body, timeout=120,
                                  headers={"x-goog-api-key": key})
            except requests.RequestException as e:
                print(f"  [translate] Gemini {model} 연결 실패({attempt + 1}/3): {type(e).__name__}")
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                print(f"  [translate] Gemini 키 거부({r.status_code}) — 이번 실행에서 Gemini 사용 중단")
                _gemini_dead.update(_gemini_models())
                return None
            if r.status_code in (400, 404):
                print(f"  [translate] Gemini {model} 사용 불가({r.status_code}) — 다음 모델: {r.text[:120]}")
                _gemini_dead.add(model)
                break
            if r.status_code == 429:
                if "PerDay" in r.text or attempt == 2:          # 일 한도 소진 → 다음 모델(한도가 모델별)
                    print(f"  [translate] Gemini {model} 무료 한도 소진 — 다음 모델")
                    _gemini_dead.add(model)
                    break
                time.sleep(30)                                  # 분당 한도 → 잠시 쉬고 재시도
                continue
            if r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                out = json.loads("".join(p.get("text", "") for p in parts)).get("t")
            except (KeyError, IndexError, ValueError, AttributeError):
                out = None
            if isinstance(out, list) and len(out) == len(texts):
                return [str(x).strip() or None for x in out]
            print(f"  [translate] Gemini {model} 응답 형식 불일치({attempt + 1}/3)")
    return None


# ── 2. 구글 무료 번역(gtx) ──────────────────────────────────────────────────────
GOOGLE_CHARS = 3500                  # 한 요청에 묶는 글자 수(URL 길이 여유)
_GTX = "https://translate.googleapis.com/translate_a/single"
_google_dead_until = 0.0


def _google_request(q: str) -> str | None:
    global _google_dead_until
    if time.monotonic() < _google_dead_until:
        return None
    try:
        r = requests.get(_GTX, params={"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": q},
                         headers=_UA, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"HTTP {r.status_code}")
        r.raise_for_status()
        out = "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
        time.sleep(1.0)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  [translate] Google 실패 — 10분간 중단: {type(e).__name__}: {str(e)[:80]}")
        _google_dead_until = time.monotonic() + 600
        return None


def _google_batch(texts: list[str]) -> list[str | None]:
    """여러 줄을 줄바꿈으로 묶어 한 번에. 줄 수가 어긋나는 묶음은 한 줄씩 다시."""
    out: list[str | None] = [None] * len(texts)
    groups, cur, size = [], [], 0
    for i, t in enumerate(texts):
        if cur and size + len(t) + 1 > GOOGLE_CHARS:
            groups.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(t) + 1
    if cur:
        groups.append(cur)
    for g in groups:
        res = _google_request("\n".join(texts[i] for i in g))
        if res is None:
            break                                   # 막혔으면 나머지는 다음 실행에
        lines = [s.strip() for s in res.split("\n")]
        if len(lines) == len(g):
            for i, s in zip(g, lines):
                out[i] = s or None
            continue
        for i in g:                                 # 줄이 합쳐지거나 쪼개진 묶음 → 한 줄씩
            s = _google_request(texts[i])
            out[i] = s.strip() if s and s.strip() else None
    return out


# ── 3. OpenAI(유료 — 명시적으로 켰을 때만) ─────────────────────────────────────
OPENAI_BATCH = 40


def _openai_batch(texts: list[str]) -> list[str | None] | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client = OpenAI(timeout=60)
    payload = json.dumps({"items": texts}, ensure_ascii=False)
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model=os.getenv("TRANSLATE_MODEL", "gpt-4o-mini"), temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": payload}],
            )
            out = json.loads(r.choices[0].message.content or "{}").get("t")
            if isinstance(out, list) and len(out) == len(texts):
                return [str(x).strip() or None for x in out]
        except Exception as e:  # noqa: BLE001
            print(f"  [translate] OpenAI 실패({attempt + 1}/3): {type(e).__name__}: {str(e)[:120]}")
            time.sleep(3 * (attempt + 1))
    return None


def translate_many(texts: list[str], max_chars: int = MAX_CHARS) -> list[str | None]:
    """여러 문자열 → 한국어. 빈 문자열은 빈 문자열, 실패는 None."""
    _load_env()
    provider = os.getenv("TRANSLATE_PROVIDER", "auto").lower()
    out: list[str | None] = [t if not (t and t.strip()) else None for t in texts]
    todo = [i for i, t in enumerate(texts) if t and t.strip()]
    if provider == "none" or not todo:
        return out
    clean = {i: _clean(texts[i], max_chars) for i in todo}

    if provider == "openai":
        for b in range(0, len(todo), OPENAI_BATCH):
            chunk = todo[b:b + OPENAI_BATCH]
            res = _openai_batch([clean[i] for i in chunk]) or [None] * len(chunk)
            for i, s in zip(chunk, res):
                out[i] = s
            STATS["openai"] += sum(1 for s in res if s)
    else:
        if provider in ("auto", "gemini"):
            for b in range(0, len(todo), GEMINI_BATCH):
                chunk = todo[b:b + GEMINI_BATCH]
                res = _gemini_batch([clean[i] for i in chunk])
                if res is None:
                    break                           # 키 없음·한도 소진 → 남은 건 구글로
                for i, s in zip(chunk, res):
                    out[i] = s
                STATS["gemini"] += sum(1 for s in res if s)
        rest = [i for i in todo if out[i] is None]
        if rest and provider in ("auto", "google"):
            res = _google_batch([clean[i] for i in rest])
            for i, s in zip(rest, res):
                out[i] = s
            STATS["google"] += sum(1 for s in res if s)
    STATS["failed"] += sum(1 for i in todo if out[i] is None)
    return out


def translate_one(text: str, max_chars: int = MAX_CHARS) -> str | None:
    return translate_many([text], max_chars)[0]
