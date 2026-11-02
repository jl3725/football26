"""선수 표 CSV 칸 단위 병합(scripts/csv_cell_merge.py).

2026-11-02: 10/28 주간 빌드 뒤 TM 수집 커밋이 옛 파일로 작업하고 충돌을 줄 단위 '이번 수집 값 우선'으로 풀어, 주간 빌드가 바꾼
칸(지난 시즌 기록·FBref·팀 득실)을 옛 값으로 되돌렸다 — 스탄코비치 76 → 69.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import csv_cell_merge as cm  # noqa: E402


def _df(rows):
    return pd.DataFrame(rows, columns=["squad", "player", "prev_minutes", "tm_photo", "minutes"]).astype(str)


def test_each_side_keeps_its_own_cells() -> None:
    o = _df([["Inter", "Stanković", "", "old.png", "47"]])
    a = _df([["Inter", "Stanković", "3071", "old.png", "47"]])          # 주간 빌드: 지난 시즌 기록
    b = _df([["Inter", "Stanković", "", "new.png", "47.0"]])            # TM(옛 파일 기준): 사진만 + 표기 차이(47.0)
    m, st = cm.merge3(o, a, b)
    r = m.iloc[0]
    assert (r["prev_minutes"], r["tm_photo"], r["minutes"]) == ("3071", "new.png", "47")
    assert st["conflict"] == 0


def test_both_changed_prefers_given_side_and_rows() -> None:
    o = _df([["A", "x", "1", "", "10"], ["A", "gone", "1", "", "5"]])
    a = _df([["A", "x", "2", "", "10"], ["A", "gone", "1", "", "5"], ["A", "new_a", "", "", "1"]])
    b = _df([["A", "x", "3", "", "10"]])                                # 'gone' 을 지움(a 는 안 바꿈) → 지운다
    m, st = cm.merge3(o, a, b, prefer="b")
    assert m.set_index("player").loc["x", "prev_minutes"] == "3" and st["conflict"] == 1
    assert set(m["player"]) == {"x", "new_a"}
    assert cm.merge3(o, a, b, prefer="a")[0].set_index("player").loc["x", "prev_minutes"] == "2"


def test_git_rebase_uses_cell_merge(tmp_path) -> None:
    """실제 git rebase — 같은 행을 두 작업이 다른 칸만 바꿨을 때(예전엔 충돌 → -X theirs 로 한쪽 칸이 사라짐)."""
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    git("config", "merge.csvcells.driver", f'python "{ROOT / "scripts" / "csv_cell_merge.py"}" %O %A %B')
    (tmp_path / ".gitattributes").write_text("data/players*.csv merge=csvcells\n")
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "players_full_SerieA.csv"
    put = lambda body: f.write_bytes(("squad,player,prev_minutes,tm_photo\n" + body).encode("utf-8"))  # noqa: E731
    put("Inter,Stanković,,old.png\nInter,Lautaro,2000,l.png\n")
    git("add", "."); git("commit", "-qm", "base")
    git("checkout", "-qb", "tm")                                        # TM 작업(옛 파일 기준)
    put("Inter,Stanković,,new.png\nInter,Lautaro,2000.0,l.png\n")
    git("commit", "-qam", "tm photo")
    git("checkout", "-q", "main")                                       # 그사이 주간 빌드
    put("Inter,Stanković,3071,old.png\nInter,Lautaro,2100,l.png\n")
    git("commit", "-qam", "weekly prev")
    git("checkout", "-q", "tm")
    git("rebase", "-q", "main")
    out = pd.read_csv(f, dtype=str, keep_default_na=False).set_index("player")
    assert out.loc["Stanković", "prev_minutes"] == "3071" and out.loc["Stanković", "tm_photo"] == "new.png"
    assert out.loc["Lautaro", "prev_minutes"] == "2100"                   # 표기만 바뀐(2000 → 2000.0) 칸은 변경으로 안 본다
