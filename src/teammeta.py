"""
streamlit 비의존 팀 정적 메타(색·로고·풀네임·수용인원).

`src/ui/common.py` 는 streamlit 을 임포트하므로 API/서버 프로세스에서 끌어오면
무거운 의존이 딸려온다. 여기에 순수 데이터만 추출해 API·CLI 등 어디서든 가볍게
재사용한다. (추후 리그 확장 시 리그별 dict 로 확장)
"""
from __future__ import annotations

# EPL 25/26 팀 대표 컬러
TEAM_COLOR: dict[str, str] = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Bournemouth": "#DA291C",
    "Brentford": "#E30613", "Brighton": "#0057B8", "Burnley": "#6C1D45",
    "Chelsea": "#034694", "Crystal Palace": "#1B458F", "Everton": "#003399",
    "Fulham": "#1d1d1f", "Leeds United": "#1D428A", "Liverpool": "#C8102E",
    "Manchester City": "#6CABDD", "Manchester Utd": "#DA291C",
    "Newcastle United": "#241F20", "Nottingham Forest": "#DD0000",
    "Sunderland": "#EB172B", "Tottenham Hotspur": "#132257",
    "West Ham United": "#7A263A", "Wolves": "#FDB913",
}

# Transfermarkt verein id (크레스트 로고용)
TEAM_VEREIN: dict[str, int] = {
    "Arsenal": 11, "Aston Villa": 405, "Bournemouth": 989, "Brentford": 1148,
    "Brighton": 1237, "Burnley": 1132, "Chelsea": 631, "Crystal Palace": 873,
    "Everton": 29, "Fulham": 931, "Leeds United": 399, "Liverpool": 31,
    "Manchester City": 281, "Manchester Utd": 985, "Newcastle United": 762,
    "Nottingham Forest": 703, "Sunderland": 289, "Tottenham Hotspur": 148,
    "West Ham United": 379, "Wolves": 543,
}

# 풀네임 + 홈구장 수용인원
TEAM_EXTRA: dict[str, tuple[str, int]] = {
    "Arsenal": ("Arsenal FC", 60704), "Aston Villa": ("Aston Villa FC", 42657),
    "Bournemouth": ("AFC Bournemouth", 11307), "Brentford": ("Brentford FC", 17250),
    "Brighton": ("Brighton & Hove Albion", 31800), "Burnley": ("Burnley FC", 21944),
    "Chelsea": ("Chelsea FC", 40343), "Crystal Palace": ("Crystal Palace FC", 25486),
    "Everton": ("Everton FC", 52888), "Fulham": ("Fulham FC", 29600),
    "Leeds United": ("Leeds United FC", 37792), "Liverpool": ("Liverpool FC", 61276),
    "Manchester City": ("Manchester City FC", 53400), "Manchester Utd": ("Manchester United FC", 74310),
    "Newcastle United": ("Newcastle United FC", 52305), "Nottingham Forest": ("Nottingham Forest FC", 30404),
    "Sunderland": ("Sunderland AFC", 49000), "Tottenham Hotspur": ("Tottenham Hotspur FC", 62850),
    "West Ham United": ("West Ham United FC", 62500), "Wolves": ("Wolverhampton Wanderers FC", 31750),
}


