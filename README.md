# Football26 — EPL 25/26 전술 분석 대시보드

EPL 2025-26 시즌 선수 통계를 기반으로 **팀 포메이션 보드**, **선수 역할 분류**, **유사 선수 추천**을 제공하는 Streamlit 앱.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 포메이션 보드 | 팀별 실측 라인업(Sofascore) 기반 RB/CB/LB 정확 배치 |
| 선수 역할 | 90분당 지표 백분위로 아키타입 자동 분류 (스트라이커 / 인사이드 윙어 / 앵커 등) |
| 유사 선수 | 10개 xG 기반 피처 코사인 유사도로 스타일 유사 선수 추천 (Vector RAG) |
| 배지 시스템 | 리그 상위 선수 자동 하이라이트 (득점 머신 / 키패스 장인 등) |

## 데이터 소스

- **FBref** — 출전시간·크로스·태클·인터셉트 등 기본 지표
- **Understat** — xG, npxG, xA, 키패스 (90분당)
- **Sofascore** — 경기별 라인업 (포메이션 + RB/CB/LB 슬롯 도출)

## 로컬 실행

```bash
pip install -r requirements.txt
python -m streamlit run app.py
# → http://localhost:8600
```

### 데이터 갱신 (선택)

```bash
# 1. FBref 기본 스탯
python src/fetch_fbref.py

# 2. Understat xG 병합
python src/fetch_understat.py

# 3. Sofascore 라인업 (팀 지정)
python src/fetch_lineups.py "Arsenal" "Liverpool" "Manchester City"
```

## 프로젝트 구조

```
app.py                          # Streamlit 메인
src/
  similar_players.py            # Vector RAG (코사인 유사도)
  team_analysis.py              # 포메이션 / 역할 분석
  fetch_fbref.py                # FBref 수집
  fetch_understat.py            # Understat xG 수집
  fetch_lineups.py              # Sofascore 라인업 스크래퍼
data/
  players_full_2025_2026.csv    # 선수 통계 (551명)
  player_slots_2025_2026.csv    # 선수별 포메이션 슬롯
  team_formations.json          # 팀별 주요 포메이션
```

## 기술 스택

- **Streamlit** — 프론트엔드
- **scikit-learn** — 벡터 임베딩 / 코사인 유사도
- **soccerdata** — FBref / Understat API 래퍼
- **pandas / numpy** — 데이터 처리
