"""UEFA 협회(국가)·클럽 계수 수집 — kassiesa.net (UEFA 계수 표준 소스, stdlib만).

- 협회계수(crank{year}): 국가/리그 단위 5시즌 누적 → _LEAGUE_LEVEL 근거화용.
- 클럽계수(trank{year}): 클럽 단위 유럽대항전 경쟁력 → 유럽강도 축용.
연도(계수 시즌 종료년)는 최신부터 자동 탐지. 결과:
  data/uefa_association_coefficients.csv, data/uefa_club_coefficients.csv

사용: python src/fetch_uefa_coefficients.py
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ASSOC = ROOT / "data" / "uefa_association_coefficients.csv"
OUT_CLUB = ROOT / "data" / "uefa_club_coefficients.csv"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
BASE = "https://kassiesa.net/uefa/data/method5/{kind}{year}.html"


def _current_coeff_year() -> int:
    """계수 창의 '종료년' = 가장 최근 완료 시즌 종료년. 6월 이후면 올해, 이전이면 작년.
    (진행중 시즌이 창에 0으로 섞인 다음해 페이지를 피해 '완성된' 계수를 고르기 위함)"""
    now = dt.datetime.now()
    return now.year if now.month >= 6 else now.year - 1


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _rows(html: str) -> list[str]:
    return re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)


def _cells(tr: str) -> list[str]:
    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
    return [c for c in cells if c != ""]   # 국기/여백 빈 셀 제거


def _floats(cells: list[str]) -> list[float]:
    out = []
    for c in cells:
        try:
            out.append(float(c))
        except ValueError:
            pass
    return out


def _is_num(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_assoc(html: str) -> list[dict]:
    # 빈셀 제거 후: [rank, country, s1..s5, total, teams]
    # total(계수) = rank 제외 최댓값(누적 총점은 항상 개별시즌·팀수보다 큼)
    rows = []
    for tr in _rows(html):
        c = _cells(tr)
        if len(c) >= 8 and c[0].isdigit() and not _is_num(c[1]):
            nums = _floats(c[1:])
            if not nums:
                continue
            teams = int(c[-1]) if c[-1].isdigit() and int(c[-1]) < 40 else 0
            rows.append({"rank": int(c[0]), "country": c[1],
                         "coefficient": max(nums), "teams": teams})
    return rows


def _parse_club(html: str) -> list[dict]:
    # 빈셀 제거 후: [rank, club, country, s1..s5, total, countrypart]
    # total(계수) = rank 제외 최댓값(시즌 결장 클럽도 인덱스 흔들림 없이 안전)
    rows = []
    for tr in _rows(html):
        c = _cells(tr)
        if len(c) >= 5 and c[0].isdigit() and not _is_num(c[1]) and not _is_num(c[2]):
            nums = _floats(c[2:])
            if not nums:
                continue
            rows.append({"rank": int(c[0]), "club": c[1], "country": c[2],
                         "coefficient": max(nums)})
    return rows


def _pick(kind: str, parse_fn, min_top: float) -> tuple[int, list[dict]]:
    """날짜 기반 '완료 계수 종료년' 우선 + 페이지 부재 시 인접년 폴백.
    진행중 시즌이 섞인 다음해 페이지(계수 미완성)를 피한다."""
    y0 = _current_coeff_year()
    for y in (y0, y0 - 1, y0 + 1, y0 - 2):
        try:
            rows = parse_fn(_get(BASE.format(kind=kind, year=y)))
        except (urllib.error.URLError, OSError):
            continue
        if rows and max(r["coefficient"] for r in rows) >= min_top:
            return y, rows
    return 0, []


def fetch_assoc() -> tuple[int, list[dict]]:
    return _pick("crank", _parse_assoc, 40.0)


def fetch_club() -> tuple[int, list[dict]]:
    return _pick("trank", _parse_club, 40.0)


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ay, assoc = fetch_assoc()
    cy, club = fetch_club()
    if not assoc and not club:
        print("[uefa] 계수 수집 실패 — 기존 파일 유지", file=sys.stderr)
        return 1

    if assoc:
        _write(OUT_ASSOC, assoc, ["rank", "country", "coefficient", "teams"])
        top = " · ".join(f"{r['rank']}.{r['country']}({r['coefficient']})" for r in assoc[:7])
        print(f"[uefa] 협회계수 {len(assoc)}개국 (기준 {ay}) -> {OUT_ASSOC.name}")
        print("  TOP7: " + top)
    if club:
        _write(OUT_CLUB, club, ["rank", "club", "country", "coefficient"])
        print(f"[uefa] 클럽계수 {len(club)}팀 (기준 {cy}) -> {OUT_CLUB.name}")
        print("  TOP5: " + " · ".join(f"{r['rank']}.{r['club']}" for r in club[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
