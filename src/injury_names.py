"""
TM 부상명 한글 표기 — 'Ankle injury' → '발목 부상'. data/injury_names_ko.json 에 한 번 옮겨 두고 API 가 읽을 때 바꾼다.

2026-10-23 사용자 "글이 너무 많다"(글 줄이기 D3): 한글 화면에 'Ankle injury'·'Thigh problems'·'23/10/2026' 이 섞여 읽기 어려웠다.
TM 부상명은 종류가 정해져 있다(전 리그 두 시즌 136종). 손으로 쓴 사전 대신, 처음 보는 이름만 무료 Gemini(축구 부상 표기 지시) →
무료 번역 체인 순서로 옮겨 저장하고, 다음부터는 저장본만 쓴다. 못 옮긴 이름은 원문 그대로 둔다(다음 실행에서 다시 시도).
수집 원본(transfermarkt_injuries 등)은 바꾸지 않는다.

사용: python src/injury_names.py            # 새 부상명만 옮겨 저장(daily_data 'injury_names' 단계)
"""
from __future__ import annotations

import glob
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "injury_names_ko.json"
_COLS = ("injury", "new_injury", "old_injury")
_PATTERNS = ("transfermarkt_injuries_*.csv", "transfermarkt_injury_changes_*.csv", "tm_injury_history_*.csv")
_HANGUL = re.compile(r"[가-힣]")

_SYSTEM = ("You translate Transfermarkt injury labels into the short Korean wording a Korean football news desk uses "
           "(e.g. 'Hamstring injury' → '햄스트링 부상', 'Cruciate ligament tear' → '십자인대 파열', 'Dead leg' → '허벅지 타박상', "
           "'Knock' → '타박상', 'Ill' → '질병', 'Fitness' → '컨디션 관리'). Keep each under 12 Korean characters, no explanations. "
           "Input JSON {\"items\": [...]}; reply JSON {\"t\": [...]} with the same count and order.")


def _load() -> dict[str, str]:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    return {k.strip().lower(): v for k, v in _load().items() if v}


def ko(name) -> str:
    """부상명 → 한글(저장본에 있으면). 이미 한글이거나 모르는 이름은 그대로."""
    s = str(name or "").strip()
    if not s or _HANGUL.search(s):
        return s
    return _table().get(s.lower(), s)


def collect(data_dir: Path | None = None) -> set[str]:
    """data/ 의 TM 부상 표에 나온 부상명 전부(한글·빈 값 제외)."""
    import pandas as pd  # noqa: PLC0415
    d = data_dir or ROOT / "data"
    names: set[str] = set()
    for pat in _PATTERNS:
        for f in glob.glob(str(d / pat)):
            try:
                t = pd.read_csv(f)
            except Exception:  # noqa: BLE001 — 깨진 파일 하나가 전체를 막지 않게
                continue
            for c in _COLS:
                if c in t.columns:
                    names.update(str(x).strip() for x in t[c].dropna() if str(x).strip())
    return {n for n in names if not _HANGUL.search(n) and n.lower() != "nan"}


def _ok(src: str, out) -> bool:
    return isinstance(out, str) and bool(_HANGUL.search(out)) and 0 < len(out.strip()) <= 20 and out.strip() != src


def _gemini(items: list[str]) -> list[str | None]:
    try:
        import llm  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return [None] * len(items)
    if not llm.available():
        return [None] * len(items)
    llm.start("injury_names", daily=6)
    out: list[str | None] = []
    for i in range(0, len(items), 60):
        chunk = items[i:i + 60]
        got = None
        if llm.remaining() > 0:
            try:
                got = llm.generate_json(json.dumps({"items": chunk}, ensure_ascii=False), system=_SYSTEM)
            except Exception:  # noqa: BLE001
                got = None
        t = (got or {}).get("t") if isinstance(got, dict) else None
        out += [x if _ok(s, x) else None for s, x in zip(chunk, t)] if isinstance(t, list) and len(t) == len(chunk) \
            else [None] * len(chunk)
    llm.finish()
    return out


def update(names: set[str] | None = None) -> tuple[int, int]:
    """새 부상명만 옮겨 저장 → (새로 옮긴 수, 아직 못 옮긴 수)."""
    have = _load()
    todo = sorted(n for n in (names if names is not None else collect()) if not have.get(n))
    if not todo:
        return 0, 0
    got = _gemini(todo)
    rest = [n for n, g in zip(todo, got) if not g]
    if rest:
        try:
            from translate import translate_many  # noqa: PLC0415
            tr = dict(zip(rest, translate_many(rest)))
        except Exception:  # noqa: BLE001
            tr = {}
        got = [g or (tr.get(n) if _ok(n, tr.get(n)) else None) for n, g in zip(todo, got)]
    n_new = 0
    for n, g in zip(todo, got):
        if g:
            have[n] = g.strip()
            n_new += 1
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(dict(sorted(have.items(), key=lambda kv: kv[0].lower())), ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    _table.cache_clear()
    return n_new, len(todo) - n_new


def main() -> int:
    n_new, n_left = update()
    print(f"injury_names: 새로 옮김 {n_new} · 못 옮김 {n_left} · 저장 {len(_load())} -> {PATH.name}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
