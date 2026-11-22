"""Transfermarkt HTTP — 클라우드에서도 열리게 하는 공통 접속.

TM(AWS WAF)은 데이터센터 IP(GitHub Actions 등)에 202 + 빈 본문(자바스크립트 확인 페이지)을 준다.
실제 브라우저(seleniumbase UC 헤드리스)로 한 번 열면 확인을 통과해 aws-waf-token 쿠키가 생기고,
이 쿠키를 requests 세션에 넘기면 일반 요청도 200 이 된다(2026-10-15 GH 러너 진단: scripts/diag_sources.py).

- 집 회선처럼 처음부터 200 이면 브라우저를 열지 않는다(기존 동작 그대로).
- 202 를 받으면 토큰을 새로 받아 한 번 더 요청한다. 토큰은 몇 분~수십 분 유효 — 만료되면 다시 받는다.
- 브라우저 기동 실패·여전히 202 면 202 응답을 그대로 돌려준다 → 각 수집기의 '비정상 응답이면 저장 안 함' 가드가 막는다.
- 받은 쿠키는 파일(TM_COOKIE_FILE, 기본 .cache/tm_cookies.json)에 남겨 같은 워크플로의 다음 수집기(별도 프로세스)가
  브라우저를 다시 열지 않고 재사용한다(리그 8 × 단계 5 = 40회 기동 방지).
- 405 는 202 와 다르다 — 사람이 푸는 확인(CAPTCHA) 단계라 풀지 않고 그 실행의 TM 요청을 멈춘다. 405 가 HARD_STREAK 번
  이어지면 멈춤 표시(TM_STOP_FILE, 기본 .cache/tm_stopped)를 남기고, 같은 실행의 다음 수집기도 표시를 보고 요청 없이 405 를
  돌려받는다. 2026-11-21 두 번 실행 도중부터 405 만 왔는데 202 만 알아봐서 1,300번 넘게 계속 요청하고 단계마다
  exit 1(빨간불)이었다. scripts/ci_try.sh 는 SOURCE_DOWN_MARK 로 이 표시를 보고 실패를 원천 중단(75)으로 적는다.
"""
from __future__ import annotations

import atexit
import json
import os
import time
from pathlib import Path

import requests

ORIGIN = "https://www.transfermarkt.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")

COOKIE_FILE = Path(os.environ.get("TM_COOKIE_FILE") or Path(__file__).resolve().parent.parent / ".cache" / "tm_cookies.json")

STOP_FILE = Path(os.environ.get("TM_STOP_FILE") or COOKIE_FILE.parent / "tm_stopped")
STOP_TTL_S = 3 * 3600    # 멈춤 표시 유효 시간 — 클라우드 러너는 실행마다 새로 시작, 집 PC 는 3시간 뒤 다시 시도

_session: requests.Session | None = None
_refreshes = 0
_fail_streak = 0
_hard_streak = 0
MAX_FAIL_STREAK = 3      # 토큰을 새로 받아도 계속 202 면 그 실행에선 더 시도하지 않는다(무한 루프 방지)
HARD_BLOCK = 405         # AWS WAF CAPTCHA — 브라우저 확인(202)과 달리 풀지 않는다
HARD_STREAK = 2          # 한 번 튄 405 로 실행 전체를 멈추지 않게 — 두 번 이어지면 멈춤


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        try:   # 앞 단계가 받아 둔 토큰 재사용
            saved = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            _session.headers["User-Agent"] = saved.get("ua") or UA
            for c in saved.get("cookies", []):
                _session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
        except (OSError, ValueError, KeyError):
            pass
        atexit.register(_session.close)
    return _session


def _blocked(r: requests.Response) -> bool:
    return r.status_code == 202 or (r.status_code == 200 and not r.text.strip())


def refresh_token(url: str = ORIGIN) -> bool:
    """브라우저로 TM 을 열어 WAF 확인을 통과하고 쿠키·UA 를 세션에 옮긴다. 성공 여부."""
    global _refreshes
    if _fail_streak >= MAX_FAIL_STREAK:
        return False
    _refreshes += 1
    try:
        import seleniumbase as sb
    except ImportError:
        print("[tm_http] seleniumbase 없음 — 토큰 발급 불가", flush=True)
        return False
    d = None
    try:
        d = sb.Driver(uc=True, headless=True)
        d.get(url)
        for _ in range(20):
            if any(c["name"] == "aws-waf-token" for c in d.get_cookies()):
                break
            time.sleep(1)
        cookies = d.get_cookies()
        if not any(c["name"] == "aws-waf-token" for c in cookies):
            print("[tm_http] aws-waf-token 을 받지 못함", flush=True)
            return False
        s = session()
        s.headers["User-Agent"] = d.execute_script("return navigator.userAgent")
        for c in cookies:
            s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
        try:
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(json.dumps({"ua": s.headers["User-Agent"], "cookies": [
                {k: c.get(k) for k in ("name", "value", "domain", "path")} for c in cookies]}), encoding="utf-8")
        except OSError:
            pass
        print(f"[tm_http] WAF 토큰 발급({_refreshes}회차)", flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[tm_http] 브라우저 토큰 발급 실패: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return False
    finally:
        if d is not None:
            try:
                d.quit()
            except Exception:  # noqa: BLE001
                pass


def stopped() -> bool:
    """이 실행(또는 3시간 안의 앞 실행)에서 TM 이 405 로 막아 요청을 멈췄는가."""
    try:
        return time.time() - STOP_FILE.stat().st_mtime < STOP_TTL_S
    except OSError:
        return False


def _stop(url: str) -> None:
    try:
        STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        STOP_FILE.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {url}\n", encoding="utf-8")
    except OSError:
        pass
    print(f"[tm_http] TM 이 {HARD_BLOCK}(CAPTCHA)로 막음 — 이 실행의 TM 요청 멈춤(원천 중단, 받은 것은 저장)", flush=True)


def _stopped_response(url: str) -> requests.Response:
    r = requests.Response()
    r.status_code, r.url, r.reason, r._content = HARD_BLOCK, url, "TM stopped (CAPTCHA)", b""
    return r


def get(url: str, headers: dict | None = None, params: dict | None = None, timeout: float = 30) -> requests.Response:
    """requests.get 대신 — WAF 202 면 토큰을 받아 한 번 더. 수집기의 기존 headers(H)는 UA 를 빼고 합친다.
    405(CAPTCHA)가 이어지면 멈춤 — 이후 요청은 보내지 않고 405 응답을 그대로 돌려준다(수집기는 실패로 건너뜀)."""
    global _fail_streak, _hard_streak
    if stopped():
        return _stopped_response(url)
    h = {k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}
    r = session().get(url, headers=h, params=params, timeout=timeout)
    if _blocked(r) and refresh_token(url):
        r = session().get(url, headers=h, params=params, timeout=timeout)
    _fail_streak = _fail_streak + 1 if _blocked(r) else 0
    _hard_streak = _hard_streak + 1 if r.status_code == HARD_BLOCK else 0
    if _hard_streak >= HARD_STREAK:
        _stop(url)
    return r
