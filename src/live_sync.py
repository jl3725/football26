"""
실행 중 데이터 받기(Render 운영 서버) — 자주 바뀌는 파일은 재배포 대신 서버가 GitHub(공개 저장소)에서 직접 받는다.

2026-10-26: 데이터 커밋마다 Render 가 재배포해(36시간에 25번, 그중 뉴스 7번) 서버가 다시 뜨고 모든 캐시가 비었다 —
그 사이 뉴스 탭이 안 열렸다. render.yaml buildFilter 가 아래 파일만 바뀐 커밋은 재배포하지 않고, 서버가 이렇게 받는다.
  뉴스 DB   2시간마다 — 원격 data/news_db.ref.json 의 sha 가 바뀌었으면 news.db.gz 를 디스크로 받아 풀고(512MB 서버라
            메모리에 통째로 올리지 않음) data/news_view.db 만 갈아 끼운다(src/news_view.py). 뉴스 캐시만 무효화된다
  작은 파일 30분마다 — AI 뉴스 요약 · 루머 판정표 · 매체 적중률 · DATA 상태(실행 원장 · watchdog). ETag 로 바뀐 것만
켜는 조건: RENDER 환경변수(Render 가 넣음) 또는 LIVE_SYNC=1. 로컬·CI 는 꺼짐(git 이 최신을 준다).
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import shutil
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SMALL = ["data/ai/news_digest.json", "data/news_claims.csv", "data/news_reliability.csv", "data/ops/watchdog.json"]
SMALL_EVERY, NEWS_EVERY, FIRST_WAIT = 30 * 60, 2 * 3600, 90
STATE: dict = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "enabled": False,
               "news_sha": "", "news_at": "", "small_at": "", "small_updated": 0, "last_error": ""}
_ETAGS: dict[str, str] = {}


def enabled() -> bool:
    return bool(os.getenv("RENDER")) or os.getenv("LIVE_SYNC") == "1"


def _raw(path: str) -> str:
    import news_store  # noqa: PLC0415
    return f"https://raw.githubusercontent.com/{news_store.repo()}/main/{path}"


def _small_paths() -> list[str]:
    runs = sorted(f"data/ops/runs/{p.name}" for p in (DATA / "ops" / "runs").glob("*.jsonl"))
    return SMALL + runs


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(body)
    os.replace(tmp, path)


def sync_small(get=requests.get) -> int:
    """바뀐 작은 파일 수."""
    n = 0
    for rel in _small_paths():
        h = {"If-None-Match": _ETAGS[rel]} if rel in _ETAGS else {}
        try:
            r = get(_raw(rel), headers=h, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        p = ROOT / rel
        if not p.exists() or p.read_bytes() != r.content:
            _write(p, r.content)
            n += 1
        if r.headers.get("ETag"):
            _ETAGS[rel] = r.headers["ETag"]
    STATE["small_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    STATE["small_updated"] += n
    return n


def sync_news(get=requests.get) -> bool:
    """원격 뉴스 DB 가 바뀌었으면 받아서 news_view.db 를 갈아 끼운다. 바꿨으면 True."""
    import news_store  # noqa: PLC0415
    import news_view  # noqa: PLC0415
    r = get(_raw("data/news_db.ref.json"), timeout=30)
    if r.status_code != 200:
        return False
    remote = r.json()
    sha = str(remote.get("sha") or "")
    local = news_store.read_ref()
    if not sha or (sha == local.get("sha") and news_view.VIEW_DB.exists()):
        STATE["news_sha"] = sha
        return False
    url = f"https://raw.githubusercontent.com/{news_store.repo()}/{sha}/{news_store.NAME}"
    gz = DATA / "news.db.gz.part"
    db_tmp = DATA / "news.db.part"
    try:
        with get(url, stream=True, timeout=180) as resp:          # 디스크로 흘려 받기(메모리 X)
            resp.raise_for_status()
            with gz.open("wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
        with gzip.open(gz, "rb") as src, db_tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        if news_store.articles(db_tmp) <= 0:
            raise ValueError("기사 0건")
        os.replace(db_tmp, news_store.DB)
        news_view.build(news_store.DB, log=lambda *_: None)
        news_store.REF.write_text(json.dumps(remote, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    finally:
        gz.unlink(missing_ok=True)
        db_tmp.unlink(missing_ok=True)
    import datastore as ds  # noqa: PLC0415
    ds.forget(ds.NEWS_TABLES)                                     # 옛 뉴스 표 사본을 메모리에서 바로 내린다
    STATE["news_sha"] = sha
    STATE["news_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print(f"[live-sync] 뉴스 갱신 {sha[:12]} — 기사 {remote.get('articles')}건", flush=True)
    return True


def _loop() -> None:
    time.sleep(FIRST_WAIT)                                        # 데우기(warm-up)가 먼저
    last_small = last_news = 0.0
    while True:
        now = time.monotonic()
        try:
            if now - last_news >= NEWS_EVERY:
                last_news = now
                sync_news()
            if now - last_small >= SMALL_EVERY:
                last_small = now
                sync_small()
        except Exception as e:  # noqa: BLE001 — 받기 실패는 다음 차례에(서비스엔 영향 없음)
            STATE["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"[live-sync] 실패 {STATE['last_error']}", flush=True)
        time.sleep(60)


def start() -> bool:
    if not enabled() or STATE["enabled"]:
        return False
    STATE["enabled"] = True
    threading.Thread(target=_loop, name="live-sync", daemon=True).start()
    return True
