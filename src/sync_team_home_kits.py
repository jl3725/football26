from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "team_home_kits_2025_2026.csv"

TEAM_SLUGS = {
    "Arsenal": "arsenal",
    "Aston Villa": "aston-villa",
    "Bournemouth": "afc-bournemouth",
    "Brentford": "brentford",
    "Brighton": "brighton-hove-albion",
    "Burnley": "burnley",
    "Chelsea": "chelsea",
    "Crystal Palace": "crystal-palace",
    "Everton": "everton",
    "Fulham": "fulham",
    "Leeds United": "leeds-united",
    "Liverpool": "liverpool",
    "Manchester City": "manchester-city",
    "Manchester Utd": "manchester-united",
    "Newcastle United": "newcastle-united",
    "Nottingham Forest": "nottingham-forest",
    "Sunderland": "sunderland",
    "Tottenham Hotspur": "tottenham-hotspur",
    "West Ham United": "west-ham-united",
    "Wolves": "wolverhampton-wanderers",
}


DEFAULT_ROWS = {
    "Arsenal": ("#EF0107", "#FFFFFF", "#EF0107", "sleeves"),
    "Aston Villa": ("#670E36", "#95BFE5", "#F7D117", "sleeves"),
    "Bournemouth": ("#DA291C", "#111111", "#DA291C", "stripes"),
    "Brentford": ("#E30613", "#FFFFFF", "#111111", "stripes"),
    "Brighton": ("#0057B8", "#FFFFFF", "#FFD100", "stripes"),
    "Burnley": ("#6C1D45", "#99D6EA", "#F6C343", "sleeves"),
    "Chelsea": ("#034694", "#FFFFFF", "#DBA111", "solid"),
    "Crystal Palace": ("#1B458F", "#C4122E", "#FFFFFF", "stripes"),
    "Everton": ("#003399", "#FFFFFF", "#003399", "solid"),
    "Fulham": ("#FFFFFF", "#111111", "#D71920", "sleeves"),
    "Leeds United": ("#FFFFFF", "#1D428A", "#FFCD00", "solid"),
    "Liverpool": ("#C8102E", "#FFFFFF", "#00A398", "solid"),
    "Manchester City": ("#6CABDD", "#FFFFFF", "#1C2C5B", "solid"),
    "Manchester Utd": ("#DA291C", "#111111", "#FBE122", "solid"),
    "Newcastle United": ("#FFFFFF", "#111111", "#41B6E6", "stripes"),
    "Nottingham Forest": ("#DD0000", "#FFFFFF", "#DD0000", "solid"),
    "Sunderland": ("#EB172B", "#FFFFFF", "#111111", "stripes"),
    "Tottenham Hotspur": ("#FFFFFF", "#132257", "#132257", "solid"),
    "West Ham United": ("#7A263A", "#1BB1E7", "#F3C300", "sleeves"),
    "Wolves": ("#FDB913", "#111111", "#FDB913", "solid"),
}


def fetch(url: str, timeout: int = 20) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=timeout) as res:
        charset = res.headers.get_content_charset() or "utf-8"
        return res.read().decode(charset, errors="replace")


def find_og_image(page_html: str) -> str:
    patterns = [
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
        r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, page_html, flags=re.I)
        if m:
            return m.group(1).strip()
    return ""


def load_existing() -> dict[str, dict[str, str]]:
    if not OUT.exists():
        return {}
    with OUT.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["team"]: row for row in csv.DictReader(f)}


def write_rows(rows: list[dict[str, str]]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["team", "season", "image_url", "primary", "secondary", "accent", "pattern", "source_url", "checked_at"]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})


def sync(season: str, delay: float) -> int:
    existing = load_existing()
    rows = []
    found = 0
    for team, slug in TEAM_SLUGS.items():
        primary, secondary, accent, pattern = DEFAULT_ROWS[team]
        old = existing.get(team, {})
        source_url = f"https://www.footballkitarchive.com/{slug}-{season}-home-kit/"
        image_url = old.get("image_url", "")
        try:
            page = fetch(source_url)
            scraped = find_og_image(page)
            if scraped:
                image_url = scraped
                found += 1
        except (HTTPError, URLError, TimeoutError) as exc:
            print(f"[WARN] {team}: {exc}", file=sys.stderr)
        rows.append({
            "team": team,
            "season": season.replace("-", "/"),
            "image_url": image_url,
            "primary": old.get("primary") or primary,
            "secondary": old.get("secondary") or secondary,
            "accent": old.get("accent") or accent,
            "pattern": old.get("pattern") or pattern,
            "source_url": source_url,
            "checked_at": time.strftime("%Y-%m-%d"),
        })
        if delay:
            time.sleep(delay)
    write_rows(rows)
    print(f"[OK] wrote {OUT} ({found}/{len(rows)} image urls scraped)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Premier League home kit image URLs.")
    parser.add_argument("--season", default="2025-26", help="Football Kit Archive season slug, e.g. 2025-26")
    parser.add_argument("--delay", type=float, default=0.6, help="Delay between requests")
    args = parser.parse_args()
    return sync(args.season, args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
