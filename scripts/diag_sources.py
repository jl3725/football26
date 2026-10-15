"""클라우드(GitHub Actions) 에서 각 수집 소스가 열리는지 진단 — 로컬 예약 작업을 클라우드로 옮기기 전 확인용.

소스마다 (1) 일반 HTTP(requests) (2) 실제 브라우저(seleniumbase UC, 가상 화면 xvfb) 로 한 페이지씩만 연다.
결과는 표로 출력하고 GITHUB_STEP_SUMMARY 에도 쓴다. 데이터는 저장하지 않는다(요청 수 최소).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")
TM = "https://www.transfermarkt.com/premier-league/verletztespieler/wettbewerb/GB1"
TM2 = "https://www.transfermarkt.com/arsenal-fc/kader/verein/11/saison_id/2026/plus/1"
FBREF = "https://fbref.com/en/comps/9/Premier-League-Stats"
UNDERSTAT = "https://understat.com/league/EPL"
SOFA_API = "https://www.sofascore.com/api/v1/unique-tournament/17/seasons"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"

rows: list[tuple[str, str, str]] = []


def note(src: str, how: str, result: str) -> None:
    rows.append((src, how, result))
    print(f"[{src}] {how}: {result}", flush=True)


def http(src: str, url: str, marker: str) -> None:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=30)
        ok = marker in r.text
        note(src, "requests", f"HTTP {r.status_code} · {len(r.text):,}B · {'OK' if ok else 'marker 없음'}")
    except Exception as e:  # noqa: BLE001
        note(src, "requests", f"오류 {type(e).__name__}: {str(e)[:80]}")


def browser_checks() -> None:
    import seleniumbase as sb

    modes = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--modes=")), ["headless"])
    for mode in modes:
        # headed = 가상 화면(xvfb-run) 위의 일반 창 — Cloudflare 는 헤드리스를 더 잘 잡는다
        kw = {"uc": True, "headless": mode == "headless"}
        try:
            d = sb.Driver(**kw)
        except Exception as e:  # noqa: BLE001
            note("browser", mode, f"기동 실패 {type(e).__name__}: {str(e)[:80]}")
            continue
        try:
            # Transfermarkt — AWS WAF 챌린지를 브라우저가 풀면 표가 보인다. 쿠키를 requests 로 넘겨 두 번째 페이지도 시험.
            d.get(TM)
            for _ in range(15):
                if 'class="items"' in d.page_source:
                    break
                time.sleep(1)
            ok = 'class="items"' in d.page_source
            note("Transfermarkt", f"browser/{mode}", f"{'OK' if ok else '표 없음'} · title={d.title[:40]!r}")
            if ok:
                s = requests.Session()
                s.headers.update({"User-Agent": d.execute_script("return navigator.userAgent"), "Accept-Language": "en-US,en;q=0.9"})
                for c in d.get_cookies():
                    s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
                r = s.get(TM2, timeout=30)
                got = 'class="items"' in r.text
                names = [c["name"] for c in d.get_cookies()][:6]
                note("Transfermarkt", f"browser→requests 쿠키/{mode}", f"HTTP {r.status_code} · {'OK' if got else '표 없음'} · 쿠키 {names}")
            # FBref — Cloudflare
            d.uc_open_with_reconnect(FBREF, 6)   # UC: 드라이버 연결을 잠시 끊어 Cloudflare 검사를 통과
            for _ in range(20):
                if "stats_squads_standard_for" in d.page_source or "results20" in d.page_source:
                    break
                time.sleep(1)
            ok = "stats_squads_standard_for" in d.page_source or "results20" in d.page_source
            note("FBref", f"browser/{mode}", f"{'OK' if ok else '표 없음'} · title={d.title[:40]!r}")
            # Sofascore — 사이트를 연 뒤 브라우저 안에서 API fetch(앱의 sofascore_client 와 같은 방식)
            d.uc_open_with_reconnect("https://www.sofascore.com/", 6)
            time.sleep(4)
            res = d.execute_async_script(
                "const done = arguments[arguments.length - 1];"
                "fetch(arguments[0], {credentials: 'include', headers: {Accept: 'application/json'}})"
                ".then(async r => done([r.status, (await r.text()).slice(0, 200)])).catch(e => done([0, String(e)]));", SOFA_API)
            note("Sofascore", f"browser/{mode}", f"API HTTP {res[0]} · {'OK' if res[0] == 200 and 'seasons' in res[1] else res[1][:60]}")
        except Exception as e:  # noqa: BLE001
            note("browser", mode, f"오류 {type(e).__name__}: {str(e)[:100]}")
        finally:
            try:
                d.quit()
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    print(f"runner ip: {requests.get('https://api.ipify.org', timeout=10).text}", flush=True)
    http("ESPN(대조군)", ESPN, '"events"')
    http("Transfermarkt", TM, 'class="items"')
    http("Understat", UNDERSTAT, "<html")   # 2026 페이지는 데이터가 별도 요청 — 열림 여부만
    http("FBref", FBREF, "stats_squads_standard_for")
    http("Sofascore", SOFA_API, "seasons")
    if "--no-browser" not in sys.argv:
        browser_checks()
    md = ["| 소스 | 방식 | 결과 |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows]
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        Path(out).write_text("## 클라우드 수집 진단\n\n" + "\n".join(md) + "\n", encoding="utf-8")
    Path("diag_sources.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
