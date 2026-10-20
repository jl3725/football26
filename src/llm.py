"""
공용 Gemini(무료 등급) 호출 — 해석 계층(src/ai_notes.py 경기 리포트·뉴스 요약·주간 요약 서술, watchdog 원인 요약)이 함께 쓴다.

- 모델: 2026-10-20 실측 — gemini-3.1-flash-lite(1~2초) 우선, 막히거나 25초 넘으면 다음 모델. gemini-2.5-flash 는 신규 키 404.
- 사용량: 용도(kind)별 하루 상한을 data/ai/usage_<kind>.json 에 기록(KST 날짜별 호출 수). 상한에 닿거나
  모든 모델이 429(무료 한도 소진)면 그 실행에서는 더 부르지 않는다 — 같은 무료 키를 번역·Ask Scout 와 나눠 쓴다.
- 검증: 생성 문장의 숫자·영문 이름이 원본 사실(facts)에 있는지. 숫자는 반올림(73.8→74)·확률(0.861→86%)까지 허용.
  근거 없는 숫자·이름이 하나라도 있으면 그 문장을 버린다(지어낸 내용을 화면에 내지 않음).
GEMINI_API_KEY 가 없으면 available()=False — 호출부는 규칙 기반 문장으로 둔다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE_DIR = ROOT / "data" / "ai"
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MIN_GAP = float(os.getenv("LLM_MIN_INTERVAL", "4"))      # 무료 등급 분당 한도 여유(초)
_S = {"kind": "misc", "daily": 50, "used": 0, "calls": 0, "last": 0.0, "dead": set(), "model": None, "errors": []}


def _key() -> str | None:
    k = os.getenv("GEMINI_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def available() -> bool:
    return bool(_key())


def models() -> list[str]:
    ms = [os.getenv("GEMINI_MODEL"), "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]
    return [m for i, m in enumerate(ms) if m and m not in ms[:i]]


def _today() -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date().isoformat()


def _usage_path(kind: str) -> Path:
    return USAGE_DIR / f"usage_{kind}.json"


def start(kind: str, daily: int) -> int:
    """이 실행의 용도·하루 상한을 정하고 오늘 이미 쓴 호출 수를 읽는다. 남은 호출 수를 돌려준다."""
    used = 0
    p = _usage_path(kind)
    if p.exists():
        try:
            used = int(json.loads(p.read_text(encoding="utf-8")).get(_today(), 0))
        except (ValueError, OSError):
            used = 0
    _S.update(kind=kind, daily=int(os.getenv("LLM_DAILY_MAX", daily)), used=used, calls=0, dead=set(), errors=[])
    return remaining()


def remaining() -> int:
    if len(_S["dead"]) >= len(models()):
        return 0
    return max(0, _S["daily"] - _S["used"] - _S["calls"])


def last_model() -> str | None:
    return _S["model"]


def finish() -> dict:
    """오늘 사용량을 파일에 더해 두고(최근 14일만) 요약을 돌려준다."""
    p = _usage_path(_S["kind"])
    data: dict = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    data[_today()] = _S["used"] + _S["calls"]
    keep = sorted(data)[-14:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: data[k] for k in keep}, indent=1), encoding="utf-8")
    return {"kind": _S["kind"], "calls": _S["calls"], "today": data[_today()], "daily": _S["daily"], "model": _S["model"],
            "errors": _S["errors"][-5:]}


def generate(prompt: str, system: str | None = None, temperature: float = 0.3, json_out: bool = False,
             timeout: float = 15) -> str | None:   # 보통 1~3초 — 가끔 응답 없이 매달려(2026-10-20 실측 5/60회) 짧게
    """텍스트 한 번 생성. 키 없음·하루 상한·모든 모델 실패면 None."""
    key = _key()
    if not key or remaining() <= 0:
        return None
    import requests  # noqa: PLC0415
    body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_out:
        body["generationConfig"]["responseMimeType"] = "application/json"
    for model in models():
        if model in _S["dead"] or remaining() <= 0:
            continue
        wait = MIN_GAP - (time.time() - _S["last"])
        if wait > 0:
            time.sleep(wait)
        _S["last"] = time.time()
        _S["calls"] += 1
        try:
            r = requests.post(_URL.format(model=model), params={"key": key}, json=body, timeout=timeout)
        except requests.RequestException as e:
            _S["errors"].append(f"{model}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            _S["errors"].append(f"{model}: HTTP {r.status_code}")
            # 없는 모델·하루 무료 한도 소진이면 이 실행에선 다시 안 부름(분당 한도 429 는 다음 모델로만)
            if r.status_code == 404 or (r.status_code == 429 and "PerDay" in r.text):
                _S["dead"].add(model)
            continue
        parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if text:
            _S["model"] = model
            return text
    return None


def generate_json(prompt: str, system: str | None = None, temperature: float = 0.2):
    t = generate(prompt, system, temperature, json_out=True, timeout=30)   # 여러 팀 묶음이라 길다
    if not t:
        return None
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", t, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None


# ── 검증 ─────────────────────────────────────────────────────────────────────
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
_NAME = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž][A-Za-zÀ-ÖØ-öø-ÿĀ-ž'’_\-]{2,}")   # _ 포함 — 필드명이 새면 통째로 걸림
NAME_OK = {"VAR", "UEFA", "FIFA", "EPL", "AI"}


def _src(facts) -> str:
    """검증 근거 = 값만(키 이름은 빼서 'value_eur_m' 같은 필드명이 문장에 새면 걸리게)."""
    if isinstance(facts, dict):
        return " | ".join(_src(v) for v in facts.values())
    if isinstance(facts, (list, tuple)):
        return " | ".join(_src(v) for v in facts)
    return "" if facts is None else str(facts)


def unverified_numbers(text: str, facts) -> list[str]:
    """text 의 숫자 중 facts(문자열·dict·list)에 근거가 없는 것. 반올림·소수 한 자리·확률→퍼센트 허용."""
    ok: set[float] = set()
    for x in _NUM.findall(_src(facts).replace(",", "")):
        f = float(x)
        ok.update({f, round(f), round(f, 1)})
        if 0 < f <= 1:
            ok.update({round(f * 100), round(f * 100, 1)})
    return [x for x in _NUM.findall(str(text).replace(",", "")) if float(x) not in ok and round(float(x)) not in ok]


def unverified_names(text: str, facts) -> list[str]:
    """text 의 영문 단어(3자 이상) 중 facts 에 없는 것 — 데이터에 없는 선수·팀 이름을 지어내지 않게."""
    src = _src(facts).casefold()
    bad = []
    for w in _NAME.findall(str(text)):
        w = re.sub(r"['’]s$", "", w).strip("-'’")
        if len(w) >= 3 and w.casefold() not in src and w.upper() not in NAME_OK:
            bad.append(w)
    return bad


def problems(text: str, facts) -> list[str]:
    return unverified_numbers(text, facts) + unverified_names(text, facts)
