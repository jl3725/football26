"""
리그 레벨(EPL=100) — 교차 리그 비교의 공통 기준.

UEFA 협회계수(data/uefa_association_coefficients)를 압축해 만든다: 최상위=100, 계수 차 1점당 0.2,
하한 82(선수 품질 차이는 유럽대회 계수 비율보다 작다). 계수 데이터가 없으면 폴백값.

평점 보정(RATING_PER_LEVEL): Sofascore 평점은 리그 안 상대평가라 리그 평균이 거의 같다
(25/26 정규 출전 2,359명: 리그 평균 6.81~6.88). 2026 여름 리그를 옮긴 115명의 평점 편차 변화로
리그 레벨 1점당 평점 약 0.02 차이를 추정했다(4점+ 강한 리그로 간 44명 −0.22, 잔류 950명 −0.07,
4점+ 약한 리그로 간 19명 +0.08). 그래서 레벨 L 리그의 평점은 EPL 기준으로 0.02×(100−L) 만큼 뺀다.
"""
from __future__ import annotations

LEAGUE_COUNTRY = {"EPL": "England", "LaLiga": "Spain", "SerieA": "Italy",
                  "Bundesliga": "Germany", "Ligue1": "France",
                  "LigaPortugal": "Portugal", "Eredivisie": "Netherlands",
                  "BelgianProLeague": "Belgium"}
_FALLBACK = {"EPL": 100.0, "LaLiga": 98.0, "SerieA": 96.0, "Bundesliga": 96.0, "Ligue1": 93.0}
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
                if c is not None:
                    out[lg] = round(max(82.0, 100.0 - 0.2 * (top - c)), 1)
    except Exception:  # noqa: BLE001
        pass
    _CACHE = out
    return out


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
