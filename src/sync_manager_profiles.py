"""
Detect Premier League manager changes and sync manager profile photos.

Usage:
    python src/sync_manager_profiles.py
    python src/sync_manager_profiles.py --write --photos-only
    python src/sync_manager_profiles.py --write
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "data" / "manager_profiles_2025_2026.json"
REPORT_PATH = ROOT / "data" / "manager_change_report.md"
CHANGE_LOG_PATH = ROOT / "data" / "manager_changes_2025_2026.csv"
SOURCE_TITLE = "2025-26 Premier League"

TEAM_ALIASES = {
    "Brighton & Hove Albion": "Brighton",
    "Manchester United": "Manchester Utd",
    "Tottenham Hotspur": "Tottenham Hotspur",
    "Wolverhampton Wanderers": "Wolves",
}


def ascii_fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).casefold()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\[[^\]]+\]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "football26-manager-monitor/1.0 (local dashboard)"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("unreachable fetch retry state")


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "table":
            classes = attrs_d.get("class", "") or ""
            if self._table is None and "wikitable" in classes:
                self._table = []
                self._table_depth = 1
            elif self._table is not None:
                self._table_depth += 1
        elif self._table is not None and tag == "tr":
            self._row = []
        elif self._row is not None and tag in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._cell is not None and tag in {"td", "th"}:
            self._row.append(clean_text("".join(self._cell)))
            self._cell = None
        elif self._table is not None and self._row is not None and tag == "tr":
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif self._table is not None and tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self.tables.append(self._table)
                self._table = None
                self._table_depth = 0

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def fetch_source_managers(source_title: str = SOURCE_TITLE) -> dict[str, str]:
    title = urllib.parse.quote(source_title.replace("-", "\u2013"))
    url = (
        "https://en.wikipedia.org/w/api.php?action=parse"
        f"&page={title}&prop=text&format=json&formatversion=2"
    )
    parsed = fetch_json(url)
    parser = WikiTableParser()
    parser.feed(parsed["parse"]["text"])

    for table in parser.tables:
        if not table:
            continue
        headers = [ascii_fold(cell) for cell in table[0]]
        if "team" not in headers or "manager" not in headers:
            continue
        team_i = headers.index("team")
        manager_i = headers.index("manager")
        out: dict[str, str] = {}
        for row in table[1:]:
            if len(row) <= max(team_i, manager_i):
                continue
            team = TEAM_ALIASES.get(clean_text(row[team_i]), clean_text(row[team_i]))
            manager = clean_text(row[manager_i])
            if team and manager:
                out[team] = manager
        if out:
            return out
    raise RuntimeError("Could not find a personnel table with Team and Manager columns.")


def fetch_appointment_dates(source_title: str = SOURCE_TITLE) -> dict[str, str]:
    """위키 'Managerial changes' 표 → {감독명(ascii_fold): 부임일(Date of appointment)}.
    표가 없으면 {} 반환."""
    title = urllib.parse.quote(source_title.replace("-", "–"))
    url = (
        "https://en.wikipedia.org/w/api.php?action=parse"
        f"&page={title}&prop=text&format=json&formatversion=2"
    )
    try:
        parsed = fetch_json(url)
    except Exception:
        return {}
    parser = WikiTableParser()
    parser.feed(parsed["parse"]["text"])
    out: dict[str, str] = {}
    for table in parser.tables:
        if not table:
            continue
        headers = [ascii_fold(cell) for cell in table[0]]
        if "incoming manager" not in headers or "date of appointment" not in headers:
            continue
        inc_i = headers.index("incoming manager")
        date_i = headers.index("date of appointment")
        for row in table[1:]:
            if len(row) <= max(inc_i, date_i):
                continue
            mgr = clean_text(row[inc_i])
            appt = clean_text(row[date_i])
            if mgr and appt:
                out[ascii_fold(mgr)] = appt
    return out


def fetch_photo_urls(wiki_titles: list[str]) -> dict[str, str]:
    if not wiki_titles:
        return {}
    joined = "|".join(wiki_titles)
    title = urllib.parse.quote(joined)
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1"
        f"&prop=pageimages&piprop=thumbnail&pithumbsize=240&titles={title}"
    )
    data = fetch_json(url)
    redirects = {
        item.get("from", ""): item.get("to", "")
        for item in data.get("query", {}).get("redirects", [])
    }
    normalized = {
        item.get("from", ""): item.get("to", "")
        for item in data.get("query", {}).get("normalized", [])
    }
    pages = data.get("query", {}).get("pages", {})
    by_page_title = {}
    for page in pages.values():
        thumb = page.get("thumbnail", {})
        source = thumb.get("source", "")
        if source.startswith("http"):
            by_page_title[page.get("title", "")] = source
    out = {}
    for original in wiki_titles:
        target = redirects.get(original, normalized.get(original, original))
        out[original] = by_page_title.get(target, "")
    return out


def load_profiles(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_profiles(path: Path, profiles: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_change_log(path: Path, changed: list[dict], write_mode: bool) -> None:
    if not changed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "detected_at", "team", "previous_manager", "detected_manager",
        "official_change_date", "previous_appointed", "previous_left_date",
        "new_appointed", "change_type", "accepted", "source",
    ]
    exists = path.exists()
    seen = set()
    if exists:
        with path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                seen.add((row.get("team"), row.get("previous_manager"), row.get("detected_manager")))

    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    rows = []
    for item in changed:
        key = (item["team"], item["local"], item["source"])
        if key in seen:
            continue
        rows.append({
            "detected_at": now,
            "team": item["team"],
            "previous_manager": item["local"],
            "detected_manager": item["source"],
            "official_change_date": item.get("official_change_date", ""),
            "previous_appointed": item.get("previous_appointed", ""),
            "previous_left_date": item.get("previous_left_date", ""),
            "new_appointed": item.get("new_appointed", ""),
            "change_type": item.get("change_type", "detected"),
            "accepted": "true" if write_mode else "false",
            "source": "Wikipedia 2025-26 Premier League",
        })
    if not rows:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def build_report(local: dict, source: dict[str, str], changed: list[dict], photo_count: int) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source_count = str(len(source)) if source else "not checked"
    lines = [
        "# Manager Change Report",
        "",
        f"- Checked: {now}",
        f"- Source: https://en.wikipedia.org/wiki/2025%E2%80%9326_Premier_League",
        f"- Teams tracked: {len(local)}",
        f"- Source teams matched: {source_count}",
        f"- Photos available locally: {photo_count}",
        "",
    ]
    if changed:
        lines.append("## Change Candidates")
        lines.append("")
        for item in changed:
            lines.append(
                f"- {item['team']}: local `{item['local']}` -> source `{item['source']}`"
            )
    else:
        lines.append("## Change Candidates")
        lines.append("")
        lines.append("- None")
    missing = sorted(set(local) - set(source)) if source else []
    if missing:
        lines.extend(["", "## Missing In Source", ""])
        lines.extend(f"- {team}: local `{local[team].get('name', '')}`" for team in missing)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=PROFILE_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--changes", type=Path, default=CHANGE_LOG_PATH)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--photos-only", action="store_true")
    args = parser.parse_args(argv)

    profiles = load_profiles(args.profiles)
    source = {} if args.photos_only else fetch_source_managers()
    appoint = {} if args.photos_only else fetch_appointment_dates()

    changed = []
    if source:
        for team, profile in profiles.items():
            source_name = source.get(team)
            local_name = profile.get("name", "")
            if source_name and ascii_fold(source_name) != ascii_fold(local_name):
                # 'Managerial changes' 표에서 새 감독 부임일 자동 매칭
                new_app = appoint.get(ascii_fold(source_name), "")
                changed.append({
                    "team": team,
                    "local": local_name,
                    "source": source_name,
                    "previous_appointed": profile.get("appointed", ""),
                    "previous_left_date": "",
                    "new_appointed": new_app,
                    "official_change_date": new_app,
                    "change_type": "interim" if "interim" in ascii_fold(source_name) else "detected",
                })
                if args.write and not args.photos_only:
                    profile["previous_name"] = local_name
                    profile["previous_nationality"] = profile.get("nationality", "")
                    profile["previous_appointed"] = profile.get("appointed", "")
                    profile["previous_left_date"] = ""
                    profile["current_appointed_source"] = "wikipedia" if new_app else "pending"
                    profile["previous_style"] = profile.get("style", "")
                    profile["previous_formation"] = profile.get("formation", "")
                    profile["previous_focus"] = profile.get("focus", "")
                    profile["change_detected_at"] = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
                    profile["name"] = source_name
                    profile["wiki_title"] = source_name
                    profile["nationality"] = ""
                    profile["appointed"] = new_app
                    profile["style"] = "Pending tactical profile"
                    profile["formation"] = ""
                    profile["focus"] = "Manager change detected; tactical profile pending verification"
                    profile["photo_url"] = ""

    # 이미 교체 감지됐지만 부임일이 빈(pending) 감독 백필 — 'Managerial changes' 표 기준
    if args.write and appoint:
        for profile in profiles.values():
            if not str(profile.get("appointed") or "").strip():
                d = appoint.get(ascii_fold(profile.get("name", "")))
                if d:
                    profile["appointed"] = d
                    if profile.get("current_appointed_source") == "pending":
                        profile["current_appointed_source"] = "wikipedia"

    missing_photo_titles = [
        profile.get("wiki_title") or profile.get("name")
        for profile in profiles.values()
        if not profile.get("photo_url") and (profile.get("wiki_title") or profile.get("name"))
    ]
    photo_urls = fetch_photo_urls(missing_photo_titles)
    for profile in profiles.values():
        if profile.get("photo_url"):
            continue
        title = profile.get("wiki_title") or profile.get("name")
        if title:
            profile["photo_url"] = photo_urls.get(title, "")

    photo_count = sum(1 for p in profiles.values() if p.get("photo_url"))
    report = build_report(profiles, source, changed, photo_count)
    args.report.write_text(report, encoding="utf-8", newline="\n")
    append_change_log(args.changes, changed, args.write and not args.photos_only)

    if args.write:
        save_profiles(args.profiles, profiles)

    print(report)
    if changed and not args.write:
        print("Run with --write to accept source manager names.")
    return 2 if changed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[manager-monitor] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
