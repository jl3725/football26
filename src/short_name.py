"""
짧은 이름(성) — 서버가 문장에 넣는 선수 이름(스카우트 니즈 이유·부상·시장가치 변동 …). 웹 web/lib/names.ts 와 같은 규칙.
마지막 낱말만 떼면 'van Dijk' → 'Dijk', 'Mac Allister' → 'Allister' 였다(2026-10-27 사용자).
  · 성 앞 낱말(van·de·da·dos·Mac·von·Ben …)은 성에 붙인다 — 첫 낱말(이름)은 빼고('Ben White' → 'White')
  · 꼬리말(Jr.·II)이 붙은 두 낱말 이름은 그대로, 세 낱말 이상이면 앞 성에 꼬리말
  · 성이 앞에 오는 한국식 표기('Son Heung-min' — 하이픈 뒤 소문자)는 첫 낱말
"""
from __future__ import annotations

import re

PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "dello", "degli", "dei", "di", "da", "das", "do", "dos", "du",
             "le", "la", "les", "ter", "ten", "te", "op", "het", "'t", "mac", "mc", "st", "st.", "san", "santa", "bin", "ibn",
             "ben", "al", "el", "ul", "abu", "y", "zu", "vom", "af", "av"}
SUFFIX = {"jr", "jr.", "junior", "júnior", "jnr", "ii", "iii", "iv"}
KOREAN_ORDER = re.compile(r"^[A-Z][a-z]+-[a-z]+$")


def swapped_order(name) -> str | None:
    """성 위치를 뒤집은 표기 — 'Kang-in Lee' ↔ 'Lee Kang-in'. 두 낱말이고 한쪽이 하이픈 이름(한국식 Kang-in·Woo-Yeong)일 때만.
    원천마다 성 위치가 달라(Sofascore·TM 'Kang-in Lee', 선수 표 'Lee Kang-in') 이강인·이재성·정우영의 Sofascore 평점과
    TM id 가 끊겼다(2026-11-09). 같은 팀 안에서 정확한 이름이 없을 때만 쓰는 대체 열쇠."""
    t = str(name or "").split()
    if len(t) == 2 and ("-" in t[0] or "-" in t[1]):
        return f"{t[1]} {t[0]}"
    return None


def surname(name) -> str:
    n = str(name or "").strip()
    if not n or n == "—":
        return n
    t = n.split()
    if len(t) == 1:
        return n
    if len(t) == 2 and KOREAN_ORDER.match(t[1]):
        return t[0]
    if t[-1].lower() in SUFFIX:
        return n if len(t) == 2 else f"{surname(' '.join(t[:-1]))} {t[-1]}"
    s = len(t) - 1
    while s - 1 >= 1 and t[s - 1].lower() in PARTICLES:
        s -= 1
    return " ".join(t[s:])
