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
    raw = (value or "2026").strip()   # 활성 데이터 시즌 — 전환 시 render.yaml·ci.yml 과 함께 변경
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
    # 라이트 리그(2026-10-22 1단계 확장) — FBref·Understat·Sofascore·로컬 주간 빌드 없이 클라우드 수집(FotMob·ESPN·TM)만으로
    # 같은 모양의 표를 만든다(src/build_lite_players.py). 풀 리그 전용 수집기(FBref·Understat·Sofascore)는 lite 를 건너뛴다.
    lite: bool = False
    fotmob_id: int = 0       # FotMob 리그 id(시즌 통계·경기 상세·명단)
    espn: str = ""           # ESPN 리그 코드(eng.2 …) — 일정·라인업·교체
    division: int = 1        # 그 나라 몇 부 리그 — 2부는 UEFA 협회 계수를 1부와 나눠 쓸 수 없어 리그 수준을 따로 낸다(league_level)


# 지원 리그의 소스 식별자와 기본 UI 메타.
LEAGUES: dict[str, LeagueConfig] = {
    "EPL": LeagueConfig(
        key="EPL", name="Premier League", country="England",
        fbref_id="ENG-Premier League", tm_id="GB1", tm_slug="premier-league",
        api_football_id=39, default_team="Arsenal", espn="eng.1",
    ),
    "LaLiga": LeagueConfig(
        key="LaLiga", name="La Liga", country="Spain",
        fbref_id="ESP-La Liga", tm_id="ES1", tm_slug="laliga",
        api_football_id=140, default_team="Real Madrid", espn="esp.1",
    ),
    "Bundesliga": LeagueConfig(
        key="Bundesliga", name="Bundesliga", country="Germany",
        fbref_id="GER-Bundesliga", tm_id="L1", tm_slug="bundesliga",
        api_football_id=78, default_team="Bayern Munich", teams=18, games_per_team=34, espn="ger.1",
    ),
    "SerieA": LeagueConfig(
        key="SerieA", name="Serie A", country="Italy",
        fbref_id="ITA-Serie A", tm_id="IT1", tm_slug="serie-a",
        api_football_id=135, default_team="Inter", espn="ita.1",
    ),
    "Ligue1": LeagueConfig(
        key="Ligue1", name="Ligue 1", country="France",
        fbref_id="FRA-Ligue 1", tm_id="FR1", tm_slug="ligue-1",
        api_football_id=61, default_team="Paris Saint-Germain", espn="fra.1",
    ),
    "LigaPortugal": LeagueConfig(
        key="LigaPortugal", name="Liga Portugal", country="Portugal",
        fbref_id="POR-Primeira Liga", tm_id="PO1", tm_slug="liga-portugal-betclic",
        api_football_id=94, default_team="Sporting CP", teams=18, games_per_team=34, espn="por.1",
    ),
    "Eredivisie": LeagueConfig(
        key="Eredivisie", name="Eredivisie", country="Netherlands",
        fbref_id="NED-Eredivisie", tm_id="NL1", tm_slug="eredivisie",
        api_football_id=88, default_team="PSV", teams=18, games_per_team=34, espn="ned.1",
    ),
    "BelgianProLeague": LeagueConfig(
        key="BelgianProLeague", name="Belgian Pro League", country="Belgium",
        fbref_id="BEL-Belgian Pro League", tm_id="BE1", tm_slug="jupiler-pro-league",
        # 26/27 부터 18팀(ESPN·TM 리그 페이지 기준) — 정규 34라운드 + 플레이오프
        api_football_id=144, default_team="Club Brugge", teams=18, games_per_team=34, espn="bel.1",
    ),
    # ── 라이트 리그(클라우드 수집만) — 팀 표기는 FotMob 리그 표 기준(src/lite_league.py) ──
    "Championship": LeagueConfig(
        key="Championship", name="EFL Championship", country="England",
        fbref_id="", tm_id="GB2", tm_slug="championship", api_football_id=40,
        default_team="West Ham United", teams=24, games_per_team=46,
        lite=True, fotmob_id=48, espn="eng.2", division=2,
    ),
    "SuperLig": LeagueConfig(
        key="SuperLig", name="Süper Lig", country="Türkiye",
        fbref_id="", tm_id="TR1", tm_slug="super-lig", api_football_id=203,
        default_team="Galatasaray", teams=18, games_per_team=34,
        lite=True, fotmob_id=71, espn="tur.1",
    ),
    # 오스트리아·덴마크·스위스는 정규 라운드 뒤 상·하위 그룹 라운드(스플릿) — 경기 수는 스플릿 포함
    "AustrianBundesliga": LeagueConfig(
        key="AustrianBundesliga", name="Austrian Bundesliga", country="Austria",
        fbref_id="", tm_id="A1", tm_slug="bundesliga", api_football_id=218,
        default_team="Salzburg", teams=12, games_per_team=32,
        lite=True, fotmob_id=38, espn="aut.1",
    ),
    "DanishSuperliga": LeagueConfig(
        key="DanishSuperliga", name="Danish Superliga", country="Denmark",
        fbref_id="", tm_id="DK1", tm_slug="superligaen", api_football_id=119,
        default_team="FC København", teams=12, games_per_team=32,
        lite=True, fotmob_id=46, espn="den.1",
    ),
    "SwissSuperLeague": LeagueConfig(
        key="SwissSuperLeague", name="Swiss Super League", country="Switzerland",
        fbref_id="", tm_id="C1", tm_slug="super-league", api_football_id=207,
        default_team="Young Boys", teams=12, games_per_team=38,
        lite=True, fotmob_id=69, espn="sui.1",
    ),
}

