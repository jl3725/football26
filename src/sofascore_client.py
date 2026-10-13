"""
Sofascore API 클라이언트 — 헤드리스 브라우저 경유.

2026 중 Sofascore 가 api.sofascore.com · www.sofascore.com/api 직접 요청(tls_requests 의
여러 TLS 지문 포함)에 403 "Forbidden/challenge" 를 반환하기 시작했다. seleniumbase UC 모드
브라우저로 사이트를 한 번 연 뒤 페이지 안에서 fetch() 하면 정상 응답이 온다 → 수집기의
전송 계층만 이걸로 바꾼다. soccerdata(FBref)가 이미 쓰는 seleniumbase 를 재사용하므로
추가 의존성은 없다. 로컬 전용 — GH 러너에서는 쓰지 않는다.

사용:
    from sofascore_client import get_json
    status, data = get_json("/unique-tournament/17/seasons")   # /api/v1 이하 경로
"""
from __future__ import annotations

import atexit
import json
import time

ORIGIN = "https://www.sofascore.com"
_JS_FETCH = """
const done = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: "include", headers: {"Accept": "application/json"}})
  .then(r => r.text().then(t => done([r.status, t])))
  .catch(e => done([0, String(e)]));
"""
_driver = None


def _open():
    """브라우저를 열고 사이트에 접속. 직전 단계(soccerdata)가 남긴 드라이버 정리 직후에는 첫 기동이
    실패할 수 있어 두 번 시도한다(빌드 체인에서 '시즌 id 조회 실패'로만 보이던 원인)."""
    global _driver
    import seleniumbase as sb

    last = None
    for attempt in range(2):
        try:
            if _driver is None:
                _driver = sb.Driver(uc=True, headless=True)
                _driver.set_script_timeout(40)
                atexit.register(close)
            _driver.get(ORIGIN + "/")
            time.sleep(5)          # 챌린지 쿠키가 붙을 시간
            return _driver
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[sofascore] 브라우저 기동 실패({attempt + 1}/2): {type(e).__name__}: {str(e)[:120]}", flush=True)
            close()
            time.sleep(5)
    raise RuntimeError(f"Sofascore 브라우저를 열 수 없음: {last}")


def reset() -> None:
    """사이트를 다시 열어 챌린지 쿠키를 갱신한다(403 연속 시)."""
    _open()


def get_json(path: str) -> tuple[int, dict | None]:
    """`/api/v1{path}` 응답 → (HTTP status, JSON | None). 네트워크 오류는 status 0."""
    drv = _driver or _open()
    try:
        status, body = drv.execute_async_script(_JS_FETCH, f"{ORIGIN}/api/v1{path}")
    except Exception as e:  # noqa: BLE001  — 세션이 죽었으면(드라이버 종료 등) 한 번 다시 연다
        print(f"[sofascore] 세션 오류, 재접속: {type(e).__name__}: {str(e)[:100]}", flush=True)
        close()
        drv = _open()
        status, body = drv.execute_async_script(_JS_FETCH, f"{ORIGIN}/api/v1{path}")
    if status == 200:
        try:
            return 200, json.loads(body)
        except ValueError:
            return 0, None
    return int(status or 0), None


def close() -> None:
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:  # noqa: BLE001
            pass
        _driver = None
