"""
리그 레벨(EPL=100) — 교차 리그 비교의 공통 기준.

UEFA 협회계수(data/uefa_association_coefficients)를 압축해 만든다: 최상위=100, 계수 차 1점당 0.2,
하한 82(선수 품질 차이는 유럽대회 계수 비율보다 작다). 계수 데이터가 없으면 폴백값.

평점 보정(RATING_PER_LEVEL): Sofascore 평점은 리그 안 상대평가라 리그 평균이 거의 같다
(25/26 정규 출전 2,359명: 리그 평균 6.81~6.88). 2026 여름 리그를 옮긴 115명의 평점 편차 변화로
리그 레벨 1점당 평점 약 0.02 차이를 추정했다(4점+ 강한 리그로 간 44명 −0.22, 잔류 950명 −0.07,
4점+ 약한 리그로 간 19명 +0.08). 그래서 레벨 L 리그의 평점은 EPL 기준으로 0.02×(100−L) 만큼 뺀다.

2부 리그(라이트 리그 챔피언십, 2026-10-22): 협회 계수는 나라 단위라 EPL 과 같은 100 이 나온다 — 대신 1부 리그들의
'클럽 평균 스쿼드 시장가치(log) ↔ 레벨' 직선을 데이터로 맞춰 2부 리그에 적용한다(src/build_lite_players.py 가 수집 때
data/league_strength.json 에 적는다 — 서버는 그 파일만 읽는다). 26/27 10월: 8개 리그로 맞춘 직선에서 챔피언십 ≈ 90.6.
"""
from __future__ import annotations

import json
from pathlib import Path

LEAGUE_COUNTRY = {"EPL": "England", "LaLiga": "Spain", "SerieA": "Italy",
                  "Bundesliga": "Germany", "Ligue1": "France",
                  "LigaPortugal": "Portugal", "Eredivisie": "Netherlands",
                  "BelgianProLeague": "Belgium"}
try:                                             # 라이트 리그 1부(쉬페르리그·오스트리아·덴마크·스위스) — 나라 이름은 UEFA 표 표기
    from leagues import LEAGUES as _LG
    LEAGUE_COUNTRY.update({k: c.country for k, c in _LG.items() if c.division == 1 and k not in LEAGUE_COUNTRY})
    _SECOND = [k for k, c in _LG.items() if c.division >= 2]
except ImportError:
    _SECOND = []
_FALLBACK = {"EPL": 100.0, "LaLiga": 98.0, "SerieA": 96.0, "Bundesliga": 96.0, "Ligue1": 93.0}
SECOND_TIER_DEFAULT = 88.0      # 2부 리그 — 시장가치 직선(league_strength.json)이 아직 없을 때
STRENGTH = Path(__file__).resolve().parent.parent / "data" / "league_strength.json"
RATING_PER_LEVEL = 0.02

_CACHE: dict | None = None


def levels() -> dict[str, float]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out = dict(_FALLBACK)
    try:
        import datastore as ds
        df = ds.read_table("uefa_association_coefficients")
        if df is not None and not df.empty:
            coeff = {str(r["country"]): float(r["coefficient"]) for _, r in df.iterrows()}
            top = max(coeff.values())
            for lg, country in LEAGUE_COUNTRY.items():
                c = coeff.get(country)
                if c is not None and lg not in _SECOND:
                    out[lg] = round(max(82.0, 100.0 - 0.2 * (top - c)), 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        fitted = json.loads(STRENGTH.read_text(encoding="utf-8")).get("levels") or {}
    except (OSError, ValueError):
        fitted = {}
    for lg in _SECOND:
        out[lg] = float(fitted.get(lg) or SECOND_TIER_DEFAULT)
    _CACHE = out
    return out


# 홈 리그 지도 티어(2026-10-22 사용자와 정함) — 리그 수준 하나로 자른다: TIER 1 ≥ 92 · TIER 2 ≥ 86 · 나머지 TIER 3.
# 경계는 지금 리그 수준에서 2점 넘게 벌어진 자리(리그1 92.8 | 포르투갈 90.7, 쉬페르리그 86.5 | 덴마크 84.5) — 계수가 바뀌면
# 티어도 따라 바뀐다. 2부 리그(division ≥ 2)는 티어 칸 대신 같은 나라 1부 리그 카드 아래에 붙는다(parent_league).
TIER_CUTS = (92.0, 86.0)


def parent_league(league: str | None) -> str | None:
    """2부 리그면 같은 나라 1부 리그 키(챔피언십 → EPL), 아니면 None."""
    try:
        from leagues import LEAGUES  # noqa: PLC0415
    except ImportError:
        return None
    c = LEAGUES.get(str(league or ""))
    if c is None or c.division < 2:
        return None
    return next((k for k, o in LEAGUES.items() if o.country == c.country and o.division == 1), None)


def tier(league: str | None) -> int | None:
    """1·2·3 — 2부 리그는 None(1부 카드 아래)."""
    if parent_league(league):
        return None
    lv = level(league)
    return 1 if lv >= TIER_CUTS[0] else 2 if lv >= TIER_CUTS[1] else 3


def fit_second_tier(club_mv: dict[str, float], known: dict[str, float]) -> tuple[dict[str, float], dict]:
    """1부 리그들의 (log 클럽 평균 시장가치, 레벨) 직선 → 2부 리그 레벨. club_mv: {리그: 클럽 평균 스쿼드 가치(€)}."""
    import math  # noqa: PLC0415
    pts = [(math.log(v), known[lg]) for lg, v in club_mv.items() if lg in known and lg not in _SECOND and v and v > 0]
    if len(pts) < 4:
        return {}, {"n": len(pts)}
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx if sxx else 0.0
    icpt = my - slope * mx
    out = {lg: round(min(99.0, max(75.0, icpt + slope * math.log(club_mv[lg]))), 1)
           for lg in _SECOND if club_mv.get(lg)}
    return out, {"n": n, "slope": round(slope, 3), "intercept": round(icpt, 3)}


def level(league: str | None) -> float:
    return levels().get(str(league or ""), 96.0)


def rating_offset(league_level) -> float:
    """EPL 기준 평점 환산 시 빼는 값(레벨이 없으면 0)."""
    try:
        lv = float(league_level)
    except (TypeError, ValueError):
        return 0.0
    if lv != lv:   # NaN
        return 0.0
    return RATING_PER_LEVEL * max(0.0, 100.0 - lv)
