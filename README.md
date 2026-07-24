# Football26

8개 유럽 리그와 월드컵 데이터를 통합해 팀 분석, 선수 탐색, 이적 적합도,
라인업과 스쿼드 계획을 제공하는 축구 스카우팅 플랫폼입니다.

## 현재 제품 구성

- **주력 UI:** Next.js SPA (`web/`)
- **백엔드:** FastAPI (`api/`)
- **분석·수집:** Python (`src/`, `scripts/`)
- **데이터:** 시즌별 CSV/JSON과 `news.db`가 원본, `football.db`는 배포 시 재생성
- **선택 기능:** Qdrant(벡터 탐색), Neo4j(관계 그래프), OpenAI(Ask Scout)
- **내부 분석 UI:** Streamlit (`app.py`, `src/ui/`)

지원 리그는 Premier League, La Liga, Bundesliga, Serie A, Ligue 1,
Liga Portugal, Eredivisie, Belgian Pro League입니다.

## 주요 기능

- 팀 오버뷰, 전력 지표, 일정, 라인업과 선수 상세
- 이적 내역·루머·부상·계약·시장가치 시그널
- 스쿼드 약점 진단과 선수 추천
- Transfer Fit 및 감독 교체 시뮬레이션
- 스쿼드 관계 그래프와 케미스트리
- 전 리그 통합 홈과 월드컵 대시보드
- 자연어 Ask Scout

## 구조

```text
GitHub Actions / src/fetch_*.py
                │
                ▼
        data/*.csv · *.json · news.db
                │ scripts/build_db.py
                ▼
            data/football.db
                │
        src 분석·추천 도메인 로직
                │
                ▼
          FastAPI /api/*
                │
                ▼
             Next.js
```

자세한 계층과 변경 원칙은 [ARCHITECTURE.md](ARCHITECTURE.md)를 참고하세요.

## 로컬 실행

Python 환경:

```powershell
.\.venv\Scripts\python.exe scripts\build_db.py
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

프론트엔드:

```powershell
cd web
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다. Next.js가 `/api/*` 요청을
기본적으로 `http://127.0.0.1:8000`에 프록시합니다.

내부 Streamlit 분석 화면이 필요할 때만 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\validate_data.py --no-optional
cd web
npm run build
```

CI는 Python 컴파일, 8개 리그 API 스모크 테스트, 데이터 계약 검사와 Next.js
프로덕션 빌드를 수행합니다.

## 설정

- `FB_SEASON_START`: 활성 데이터 시즌 시작 연도. 기본값 `2025`
- `FB_LEAGUE`: 로컬 수집기의 기본 리그. 기본값 `EPL`
- `API_BASE`: Next.js가 프록시할 FastAPI 주소
- `QDRANT_URL`, `QDRANT_API_KEY`: 벡터 탐색
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`: 그래프 기능
- `OPENAI_API_KEY`: Ask Scout
- `SCOUT_TOKEN`: Ask Scout 접근 토큰
- `SCOUT_ALLOW_PUBLIC`: 로컬에서만 토큰 없는 Ask Scout를 허용할 때 `true`
- `ALLOWED_ORIGINS`: FastAPI에 직접 접근을 허용할 브라우저 origin 목록

민감한 값은 `.env` 또는 배포 서비스의 비밀 환경변수에만 저장합니다.

## 주요 디렉터리

```text
api/                 FastAPI 앱, 도메인별 라우터와 API 서비스
src/                 도메인 로직, 데이터 접근, 수집기, Streamlit 내부 UI
scripts/             DB 빌드, 데이터 검증, 벡터·KG 빌드, 운영 스크립트
tests/               API·시즌·데이터 계약 테스트
web/                 Next.js 주력 UI
data/                원본 데이터와 사전 계산 결과
.github/workflows/   CI와 정기 데이터 수집
```

배포 절차는 [DEPLOY.md](DEPLOY.md)를 참고하세요.
