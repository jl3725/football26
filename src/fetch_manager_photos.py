"""
떠난(previous) 감독 사진 수집기.

manager_profiles 에는 현 감독 photo_url 만 있고 previous_name(경질/이임 감독)의 사진이 없어,
홈 '감독 교체' 피드에서 나간 감독 얼굴이 안 나온다. 위키 pageimages 로 previous 사진을
긁어 profile["previous_photo"] 에 채운다. (sync_manager_profiles 의 배치 페처 재사용)

사용:
    python src/fetch_manager_photos.py            # 없는 것만
    python src/fetch_manager_photos.py --refresh  # 전부 다시
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_manager_profiles import fetch_photo_urls, load_profiles, save_profiles  # noqa: E402

JSON = Path(__file__).resolve().parent.parent / "data" / "manager_profiles_2025_2026.json"
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")  # "(interim)" 등 제거


def _search_photo(name: str) -> str:
    """위키 검색(generator=search)으로 정확 페이지를 찾아 썸네일 — 악센트/동명 disambiguation 대응."""
    try:
        q = urllib.parse.quote(f"{name} football manager")
        url = ("https://en.wikipedia.org/w/api.php?action=query&generator=search"
               f"&gsrsearch={q}&gsrlimit=1&prop=pageimages&piprop=thumbnail"
               "&pithumbsize=240&format=json&formatversion=2")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        for p in d.get("query", {}).get("pages", []):
            th = (p.get("thumbnail", {}) or {}).get("source", "")
            if th.startswith("http"):
                return th
    except Exception:  # noqa: BLE001
        pass
    return ""


_TM_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def _tm_photo(name: str) -> str:
    """Transfermarkt 감독(trainer) 검색 → 초상 사진. 위키에 사진 없는 감독 폴백."""
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get("https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
                         f"?query={urllib.parse.quote(name)}", headers=_TM_H, timeout=20)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.select("a[href*='/profil/trainer/']"):
            row = a.find_parent("tr")
            img = row.find("img") if row else None
            if img:
                src = img.get("data-src") or img.get("src") or ""
                if "transfermarkt" in src and "portrait" in src:
                    return src.replace("/small/", "/medium/").split("?")[0]
    except Exception:  # noqa: BLE001
        pass
    return ""


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    refresh = "--refresh" in args
    profiles = load_profiles(JSON)

    # (team, kind) → 조회할 감독명. kind = 'photo_url'(현) | 'previous_photo'(떠난)
    want: dict[tuple, str] = {}
    for team, p in profiles.items():
        # 현 감독 사진 없으면 백필 (위키타이틀 우선, 없으면 이름)
        if refresh or not str(p.get("photo_url") or "").startswith("http"):
            nm = _PAREN.sub("", str(p.get("wiki_title") or p.get("name") or "")).strip()
            if nm:
                want[(team, "photo_url")] = nm
        # 떠난 감독 사진
        prev = str(p.get("previous_name") or "").strip()
        if prev and (refresh or not str(p.get("previous_photo") or "").startswith("http")):
            want[(team, "previous_photo")] = _PAREN.sub("", prev).strip()

    names = sorted({n for n in want.values() if n})
    if not names:
        print("조회할 감독 없음(모두 사진 보유).")
        return 0
    print(f"감독 {len(names)}명 사진 조회…")
    photos = fetch_photo_urls(names)  # {name: url}

    n_ok = 0
    for (team, kind), name in want.items():
        # 위키 배치 → 위키 검색 → Transfermarkt 감독검색 순 폴백
        url = photos.get(name, "") or _search_photo(name) or _tm_photo(name)
        profiles[team][kind] = url
        if url.startswith("http"):
            n_ok += 1
        print(f"  {team:20} {kind:14} {name:24} {'O' if url.startswith('http') else 'X'}")

    save_profiles(JSON, profiles)
    print(f"[OK] {n_ok}/{len(want)} 사진 저장 → {JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
