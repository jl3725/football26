"""
감독 프로필에 위키백과 기반 설명을 자동 주입한다.

핵심: 전술/포메이션은 **팀이 아니라 감독의 속성**이므로, 감독 본인 위키
문서의 '감독 전술' 섹션(Tactics / Manager profile / Managerial style ...)에서만
뽑는다. 감독이 팀을 옮겨도 그의 위키를 따라가므로 자동으로 맞다.
(선수 시절 'Style of play' 섹션은 감독 전술이 아니므로 제외.)

주입 필드:
  - bio_ko      : 한국어 위키 요약(없으면 영어 요약을 번역)
  - bio_source  : 'ko-wiki' | 'en-wiki-translated' | 'en-wiki'
  - formation   : 감독 전술 섹션에서 가장 자주 언급된 포메이션 (있으면 갱신)
  - tactics_ko  : 감독 전술 한 줄 요약(한국어)
  - tactics_source

사용:
    python src/enrich_manager_profiles.py                # 프리뷰(쓰지 않음)
    python src/enrich_manager_profiles.py --write        # JSON 갱신
    python src/enrich_manager_profiles.py --only "Enzo Maresca"
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_manager_profiles import fetch_json  # 429 백오프 포함 재사용

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "data" / "manager_profiles_2025_2026.json"

# 감독 전술 섹션. 선수 시절 'Style of play' 는 의도적으로 제외
# (감독 섹션은 'Style of management' / 'Tactics' / 'Manager profile' 등으로 표기됨).
_MGR_SECTION_RE = re.compile(
    r"\btactics\b|manager(?:ial)? profile|manager(?:ial)? style|"
    r"style of management|management style|managerial philosophy|"
    r"coaching (?:style|philosophy)|playing philosophy",
    re.I,
)


def _norm_dash(t: str) -> str:
    return t.replace("–", "-").replace("−", "-").replace("—", "-")


def _strip_html(raw: str) -> str:
    """섹션 HTML → 본문 텍스트. 그림 캡션·표·각주·편집링크·소제목 제거."""
    # 소제목 블록(제목 + [edit] 링크) 통째 제거 — 최신 MediaWiki 는 div.mw-heading 로 감쌈
    raw = re.sub(r'<div\b[^>]*class="[^"]*mw-heading[^"]*"[^>]*>.*?</div>', " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<figure\b.*?</figure>", " ", raw, flags=re.S | re.I)  # 그림+캡션
    raw = re.sub(r"<table\b.*?</table>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<sup\b[^>]*>.*?</sup>", " ", raw, flags=re.S | re.I)  # 각주 마커
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<h[1-6]\b.*?</h[1-6]>", " ", raw, flags=re.S | re.I)  # 소제목
    # 편집 링크(중첩 span 구조까지)
    raw = re.sub(r'<span\b[^>]*class="[^"]*mw-editsection[^"]*"[^>]*>.*?</span>\s*</span>', " ", raw, flags=re.S | re.I)
    raw = re.sub(r'<span\b[^>]*class="[^"]*mw-editsection[^"]*"[^>]*>.*?</span>', " ", raw, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = _html.unescape(txt)
    txt = re.sub(r"\[\s*edit\s*\]", " ", txt, flags=re.I)  # 남은 [edit]
    txt = re.sub(r"\[\d+\]", " ", txt)               # 남은 각주 번호
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _wiki_sections(lang: str, title: str) -> list[dict]:
    d = fetch_json(
        f"https://{lang}.wikipedia.org/w/api.php?action=parse&prop=sections"
        f"&format=json&formatversion=2&redirects=1&page={urllib.parse.quote(title)}"
    )
    return d.get("parse", {}).get("sections", [])


def _section_text(lang: str, title: str, index: str) -> str:
    d = fetch_json(
        f"https://{lang}.wikipedia.org/w/api.php?action=parse&prop=text"
        f"&section={index}&format=json&formatversion=2&redirects=1&page={urllib.parse.quote(title)}"
    )
    return _strip_html(d.get("parse", {}).get("text", "") or "")


def _rest_summary(lang: str, title: str) -> str:
    try:
        d = fetch_json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )
        return (d.get("extract") or "").strip()
    except Exception:
        return ""


def _ko_title(en_title: str) -> str:
    try:
        d = fetch_json(
            "https://en.wikipedia.org/w/api.php?action=query&prop=langlinks&lllang=ko"
            f"&format=json&formatversion=2&redirects=1&titles={urllib.parse.quote(en_title)}"
        )
        for p in d.get("query", {}).get("pages", []):
            for ll in p.get("langlinks", []):
                return ll.get("title", "")
    except Exception:
        pass
    return ""


_translator = None


def _translate_ko(text: str) -> str:
    global _translator
    if not text:
        return ""
    try:
        if _translator is None:
            from deep_translator import GoogleTranslator
            _translator = GoogleTranslator(source="en", target="ko")
        return _translator.translate(text[:1500]) or ""
    except Exception as exc:
        print(f"    [translate 실패] {exc}", file=sys.stderr)
        return ""


_STYLE_KW = re.compile(
    r"\b\d-\d(?:-\d){1,3}\b|back (?:three|four|five)|three at the back|"
    r"possession|press\w*|high line|high block|low block|build-?up|counter|"
    r"vertical|positional|transition|man-to-man|zonal|attacking|defensive",
    re.I,
)


_FORM_RE = re.compile(r"\b\d-\d(?:-\d){1,3}\b")


def _is_quote(s: str) -> bool:
    return bool(re.search(r"[\"“”]", s)) or " - " in s or " – " in s


def _best_style_sentence(text: str, limit: int = 320, require_kw: bool = False) -> str:
    """전술 문장 선택. 우선순위: (1) 포메이션이 든 문장 (2) 전술 키워드 문장.
    인용문("...")은 건너뛴다. require_kw=True 면 키워드 문장이 없을 때 ""
    (서술형 career 섹션 폴백용 — 비전술 인트로가 잡히지 않도록)."""
    text = _norm_dash(text)
    sents = [s.strip() for s in re.split(r"(?<=[.])\s+", text) if s.strip()]
    if not sents:
        return ""
    for want_form in (True, False):
        for i, s in enumerate(sents):
            if _is_quote(s):
                continue
            hit = _FORM_RE.search(s) if want_form else _STYLE_KW.search(s)
            if hit:
                return " ".join(sents[i:i + 2])[:limit]
    if require_kw:
        return ""
    return " ".join(sents[:2])[:limit]


def _extract_formation(text: str) -> str:
    t = _norm_dash(text)
    forms = re.findall(r"\b\d-\d(?:-\d){1,3}\b", t)
    forms = [f for f in forms if f.count("-") <= 3]
    if not forms:
        return ""
    return Counter(forms).most_common(1)[0][0]


def enrich_one(profile: dict) -> dict:
    """감독 1명 프로필에 위키 설명 필드 계산. profile 은 변경하지 않고 새 값 dict 반환."""
    title = profile.get("wiki_title") or profile.get("name") or ""
    result: dict = {"_title": title}
    if not title or "interim" in title.lower() and not profile.get("wiki_title"):
        return result

    # --- bio (한국어 위키 우선) ---
    ko_t = _ko_title(title)
    if ko_t:
        bio = _rest_summary("ko", ko_t)
        if bio:
            result["bio_ko"] = bio
            result["bio_source"] = "ko-wiki"
    if "bio_ko" not in result:
        en_bio = _rest_summary("en", title)
        if en_bio:
            ko = _translate_ko(en_bio)
            if ko:
                result["bio_ko"] = ko
                result["bio_source"] = "en-wiki-translated"
            else:
                result["bio_ko"] = en_bio
                result["bio_source"] = "en-wiki"

    # --- 감독 전술 섹션 (영어 위키, 상세함) ---
    # 선수 'Style of play' 는 제외하고, 감독 섹션(Tactics/Manager profile/Style of
    # management ...)을 모두 합쳐 포메이션·전술문장을 뽑는다.
    try:
        secs = _wiki_sections("en", title)
    except Exception as exc:
        print(f"    [sections 실패] {title}: {exc}", file=sys.stderr)
        secs = []
    # 감독 전용 전술 섹션만 사용(서술형 career 섹션은 뉴스·전기 노이즈라 제외).
    idxs = [s.get("index") for s in secs
            if _MGR_SECTION_RE.search(s.get("line", "") or "")][:3]
    texts = []
    for i in idxs:
        try:
            texts.append(_section_text("en", title, i))
        except Exception as exc:
            print(f"    [section {i} 실패] {title}: {exc}", file=sys.stderr)
    combined = " ".join(texts).strip()
    if combined:
        form = _extract_formation(combined)
        if form:
            result["formation"] = form
        sent = _best_style_sentence(combined)
        if sent:
            ko = _translate_ko(sent)
            result["tactics_ko"] = ko or sent
            result["tactics_source"] = "en-wiki" + ("" if ko else "-raw")
    return result


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", type=Path, default=PROFILE_PATH)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", default=None, help="한 팀/감독만 (팀명 또는 감독명 부분일치)")
    ap.add_argument("--only-missing", action="store_true",
                    help="bio_ko 가 이미 있는 감독은 건너뜀 (신규·교체 감독만 — 데일리용)")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args(argv)

    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    n_bio = n_tac = n_form = 0
    for team, prof in profiles.items():
        if args.only and args.only.lower() not in team.lower() \
                and args.only.lower() not in str(prof.get("name", "")).lower():
            continue
        if args.only_missing and prof.get("bio_ko"):
            continue
        name = prof.get("name", "")
        print(f"\n### {team} — {name}")
        try:
            r = enrich_one(prof)
        except Exception as exc:
            print(f"    [enrich 실패 — 건너뜀] {name}: {exc}", file=sys.stderr)
            continue
        if r.get("bio_ko"):
            n_bio += 1
            print(f"  bio_ko    [{r.get('bio_source')}]: {r['bio_ko'][:180]}")
        if r.get("formation"):
            n_form += 1
            print(f"  formation : {r['formation']}  (기존 {prof.get('formation')!r})")
        if r.get("tactics_ko"):
            n_tac += 1
            print(f"  tactics_ko: {r['tactics_ko'][:180]}")
        if args.write:
            for k in ("bio_ko", "bio_source", "tactics_ko", "tactics_source"):
                if r.get(k):
                    prof[k] = r[k]
            if r.get("formation"):
                prof["formation"] = r["formation"]
            # 증분 저장 — 429 등으로 중단돼도 진행분 보존
            args.profiles.write_text(
                json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        time.sleep(args.sleep)

    print(f"\n요약: bio {n_bio} · tactics {n_tac} · formation {n_form}")
    if args.write:
        print(f"WROTE {args.profiles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
