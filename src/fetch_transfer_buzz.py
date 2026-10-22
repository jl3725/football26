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
sys.path.insert(0, str(ROOT / "src"))
from leagues import data_path  # noqa: E402

OUT_PATH = ROOT / "data" / "transfer_buzz.csv"

# 리그별 이적 속보 피드 — EPL: Guardian/BBC, LaLiga: Marca 이적(mercado-fichajes, 스페인어)
FEEDS_BY_LEAGUE = {
    "EPL": [
        ("Guardian", "https://www.theguardian.com/football/transfer-window/rss"),
        ("BBC", "https://feeds.bbci.co.uk/sport/football/gossip/rss.xml"),
    ],
    "LaLiga": [
        ("Marca", "https://e00-marca.uecdn.es/rss/futbol/mercado-fichajes.xml"),
    ],
    "SerieA": [
        # Gazzetta calciomercato RSS 는 2023 아카이브라 스테일 → Football Italia(영문·최신) 사용
        ("Football Italia", "https://football-italia.net/feed/"),
    ],
    "Bundesliga": [
        ("kicker", "https://newsfeed.kicker.de/news/fussball"),
    ],
    "Ligue1": [
        ("L'Équipe", "https://dwh.lequipe.fr/api/edito/rss?path=/Football/"),
    ],
    "LigaPortugal": [
        ("Record", "https://www.record.pt/rss"),
    ],
    "Eredivisie": [
        ("NOS", "https://feeds.nos.nl/nosvoetbal"),   # 구 nossportvoetbal 은 2026 중 404
        ("VoetbalPrimeur", "https://www.voetbalprimeur.nl/rss/"),
    ],
    "BelgianProLeague": [],
}

# 합의/임박 신호 키워드 (영어+스페인어). 없으면 루머로 분류.
_AGREED = re.compile(
    r"\b(agree|agreed|complete|completed|seal|sealed|sign|signs|signed|signing|"
    r"done deal|here we go|medical|unveil|wins? race|win the race|buy|bought|sold|"
    r"joins?|joining|confirm|confirmed|announce|announced|"
    r"acuerdo|fichaj|fichado|oficial|cierra|firma|firmar|vendido|traspaso|refuerzo|llega|"
    r"ufficiale|accordo|firma|acquisto|acquist|ceduto|colpo|visite mediche|preso|arriva|"
    r"offiziell|wechselt|verpflichtet|verpflichtung|unterschreibt|unterschrieb|holt|bindet|"
    r"verlängert|leihe|neuzugang|fixiert|"
    r"officiel|officielle|signe|rejoint|s.engage|recrue|transfert|accord|prêt|bouclé|"
    r"oficial|assina|assinou|refor.o|contrata|transfer.ncia|acordo|empr.stimo|fechado|rumo a|"
    r"officieel|tekent|getekend|akkoord|aanwinst|vastgelegd|overstap|verhuurd|inkomende|haalt|versterkt)\b",
    re.I,
)


def _classify(title: str) -> str:
    return "agreed" if _AGREED.search(title) else "rumor"


_HANGUL = re.compile(r"[가-힣]")   # 한글 없는 '번역'(원문 그대로 등)은 다시 번역


def _known_ko(path: Path) -> dict[str, str]:
    """기존 파일에서 이미 번역된 제목(title_en → title_ko). 같은 제목은 다시 번역하지 않는다."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {r["title_en"]: r["title_ko"] for r in csv.DictReader(fh)
                if r.get("title_ko") and r["title_ko"] != r.get("title_en") and _HANGUL.search(r["title_ko"])}


# 종합 스포츠 피드(Record 등)의 축구 외 기사 — 기사 주소의 섹션 경로로 거른다(F1·하키·사진첩이 '이적 소식'에 섞였음)
_OFF_TOPIC_LINK = re.compile(r"/(modalidades|motores|fora-de-campo|multimedia|opiniao)/", re.I)


def _fetch(league: str = "EPL") -> list[dict]:
    import feedparser
    rows, seen = [], set()
    # 피드가 없는 리그(라이트 리그)에 EPL 피드를 붙이면 그 리그 팀 이름으로 EPL 기사를 잘못 잡는다 — 빈 목록
    for src, url in FEEDS_BY_LEAGUE.get(league, []):
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            print(f"[buzz] {src} 실패: {exc}", file=sys.stderr)
            continue
        for e in feed.entries[:25]:
            title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
            title = re.sub(r"^<!\[CDATA\[\s*|\s*\]\]>$", "", title)   # 일부 피드(Record)의 CDATA 래퍼
            title = re.sub(r"\s*[-–]\s*\w+'s gossip$", "", title, flags=re.I)  # BBC 꼬리표 제거
            if not title or title.lower() in seen or _OFF_TOPIC_LINK.search(e.get("link") or ""):
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
    ap.add_argument("--league", default="EPL")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)
    if args.out is None:
        args.out = OUT_PATH if args.league == "EPL" else data_path("transfer_buzz", args.league)

    rows = _fetch(args.league)
    if not rows:
        print("[buzz] 항목 없음 — 기존 파일 유지", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: r["published"], reverse=True)
    rows = rows[:args.limit]

    # 번역 실패 시 원문을 넣되, 다음 실행이 원문인 제목만 다시 번역한다(src/translate.py — 무료 공급자)
    known = {} if args.no_translate else _known_ko(args.out)
    todo = [r for r in rows if r["title_en"] not in known]
    if todo and not args.no_translate:
        from translate import translate_many
        for r, ko in zip(todo, translate_many([r["title_en"] for r in todo])):
            if ko:
                known[r["title_en"]] = ko
    for r in rows:
        r["title_ko"] = known.get(r["title_en"]) or r["title_en"]
    if todo and not args.no_translate:
        print(f"[buzz] 번역 {sum(1 for r in todo if r['title_en'] in known)}/{len(todo)}건(신규) · 재사용 {len(rows) - len(todo)}건")

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
