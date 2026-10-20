"""
news.db 보관소 — main 이력 밖의 `data-news` 브랜치에 압축본 한 개(news.db.gz)만, 매번 덮어쓴다.

왜: news.db(약 45MB sqlite)를 2시간마다 main 에 커밋해 저장소 이력의 99%(749개 버전, 원본 9GB)가 이 파일이었다(2026-10-21).
어떻게:
  push  (daily_news 만) VACUUM → gzip → 부모 없는 커밋 하나로 data-news 에 강제 푸시 → main 에는 포인터
        data/news_db.ref.json(그 커밋 sha·크기·기사 수)만 커밋. Render 는 이 main 커밋으로 다시 배포하며 정확히 그 sha 를 받는다
        (브랜치 주소는 raw CDN 이 몇 분 옛것을 줄 수 있어 sha 주소가 먼저).
  pull  news.db 가 없으면 포인터의 sha → 브랜치 머리 → git fetch 순으로 받아 풀어 둔다. build_db·watchdog·build_kg 가 부른다.
안전: push 는 기사 수가 직전(포인터)보다 20% 넘게 줄면 거부(빈 DB 로 덮어쓰기 방지). daily_news 는 시작할 때 pull --strict.

    python src/news_store.py pull [--force] [--strict]
    python src/news_store.py push
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "news.db"
REF = ROOT / "data" / "news_db.ref.json"
BRANCH = "data-news"
NAME = "news.db.gz"
MIN_RATIO = 0.8


def repo() -> str:
    """owner/name — Actions 는 GITHUB_REPOSITORY, 아니면 origin 주소에서."""
    if os.getenv("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True,
                             timeout=10).stdout.strip()
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return "jl3725/football26"


def read_ref() -> dict:
    try:
        return json.loads(REF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def articles(path: Path) -> int:
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return int(c.execute("SELECT count(*) FROM articles").fetchone()[0])
        finally:
            c.close()
    except sqlite3.Error:
        return 0


def _install(gz_bytes: bytes, src: str) -> bool:
    """압축본을 풀어 검사(articles 표가 있고 비지 않음)한 뒤 data/news.db 로 바꿔 넣는다."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=DB.parent)
    os.close(fd)
    tmp_p = Path(tmp)
    try:
        tmp_p.write_bytes(gzip.decompress(gz_bytes))
        n = articles(tmp_p)
        if n <= 0:
            print(f"[news-store] {src}: 기사 0건 — 버림")
            return False
        os.replace(tmp_p, DB)
        print(f"[news-store] 받음 {src} — 기사 {n}건 · {DB.stat().st_size / 1e6:.1f}MB")
        return True
    except (OSError, EOFError, gzip.BadGzipFile) as e:
        print(f"[news-store] {src}: 풀기 실패 {type(e).__name__}")
        return False
    finally:
        tmp_p.unlink(missing_ok=True)


def pull(force: bool = False, strict: bool = False) -> bool:
    """news.db 가 없으면(force 면 늘) 보관소에서 받는다. 받았거나 이미 있으면 True."""
    if DB.exists() and not force:
        return True
    import requests  # noqa: PLC0415
    ref = read_ref()
    urls = []
    if ref.get("sha"):
        urls.append(f"https://raw.githubusercontent.com/{repo()}/{ref['sha']}/{NAME}")
    urls.append(f"https://raw.githubusercontent.com/{repo()}/{BRANCH}/{NAME}")
    for u in urls:
        try:
            r = requests.get(u, timeout=180)
            if r.ok and _install(r.content, u.rsplit("/", 2)[-2][:12]):
                return True
            print(f"[news-store] {u} → HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"[news-store] {u} → {type(e).__name__}")
    try:   # 마지막 — git 으로(비공개 저장소·raw 차단 대비)
        subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", BRANCH], cwd=ROOT, check=True, timeout=300)
        blob = subprocess.run(["git", "show", f"FETCH_HEAD:{NAME}"], cwd=ROOT, check=True, capture_output=True,
                              timeout=120).stdout
        if _install(blob, f"git {BRANCH}"):
            return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[news-store] git fetch 실패: {type(e).__name__}")
    if strict:
        raise SystemExit("[news-store] news.db 를 받지 못함 — 빈 DB 로 시작하면 보관소를 덮어쓰므로 멈춤")
    return False


def ensure() -> Path | None:
    """읽는 쪽(build_db·watchdog·build_kg) — 있으면 그대로, 없으면 받아 본다."""
    return DB if pull() else None


def _git(*args: str, data: bytes | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": os.getenv("GIT_AUTHOR_NAME", "github-actions[bot]"),
           "GIT_AUTHOR_EMAIL": os.getenv("GIT_AUTHOR_EMAIL", "github-actions[bot]@users.noreply.github.com")}
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    return subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True, check=True, env=env,
                          timeout=600).stdout.decode().strip()


def push(min_ratio: float = MIN_RATIO) -> dict:
    """data/news.db → data-news 브랜치(부모 없는 커밋 하나, 강제 푸시) + 포인터 갱신. 포인터는 main 커밋에 넣는다."""
    if not DB.exists():
        raise SystemExit("[news-store] data/news.db 없음 — 올릴 것이 없다")
    n = articles(DB)
    prev = int(read_ref().get("articles") or 0)
    if prev and n < prev * min_ratio:
        raise SystemExit(f"[news-store] 기사 {n}건 < 직전 {prev}건의 {min_ratio:.0%} — 덮어쓰기 거부")
    c = sqlite3.connect(DB)
    try:
        c.execute("VACUUM")                       # 지운 Google 기사(30일) 자리를 비워 압축본을 작게
    finally:
        c.close()
    with tempfile.TemporaryDirectory() as td:
        gz = Path(td) / NAME
        with DB.open("rb") as src, gzip.open(gz, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        size = gz.stat().st_size
        blob = _git("hash-object", "-w", str(gz))
    tree = _git("mktree", data=f"100644 blob {blob}\t{NAME}\n".encode())
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    commit = _git("commit-tree", tree, "-m", f"news.db {now} · 기사 {n}건")
    _git("push", "-f", "-q", "origin", f"{commit}:refs/heads/{BRANCH}")
    ref = {"sha": commit, "branch": BRANCH, "file": NAME, "bytes": size, "db_bytes": DB.stat().st_size,
           "articles": n, "updated": now}
    REF.write_text(json.dumps(ref, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[news-store] 올림 {commit[:12]} — 기사 {n}건 · 압축 {size / 1e6:.1f}MB (DB {ref['db_bytes'] / 1e6:.1f}MB)")
    return ref


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else ""
    if cmd == "pull":
        return 0 if pull(force="--force" in args, strict="--strict" in args) else 1
    if cmd == "push":
        push()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