# 구단 상세(도시·홈구장·창단·별명·한줄 설명) — overview.py TEAM_INFO 와 동일
TEAM_INFO: dict[str, dict] = {
    "Arsenal": {"city": "런던 (북부·홀로웨이)", "stadium": "에미레이츠 스타디움", "founded": 1886, "nick": "The Gunners", "desc": "북런던 명문. 아르테타 체제의 점유·고강도 전방압박으로 우승에 도전한다."},
    "Aston Villa": {"city": "버밍엄", "stadium": "빌라 파크", "founded": 1874, "nick": "The Villans", "desc": "잉글랜드 축구 창립 멤버. 에메리 부임 후 유럽대항전 단골로 부활."},
    "Bournemouth": {"city": "본머스", "stadium": "비탈리티 스타디움", "founded": 1899, "nick": "The Cherries", "desc": "남부 해안 소도시 클럽. 이라올라의 강한 압박·전환 축구."},
    "Brentford": {"city": "런던 (서부)", "stadium": "지테크 커뮤니티 스타디움", "founded": 1889, "nick": "The Bees", "desc": "데이터·셋피스 강점의 스마트 운영 클럽."},
    "Brighton": {"city": "브라이턴 앤 호브", "stadium": "아메리칸 익스프레스 스타디움", "founded": 1901, "nick": "The Seagulls", "desc": "영입·육성 모델의 모범. 공격적 점유 축구."},
    "Burnley": {"city": "번리 (랭커셔)", "stadium": "터프 무어", "founded": 1882, "nick": "The Clarets", "desc": "전통의 랭커셔 클럽. 25/26 시즌 승격."},
    "Chelsea": {"city": "런던 (풀럼)", "stadium": "스탬퍼드 브리지", "founded": 1905, "nick": "The Blues", "desc": "대규모 영입으로 젊은 스쿼드를 리빌딩 중인 서런던 명문."},
    "Crystal Palace": {"city": "런던 (남부)", "stadium": "셀허스트 파크", "founded": 1905, "nick": "The Eagles", "desc": "열성 팬덤의 남런던 클럽. 24/25 FA컵 우승으로 첫 메이저 트로피."},
    "Everton": {"city": "리버풀", "stadium": "힐 디킨슨 스타디움", "founded": 1878, "nick": "The Toffees", "desc": "리버풀 연고 전통 명문. 25/26 브램리무어 독 신구장으로 이전."},
    "Fulham": {"city": "런던 (풀럼)", "stadium": "크레이븐 코티지", "founded": 1879, "nick": "The Cottagers", "desc": "템스강변 크레이븐 코티지를 쓰는 서런던 클럽."},
    "Leeds United": {"city": "리즈 (요크셔)", "stadium": "엘런드 로드", "founded": 1919, "nick": "The Whites", "desc": "요크셔 명문. 25/26 시즌 승격."},
    "Liverpool": {"city": "리버풀", "stadium": "안필드", "founded": 1892, "nick": "The Reds", "desc": "유럽 최고 명문 중 하나. 강한 압박과 빠른 측면 전개."},
    "Manchester City": {"city": "맨체스터", "stadium": "에티하드 스타디움", "founded": 1880, "nick": "The Citizens", "desc": "과르디올라의 점유 지배 축구. 최근 잉글랜드 최강 클럽."},
    "Manchester Utd": {"city": "맨체스터", "stadium": "올드 트래퍼드", "founded": 1878, "nick": "The Red Devils", "desc": "세계적 명문. 영광 재건을 위한 리빌딩 진행 중."},
    "Newcastle United": {"city": "뉴캐슬어폰타인", "stadium": "세인트 제임스 파크", "founded": 1892, "nick": "The Magpies", "desc": "북동부 열성 클럽. 대규모 투자 이후 상위권 도약."},
    "Nottingham Forest": {"city": "노팅엄", "stadium": "시티 그라운드", "founded": 1865, "nick": "Forest", "desc": "두 차례 유러피언컵을 들어올린 역사적 클럽."},
    "Sunderland": {"city": "선덜랜드", "stadium": "스타디움 오브 라이트", "founded": 1879, "nick": "The Black Cats", "desc": "북동부 열성 클럽. 25/26 시즌 승격."},
    "Tottenham Hotspur": {"city": "런던 (북부·토트넘)", "stadium": "토트넘 홋스퍼 스타디움", "founded": 1882, "nick": "Spurs", "desc": "북런던 클럽. 24/25 유로파리그 우승."},
    "West Ham United": {"city": "런던 (동부·스트랫퍼드)", "stadium": "런던 스타디움", "founded": 1895, "nick": "The Hammers", "desc": "이스트런던 클럽. 22/23 컨퍼런스리그 우승."},
    "Wolves": {"city": "울버햄프턴", "stadium": "몰리뉴 스타디움", "founded": 1877, "nick": "Wolves", "desc": "미들랜즈 전통 클럽. 강한 포르투갈 커넥션."},
}


# 공식 주장 (overview.py TEAM_CAPTAINS 와 동일)
TEAM_CAPTAINS: dict[str, str] = {
    "Arsenal": "Martin Odegaard", "Aston Villa": "John McGinn", "Bournemouth": "Adam Smith",
    "Brentford": "Nathan Collins", "Brighton": "Lewis Dunk", "Burnley": "Josh Cullen",
    "Chelsea": "Reece James", "Crystal Palace": "Dean Henderson", "Everton": "Seamus Coleman",
    "Fulham": "Tom Cairney", "Leeds United": "Ethan Ampadu", "Liverpool": "Virgil van Dijk",
    "Manchester City": "Bernardo Silva", "Manchester Utd": "Bruno Fernandes",
    "Newcastle United": "Bruno Guimaraes", "Nottingham Forest": "Ryan Yates",
    "Sunderland": "Granit Xhaka", "Tottenham Hotspur": "Cristian Romero",
    "West Ham United": "Jarrod Bowen", "Wolves": "Toti Gomes",
}


def team_info(team: str) -> dict:
    return TEAM_INFO.get(team, {})


def team_captain(team: str) -> str:
    return TEAM_CAPTAINS.get(team, "")


def team_color(team: str) -> str:
    return TEAM_COLOR.get(team, "#444a55")


def team_logo(team: str) -> str:
    vid = TEAM_VEREIN.get(team)
    return f"https://tmssl.akamaized.net/images/wappen/head/{vid}.png" if vid else ""


def team_fullname(team: str) -> str:
    return TEAM_EXTRA.get(team, (team, 0))[0]


def team_capacity(team: str) -> int:
    return TEAM_EXTRA.get(team, (team, 0))[1]
