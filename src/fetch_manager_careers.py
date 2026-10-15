"""
감독 커리어 — 위키백과 인포박스(Infobox football biography)의 감독·선수 경력 → data/manager_careers.json.

NETWORK 탭 MANAGER 렌즈(커리어 타임라인 · 같은 클럽을 거친 다른 감독 · 감독과 함께 온 선수)의 원천.
manager_profiles 에는 현재 클럽과 직전 감독만 있어 커리어 그래프를 그릴 수 없었다(2026-10-15 사용자 요청).
문서는 10개씩 묶어 요청한다(fetch_wiki_squads 와 같은 429 대응).

출력: {감독 이름: {wiki_title, managed: [{club, start, end, role}], played: [{club, start, end}], fetched}}
사용: python src/fetch_manager_careers.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_wiki_squads import _fields, _link_text, wikitexts  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "manager_careers.json"


def infobox(text: str) -> str:
    """첫 '{{Infobox football biography' 틀 본문(중괄호 짝 맞춤)."""
    m = re.search(r"\{\{\s*Infobox (?:football|soccer) biography", text, re.I)
    if not m:
        return ""
    i, depth = m.start(), 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
            continue
        if text.startswith("}}", i):
            depth -= 1
            i += 2
            if depth == 0:
                return text[m.end():i - 2]
            continue
        i += 1
    return text[m.end():]


def years(v: str) -> tuple[int | None, int | None]:
    """'2015–2018' → (2015, 2018), '2019–' → (2019, None), '2018' → (2018, 2018)."""
    t = re.sub(r"<[^>]+>|\{\{[^{}]*\}\}", "", v)
    ys = [int(y) for y in re.findall(r"(1[89]\d{2}|20\d{2})", t)]
    if not ys:
        return None, None
    if len(ys) == 1:
        return (ys[0], None) if re.search(r"[–\-]\s*$", t.strip()) else (ys[0], ys[0])
    return ys[0], ys[1]


def career(box: str) -> tuple[list[dict], list[dict]]:
    f = _fields(box)
    managed, played = [], []
    for kind, ykey, ckey, out in (("m", "manageryears", "managerclubs", managed), ("p", "years", "clubs", played)):
        for n in range(1, 40):
            c = f.get(f"{ckey}{n}")
            if c is None:
                continue
            raw = re.sub(r"<ref.*?</ref>|<ref[^>]*/>", "", c, flags=re.S)
            role = ""
            low = raw.lower()
            for k in ("caretaker", "interim", "assistant", "player-manager", "player-coach"):
                if k in low:
                    role = k
            club = re.sub(r"\s*\(.*?\)\s*", " ", _link_text(raw)).replace("→", "").strip(" ,")
            if not club or "loan" in low and kind == "p" and False:
                continue
            s, e = years(f.get(f"{ykey}{n}", ""))
            rec = {"club": club, "start": s, "end": e}
            if kind == "m":
                rec["role"] = role
            else:
                rec["loan"] = "→" in raw or "loan" in low
            out.append(rec)
    return managed, played


def managers() -> dict[str, str]:
    """현재 시즌 8개 리그 감독 → 위키 문서 제목."""
    out = {}
    for lg in LEAGUES:
        p = data_path("manager_profiles", lg, ext="json")
        if not p.exists():
            continue
        for team, m in json.loads(p.read_text(encoding="utf-8")).items():
            if isinstance(m, dict) and m.get("name"):
                out[m["name"]] = m.get("wiki_title") or m["name"]
    return out


def main() -> int:
    mgrs = managers()
    texts = wikitexts(sorted(set(mgrs.values())))
    today = dt.date.today().isoformat()
    res, miss = {}, []
    for name, title in sorted(mgrs.items()):
        box = infobox(texts.get(title, ""))
        managed, played = career(box) if box else ([], [])
        if not managed:
            miss.append(name)
        res[name] = {"wiki_title": title, "managed": managed, "played": played, "fetched": today}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[manager_careers] {len(res) - len(miss)}/{len(res)} 감독 경력 확인" + (f" · 없음 {miss[:12]}" if miss else ""))
    return 0 if len(miss) < len(res) * 0.4 else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
