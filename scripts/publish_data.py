"""
데이터 배포본 — 서버 DB·미리 계산한 캐시·데이터 파일을 data-live 브랜치(이력 없는 커밋 하나)에 올린다. 운영 서버가 바뀐 파일만
받아 교체한다(src/live_sync.py). 코드 배포와 데이터 갱신을 나눈다.

2026-10-26: 데이터 커밋마다 Render 가 재배포했다(3일 72번, 하루 24번) — 서버가 다시 뜨고 캐시가 비어 첫 화면이 느렸고, 그 사이
뉴스 탭이 안 열렸다. 이제 render.yaml 이 data/** 만 바뀐 커밋은 재배포하지 않고, 이 스크립트(Publish Data 워크플로)가
Render 빌드와 같은 일(build_db · precompute_team_units)을 클라우드에서 해서 올린다.

data-live 트리
  manifest.json          main 커밋 · 만든 시각 · 파일별 sha256 · DB 묶음(football.db 의 sha256)
  data/…                 데이터 파일(main 에서 추적하는 것 — 서버가 따로 받는 뉴스·운영 기록 제외)
  data/football.db.gz    서버 DB(압축)
  data/team_units.json · data/runtime_cache/*.pkl   같은 DB 로 만든 캐시 — DB 가 바뀔 때만 새로(아니면 이전 것 그대로)
  web/vercel.json        이 브랜치는 웹 빌드 안 함

    python scripts/publish_data.py [--dry-run]     (먼저 SKIP_NEWS=1 build_db.py · precompute_team_units.py)
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "data-live"
DB = ROOT / "data" / "football.db"
DB_GZ = "data/football.db.gz"
# 서버가 따로 받는 것(src/live_sync.py SMALL · 뉴스 포인터)·서버가 직접 쓰는 것(Ask Scout 사용량) — 배포본에서 뺀다
EXCLUDE_PREFIX = ("data/ops/", "data/ai/usage_")
EXCLUDE = {"data/news_db.ref.json", "data/ai/news_digest.json", "data/news_claims.csv", "data/news_reliability.csv"}
VERCEL_SKIP = '{\n  "git": {"deploymentEnabled": false},\n  "ignoreCommand": "exit 0"\n}\n'


def _git(*args: str, data: bytes | None = None, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True, check=True,
                          env={**os.environ, **(env or {})}).stdout.decode().strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def data_files() -> list[str]:
    """main 이 추적하는 데이터 파일 중 배포본에 넣을 것."""
    out = []
    for p in _git("ls-files", "data").splitlines():
        if p in EXCLUDE or p.startswith(EXCLUDE_PREFIX) or not (ROOT / p).exists():
            continue
        out.append(p)
    return out


def db_group() -> list[str]:
    """DB 와 같이 가야 하는 캐시(같은 DB 로 만든 것만 서버가 쓴다 — api/services/player_data.same_build)."""
    files = ["data/team_units.json"] if (ROOT / "data" / "team_units.json").exists() else []
    return files + sorted(f"data/runtime_cache/{p.name}" for p in (ROOT / "data" / "runtime_cache").glob("*.pkl"))


def remote_state() -> tuple[str | None, dict]:
    """(data-live 커밋, manifest) — 없으면 (None, {})."""
    try:
        _git("fetch", "-q", "--depth=1", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
        commit = _git("rev-parse", f"refs/remotes/origin/{BRANCH}")
        return commit, json.loads(_git("show", f"{commit}:manifest.json"))
    except (subprocess.CalledProcessError, ValueError):
        return None, {}


def plan(local: dict[str, str], db_sha: str, remote: dict) -> dict:
    """무엇을 새로 올리나 — {'changed': [...], 'db_changed': bool}. 순수 함수(테스트용)."""
    rfiles = remote.get("files") or {}
    db_changed = remote.get("db_sha") != db_sha
    changed = [p for p, h in local.items() if rfiles.get(p) != h]
    removed = [p for p in rfiles if p not in local and not p.startswith(("data/runtime_cache/", "data/team_units.json"))]
    return {"changed": changed, "removed": removed, "db_changed": db_changed}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry = "--dry-run" in sys.argv
    if not DB.exists():
        print("[publish-data] data/football.db 없음 — 먼저 SKIP_NEWS=1 python scripts/build_db.py")
        return 1
    main_sha = _git("rev-parse", "HEAD")
    files = {p: sha256(ROOT / p) for p in data_files()}
    db_sha = sha256(DB)
    rcommit, remote = remote_state()
    pl = plan(files, db_sha, remote)
    if not pl["changed"] and not pl["removed"] and not pl["db_changed"]:
        print(f"[publish-data] 바뀐 것 없음 — 올리지 않음(data-live {str(rcommit)[:12]})")
        return 0
    print(f"[publish-data] 데이터 파일 {len(pl['changed'])}개 바뀜 · 지움 {len(pl['removed'])} · DB {'바뀜' if pl['db_changed'] else '그대로'}")
    if dry:
        return 0
    names = list(files)                                # 경로 → blob sha (한 번에 — 파일 870개를 하나씩 부르면 느리다)
    entries: dict[str, str] = dict(zip(names, _git("hash-object", "-w", "--stdin-paths",
                                                   data="\n".join(names).encode()).splitlines()))
    if pl["db_changed"] or not rcommit:
        with tempfile.TemporaryDirectory() as td:
            gz = Path(td) / "football.db.gz"
            with DB.open("rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            entries[DB_GZ] = _git("hash-object", "-w", str(gz))
        group = {p: sha256(ROOT / p) for p in db_group()}
        gnames = list(group)
        entries.update(zip(gnames, _git("hash-object", "-w", "--stdin-paths", data="\n".join(gnames).encode()).splitlines()))
    else:                                              # DB 그대로 — 이전 배포본의 DB·캐시 묶음을 그대로 둔다
        group = {p: h for p, h in (remote.get("files") or {}).items()
                 if p.startswith("data/runtime_cache/") or p == "data/team_units.json"}
        ls = _git("ls-tree", "-r", rcommit)
        for line in ls.splitlines():
            meta, path = line.split("\t", 1)
            if path == DB_GZ or path in group:
                entries[path] = meta.split()[2]
    manifest = {"main_sha": main_sha, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "db_sha": db_sha, "db_gz": DB_GZ, "files": {**files, **group}}
    entries["manifest.json"] = _git("hash-object", "-w", "--stdin",
                                    data=(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode())
    entries["web/vercel.json"] = _git("hash-object", "-w", "--stdin", data=VERCEL_SKIP.encode())
    with tempfile.TemporaryDirectory() as td:
        env = {"GIT_INDEX_FILE": str(Path(td) / "index")}
        _git("read-tree", "--empty", env=env)
        info = "".join(f"100644 {sha}\t{path}\n" for path, sha in sorted(entries.items()))
        _git("update-index", "--index-info", data=info.encode(), env=env)
        tree = _git("write-tree", env=env)
    commit = _git("commit-tree", tree, "-m", f"data-live {main_sha[:12]} · {manifest['built_at']}",
                  env={"GIT_AUTHOR_NAME": os.getenv("GIT_AUTHOR_NAME", "github-actions[bot]"),
                       "GIT_AUTHOR_EMAIL": os.getenv("GIT_AUTHOR_EMAIL", "github-actions[bot]@users.noreply.github.com"),
                       "GIT_COMMITTER_NAME": os.getenv("GIT_COMMITTER_NAME", "github-actions[bot]"),
                       "GIT_COMMITTER_EMAIL": os.getenv("GIT_COMMITTER_EMAIL", "github-actions[bot]@users.noreply.github.com")})
    _git("push", "-f", "-q", "origin", f"{commit}:refs/heads/{BRANCH}")
    print(f"[publish-data] 올림 {commit[:12]} — main {main_sha[:12]} · 파일 {len(manifest['files'])} · DB {db_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
