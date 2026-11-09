"""
실행 중 데이터 받기(Render 운영 서버) — 자주 바뀌는 파일은 재배포 대신 서버가 GitHub(공개 저장소)에서 직접 받는다.

2026-10-26: 데이터 커밋마다 Render 가 재배포해(36시간에 25번, 그중 뉴스 7번) 서버가 다시 뜨고 모든 캐시가 비었다 —
그 사이 뉴스 탭이 안 열렸다. render.yaml buildFilter 가 아래 파일만 바뀐 커밋은 재배포하지 않고, 서버가 이렇게 받는다.
  뉴스 DB   2시간마다 — 원격 data/news_db.ref.json 의 sha 가 바뀌었으면 news.db.gz 를 디스크로 받아 풀고(512MB 서버라
            메모리에 통째로 올리지 않음) data/news_view.db 만 갈아 끼운다(src/news_view.py). 뉴스 캐시만 무효화된다
  작은 파일 30분마다 — AI 뉴스 요약 · 루머 판정표 · 매체 적중률 · DATA 상태(실행 원장 · watchdog). ETag 로 바뀐 것만
  나머지 데이터 3분마다 — data-live 브랜치(scripts/publish_data.py, Publish Data 워크플로가 Render 빌드와 같은 일을 클라우드에서)의
            manifest 를 보고 바뀐 파일만 받는다. 전부 임시 파일로 받아 지문(sha256)을 맞춘 뒤 한꺼번에 바꿔 넣고(DB 마지막),
            서버 DB 가 바뀌었으면 우리 코드의 계산 캐시를 모두 비우고 미리 데우기를 다시 돌린다(재배포 때 프로세스가 새로
            뜨며 하던 일 — 이제 프로세스를 끄지 않고). render.yaml 은 data/** 만 바뀐 커밋을 재배포하지 않는다.
            확인은 브랜치 머리 커밋만(head — git 목록 1KB) 보고, 받을 때는 그 커밋 번호 주소로 — 브랜치 이름 주소는 raw CDN 이
            5분까지 옛것을 줘서 10분 주기에 최대 15분 늦었다(2026-10-29 사용자 '실시간 느낌')
켜는 조건: RENDER 환경변수(Render 가 넣음) 또는 LIVE_SYNC=1. 로컬·CI 는 꺼짐(git 이 최신을 준다).
Render 빌드도 DB 를 새로 만들지 않고 이것으로 받는다(scripts/fetch_live_data.py).
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
# 작은 파일(실행 원장 등)은 10분마다 — 30분이면 DATA STATUS 가 그만큼 늦었고, 서버가 깨어난 직후엔 배포 시점(하루 전) 원장으로
# 계산해 '지연 19건'으로 보였다(2026-11-05 사용자). 화면이 열릴 때도 5분 넘게 묵었으면 바로 받는다(refresh_small)
SMALL_EVERY, NEWS_EVERY, DATA_EVERY, FIRST_WAIT = 10 * 60, 2 * 3600, 3 * 60, 90
SMALL_FRESH = 5 * 60
_SMALL_LOCK = threading.Lock()
# 스스로 깨어 있기 — Render 무료 서버는 15분 동안 들어오는 요청이 없으면 잠들고(깨는 데 30~60초 + 데우기), 10분마다 깨우기로 한
# GitHub 작업(keep_alive.yml)은 실제로 6~8시간에 한 번만 돌았다(2026-11-05 사용자 '오래 안 켜면 죽나요'). 자기 공개 주소
# (Render 가 넣는 RENDER_EXTERNAL_URL)로 8분마다 /api/health 를 불러 들어오는 요청을 만든다
SELF_PING_EVERY = 8 * 60
# 실행 중 DB 교체 최소 간격 · 데우는 중엔 교체 미룸 — 교체마다 캐시를 다 비우고 다시 데우는데(운영 0.1 CPU 로 수 분),
# 경기일엔 배포본이 10~15분마다 바뀌어(11/1 하루 29번) 서버가 거의 늘 데우는 중이었고, 데우기가 겹치면 메모리가 넘쳐
# 재시작됐다(2026-11-03 사용자 '운영이 자꾸 느리고 안 뜬다'). 방금 경기 평점(JUST PLAYED)은 Vercel 이 따로 받아 영향 없음
SWAP_MIN_GAP = 20 * 60
# 배포본 캐시가 다른 코드로 만든 것이면 DB 교체를 이만큼까지 미룬다 — 캐시 없이 바꾸면 서버가 0.1 CPU 로 선수 표·세부 지표를
# 직접 다시 만든다. 평소 배포본은 운영 코드로 캐시를 만들어(scripts/cache_code.py) 지문이 다른 건 배포 전후 잠깐뿐
CACHE_WAIT = 2 * 3600
TRIM_EVERY = 10 * 60      # 메모리 돌려주기 주기(src/memtrim.py)
WARM_STALE = 30 * 60      # 데우기가 이보다 오래 '진행 중'이면 멈춘 것으로 보고 교체를 막지 않는다
DATA_BRANCH = "data-live"
STATE: dict = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "enabled": False,
               "news_sha": "", "news_at": "", "small_at": "", "small_updated": 0, "last_error": "",
               "data_sha": "", "data_ref": "", "data_caches": True, "data_at": "", "data_files": 0, "db_at": "",
               "warming": False, "warm_at": "", "warm_sec": None, "swap_wait": "", "swaps_deferred": 0,
               "ping_at": "", "pings": 0, "ping_fail": 0}
_WARM_T0: list[float] = []
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


def head(branch: str = DATA_BRANCH, get=requests.get) -> str:
    """브랜치 머리 커밋 — git 스마트 HTTP 목록(github.com/…git/info/refs). raw CDN 처럼 묵지 않고 REST API 처럼 시간당
    60회 한도(Render 는 나가는 IP 를 여럿이 같이 쓴다)도 없다. 못 읽으면 ''(호출하는 쪽이 브랜치 이름 주소로)."""
    import news_store  # noqa: PLC0415
    try:
        r = get(f"https://github.com/{news_store.repo()}.git/info/refs?service=git-upload-pack", timeout=20)
        if r.status_code != 200:
            return ""
        m = re.search(rf"([0-9a-f]{{40}}) refs/heads/{re.escape(branch)}(?![\w/-])", r.content.decode("latin-1"))
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001 — 못 보면 예전 방식으로
        return ""


# 마지막으로 맞춘 배포본(data-live 커밋·main 커밋) 기록 — 빌드에서 받은 그대로 뜬 서버가 시작할 때 900개 파일·DB(70MB)
# 지문을 다시 계산하지 않게(0.1 CPU 에서 데우기를 늦춘다). 디스크가 이 기록보다 새것이면 머리 커밋이 달라 어차피 다시 맞춘다
def _mark() -> Path:
    return ROOT / "data" / "runtime_cache" / "live_sync.json"


def _load_mark() -> None:
    if STATE["data_ref"] or STATE.get("mark_read"):
        return
    STATE["mark_read"] = True
    try:
        m = json.loads(_mark().read_text(encoding="utf-8"))
        if m.get("code_sig") == _code_sig():                    # 다른 코드가 남긴 기록(캐시 판단이 달랐다)은 안 믿는다
            STATE.update(data_ref=str(m.get("ref") or ""), data_sha=str(m.get("main_sha") or ""),
                         data_caches=bool(m.get("caches", True)))
    except (OSError, ValueError):
        pass


def _save_mark() -> None:
    try:
        _mark().parent.mkdir(parents=True, exist_ok=True)
        _mark().write_text(json.dumps({"ref": STATE["data_ref"], "main_sha": STATE["data_sha"], "caches": STATE["data_caches"],
                                    "code_sig": _code_sig(), "at": STATE["data_at"]}), encoding="utf-8")
    except OSError:
        pass


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


def warming(on: bool, sec: float | None = None) -> None:
    """api 미리 데우기 시작·끝 — 데우는 중엔 DB 교체를 미룬다(swap_wait)."""
    STATE["warming"] = on
    if on:
        _WARM_T0[:] = [time.monotonic()]
    else:
        STATE["warm_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        STATE["warm_sec"] = None if sec is None else round(sec, 1)


def swap_wait(now: dt.datetime | None = None) -> str:
    """지금 DB 를 바꿔 넣으면 안 되는 이유('' = 바꿔도 됨) — 데우는 중 · 직전 교체 SWAP_MIN_GAP 안."""
    if STATE.get("warming") and _WARM_T0 and time.monotonic() - _WARM_T0[0] < WARM_STALE:
        return "warming"
    if STATE.get("db_at"):
        try:
            last = dt.datetime.fromisoformat(STATE["db_at"])
        except ValueError:
            return ""
        if ((now or dt.datetime.now(dt.timezone.utc)) - last).total_seconds() < SWAP_MIN_GAP:
            return "gap"
    return ""


def _swapped_within(sec: float) -> bool:
    """직전 DB 교체가 sec 초 안인가(시작 뒤 아직 교체 전이면 False — 너무 오래 미루지 않게)."""
    try:
        last = dt.datetime.fromisoformat(STATE["db_at"]) if STATE.get("db_at") else None
    except ValueError:
        return False
    return last is not None and (dt.datetime.now(dt.timezone.utc) - last).total_seconds() < sec


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


_SIG: list[str] = []


def _code_sig() -> str:
    """이 서버 코드의 지문(src/code_sig.py) — 실행 중엔 코드가 안 바뀌므로 한 번만 계산."""
    if not _SIG:
        from code_sig import code_sig  # noqa: PLC0415
        _SIG.append(code_sig(ROOT))
    return _SIG[0]


def sync_data(get=requests.get, notify: bool = True) -> int:
    """data-live 배포본에서 바뀐 파일만 받아 바꿔 넣는다. 바꾼 파일 수(0 = 그대로).
    실행 중(notify=True)엔 데우는 중이거나 직전 교체가 SWAP_MIN_GAP 안이면 다음 차례로 미룬다(시작 때는 바로)."""
    wait = swap_wait() if notify else ""
    STATE["swap_wait"] = wait
    if wait:
        STATE["swaps_deferred"] += 1
        return 0
    _load_mark()
    ref = head(get=get)
    if ref and ref == STATE["data_ref"]:
        return 0                                                  # 배포본 그대로 — manifest 도 안 받는다
    at = ref or DATA_BRANCH                                       # 커밋 번호 주소 = CDN 이 옛것을 줄 일 없음
    r = get(_raw("manifest.json", at), timeout=30)
    if r.status_code != 200:
        return 0
    man = r.json()
    main_sha = str(man.get("main_sha") or "")
    if not main_sha or main_sha == STATE["data_sha"]:
        STATE["data_ref"] = ref
        return 0
    files = dict(man.get("files") or {})
    # 캐시(선수 표·OVR 등)는 만든 코드가 이 서버 코드와 같을 때만 받는다 — 모델만 바뀐 배포 직후 서버가 새 코드로 만든 캐시를
    # 옛 코드의 캐시로 덮어쓰던 것(2026-10-27). 안 받으면 DB 가 바뀔 때 이 서버가 자기 코드로 다시 만든다.
    caches = man.get("code_sig") == _code_sig()
    if not caches:
        files = {p: h for p, h in files.items() if not p.startswith("data/runtime_cache/") and p != "data/team_units.json"}
    db_path, db_sha = ROOT / "data" / "football.db", str(man.get("db_sha") or "")
    db_needed = bool(db_sha) and _sha256(db_path) != db_sha
    if notify and db_needed and not caches and _swapped_within(CACHE_WAIT):
        STATE["swap_wait"] = "caches"                              # 이 서버 코드의 캐시가 올 때까지(최대 CACHE_WAIT)
        STATE["swaps_deferred"] += 1
        return 0
    todo = {p: h for p, h in files.items() if _sha256(ROOT / p) != h}
    gz, tmp_db = db_path.with_name("football.db.gz.part"), db_path.with_name("football.db.part")
    parts: list[tuple[Path, Path]] = []
    def fetch(item):
        rel, h = item
        body = get(_raw(rel, at), timeout=60).content
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        tmp.write_bytes(body)
        parts.append((tmp, dst))                        # 지움 목록에 먼저 — 지문이 달라도 임시 파일은 치운다
        if hashlib.sha256(body).hexdigest() != h:
            raise ValueError(f"지문 다름 {rel}")

    try:
        # 1) 전부 임시 파일로 받아 지문 확인(머리 커밋을 못 봐 브랜치 주소로 받다 CDN 이 옛 파일을 주면 다음 차례에) — 8개씩 동시에(한 개씩이면 677개에 7분 걸렸다)
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(fetch, todo.items()))
        if db_needed:
            with get(_raw(str(man.get("db_gz") or "data/football.db.gz"), at), stream=True, timeout=180) as resp:
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
    STATE.update(data_sha=main_sha, data_ref=ref, data_caches=caches, data_at=now, data_files=STATE["data_files"] + len(parts))
    _save_mark()
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


def self_url() -> str:
    return (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_PING_URL") or "").rstrip("/")


def self_ping(get=requests.get) -> bool:
    """자기 공개 주소로 /api/health 한 번 — 잠들지 않게. 주소가 없으면(로컬) 아무것도 안 한다."""
    url = self_url()
    if not url:
        return False
    try:
        ok = get(f"{url}/api/health", timeout=30).status_code == 200
    except requests.RequestException:
        ok = False
    STATE["ping_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    STATE["pings" if ok else "ping_fail"] += 1
    return ok


def refresh_small(max_age: float = SMALL_FRESH) -> bool:
    """DATA STATUS 처럼 작은 파일(실행 원장)을 바로 읽는 화면이 열릴 때 — 마지막 받은 지 max_age 초가 넘었으면 지금 받는다.
    이미 받는 중이면(다른 요청·루프) 기다리지 않고 지나간다. 받았으면 True."""
    if not enabled():
        return False
    at = STATE.get("small_at") or ""
    if at:
        try:
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(at)).total_seconds()
            if age < max_age:
                return False
        except ValueError:
            pass
    if not _SMALL_LOCK.acquire(blocking=False):
        return False
    try:
        sync_small()
        return True
    except Exception as e:  # noqa: BLE001
        STATE["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return False
    finally:
        _SMALL_LOCK.release()


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
    url = f"https://raw.githubusercontent.com/{news_store.repo()}/{sha}/{news_store.archive_name(remote)}"   # gz | xz
    gz = DATA / "news.db.gz.part"
    db_tmp = DATA / "news.db.part"
    try:
        with get(url, stream=True, timeout=180) as resp:          # 디스크로 흘려 받기(메모리 X)
            resp.raise_for_status()
            with gz.open("wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
        with news_store.open_archive(gz) as src, db_tmp.open("wb") as dst:
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
    last_data = last_trim = last_ping = time.monotonic()
    while True:
        now = time.monotonic()
        if now - last_ping >= SELF_PING_EVERY:
            last_ping = now
            self_ping()
        try:
            if now - last_small >= SMALL_EVERY:                    # 작은 파일 먼저 — 몇 초면 끝나 DATA STATUS 가 바로 맞는다
                last_small = now
                with _SMALL_LOCK:
                    sync_small()
            if now - last_data >= DATA_EVERY:
                last_data = now
                sync_data()
            if now - last_news >= NEWS_EVERY:
                last_news = now
                sync_news()
        except Exception as e:  # noqa: BLE001 — 받기 실패는 다음 차례에(서비스엔 영향 없음)
            STATE["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"[live-sync] 실패 {STATE['last_error']}", flush=True)
        if now - last_trim >= TRIM_EVERY:                          # 요청이 쓰고 놓은 메모리도 주기적으로(src/memtrim.py)
            last_trim = now
            try:
                import memtrim  # noqa: PLC0415
                memtrim.trim()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(60)


def start() -> bool:
    if not enabled() or STATE["enabled"]:
        return False
    STATE["enabled"] = True
    threading.Thread(target=_loop, name="live-sync", daemon=True).start()
    return True
