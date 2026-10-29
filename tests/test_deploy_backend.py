"""백엔드 배포 판단(scripts/deploy_backend.py) — 코드가 그대로면 배포 안 함(빌드 분 아낌, 2026-10-29 자동 배포 끔)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deploy_backend as db  # noqa: E402


def _c(sha: str) -> dict:
    return {"sha": sha, "commit": {"committer": {"date": "2026-10-29T00:00:00Z"}}}


def test_has_code(monkeypatch) -> None:
    assert db.has_code("abc1234", None)                              # 백엔드 커밋을 못 찾으면 배포 안 함
    assert not db.has_code("", _c("f" * 40))                         # 운영 커밋을 모르면 배포
    assert db.has_code("abc1234", _c("abc1234" + "0" * 33))          # 같은 커밋
    monkeypatch.setattr(db, "_gh", lambda path, **kw: {"status": "ahead" if path.endswith("...new1234") else "behind"})
    assert db.has_code("new1234", _c("old" + "0" * 37))              # 운영이 최신 백엔드 커밋 뒤(데이터 커밋 위)
    assert not db.has_code("old1234", _c("new" + "0" * 37))


def test_backend_paths_cover_build_and_code_sig() -> None:
    # 빌드가 쓰는 스크립트·코드 지문(src/code_sig.py)에 든 스크립트가 바뀌어도 배포해야 한다
    for p in ("api", "src", "requirements.txt", "render.yaml", "scripts/fetch_live_data.py",
              "scripts/build_db.py", "scripts/precompute_team_units.py"):
        assert p in db.BACKEND_PATHS
