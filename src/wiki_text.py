"""
위키 소개 첫 문장 다듬기 — 화면에 보이는 2줄을 원어 표기·생년월일 괄호가 차지하지 않게.

2026-10-23 사용자 "글이 너무 많다": 감독 소개가 '미켈 아르테타 아마트리아인(스페인어: Mikel Arteta Amatriain,
1982년 3월 26일 산세바스티안 ~ )은 …'으로 시작해 접힌 2줄 대부분이 괄호였다. 클럽도 '(영어: Arsenal Football Club→…)'.
규칙: 첫 문장 안의 괄호 중 '언어 이름:'·연도·로마자·'~' 를 담은 것만 지운다(뜻이 있는 짧은 한글 괄호는 남김).
수집본(bio_ko·desc_ko)은 그대로 두고 API 가 내보낼 때만 적용 — 감독·클럽·대표팀 어느 원천이든 같은 규칙.
"""
from __future__ import annotations

import re

_PAREN = re.compile(r"\s*[(（]([^()（）]{0,200})[)）]")
# 괄호 속이 원어·생몰·발음 표기인지 — '스페인어:', '1982년', 로마자 단어, '~'·'–'(생몰 범위), IPA
_NOISE = re.compile(r"[가-힣]{1,6}어\s*[:：]|\d{3,4}년|[A-Za-zÀ-ÿ]{3,}|[~–]|\[|ˈ")
_FIRST_END = re.compile(r"(다|요)\.\s")


def tidy_intro(text: str | None) -> str:
    """첫 문장 안의 원어·생년월일 괄호를 지운다. 둘째 문장부터는 손대지 않는다."""
    if not text:
        return text or ""
    t = str(text)
    m = _FIRST_END.search(t)
    cut = m.end() if m else len(t)
    head, rest = t[:cut], t[cut:]
    head = _PAREN.sub(lambda p: "" if _NOISE.search(p.group(1)) else p.group(0), head)
    head = re.sub(r"\s{2,}", " ", head).strip()
    return (head + (" " + rest.lstrip() if rest.strip() else "")).strip()
