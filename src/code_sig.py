"""
캐시를 만든 코드의 지문 — data-live 배포본(scripts/publish_data.py)과 운영 서버(src/live_sync.py)가 같은 값으로 비교한다.

2026-10-27: 선수 표 캐시(data/runtime_cache/frame_*.pkl)에는 OVR 이 미리 계산돼 있는데, 배포본은 DB 가 같으면 캐시를 그대로
재사용했다 — 모델(ratings_v3)만 바뀐 날엔 옛 OVR 이 갔고, 새 코드로 막 빌드한 서버도 그 옛 캐시를 받아 덮어썼다.
지문 = 캐시를 만드는 코드(src·api 전체 + 빌드 스크립트 두 개)의 .py 내용. 줄바꿈은 LF 로 맞춘다(로컬 Windows 와 같은 값).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIRS = ("src", "api")
CODE_FILES = ("scripts/build_db.py", "scripts/precompute_team_units.py")


def code_sig(root: Path = ROOT) -> str:
    paths = [p for d in CODE_DIRS for p in (root / d).rglob("*.py") if "__pycache__" not in p.parts]
    paths += [root / f for f in CODE_FILES if (root / f).exists()]
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda q: q.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        h.update(p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()
