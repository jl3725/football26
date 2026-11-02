"""
선수 표 CSV 칸 단위 3-way 병합 — git 병합 드라이버(.gitattributes `merge=csvcells`)이자 복구 도구.

2026-11-02: 여러 작업이 같은 선수 표(players_full_*·players_*)를 통째로 다시 쓴다 — 로컬 주간 빌드(FBref·Sofascore·지난 시즌),
로컬 Sofascore 일일, 클라우드 TM(계약·사진). 푸시 충돌을 줄 단위 '-X theirs'(이번 수집 값 우선)로 풀었더니, 옛 파일로 작업한
쪽이 이기면서 다른 작업이 바꾼 칸까지 옛 값으로 덮었다: 10/28 주간 빌드 뒤 TM 커밋 하나가 세리에A 팀 득실 470행·xG 240행·
Sofascore 평점 81행·지난 시즌 기록 68행(스탄코비치 76 → 69)을 되돌렸다.

규칙(칸마다): 한쪽만 기준(base)에서 바뀌었으면 그쪽, 둘 다 같은 값이면 그 값, 둘 다 다르게 바꿨으면 prefer 쪽.
숫자는 값으로 비교(3071 == 3071.0 — 다시 쓰며 생긴 표기 차이를 '변경'으로 보지 않는다). 행 키 = (squad, player).
키가 없거나 겹치면 0 이 아닌 값으로 끝나 git 기본 병합(줄 단위)에 맡긴다.

    git 드라이버: python scripts/csv_cell_merge.py %O %A %B      (%A 에 결과를 쓴다. rebase 에선 %B = 다시 얹는 커밋 → prefer B)
    복구:        python scripts/csv_cell_merge.py --repair <커밋> [--files glob]   (그 커밋이 바꾼 칸 중 지금도 옛 값인 것만 되살림)
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
KEY = ["squad", "player"]


def _read(src) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(src, dtype=str, keep_default_na=False)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=KEY)
    if not set(KEY) <= set(df.columns) or df.duplicated(KEY).any():
        return None
    return df


def _same(x: str, y: str) -> bool:
    if x == y:
        return True
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return False
    return fx == fy or (fx != fx and fy != fy)


def merge3(o: pd.DataFrame, a: pd.DataFrame, b: pd.DataFrame, prefer: str = "b") -> tuple[pd.DataFrame, dict]:
    """칸 단위 3-way 병합 → (결과, 통계). 행: 한쪽이 지운 행은 다른 쪽이 안 바꿨으면 지운다."""
    cols = list(a.columns) + [c for c in b.columns if c not in a.columns]
    oi, ai, bi = (x.set_index(KEY) for x in (o, a, b))
    keys = list(ai.index) + [k for k in bi.index if k not in ai.index]
    st = {"from_a": 0, "from_b": 0, "conflict": 0, "rows_dropped": 0}
    out = []
    for k in keys:
        ra = ai.loc[k] if k in ai.index else None
        rb = bi.loc[k] if k in bi.index else None
        ro = oi.loc[k] if k in oi.index else None
        if ra is None or rb is None:                      # 한쪽에만 있는 행
            only, other_dropped = (rb, ra is None) if ra is None else (ra, rb is None)
            if ro is not None and other_dropped:          # 기준에 있던 행을 다른 쪽이 지웠는데 이쪽이 안 바꿨으면 지움
                unchanged = all(_same(str(only.get(c, "")), str(ro.get(c, ""))) for c in cols if c not in KEY)
                if unchanged:
                    st["rows_dropped"] += 1
                    continue
            out.append({**dict(zip(KEY, k)), **{c: str(only.get(c, "")) for c in cols if c not in KEY}})
            continue
        row = dict(zip(KEY, k))
        for c in cols:
            if c in KEY:
                continue
            va, vb = str(ra.get(c, "")), str(rb.get(c, ""))
            vo = str(ro.get(c, "")) if ro is not None and c in ro.index else None
            if _same(va, vb):
                row[c] = va
            elif vo is not None and _same(va, vo):
                row[c] = vb
                st["from_b"] += 1
            elif vo is not None and _same(vb, vo):
                row[c] = va
                st["from_a"] += 1
            else:
                row[c] = vb if prefer == "b" else va
                st["conflict"] += 1
        out.append(row)
    return pd.DataFrame(out, columns=cols), st


def _write(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def driver(o_path: str, a_path: str, b_path: str) -> int:
    o, a, b = _read(o_path), _read(a_path), _read(b_path)
    if o is None or a is None or b is None:
        return 1                                          # 키가 없거나 겹침 — git 기본 병합으로
    merged, st = merge3(o, a, b, prefer="b")
    _write(merged, Path(a_path))
    print(f"[csv-merge] {Path(a_path).name}: 칸 병합 (최신 쪽 {st['from_a']} · 이번 커밋 {st['from_b']} · 둘 다 바꿈 {st['conflict']})",
          file=sys.stderr)
    return 0


def _show(rev: str, path: str) -> pd.DataFrame | None:
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    return _read(io.BytesIO(r.stdout)) if r.returncode == 0 else None


def repair(commit: str, pattern: str = "data/players*.csv") -> int:
    """commit 이 바꾼 칸 중 지금(작업 트리)도 그 커밋 이전 값으로 남은 것만 되살린다 — 나중에 다른 작업이 새로 바꾼 칸은 그대로."""
    files = subprocess.run(["git", "diff", "--name-only", f"{commit}^", commit, "--", pattern], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    for f in files:
        o, b, a = _show(f"{commit}^", f), _show(commit, f), _read(ROOT / f)
        if o is None or b is None or a is None:
            print(f"  건너뜀 {f}(키 없음·겹침)")
            continue
        merged, st = merge3(o, a, b, prefer="a")
        if st["from_b"]:
            _write(merged, ROOT / f)
        print(f"  {f}: 되살린 칸 {st['from_b']} · 그 뒤 바뀐 칸 유지 {st['from_a'] + st['conflict']}")
    return 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if argv and argv[0] == "--repair":
        pat = argv[argv.index("--files") + 1] if "--files" in argv else "data/players*.csv"
        return repair(argv[1], pat)
    if len(argv) != 3:
        print(__doc__)
        return 2
    return driver(*argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