@dataclass(frozen=True)
class CandidateLeague:
    """아직 수집하지 않은 후보 리그 — 홈 리그 지도에 '준비 중'으로 보이고, 빅5 이적 실적(src/fetch_league_exports.py)만 미리 센다.
    브라질·아르헨티나·MLS 는 달력 연도 시즌이라 시즌 처리를 바꾼 뒤에 LEAGUES 로 옮긴다."""
    key: str
    name: str
    country: str
    tm_id: str
    tm_slug: str


CANDIDATE_LEAGUES: dict[str, CandidateLeague] = {
    "Brazil": CandidateLeague("Brazil", "Brasileirão", "Brazil", "BRA1", "campeonato-brasileiro-serie-a"),
    "Argentina": CandidateLeague("Argentina", "Liga Profesional", "Argentina", "ARG1", "torneo-apertura"),
    "MLS": CandidateLeague("MLS", "MLS", "United States", "MLS1", "major-league-soccer"),
}

# 풀 리그(로컬 주간 빌드·FBref·Understat·Sofascore 가 있는 리그)와 라이트 리그.
FULL_LEAGUES: list[str] = [k for k, c in LEAGUES.items() if not c.lite]
LITE_LEAGUES: list[str] = [k for k, c in LEAGUES.items() if c.lite]


# 리그 경기 대회 코드(ESPN 표기 — schedule_full·경기별 기록의 comp_code). 예전엔 곳곳에서 `endswith(".1")` 로 리그 경기를
# 골랐는데, 2부 리그(eng.2 챔피언십)를 컵으로 셌다(2026-10-22 1단계 확장).
LEAGUE_CODES: frozenset[str] = frozenset(c.espn for c in LEAGUES.values() if c.espn)


def is_league_code(code) -> bool:
    return str(code or "") in LEAGUE_CODES


def is_lite(league: str | None) -> bool:
    c = LEAGUES.get(str(league or ""))
    return bool(c and c.lite)

# 레거시 파일명(`*_2025_2026.csv`, 리그 토큰 없음)을 쓰는 리그.
PRIMARY_LEAGUE = "EPL"

# 활성 리그 — 환경변수로 전환(미설정 시 EPL).
ACTIVE_LEAGUE = os.getenv("FB_LEAGUE", PRIMARY_LEAGUE)
if ACTIVE_LEAGUE not in LEAGUES:
    # 모르는 리그를 조용히 EPL 로 바꾸면 'FB_LEAGUE=<리그> 수집기'가 EPL 파일을 덮어쓴다(2026-10-22 리그 확장 점검).
    # 'ALL'(전 리그 — 수집기가 스스로 해석)·빈 값만 EPL 기본값으로 두고, 나머지 모르는 값은 멈춘다.
    if ACTIVE_LEAGUE.strip() not in ("", "ALL", "all"):
        raise RuntimeError(f"FB_LEAGUE={ACTIVE_LEAGUE!r} 는 src/leagues.py LEAGUES 에 없는 리그")
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
    # FBref 가 2026 중 세리에A 대회명을 'Serie A (M)'으로 바꿨다(여자부 'Serie A (F)'와 구분).
    # soccerdata 기본값('Serie A')으로는 시즌 목록을 못 찾아 'No objects to concatenate' 로 실패.
    ita = sd_config.LEAGUE_DICT.get("ITA-Serie A")
    if ita is not None:
        ita["FBref"] = "Serie A (M)"


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
    for lk in sorted(LEAGUES, key=len, reverse=True):      # 긴 키 먼저(겹치는 접미사 방지)
        if lk != PRIMARY_LEAGUE and head.endswith("_" + lk):
            return (head[: -(len(lk) + 1)], lk, season)
    return (head, PRIMARY_LEAGUE, season)
