"""이적 속보/루머 피드 수집 — Guardian Transfer Window + BBC Gossip RSS.

로마노/온스테인 등의 속보를 신문사(Guardian·BBC)가 기사로 중계한 것을 무료·합법(RSS)
으로 수집한다. 한국어 번역 + 루머/합의 분류해 data/transfer_buzz.csv 에 기록.
홈 대시보드 '이적 속보 LIVE' 피드가 datastore.read_table("transfer_buzz") 로 사용.

사용:
    python src/fetch_transfer_buzz.py            # data/transfer_buzz.csv 갱신
    python src/fetch_transfer_buzz.py --no-translate
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "transfer_buzz.csv"

FEEDS = [
    ("Guardian", "https://www.theguardian.com/football/transfer-window/rss"),
    ("BBC", "https://feeds.bbci.co.uk/sport/football/gossip/rss.xml"),
]

# 합의/임박 신호 키워드 (없으면 루머로 분류)
_AGREED = re.compile(
    r"\b(agree|agreed|complete|completed|seal|sealed|sign|signs|signed|signing|"
    r"done deal|here we go|medical|unveil|wins? race|win the race|buy|bought|sold|"
    r"joins?|joining|confirm|confirmed|announce|announced)\b",
    re.I,
)


def _classify(title: str) -> str:
    return "agreed" if _AGREED.search(title) else "rumor"


_translator = None


def _to_ko(text: str) -> str:
    global _translator
    if not text:
        return ""
    try:
        if _translator is None:
            from deep_translator import GoogleTranslator
            _translator = GoogleTranslator(source="en", target="ko")
        return _translator.translate(text[:480]) or ""
    except Exception as exc:
        print(f"    [translate 실패] {exc}", file=sys.stderr)
        return ""


def _fetch() -> list[dict]:
    import feedparser
    rows, seen = [], set()
    for src, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            print(f"[buzz] {src} 실패: {exc}", file=sys.stderr)
            continue
        for e in feed.entries[:25]:
            title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
            title = re.sub(r"\s*[-–]\s*\w+'s gossip$", "", title, flags=re.I)  # BBC 꼬리표 제거
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            pub = ""
            if e.get("published_parsed"):
                try:
                    pub = time.strftime("%Y-%m-%d %H:%M", e["published_parsed"])
                except Exception:
                    pub = ""
            rows.append({
                "source": src, "title_en": title, "tier": _classify(title),
                "link": e.get("link") or "", "published": pub,
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    rows = _fetch()
    if not rows:
        print("[buzz] 항목 없음 — 기존 파일 유지", file=sys.stderr)
        return 1

    if not args.no_translate:
        for r in rows:
            r["title_ko"] = _to_ko(r["title_en"]) or r["title_en"]
            time.sleep(0.2)
    else:
        for r in rows:
            r["title_ko"] = r["title_en"]

    rows.sort(key=lambda r: r["published"], reverse=True)
    rows = rows[:args.limit]

    fields = ["source", "title_en", "title_ko", "tier", "link", "published"]
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    agreed = sum(1 for r in rows if r["tier"] == "agreed")
    print(f"[buzz] {len(rows)}건 기록 (합의 {agreed} · 루머 {len(rows) - agreed}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
