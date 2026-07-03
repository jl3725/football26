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
    # Serie A 25/26
    "Inter": "#0A2896", "Milan": "#FB090B", "Juventus": "#1A1A1A", "Napoli": "#009DE0",
    "Roma": "#8E1F2F", "Lazio": "#6AADE4", "Atalanta": "#1961B3", "Fiorentina": "#5D2E8C",
    "Bologna": "#A5152A", "Torino": "#7B1E1E", "Udinese": "#2B2B2B", "Genoa": "#B0182B",
    "Cagliari": "#B31942", "Como": "#0B4DA1", "Cremonese": "#A61C2B", "Hellas Verona": "#1C2E63",
    "Lecce": "#D4A017", "Parma": "#F4C400", "Pisa": "#12284B", "Sassuolo": "#00A752",
    # Serie A 26/27 승격
    "Frosinone": "#0055A5", "Monza": "#E2001A", "Venezia": "#0A5C36",
    # Bundesliga 25/26
    "Bayern Munich": "#DC052D", "Dortmund": "#FDE100", "Leverkusen": "#E32219",
    "RB Leipzig": "#DD0741", "Stuttgart": "#E32219", "Frankfurt": "#E1000F",
    "Freiburg": "#C4122E", "Union Berlin": "#EB1923", "Werder Bremen": "#1D9053",
    "Gladbach": "#00843D", "Wolfsburg": "#65B32E", "Mainz 05": "#C3141E",
    "Augsburg": "#BA3733", "Hoffenheim": "#1961B4", "Köln": "#ED1C24",
    "St Pauli": "#61371C", "Hamburger SV": "#003DA5", "Heidenheim": "#E30613",
    # Bundesliga 26/27 승격
    "Schalke 04": "#004D9D", "SC Paderborn": "#164194", "SV Elversberg": "#C4122E",
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
    # Serie A 25/26 (Transfermarkt verein id)
    "Inter": 46, "Milan": 5, "Juventus": 506, "Napoli": 6195, "Roma": 12, "Lazio": 398,
    "Atalanta": 800, "Fiorentina": 430, "Bologna": 1025, "Torino": 416, "Udinese": 410,
    "Genoa": 252, "Cagliari": 1390, "Como": 1047, "Cremonese": 2239, "Hellas Verona": 276,
    "Lecce": 1005, "Parma": 130, "Pisa": 4171, "Sassuolo": 6574,
    # Serie A 26/27 승격
    "Frosinone": 8970, "Monza": 2919, "Venezia": 607,
    # Bundesliga 25/26 (Transfermarkt verein id)
    "Bayern Munich": 27, "Dortmund": 16, "Leverkusen": 15, "RB Leipzig": 23826,
    "Stuttgart": 79, "Frankfurt": 24, "Freiburg": 60, "Union Berlin": 89,
    "Werder Bremen": 86, "Gladbach": 18, "Wolfsburg": 82, "Mainz 05": 39,
    "Augsburg": 167, "Hoffenheim": 533, "Köln": 3, "St Pauli": 35,
    "Hamburger SV": 41, "Heidenheim": 2036,
    # Bundesliga 26/27 승격
    "Schalke 04": 33, "SC Paderborn": 127, "SV Elversberg": 64,
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
    # Serie A 25/26
    "Inter": ("FC Internazionale Milano", 75923), "Milan": ("AC Milan", 75923),
    "Juventus": ("Juventus FC", 41507), "Napoli": ("SSC Napoli", 54726),
    "Roma": ("AS Roma", 70634), "Lazio": ("SS Lazio", 70634),
    "Atalanta": ("Atalanta BC", 19300), "Fiorentina": ("ACF Fiorentina", 43147),
    "Bologna": ("Bologna FC 1909", 38279), "Torino": ("Torino FC", 27958),
    "Udinese": ("Udinese Calcio", 25144), "Genoa": ("Genoa CFC", 33205),
    "Cagliari": ("Cagliari Calcio", 16416), "Como": ("Como 1907", 13602),
    "Cremonese": ("US Cremonese", 16003), "Hellas Verona": ("Hellas Verona FC", 39211),
    "Lecce": ("US Lecce", 31533), "Parma": ("Parma Calcio 1913", 22885),
    "Pisa": ("Pisa SC", 17000), "Sassuolo": ("US Sassuolo", 21584),
    # Serie A 26/27 승격
    "Frosinone": ("Frosinone Calcio", 16227), "Monza": ("AC Monza", 16917),
    "Venezia": ("Venezia FC", 11150),
    # Bundesliga 25/26
    "Bayern Munich": ("FC Bayern München", 75024), "Dortmund": ("Borussia Dortmund", 81365),
    "Leverkusen": ("Bayer 04 Leverkusen", 30210), "RB Leipzig": ("RB Leipzig", 47069),
    "Stuttgart": ("VfB Stuttgart", 60449), "Frankfurt": ("Eintracht Frankfurt", 58000),
    "Freiburg": ("SC Freiburg", 34700), "Union Berlin": ("1. FC Union Berlin", 22012),
    "Werder Bremen": ("SV Werder Bremen", 42100), "Gladbach": ("Borussia Mönchengladbach", 54042),
    "Wolfsburg": ("VfL Wolfsburg", 30000), "Mainz 05": ("1. FSV Mainz 05", 33305),
    "Augsburg": ("FC Augsburg", 30660), "Hoffenheim": ("TSG 1899 Hoffenheim", 30150),
    "Köln": ("1. FC Köln", 50000), "St Pauli": ("FC St. Pauli", 29546),
    "Hamburger SV": ("Hamburger SV", 57000), "Heidenheim": ("1. FC Heidenheim", 15000),
    # Bundesliga 26/27 승격
    "Schalke 04": ("FC Schalke 04", 62271), "SC Paderborn": ("SC Paderborn 07", 15000),
    "SV Elversberg": ("SV 07 Elversberg", 10000),
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
    # Serie A 25/26
    "Inter": {"city": "밀라노", "stadium": "산 시로 (주세페 메아차)", "founded": 1908, "nick": "Nerazzurri", "desc": "밀라노 명문. 최근 세리에A 최강 중 하나, 강한 조직력."},
    "Milan": {"city": "밀라노", "stadium": "산 시로 (주세페 메아차)", "founded": 1899, "nick": "Rossoneri", "desc": "유러피언컵 다관왕의 세계적 명문. 붉은-검정 클럽."},
    "Juventus": {"city": "토리노", "stadium": "알리안츠 스타디움", "founded": 1897, "nick": "La Vecchia Signora", "desc": "이탈리아 최다 우승의 명문. 흑백 유니폼."},
    "Napoli": {"city": "나폴리", "stadium": "디에고 아르만도 마라도나", "founded": 1926, "nick": "Partenopei", "desc": "남부의 자존심. 마라도나 전설의 하늘색 클럽."},
    "Roma": {"city": "로마", "stadium": "스타디오 올림피코", "founded": 1927, "nick": "Giallorossi", "desc": "수도 로마의 열성 클럽. 늑대 상징."},
    "Lazio": {"city": "로마", "stadium": "스타디오 올림피코", "founded": 1900, "nick": "Biancocelesti", "desc": "로마 더비의 하늘색 클럽. 독수리 상징."},
    "Atalanta": {"city": "베르가모", "stadium": "게비스 스타디움", "founded": 1907, "nick": "La Dea", "desc": "가스페리니의 공격 축구로 유럽대항전 단골이 된 돌풍의 팀."},
    "Fiorentina": {"city": "피렌체", "stadium": "아르테미오 프랑키", "founded": 1926, "nick": "Viola", "desc": "토스카나의 보라색 클럽."},
    "Bologna": {"city": "볼로냐", "stadium": "레나토 달라라", "founded": 1909, "nick": "Rossoblù", "desc": "에밀리아로마냐 전통 클럽. 최근 유럽대항전 진출."},
    "Torino": {"city": "토리노", "stadium": "올림피코 그란데 토리노", "founded": 1906, "nick": "Il Toro", "desc": "토리노 더비의 적갈색(그라나타) 클럽."},
    "Udinese": {"city": "우디네", "stadium": "블루에너지 스타디움", "founded": 1896, "nick": "Le Zebrette", "desc": "프리울리 연고. 스카우팅·육성 강점의 클럽."},
    "Genoa": {"city": "제노바", "stadium": "루이지 페라리스", "founded": 1893, "nick": "Il Grifone", "desc": "이탈리아 최고(最古) 클럽 중 하나. 붉은-파랑."},
    "Cagliari": {"city": "칼리아리 (사르데냐)", "stadium": "우니폴 도무스", "founded": 1920, "nick": "Casteddu", "desc": "사르데냐 섬 연고 클럽."},
    "Como": {"city": "코모", "stadium": "주세페 시니갈리아", "founded": 1907, "nick": "Lariani", "desc": "코모 호반 클럽. 대규모 투자로 부활."},
    "Cremonese": {"city": "크레모나", "stadium": "조반니 지니", "founded": 1903, "nick": "Grigiorossi", "desc": "롬바르디아 크레모나 연고 클럽."},
    "Hellas Verona": {"city": "베로나", "stadium": "마르칸토니오 벤테고디", "founded": 1903, "nick": "Gialloblù", "desc": "베네토 베로나의 노랑-파랑 클럽."},
    "Lecce": {"city": "레체", "stadium": "비아 델 마레", "founded": 1908, "nick": "I Salentini", "desc": "풀리아 살렌토 반도 연고 클럽."},
    "Parma": {"city": "파르마", "stadium": "엔니오 타르디니", "founded": 1913, "nick": "Crociati", "desc": "에밀리아 명문. 90~00년대 유럽대항전 강호."},
    "Pisa": {"city": "피사", "stadium": "아레나 가리발디", "founded": 1909, "nick": "Nerazzurri", "desc": "토스카나 피사 연고. 오랜만의 세리에A 복귀."},
    "Sassuolo": {"city": "사수올로 (레조에밀리아)", "stadium": "마페이 스타디움", "founded": 1920, "nick": "Neroverdi", "desc": "에밀리아 소도시의 녹-검정 클럽."},
    # Serie A 26/27 승격
    "Frosinone": {"city": "프로시노네 (라치오)", "stadium": "베니토 스티르페", "founded": 1928, "nick": "Canarini", "desc": "라치오주 프로시노네 연고. 26/27 승격."},
    "Monza": {"city": "몬차 (롬바르디아)", "stadium": "U-파워 스타디움", "founded": 1912, "nick": "Biancorossi", "desc": "롬바르디아 몬차 연고. 26/27 승격."},
    "Venezia": {"city": "베네치아", "stadium": "피에르 루이지 펜초", "founded": 1907, "nick": "Arancioneroverdi", "desc": "베네치아 연고. 감각적 유니폼으로 유명. 26/27 승격."},
    # Bundesliga 25/26
    "Bayern Munich": {"city": "뮌헨", "stadium": "알리안츠 아레나", "founded": 1900, "nick": "Die Roten", "desc": "독일 최고 명문. 분데스리가 최다 우승."},
    "Dortmund": {"city": "도르트문트", "stadium": "지그날 이두나 파크", "founded": 1909, "nick": "BVB", "desc": "노란 벽(옐로월)의 열성 팬덤. 강한 압박·역습."},
    "Leverkusen": {"city": "레버쿠젠", "stadium": "바이아레나", "founded": 1904, "nick": "Die Werkself", "desc": "바이엘 제약 모기업. 사비 알론소 체제서 무패 우승."},
    "RB Leipzig": {"city": "라이프치히", "stadium": "레드불 아레나", "founded": 2009, "nick": "Die Roten Bullen", "desc": "레드불 프로젝트. 젊은 영입·고강도 압박."},
    "Stuttgart": {"city": "슈투트가르트", "stadium": "MHP아레나", "founded": 1893, "nick": "Die Schwaben", "desc": "슈바벤 지역 전통 클럽."},
    "Frankfurt": {"city": "프랑크푸르트", "stadium": "도이체방크 파크", "founded": 1899, "nick": "Die Adler", "desc": "22 유로파리그 우승. 열광적 홈 분위기."},
    "Freiburg": {"city": "프라이부르크", "stadium": "유로파-파크 슈타디온", "founded": 1904, "nick": "Breisgau-Brasilianer", "desc": "육성·운영의 모범 소도시 클럽."},
    "Union Berlin": {"city": "베를린 (쾨페니크)", "stadium": "알테 푀르스터라이", "founded": 1966, "nick": "Die Eisernen", "desc": "노동자 정서의 열성 클럽. 최근 유럽대항전."},
    "Werder Bremen": {"city": "브레멘", "stadium": "베저슈타디온", "founded": 1899, "nick": "Die Werderaner", "desc": "북부 전통 명문. 녹백 클럽."},
    "Gladbach": {"city": "묀헨글라트바흐", "stadium": "보루시아-파크", "founded": 1900, "nick": "Die Fohlen", "desc": "70년대 황금기의 전통 클럽."},
    "Wolfsburg": {"city": "볼프스부르크", "stadium": "폭스바겐 아레나", "founded": 1945, "nick": "Die Wölfe", "desc": "폭스바겐 연고. 09 분데스 우승."},
    "Mainz 05": {"city": "마인츠", "stadium": "메바 아레나", "founded": 1905, "nick": "Die Nullfünfer", "desc": "클롭·투헬을 배출한 라인란트 클럽."},
    "Augsburg": {"city": "아우크스부르크", "stadium": "WWK 아레나", "founded": 1907, "nick": "Die Fuggerstädter", "desc": "바이에른 슈바벤 연고 클럽."},
    "Hoffenheim": {"city": "진스하임", "stadium": "프리제로 아레나", "founded": 1899, "nick": "Die Kraichgauer", "desc": "SAP 창업주 후원의 크라이히가우 클럽."},
    "Köln": {"city": "쾰른", "stadium": "라인에네르기슈타디온", "founded": 1948, "nick": "Die Geißböcke", "desc": "라인란트 대도시 열성 클럽. 염소 마스코트."},
    "St Pauli": {"city": "함부르크 (장크트파울리)", "stadium": "밀레른토어 슈타디온", "founded": 1910, "nick": "Kiezkicker", "desc": "반체제·서브컬처로 유명한 함부르크 항구 클럽."},
    "Hamburger SV": {"city": "함부르크", "stadium": "폭스파르크슈타디온", "founded": 1887, "nick": "Die Rothosen", "desc": "북부 명문. 오랜만의 분데스 복귀."},
    "Heidenheim": {"city": "하이덴하임", "stadium": "포이트-아레나", "founded": 1846, "nick": "FCH", "desc": "바덴뷔르템베르크 소도시 클럽."},
    # Bundesliga 26/27 승격
    "Schalke 04": {"city": "겔젠키르헨", "stadium": "펠틴스-아레나", "founded": 1904, "nick": "Die Knappen", "desc": "루르 지역 광부 정서의 전통 명문. 26/27 승격."},
    "SC Paderborn": {"city": "파더보른", "stadium": "홈 도이체 아레나", "founded": 1907, "nick": "SCP", "desc": "노르트라인베스트팔렌 소도시 클럽. 26/27 승격."},
    "SV Elversberg": {"city": "슈피저 (자를란트)", "stadium": "우르잔 아레나", "founded": 1907, "nick": "Die SVE", "desc": "자를란트 소도시 클럽. 26/27 승격."},
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
