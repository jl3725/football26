"""
Sofascore IP 차단 해제 대기 후 자동 스크래핑.
실행: python _wait_and_scrape.py
"""
import sys, time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # cp949 콘솔에서도 유니코드 출력
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import tls_requests

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}
BASE = "https://api.sofascore.com/api/v1"

TEAMS = [
    # Arsenal/Man Utd도 등번호 수집 위해 재스크래핑 목록에 포함(전 20팀)
    "Arsenal", "Manchester Utd",
    "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea",
    "Crystal Palace", "Everton", "Fulham", "Leeds United", "Liverpool",
    "Manchester City", "Newcastle United", "Nottingham Forest",
    "Sunderland", "Tottenham Hotspur", "West Ham United", "Wolves",
    "Aston Villa",
]

POLL_INTERVAL = 120  # 2분마다 차단 여부 확인

print("=== Sofascore 차단 해제 대기 중 ===")
print(f"대상 팀: {len(TEAMS)}팀")
print("API 접근 가능해지면 자동으로 스크래핑 시작합니다.\n")

attempt = 0
while True:
    attempt += 1
    r = tls_requests.get(BASE + "/unique-tournament/17/seasons", headers=H, timeout=15)
    now = time.strftime("%H:%M:%S")
    if r.status_code == 200:
        print(f"[{now}] [OK] 차단 해제! 스크래핑 시작합니다.\n")
        break
    print(f"[{now}] 시도 #{attempt}: 여전히 {r.status_code} - {POLL_INTERVAL}초 후 재시도")
    time.sleep(POLL_INTERVAL)

# 차단 해제되면 fetch_lineups.main() 호출
from fetch_lineups import main as scrape
sys.exit(scrape(TEAMS))
