"""
팀 대표색 — ESPN 팀 목록의 color/alternateColor 로 data/team_colors.json 을 만든다.

teammeta.TEAM_COLOR(손으로 고른 색)에 없는 팀의 대체값이다. 26/27 승격팀(포르투갈 2·벨기에 3)이
회색(#444a55)으로 나오던 것 — 시즌마다 승격팀이 바뀌어도 자동으로 채워진다.
어두운 화면에서 안 보이는 아주 어둡거나 밝은 색이면 보조색을 쓴다(예: 비세우 검정 → 빨강).

    python src/fetch_team_colors.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from espn_common import LEAGUE_CODE, squad_of  # noqa: E402

OUT = ROOT / "data" / "team_colors.json"


def _lum(hex6: str) -> float:
    try:
        r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return -1.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def pick(color: str | None, alt: str | None) -> str | None:
    """어두운 배경에서 보이는 색 — 휘도 0.08~0.92 를 우선, 아니면 보조색."""
    for c in (color, alt):
        c = (c or "").strip().lstrip("#")
        if len(c) == 6 and 0.08 <= _lum(c) <= 0.92:
            return "#" + c.upper()
    c = (color or alt or "").strip().lstrip("#")
    return "#" + c.upper() if len(c) == 6 else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out: dict[str, str] = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    n = 0
    for league, (code, _) in LEAGUE_CODE.items():
        try:
            j = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/teams", timeout=30).json()
            teams = j["sports"][0]["leagues"][0]["teams"]
        except Exception as e:  # noqa: BLE001
            print(f"[team-colors] {league} 실패: {type(e).__name__}", file=sys.stderr)
            continue
        for t in teams:
            t = t.get("team") or {}
            name = squad_of(t, league) or t.get("displayName")
            col = pick(t.get("color"), t.get("alternateColor"))
            if name and col:
                out[name] = col
                n += 1
    if not n:
        print("[team-colors] 받은 팀 없음 — 기존 파일 유지", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(dict(sorted(out.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[team-colors] {n}팀 → {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
