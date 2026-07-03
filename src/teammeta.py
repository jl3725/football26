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
    # 26/27 승격
    "Coventry City": "#7BB6E0", "Hull City": "#F5A12D", "Ipswich Town": "#2A5CAF",
    # La Liga 25/26
    "Barcelona": "#A50044", "Real Madrid": "#FEBE10", "Villarreal": "#F4D03F",
    "Atlético Madrid": "#CB3524", "Real Betis": "#00954C", "Celta Vigo": "#8AC3EE",
    "Getafe": "#005999", "Rayo Vallecano": "#E53027", "Valencia": "#F18E00",
    "Real Sociedad": "#0067B1", "Espanyol": "#007FC8", "Athletic Club": "#EE2523",
    "Elche": "#00963E", "Alavés": "#0761AF", "Sevilla": "#D81920", "Osasuna": "#0A346F",
    "Mallorca": "#E20613", "Levante": "#004E9E", "Girona": "#CE1126", "Oviedo": "#004B9E",
    # La Liga 26/27 승격
    "Deportivo A Coruña": "#0075BE", "Málaga": "#0067B1", "Racing Santander": "#009B48",
}

# Transfermarkt verein id (크레스트 로고용)
TEAM_VEREIN: dict[str, int] = {
    "Arsenal": 11, "Aston Villa": 405, "Bournemouth": 989, "Brentford": 1148,
    "Brighton": 1237, "Burnley": 1132, "Chelsea": 631, "Crystal Palace": 873,
    "Everton": 29, "Fulham": 931, "Leeds United": 399, "Liverpool": 31,
    "Manchester City": 281, "Manchester Utd": 985, "Newcastle United": 762,
    "Nottingham Forest": 703, "Sunderland": 289, "Tottenham Hotspur": 148,
    "West Ham United": 379, "Wolves": 543,
    # 26/27 승격 팀 로고는 TEAM_LOGO_URL(ESPN) override 사용 (verein id 미확정)
    # La Liga 25/26 (Transfermarkt verein id)
    "Barcelona": 131, "Real Madrid": 418, "Villarreal": 1050, "Atlético Madrid": 13,
    "Real Betis": 150, "Celta Vigo": 940, "Getafe": 3709, "Rayo Vallecano": 367,
    "Valencia": 1049, "Real Sociedad": 681, "Espanyol": 714, "Athletic Club": 621,
    "Elche": 1531, "Alavés": 1108, "Sevilla": 368, "Osasuna": 331, "Mallorca": 237,
    "Levante": 3368, "Girona": 12321, "Oviedo": 2497,
    # La Liga 26/27 승격 (Segunda → Primera)
    "Deportivo A Coruña": 897, "Málaga": 1084, "Racing Santander": 630,
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
    # 26/27 승격
    "Coventry City": ("Coventry City FC", 32609), "Hull City": ("Hull City AFC", 25586),
    "Ipswich Town": ("Ipswich Town FC", 30311),
    # La Liga 25/26
    "Barcelona": ("FC Barcelona", 99354), "Real Madrid": ("Real Madrid CF", 78297),
    "Villarreal": ("Villarreal CF", 23500), "Atlético Madrid": ("Atlético de Madrid", 70460),
    "Real Betis": ("Real Betis Balompié", 60720), "Celta Vigo": ("RC Celta de Vigo", 29000),
    "Getafe": ("Getafe CF", 17393), "Rayo Vallecano": ("Rayo Vallecano", 14708),
    "Valencia": ("Valencia CF", 49430), "Real Sociedad": ("Real Sociedad", 39500),
    "Espanyol": ("RCD Espanyol", 40000), "Athletic Club": ("Athletic Club", 53289),
    "Elche": ("Elche CF", 33732), "Alavés": ("Deportivo Alavés", 19840),
    "Sevilla": ("Sevilla FC", 43883), "Osasuna": ("CA Osasuna", 23576),
    "Mallorca": ("RCD Mallorca", 23142), "Levante": ("Levante UD", 26354),
    "Girona": ("Girona FC", 14624), "Oviedo": ("Real Oviedo", 30500),
    # La Liga 26/27 승격
    "Deportivo A Coruña": ("RC Deportivo de La Coruña", 32000),
    "Málaga": ("Málaga CF", 30044), "Racing Santander": ("Real Racing Club", 22222),
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
    # 26/27 승격
    "Coventry City": {"city": "코번트리", "stadium": "코번트리 빌딩 소사이어티 아레나", "founded": 1883, "nick": "The Sky Blues", "desc": "26/27 승격. 잉글랜드 미들랜즈의 스카이 블루스."},
    "Hull City": {"city": "킹스턴어폰헐", "stadium": "MKM 스타디움", "founded": 1904, "nick": "The Tigers", "desc": "26/27 승격. 요크셔 험버사이드의 타이거스."},
    "Ipswich Town": {"city": "입스위치", "stadium": "포트먼 로드", "founded": 1878, "nick": "The Tractor Boys", "desc": "26/27 승격. 이스트앵글리아의 트랙터 보이스."},
    # La Liga 25/26
    "Barcelona": {"city": "바르셀로나", "stadium": "스포티파이 캄 노우", "founded": 1899, "nick": "Blaugrana", "desc": "카탈루냐 명문. 티키타카의 상징."},
    "Real Madrid": {"city": "마드리드", "stadium": "산티아고 베르나베우", "founded": 1902, "nick": "Los Blancos", "desc": "유러피언컵 최다 우승의 세계적 명문."},
    "Villarreal": {"city": "비야레알", "stadium": "에스타디오 데 라 세라미카", "founded": 1923, "nick": "Yellow Submarine", "desc": "발렌시아주 소도시 클럽. 유럽대항전 단골."},
    "Atlético Madrid": {"city": "마드리드", "stadium": "메트로폴리타노", "founded": 1903, "nick": "Los Colchoneros", "desc": "시메오네의 강한 조직력·수비."},
    "Real Betis": {"city": "세비야", "stadium": "베니토 비야마린", "founded": 1907, "nick": "Los Verdiblancos", "desc": "안달루시아 열성 팬덤의 녹백 클럽."},
    "Celta Vigo": {"city": "비고", "stadium": "발라이도스", "founded": 1923, "nick": "Os Celestes", "desc": "갈리시아 연고의 하늘색 클럽."},
    "Getafe": {"city": "헤타페", "stadium": "콜리세움", "founded": 1983, "nick": "Azulones", "desc": "마드리드 근교의 강한 수비 클럽."},
    "Rayo Vallecano": {"city": "마드리드 (바예카스)", "stadium": "바예카스", "founded": 1924, "nick": "Los Franjirrojos", "desc": "노동자 동네의 열성 클럽."},
    "Valencia": {"city": "발렌시아", "stadium": "메스타야", "founded": 1919, "nick": "Los Che", "desc": "지중해 연안 전통 명문."},
    "Real Sociedad": {"city": "산세바스티안", "stadium": "레알레 아레나", "founded": 1909, "nick": "La Real", "desc": "바스크 육성 명가."},
    "Espanyol": {"city": "바르셀로나 (코르네야)", "stadium": "RCDE 스타디움", "founded": 1900, "nick": "Los Pericos", "desc": "바르셀로나의 또 다른 클럽."},
    "Athletic Club": {"city": "빌바오", "stadium": "산 마메스", "founded": 1898, "nick": "Los Leones", "desc": "바스크 순혈주의 정책의 전통 명문."},
    "Elche": {"city": "엘체", "stadium": "마르티네스 발레로", "founded": 1923, "nick": "Franjiverdes", "desc": "발렌시아주 녹색 띠 클럽."},
    "Alavés": {"city": "비토리아", "stadium": "멘디소로사", "founded": 1921, "nick": "Babazorros", "desc": "바스크 알라바 연고 클럽."},
    "Sevilla": {"city": "세비야", "stadium": "라몬 산체스 피스후안", "founded": 1890, "nick": "Los Nervionenses", "desc": "유로파리그 최다 우승 클럽."},
    "Osasuna": {"city": "팜플로나", "stadium": "엘 사다르", "founded": 1920, "nick": "Los Rojillos", "desc": "나바라 연고의 붉은 클럽."},
    "Mallorca": {"city": "팔마", "stadium": "손 모이시", "founded": 1916, "nick": "Los Bermellones", "desc": "발레아레스 제도 연고 클럽."},
    "Levante": {"city": "발렌시아", "stadium": "시우타트 데 발렌시아", "founded": 1909, "nick": "Granotes", "desc": "발렌시아의 청적 클럽."},
    "Girona": {"city": "지로나", "stadium": "몬틸리비", "founded": 1930, "nick": "Gironins", "desc": "시티 풋볼 그룹 소속 카탈루냐 클럽."},
    "Oviedo": {"city": "오비에도", "stadium": "카를로스 타르티에레", "founded": 1926, "nick": "Los Carbayones", "desc": "아스투리아스 전통 클럽."},
    # La Liga 26/27 승격
    "Deportivo A Coruña": {"city": "아 코루냐", "stadium": "리아소르", "founded": 1906, "nick": "Superdépor", "desc": "갈리시아 전통 명문. 26/27 시즌 승격."},
    "Málaga": {"city": "말라가", "stadium": "라 로살레다", "founded": 1904, "nick": "Los Boquerones", "desc": "안달루시아 코스타델솔 클럽. 26/27 시즌 승격."},
    "Racing Santander": {"city": "산탄데르", "stadium": "엘 사르디네로", "founded": 1913, "nick": "Los Racinguistas", "desc": "칸타브리아 전통 클럽. 26/27 시즌 승격."},
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


# ESPN 로고 override — Transfermarkt verein id 가 불확실/충돌하는 팀(승격팀 등).
# (예: 1049 는 Valencia. 승격팀은 ESPN 라벨이 정확해 ESPN 로고 URL 을 직접 지정.)
TEAM_LOGO_URL: dict[str, str] = {
    "Coventry City": "https://a.espncdn.com/i/teamlogos/soccer/500/388.png",
    "Hull City": "https://a.espncdn.com/i/teamlogos/soccer/500/306.png",
    "Ipswich Town": "https://a.espncdn.com/i/teamlogos/soccer/500/373.png",
}


def team_logo(team: str) -> str:
    if team in TEAM_LOGO_URL:
        return TEAM_LOGO_URL[team]
    vid = TEAM_VEREIN.get(team)
    return f"https://tmssl.akamaized.net/images/wappen/head/{vid}.png" if vid else ""


def team_fullname(team: str) -> str:
    return TEAM_EXTRA.get(team, (team, 0))[0]


def team_capacity(team: str) -> int:
    return TEAM_EXTRA.get(team, (team, 0))[1]
