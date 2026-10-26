"""
실행 중 데이터 받기(Render 운영 서버) — 자주 바뀌는 파일은 재배포 대신 서버가 GitHub(공개 저장소)에서 직접 받는다.

2026-10-26: 데이터 커밋마다 Render 가 재배포해(36시간에 25번, 그중 뉴스 7번) 서버가 다시 뜨고 모든 캐시가 비었다 —
그 사이 뉴스 탭이 안 열렸다. render.yaml buildFilter 가 아래 파일만 바뀐 커밋은 재배포하지 않고, 서버가 이렇게 받는다.
  뉴스 DB   2시간마다 — 원격 data/news_db.ref.json 의 sha 가 바뀌었으면 news.db.gz 를 디스크로 받아 풀고(512MB 서버라
            메모리에 통째로 올리지 않음) data/news_view.db 만 갈아 끼운다(src/news_view.py). 뉴스 캐시만 무효화된다
  작은 파일 30분마다 — AI 뉴스 요약 · 루머 판정표 · 매체 적중률 · DATA 상태(실행 원장 · watchdog). ETag 로 바뀐 것만
  나머지 데이터 10분마다 — data-live 브랜치(scripts/publish_data.py, Publish Data 워크플로가 Render 빌드와 같은 일을 클라우드에서)의
            manifest 를 보고 바뀐 파일만 받는다. 전부 임시 파일로 받아 지문(sha256)을 맞춘 뒤 한꺼번에 바꿔 넣고(DB 마지막),
            서버 DB 가 바뀌었으면 우리 코드의 계산 캐시를 모두 비우고 미리 데우기를 다시 돌린다(재배포 때 프로세스가 새로
            뜨며 하던 일 — 이제 프로세스를 끄지 않고). render.yaml 은 data/** 만 바뀐 커밋을 재배포하지 않는다
켜는 조건: RENDER 환경변수(Render 가 넣음) 또는 LIVE_SYNC=1. 로컬·CI 는 꺼짐(git 이 최신을 준다).
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import hashlib
import os
import re
import shutil
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SMALL = ["data/ai/news_digest.json", "data/news_claims.csv", "data/news_reliability.csv", "data/ops/watchdog.json"]
SMALL_EVERY, NEWS_EVERY, DATA_EVERY, FIRST_WAIT = 30 * 60, 2 * 3600, 10 * 60, 90
DATA_BRANCH = "data-live"
STATE: dict = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "enabled": False,
               "news_sha": "", "news_at": "", "small_at": "", "small_updated": 0, "last_error": "",
               "data_sha": "", "data_at": "", "data_files": 0, "db_at": ""}
_ETAGS: dict[str, str] = {}
_HASHES: dict[str, tuple[float, int, str]] = {}        # 경로 → (수정 시각, 크기, sha256) — 같은 파일을 매번 다시 읽지 않게
_ON_DB_SWAP: list = []
# 데이터를 바꿔 넣은 뒤 비울 계산 캐시 — 우리 모듈의 lru_cache 함수 전부 + 이 이름 규칙의 dict(설정 표 같은 상수는 안 걸린다)
CACHE_NAME = re.compile(r"^_[A-Z0-9_]*(CACHE|MEMO|MEMO_LOCKS|SNAP|POOL|FRAME|CAL|TRACK|PROGRESS|CSV|PAIRS|LINKS|SCOPE)$")


def enabled() -> bool:
    return bool(os.getenv("RENDER")) or os.getenv("LIVE_SYNC") == "1"


def _raw(path: str, ref: str = "main") -> str:
    import news_store  # noqa: PLC0415
    return f"https://raw.githubusercontent.com/{news_store.repo()}/{ref}/{path}"


def _sha256(p: Path) -> str | None:
    try:
        st = p.stat()
    except OSError:
        return None
    hit = _HASHES.get(str(p))
    if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2]
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    _HASHES[str(p)] = (st.st_mtime, st.st_size, h.hexdigest())
    return h.hexdigest()


def on_db_swap(fn) -> None:
    """서버 DB 를 바꿔 넣은 뒤 부를 함수(api: 미리 데우기)."""
    _ON_DB_SWAP.append(fn)


def reset_caches(modules=None) -> int:
    """우리 코드(저장소 안 모듈)의 계산 캐시를 모두 비운다 — lru_cache 함수와 CACHE_NAME 규칙의 dict.
    · `_CACHE: dict | None` 처럼 None 이 '아직 안 읽음'인 캐시는 None 으로 되돌린다 — 빈 dict 로 비우면 '읽었음'으로 보고
      다시 안 읽어 리그 등급이 사라졌다(league_level._CACHE, 2026-10-26 테스트가 잡음)
    · {'key','body'} 꼴 dict 는 값만 비운다(코드가 그 열쇠를 바로 읽는다)
    modules: 살펴볼 모듈(테스트용, 기본 = 불러온 모든 모듈). 비운 수."""
    import sys  # noqa: PLC0415
    n = 0
    for mod in list(modules if modules is not None else sys.modules.values()):
        f = str(getattr(mod, "__file__", "") or "")
        if not f.startswith(str(ROOT)) or "site-packages" in f:
            continue
        ann = getattr(mod, "__annotations__", {}) or {}
        for k, v in list(vars(mod).items()):
            try:
                if callable(getattr(v, "cache_clear", None)) and getattr(v, "__module__", "") == mod.__name__:
                    v.cache_clear()
                    n += 1
                elif isinstance(v, dict) and CACHE_NAME.match(k):
                    a = str(ann.get(k, "")).replace(" ", "")
                    if a.endswith("|None") or a.startswith(("None|", "Optional[")):   # 맨 바깥이 '… | None' 일 때만
                        setattr(mod, k, None)
                    elif set(v) == {"key", "body"}:
                        v.update(key=None, body=None)
                    else:
                        v.clear()
                    n += 1
            except Exception:  # noqa: BLE001 — 못 비운 캐시 하나가 교체를 막지 않게
                continue
    return n


def sync_data(get=requests.get, notify: bool = True) -> int:
    """data-live 배포본에서 바뀐 파일만 받아 바꿔 넣는다. 바꾼 파일 수(0 = 그대로)."""
    r = get(_raw("manifest.json", DATA_BRANCH), timeout=30)
    if r.status_code != 200:
        return 0
    man = r.json()
    main_sha = str(man.get("main_sha") or "")
    if not main_sha or main_sha == STATE["data_sha"]:
        return 0
    files = dict(man.get("files") or {})
    db_path, db_sha = ROOT / "data" / "football.db", str(man.get("db_sha") or "")
    todo = {p: h for p, h in files.items() if _sha256(ROOT / p) != h}
    db_needed = bool(db_sha) and _sha256(db_path) != db_sha
    gz, tmp_db = db_path.with_name("football.db.gz.part"), db_path.with_name("football.db.part")
    parts: list[tuple[Path, Path]] = []
    def fetch(item):
        rel, h = item
        body = get(_raw(rel, DATA_BRANCH), timeout=60).content
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        tmp.write_bytes(body)
        parts.append((tmp, dst))                        # 지움 목록에 먼저 — 지문이 달라도 임시 파일은 치운다
        if hashlib.sha256(body).hexdigest() != h:
            raise ValueError(f"지문 다름 {rel}")

    try:
        # 1) 전부 임시 파일로 받아 지문 확인(CDN 이 옛 파일을 주면 다음 차례에) — 8개씩 동시에(한 개씩이면 677개에 7분 걸렸다)
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(fetch, todo.items()))
        if db_needed:
            with get(_raw(str(man.get("db_gz") or "data/football.db.gz"), DATA_BRANCH), stream=True, timeout=180) as resp:
                resp.raise_for_status()
                with gz.open("wb") as fh:
                    for chunk in resp.iter_content(1 << 20):
                        fh.write(chunk)
            with gzip.open(gz, "rb") as src, tmp_db.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if _sha256(tmp_db) != db_sha:
                raise ValueError("DB 지문 다름")
            parts.append((tmp_db, db_path))            # DB 는 마지막 — 같은 DB 로 만든 캐시가 먼저 자리 잡게
        for tmp, dst in parts:                         # 2) 한꺼번에 바꿔 넣기
            os.replace(tmp, dst)
    finally:
        for tmp, _ in parts:
            Path(tmp).unlink(missing_ok=True)
        gz.unlink(missing_ok=True)
        tmp_db.unlink(missing_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    STATE.update(data_sha=main_sha, data_at=now, data_files=STATE["data_files"] + len(parts))
    if db_needed:
        STATE["db_at"] = now
        n = reset_caches()
        print(f"[live-sync] 데이터 교체 {main_sha[:12]} — 파일 {len(parts)}개(DB 포함) · 캐시 {n}개 비움", flush=True)
        if notify:
            for fn in _ON_DB_SWAP:
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    print(f"[live-sync] 교체 뒤 작업 실패 {type(e).__name__}", flush=True)
    elif parts:
        print(f"[live-sync] 데이터 파일 {len(parts)}개 교체 {main_sha[:12]}", flush=True)
    return len(parts)


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
    time.sleep(FIRST_WAIT)                                        # 데우기(warm-up)가 먼저(시작 때 데이터는 데우기 전에 받는다)
    last_small = last_news = 0.0
    last_data = time.monotonic()
    while True:
        now = time.monotonic()
        try:
            if now - last_data >= DATA_EVERY:
                last_data = now
                sync_data()
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
