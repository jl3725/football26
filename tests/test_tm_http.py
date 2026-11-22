from __future__ import annotations

import pytest

import tm_http


@pytest.fixture(autouse=True)
def _no_real_stop_file(monkeypatch, tmp_path):
    """이 PC 의 .cache/tm_stopped 가 시험 결과를 바꾸지 않게."""
    monkeypatch.setattr(tm_http, "STOP_FILE", tmp_path / "tm_stopped")


class _Resp:
    def __init__(self, code: int, text: str) -> None:
        self.status_code, self.text = code, text


class _Sess:
    """첫 요청은 WAF 202(빈 본문), 토큰 발급 뒤엔 200."""
    def __init__(self) -> None:
        self.calls, self.token = 0, False
        self.headers: dict = {}

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls += 1
        return _Resp(200, '<table class="items">') if self.token else _Resp(202, "")


def test_waf_202_triggers_token_then_retry(monkeypatch) -> None:
    s = _Sess()
    monkeypatch.setattr(tm_http, "session", lambda: s)
    monkeypatch.setattr(tm_http, "_fail_streak", 0)

    def fake_refresh(url):
        s.token = True
        return True
    monkeypatch.setattr(tm_http, "refresh_token", fake_refresh)
    r = tm_http.get("https://www.transfermarkt.com/x", headers={"User-Agent": "old", "X": "1"})
    assert r.status_code == 200 and s.calls == 2
    assert tm_http._fail_streak == 0


def test_home_line_200_never_opens_browser(monkeypatch) -> None:
    s = _Sess(); s.token = True
    monkeypatch.setattr(tm_http, "session", lambda: s)

    def boom(url):
        raise AssertionError("브라우저를 열면 안 됨")
    monkeypatch.setattr(tm_http, "refresh_token", boom)
    assert tm_http.get("https://www.transfermarkt.com/x").status_code == 200 and s.calls == 1


def test_still_blocked_returns_202_and_counts_streak(monkeypatch) -> None:
    s = _Sess()
    monkeypatch.setattr(tm_http, "session", lambda: s)
    monkeypatch.setattr(tm_http, "_fail_streak", 0)
    monkeypatch.setattr(tm_http, "refresh_token", lambda url: False)
    r = tm_http.get("https://www.transfermarkt.com/x")
    assert r.status_code == 202          # 수집기의 '비정상이면 저장 안 함' 가드가 처리
    assert tm_http._fail_streak == 1


class _Captcha(_Sess):
    """AWS WAF CAPTCHA — 토큰과 상관없이 405."""
    def get(self, url, headers=None, params=None, timeout=None):
        self.calls += 1
        return _Resp(405, "<html>captcha</html>")


def test_405_streak_stops_tm_requests(monkeypatch, tmp_path) -> None:
    s = _Captcha()
    monkeypatch.setattr(tm_http, "session", lambda: s)
    monkeypatch.setattr(tm_http, "STOP_FILE", tmp_path / "tm_stopped")
    monkeypatch.setattr(tm_http, "_hard_streak", 0)
    monkeypatch.setattr(tm_http, "refresh_token", lambda url: False)
    assert tm_http.get("https://www.transfermarkt.com/a").status_code == 405
    assert not tm_http.stopped()                     # 한 번 튄 405 로는 멈추지 않음
    assert tm_http.get("https://www.transfermarkt.com/b").status_code == 405
    assert tm_http.stopped() and s.calls == 2
    r = tm_http.get("https://www.transfermarkt.com/c")   # 멈춘 뒤엔 요청을 보내지 않고 405
    assert r.status_code == 405 and s.calls == 2


def test_stop_file_from_earlier_step_skips_network(monkeypatch, tmp_path) -> None:
    s = _Sess(); s.token = True
    stop = tmp_path / "tm_stopped"
    stop.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tm_http, "session", lambda: s)
    monkeypatch.setattr(tm_http, "STOP_FILE", stop)
    assert tm_http.get("https://www.transfermarkt.com/x").status_code == 405 and s.calls == 0


def test_200_resets_405_streak(monkeypatch, tmp_path) -> None:
    s = _Sess(); s.token = True
    monkeypatch.setattr(tm_http, "session", lambda: s)
    monkeypatch.setattr(tm_http, "STOP_FILE", tmp_path / "tm_stopped")
    monkeypatch.setattr(tm_http, "_hard_streak", 1)
    assert tm_http.get("https://www.transfermarkt.com/x").status_code == 200
    assert tm_http._hard_streak == 0 and not tm_http.stopped()
