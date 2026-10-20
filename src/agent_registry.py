"""
에이전트 레지스트리 — 수집 에이전트마다 소스·실행 위치·주기·산출물·검증을 이 파일 한 곳에 적는다(설계도 1단계).

전에는 이 정보가 워크플로 9개·로컬 작업 스케줄러·각 수집기 주석에 흩어져 있어, '이 데이터가 언제 갱신되나'를
알려면 여러 파일을 읽어야 했다. 이제 DATA STATUS 화면(/status)·watchdog 이 이 표와 실행 원장(run_ledger)을 맞춰
'에이전트별로 마지막 성공이 언제였고, 허용 지연(max_age_h)을 넘었는지'를 보여 준다.

- feed = 같은 주기로 도는 단계 묶음. steps 는 실행 원장 라벨의 첫 단어(scripts/ci_try.sh "schedule EPL" → schedule,
  build_season 단계 이름)와 같다. tests/test_agent_registry.py 가 워크플로·build_season 의 모든 단계가 여기 있는지 검사한다.
- max_age_h = 마지막 성공에서 이만큼 지나면 '지연'. GH 예약 실행은 실제로 3~7시간 밀리므로 하루 1회는 30~36시간.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Feed:
    key: str
    label: str                 # 화면 표기(한글)
    steps: tuple[str, ...]     # 실행 원장 단계 이름
    runners: tuple[str, ...]   # GH 워크플로 파일 이름 또는 local-* 작업
    cadence: str               # 사람이 읽는 주기
    max_age_h: float           # 마지막 성공 후 이 시간이 지나면 지연
    outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Agent:
    key: str
    en: str
    ko: str
    does: str
    sources: tuple[str, ...]
    feeds: tuple[Feed, ...]
    checks: tuple[str, ...] = ()            # 저장 전 검증·감시(validate_data 계약, watchdog 점검 이름)
    extras: tuple[str, ...] = field(default=())   # 원장 밖에서 도는 것(라이브 스코어 등) — 화면 안내용


WEEK_H = 8 * 24   # 주 1회 작업 — 하루 여유

AGENTS: tuple[Agent, ...] = (
    Agent("match", "MATCH", "경기", "일정·결과, 리그·컵·유럽 라인업과 교체, 경기 기록·xG",
          ("ESPN", "Understat"), (
              Feed("schedule", "일정·결과", ("schedule",), ("match_refresh", "daily_data", "local-season-weekly"),
                   "매일 2회 · 08:15·13:30 KST", 30, ("schedule_full_*",)),
              Feed("lineups", "라인업·교체", ("lineups", "subs", "cup_lineups", "espn_lineups", "espn_subs"),
                   ("match_refresh", "daily_data", "local-season-weekly"), "매일 2회", 30,
                   ("espn_lineups_*", "espn_subs_*", "cup_lineups_*")),
              Feed("match_stats", "경기 기록·xG", ("match_stats",), ("match_refresh",), "매일 08:15 KST", 30,
                   ("match_stats_*",)),
          ), checks=("validate: schedule_full·espn_lineups 계약",),
          extras=("라이브 스코어 — Vercel 서버 라우트 /live-scores, ESPN 30초 캐시(원장 밖)",
                  "경기 종료 감시 — match_watch.yml: 경기일 5분 간격, 끝나고 20분 뒤 match_refresh 즉시 실행")),
    Agent("team", "TEAM", "팀·감독", "순위, 감독·교체 감지, 팀 정보·색, 팀 유닛 지표",
          ("ESPN", "Wikipedia", "UEFA", "StatBunker"), (
              Feed("standings", "순위", ("standings", "standings_history"), ("match_refresh", "daily_data"),
                   "매일 2회", 30, ("standings_*",)),
              Feed("managers", "감독·교체", ("laliga_managers", "serie_managers", "bundes_managers", "ligue_managers",
                                          "ligapt_managers", "erediv_managers", "mgr_changes", "manager_careers",
                                          "sync_manager_profiles", "enrich_manager"),
                   ("daily_data",), "매일 13:30 KST", 36, ("manager_profiles_*", "manager_changes_*")),
              Feed("team_info", "팀 정보·계수", ("enrich_team", "team_colors", "uefa_coefficients"), ("daily_data",),
                   "매일 13:30 KST", 36),
              Feed("units", "팀 유닛 지표", ("team_defense", "unit_metrics", "statbunker"), ("local-season-weekly",),
                   "주 1회 · 수 12:30 KST(이 PC)", WEEK_H, ("team_unit_metrics_*", "team_defense_*")),
          ), checks=("validate: standings 계약", "watchdog: coverage(감독 프로필)")),
    Agent("stats", "STATS", "선수 스탯·평점", "선수 시즌 스탯·고급 지표·xG·히트맵, 경기별 평점·최근 폼",
          ("FBref", "Sofascore", "Understat", "FotMob"), (
              Feed("sofascore", "Sofascore 평점", ("sofascore", "merge_sofascore"),
                   ("local-sofascore-daily", "local-season-weekly"), "매일 11:40 KST(이 PC)", 48,
                   ("players_sofascore_stats_*",)),
              Feed("fotmob", "FotMob 평점·최근 폼·골·도움", ("fotmob_ratings", "fotmob_matches"), ("daily_data", "match_refresh"),
                   "매일 2회 · 경기 20분 뒤", 30, ("fotmob_*",)),
              Feed("understat", "xG 계열(Understat)", ("understat_live",), ("match_refresh",), "매일 · 경기 20분 뒤", 36,
                   ("understat_players_*",)),
              Feed("rating_history", "평점 일일 기록", ("rating_history",), ("daily_data",), "매일 13:30 KST", 36),
              Feed("season_build", "FBref·Understat·히트맵", ("fbref", "understat", "prev_season", "comp_usage",
                                                            "heatmaps"),
                   ("local-season-weekly",), "주 1회 · 수 12:30 KST(이 PC)", WEEK_H,
                   ("players_full_*", "player_heatmaps_*")),
          ), checks=("validate: players_full 계약 · 팀 xG 0", "watchdog: ratings·rating_history·xg")),
    Agent("transfer", "TRANSFER", "이적", "이적·루머, 뉴스 이적 소문",
          ("Transfermarkt", "뉴스 RSS"), (
              Feed("transfers", "이적·루머", ("transfers", "rumors"), ("tm_data", "transfer_watch"),
                   "매일 10:30·18:30 KST · 창 열리면 1~3시간", 24, ("transfers_*", "transfer_rumors_*")),
              Feed("buzz", "이적 소문(뉴스)", ("buzz",), ("daily_data",), "매일 13:30 KST", 36),
          ), checks=("validate: transfers 계약", "watchdog: tm_agent"),
          extras=("이적시장 감시 — transfer_watch.yml: 창이 열려 있을 때 리그 이적 페이지로 새 이적 클럽만 다시 받기(마감 7일 전부터 60분)",)),
    Agent("value", "VALUE", "가치·계약", "시장가치 스냅샷, 계약 만료, TM 선수 정보(국적·포지션·사진)",
          ("Transfermarkt",), (
              Feed("contracts", "계약·시장가치", ("contracts", "market_value"), ("tm_data",), "매일 10:30·18:30 KST",
                   24, ("market_value_*",)),
              Feed("tm_profile", "TM 선수 정보", ("transfermarkt",), ("local-season-weekly",),
                   "주 1회 · 수 12:30 KST(이 PC)", WEEK_H),
          )),
    Agent("injury", "INJURY", "부상", "현재 부상자·결장 명단, 통산 부상 이력",
          ("Transfermarkt", "FotMob"), (
              Feed("current", "현재 부상·결장", ("injuries", "fotmob_injuries"), ("tm_data", "match_refresh", "daily_data"),
                   "하루 3~4회", 24, ("transfermarkt_injuries_*", "fotmob_injuries*")),
              Feed("history", "통산 부상 이력", ("injury_history",), ("tm_data",), "주 1회 · 월 12:30 KST", WEEK_H,
                   ("tm_injury_history_*",)),
          ), checks=("수집기 가드: 부상자 0명·이력 급감 저장 차단",)),
    Agent("news", "NEWS", "뉴스", "뉴스 수집·번역(팀 태그) · 선수 태깅(이름 전체·성+클럽, news_tags)",
          ("ESPN", "뉴스 RSS"), (
              Feed("news", "뉴스 수집·번역", ("news",), ("daily_news",), "2시간마다", 6, ("news.db",)),
          ), checks=("watchdog: news(수집 1일·번역률 50%)",)),
    Agent("intl", "INTERNATIONAL", "국가대표", "FIFA 랭킹, A매치 일정·기간, 대표팀 소집 명단 → 팀 일정 탭·예측",
          ("FIFA", "ESPN", "Wikipedia"), (
              Feed("fifa_ranking", "FIFA 랭킹", ("fifa_ranking",), ("daily_data",), "매일 13:30 KST", 36,
                   ("fifa_ranking.csv",)),
              Feed("callups", "A매치 기간·소집 명단", ("intl",), ("daily_data",), "매일 13:30 KST", 36,
                   ("intl_matches.csv", "intl_windows.json", "intl_callups.csv")),
          ), checks=("수집기: 국가대표 경기 0건·매칭 소집 0명이면 기존 파일 유지",)),
    Agent("identity", "IDENTITY", "기준 정보", "리그 소속팀(승격·강등), 선수 이름 레지스트리, 위키 스쿼드",
          ("Transfermarkt", "ESPN", "Wikipedia"), (
              Feed("season_teams", "리그 소속팀", ("season_teams",), ("daily_data",), "매일 13:30 KST", 36),
              Feed("names", "선수 이름 레지스트리", ("player_registry",), ("match_refresh", "daily_data"), "매일 2회", 30,
                   ("player_registry_*",)),
              Feed("wiki_squads", "위키 스쿼드", ("wiki_squads",), ("daily_data",), "매일 13:30 KST", 36),
          ), checks=("watchdog: names(기준 명단 밖 이름)",)),
    Agent("analyst", "ANALYST", "예측·해석", "경기 예측(모델·ClubElo·팬 투표)과 성적표",
          ("ClubElo", "Sofascore 팬 투표"), (
              Feed("predictions", "예측·성적표", ("clubelo", "log_predictions"), ("match_refresh", "daily_data"),
                   "매일 2회", 30, ("predictions_log.csv",)),
              Feed("fanvote", "팬 투표", ("fanvote",), ("local-fanvote",), "매일 10:30·18:30 KST(이 PC)", 24,
                   ("fan_votes.csv",)),
          ), extras=("경기 리뷰 — /api/review, ESPN 경기 상세로 규칙 기반 생성(요청 시)",)),
    Agent("watchdog", "WATCHDOG", "감시·검증", "OVR·평점 자체 검증, 운영 점검(문제 시 GitHub 이슈)",
          ("모든 에이전트 결과",), (
              Feed("audits", "OVR·평점 검증", ("ovr_consistency", "rating_audit"), ("daily_data",), "매일 13:30 KST", 36,
                   ("eval/ovr_audit.json", "eval/rating_audit.json")),
          ), extras=("운영 점검 — watchdog.yml 매일 17:00 KST, 결과는 data/ops/watchdog.json",)),
    Agent("serving", "SERVING", "서빙", "홈 스냅샷, 외부 저장소 깨우기, 그래프·벡터 주간 재적재",
          ("통합 DB",), (
              Feed("hub", "홈 스냅샷", ("precompute_hub",), ("match_refresh", "daily_data"), "매일 2회", 30,
                   ("home_all.json",)),
              Feed("infra", "벡터·그래프 핑", ("infra_ping",), ("daily_data",), "매일 13:30 KST", 36),
              Feed("graph", "그래프·벡터 재적재", ("kg_reload", "kg_extras", "vectors_reload"), ("kg_reload",),
                   "주 1회 · 화 12:00 KST", WEEK_H),
          ), checks=("watchdog: hub(스냅샷 36시간)",)),
)


def step_index() -> dict[str, tuple[Agent, Feed]]:
    """단계 이름 → (에이전트, feed)."""
    out: dict[str, tuple[Agent, Feed]] = {}
    for a in AGENTS:
        for f in a.feeds:
            for s in f.steps:
                out[s] = (a, f)
    return out
