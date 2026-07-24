"""
리그/시즌 설정 척추(config spine).

지금까지 온 코드는 EPL·25/26 이 여러 파일에 하드코딩돼 있었다. 이 모듈은 그
가정을 **한 곳**으로 모아, 추후 라리가·분데스리가 확장 시 여기 dict 만 늘리면
되도록 한다. 데이터 파일 경로도 여기서 만들어(`data_path`) 파일명 규칙을 통일한다.

핵심 설계
---------
* `SEASON`          : 파일명용 시즌 토큰(예 "2025_2026")
* `SEASON_FBREF`    : soccerdata/FBref 용("2025-2026")
* `SEASON_START`    : 시즌 시작 연도(int, 2025)
* `LEAGUES`         : 리그키 → `LeagueConfig`
* `ACTIVE_LEAGUE`   : 환경변수 `FB_LEAGUE`(기본 "EPL")
* `PRIMARY_LEAGUE`  : 레거시 파일명(리그 토큰 없는 `*_2025_2026.csv`)을 쓰는 리그

파일명 규칙(back-compat)
-----------------------
기존 EPL 파일들은 `standings_2025_2026.csv` 처럼 리그 토큰이 없다. 이를 깨지
않도록 **PRIMARY_LEAGUE(EPL)** 는 레거시 이름을 그대로 쓰고, 그 외 리그만
`standings_ES1_2025_2026.csv` 처럼 리그키를 끼워 넣는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ── 경로 ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# ── 시즌 ─────────────────────────────────────────────────────────────
# 단일 활성 시즌. (다중 시즌은 datastore 레벨에서 season 인자로 처리)
# 배포/수집기가 같은 시즌을 명시할 수 있도록 환경변수로 덮어쓸 수 있다.
def parse_season_start(value: str | None) -> int:
    """환경변수 값을 시즌 시작 연도로 검증해 반환한다."""
    raw = (value or "2025").strip()
    try:
        year = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"FB_SEASON_START must be a year, got {raw!r}") from exc
    if not 2000 <= year <= 2100:
        raise RuntimeError(f"FB_SEASON_START out of range: {year}")
    return year


SEASON_START = parse_season_start(os.getenv("FB_SEASON_START"))
SEASON = f"{SEASON_START}_{SEASON_START + 1}"        # 파일명 토큰
SEASON_FBREF = f"{SEASON_START}-{SEASON_START + 1}"  # soccerdata 형식


@dataclass(frozen=True)
class LeagueConfig:
    """한 리그의 소스별 식별자 + 표시 메타."""
    key: str                 # 내부 키(파일명/DB에 사용) — Transfermarkt 대회코드 재사용
    name: str                # 표시명
    country: str
    fbref_id: str            # soccerdata/FBref 리그 id
    tm_id: str               # Transfermarkt 대회 코드(GB1 …) == key
    tm_slug: str             # Transfermarkt URL slug(premier-league …)
    api_football_id: int     # API-Football 리그 id
    default_team: str        # UI 기본 선택 팀
    teams: int = 20
    games_per_team: int = 38


# 지원 리그의 소스 식별자와 기본 UI 메타.
LEAGUES: dict[str, LeagueConfig] = {
    "EPL": LeagueConfig(
        key="EPL", name="Premier League", country="England",
        fbref_id="ENG-Premier League", tm_id="GB1", tm_slug="premier-league",
        api_football_id=39, default_team="Arsenal",
    ),
    "LaLiga": LeagueConfig(
        key="LaLiga", name="La Liga", country="Spain",
        fbref_id="ESP-La Liga", tm_id="ES1", tm_slug="laliga",
        api_football_id=140, default_team="Real Madrid",
    ),
    "Bundesliga": LeagueConfig(
        key="Bundesliga", name="Bundesliga", country="Germany",
        fbref_id="GER-Bundesliga", tm_id="L1", tm_slug="bundesliga",
        api_football_id=78, default_team="Bayern Munich", teams=18, games_per_team=34,
    ),
    "SerieA": LeagueConfig(
        key="SerieA", name="Serie A", country="Italy",
        fbref_id="ITA-Serie A", tm_id="IT1", tm_slug="serie-a",
        api_football_id=135, default_team="Inter",
    ),
    "Ligue1": LeagueConfig(
        key="Ligue1", name="Ligue 1", country="France",
        fbref_id="FRA-Ligue 1", tm_id="FR1", tm_slug="ligue-1",
        api_football_id=61, default_team="Paris Saint-Germain",
    ),
    "LigaPortugal": LeagueConfig(
        key="LigaPortugal", name="Liga Portugal", country="Portugal",
        fbref_id="POR-Primeira Liga", tm_id="PO1", tm_slug="liga-portugal-betclic",
        api_football_id=94, default_team="Sporting CP", teams=18, games_per_team=34,
    ),
    "Eredivisie": LeagueConfig(
        key="Eredivisie", name="Eredivisie", country="Netherlands",
        fbref_id="NED-Eredivisie", tm_id="NL1", tm_slug="eredivisie",
        api_football_id=88, default_team="PSV", teams=18, games_per_team=34,
    ),
    "BelgianProLeague": LeagueConfig(
        key="BelgianProLeague", name="Belgian Pro League", country="Belgium",
        fbref_id="BEL-Belgian Pro League", tm_id="BE1", tm_slug="jupiler-pro-league",
        api_football_id=144, default_team="Club Brugge", teams=16, games_per_team=30,
    ),
}

# 레거시 파일명(`*_2025_2026.csv`, 리그 토큰 없음)을 쓰는 리그.
PRIMARY_LEAGUE = "EPL"

# 활성 리그 — 환경변수로 전환(미설정 시 EPL).
ACTIVE_LEAGUE = os.getenv("FB_LEAGUE", PRIMARY_LEAGUE)
if ACTIVE_LEAGUE not in LEAGUES:
    ACTIVE_LEAGUE = PRIMARY_LEAGUE


def league_config(league: str | None = None) -> LeagueConfig:
    """리그키 → LeagueConfig (미지정 시 ACTIVE_LEAGUE)."""
    return LEAGUES[league or ACTIVE_LEAGUE]


def register_soccerdata_custom_leagues() -> None:
    try:
        import soccerdata._config as sd_config
    except Exception:  # noqa: BLE001
        return
    sd_config.LEAGUE_DICT.setdefault(
        "POR-Primeira Liga",
        {
            "FBref": "Primeira Liga",
            "ESPN": "por.1",
            "Sofascore": "Liga Portugal Betclic",
            "season_start": "Aug",
            "season_end": "May",
        },
    )
    sd_config.LEAGUE_DICT.setdefault(
        "NED-Eredivisie",
        {
            "FBref": "Eredivisie",
            "ESPN": "ned.1",
            "Sofascore": "Eredivisie",
            "season_start": "Aug",
            "season_end": "May",
        },
    )
    sd_config.LEAGUE_DICT.setdefault(
        "BEL-Belgian Pro League",
        {
            "FBref": "Belgian Pro League",
            "ESPN": "bel.1",
            "Sofascore": "Pro League",
            "season_start": "Jul",
            "season_end": "May",
        },
    )


def data_path(stem: str, league: str | None = None,
              season: str | None = None, ext: str = "csv") -> Path:
    """
    데이터 파일 경로 생성.

        data_path("standings")                 -> data/standings_2025_2026.csv          (EPL)
        data_path("standings", "LaLiga")       -> data/standings_LaLiga_2025_2026.csv

    PRIMARY_LEAGUE(EPL)은 레거시 이름을 유지해 기존 파일을 깨지 않는다.
    """
    league = league or ACTIVE_LEAGUE
    season = season or SEASON
    if league == PRIMARY_LEAGUE:
        name = f"{stem}_{season}.{ext}"
    else:
        name = f"{stem}_{league}_{season}.{ext}"
    return DATA_DIR / name


def parse_data_filename(name: str) -> tuple[str, str, str] | None:
    """
    데이터 파일명 → (stem, league, season). build_db 가 CSV 를 테이블에
    매핑할 때 사용. 규칙에 안 맞으면 None.

        "standings_2025_2026.csv"        -> ("standings", "EPL", "2025_2026")
        "standings_LaLiga_2025_2026.csv" -> ("standings", "LaLiga", "2025_2026")
    """
    stem_full = name.rsplit(".", 1)[0]
    import re
    m = re.search(r"_(\d{4}_\d{4})$", stem_full)
    if not m:
        return None
    season = m.group(1)
    head = stem_full[: m.start()]
    # 뒤쪽에 리그키가 붙어있는지 검사
    for lk in LEAGUES:
        if lk != PRIMARY_LEAGUE and head.endswith("_" + lk):
            return (head[: -(len(lk) + 1)], lk, season)
    return (head, PRIMARY_LEAGUE, season)
