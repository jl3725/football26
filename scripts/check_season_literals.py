"""
화면에 나가는 코드에 시즌 문구가 박혀 있는지 검사(CI) — "25/26" 같은 문자열이 시즌이 바뀌어도 남는 것을 막는다.

배경: 2026-10 시즌 전환 뒤에도 홈 상단·사이드바에 '25/26' 이 남아 있었다. 시즌 표시는 항상
/api/context(data_season·window.label) 나 leagues.SEASON_START 에서 받아 써야 한다.

검사 대상: web/app·web/components·web/lib(.ts/.tsx — 주석 제외), api/(.py — 주석·독스트링 제외)
잡는 형태: 25/26 · 2025-26 · 2025/26 · 2025–26 · 2025_2026
예외: 해당 줄에 `season-literal-ok` 주석을 달면 통과(의도된 과거 시즌 표기 등).

사용: python scripts/check_season_literals.py   # 위반이 있으면 종료코드 1
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAT = re.compile(r"(?<![\d/.:-])(?:\d{2}/\d{2}|20\d{2}\s?[-–/_]\s?(?:20)?\d{2})(?![\d/:-]|\.\d)")
OK = "season-literal-ok"


def _season_like(s: str) -> bool:
    """날짜(10/13)·비율 등과 구분 — 앞뒤 해가 이어지는 쌍(25/26, 2025-26)만 시즌으로 본다."""
    for m in PAT.finditer(s):
        a, b = re.split(r"\s?[-–/_]\s?", m.group(0))
        if int(a[-2:]) + 1 == int(b[-2:]) % 100 or (int(a[-2:]) == 99 and b[-2:] == "00"):
            return True
    return False


def _strip_ts_comments(src: str) -> list[str]:
    """// 줄 주석과 /* */ 블록 주석을 공백으로 지운 줄 목록(문자열 안의 // 는 보존 — URL 등)."""
    out, i, n = [], 0, len(src)
    buf, quote = [], None
    while i < n:
        c = src[i]
        if quote:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            buf.append(c)
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            buf.append("\n" * src.count("\n", i, j))
            i = j
            continue
        else:
            buf.append(c)
        i += 1
    out = "".join(buf).split("\n")
    return out


def scan_ts(path: Path) -> list[tuple[int, str]]:
    raw = path.read_text(encoding="utf-8").split("\n")
    code = _strip_ts_comments("\n".join(raw))
    return [(i + 1, raw[i].strip()) for i, line in enumerate(code)
            if _season_like(line) and OK not in raw[i]]


def scan_py(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8")
    raw = src.split("\n")
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                docs.add(id(body[0].value))
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
                and _season_like(node.value) and OK not in raw[node.lineno - 1]):
            hits.append((node.lineno, raw[node.lineno - 1].strip()))
    return hits


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = [p for d in ("web/app", "web/components", "web/lib") for p in (ROOT / d).rglob("*.ts*")
             if "node_modules" not in p.parts]
    files += list((ROOT / "api").rglob("*.py"))
    bad = []
    for p in sorted(files):
        hits = scan_py(p) if p.suffix == ".py" else scan_ts(p)
        bad += [(p.relative_to(ROOT).as_posix(), ln, s) for ln, s in hits]
    for f, ln, s in bad:
        print(f"{f}:{ln}: {s[:140]}")
    if bad:
        print(f"\n[FAIL] 시즌 문구 하드코딩 {len(bad)}곳 — /api/context(data_season) 나 leagues.SEASON_START 에서 "
              f"받아 쓰거나, 의도된 표기면 줄에 '{OK}' 주석을 다세요.")
        return 1
    print(f"[OK] 시즌 문구 하드코딩 없음 ({len(files)}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
