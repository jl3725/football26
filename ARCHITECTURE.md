# Football26 Architecture

## 계층

### 1. 수집

`src/fetch_*.py`, `src/sync_*.py`와 GitHub Actions가 외부 축구 데이터를
리그·시즌별 CSV/JSON 또는 `news.db`로 저장합니다. 수집 결과는 재현 가능한
원본이며 애플리케이션 코드가 직접 수정하지 않습니다.

### 2. 저장

`scripts/build_db.py`가 원본 파일을 `data/football.db`로 통합합니다.
`src/datastore.py`는 SQLite를 우선 읽고 DB가 없을 때 CSV로 폴백합니다.
`football.db`는 파생물이므로 Git에 저장하지 않습니다.

`scripts/validate_data.py`는 핵심 테이블의 존재, 최소 행 수, 필수 컬럼과
팀 단위 중복을 검사합니다. 선택 데이터 누락은 경고로 분리합니다.

### 3. 도메인

등급, 팀 분석, 선수 유사도, 이적 적합도, 감독 시뮬레이션 같은 판단 로직은
`src/`의 순수 Python 모듈에 둡니다. UI나 HTTP 객체를 이 계층으로 가져오지
않는 것이 원칙입니다.

### 4. API

`api/main.py`가 FastAPI 애플리케이션을 구성합니다. 현재 분리된 경계는 다음과
같습니다.

```text
api/bootstrap.py                src 모듈 경로 부트스트랩
api/routers/meta.py             상태·시즌·리그
api/routers/teams.py            현재/다음 시즌 팀 카탈로그
api/routers/world_cup.py        월드컵 HTTP 경계
api/services/player_data.py     선수 로딩·사진·숫자 공통 처리
api/services/world_cup.py       월드컵 집계·FIFA 예상 랭킹
```

라우터에는 요청 해석과 응답 조립만 두고, 계산은 `src/` 또는 service로
위임합니다. `api/main.py`에 남은 기능은 테스트를 유지하면서 clubs, players,
transfers, scout 순으로 점진 분리합니다.

### 5. UI

`web/`의 Next.js 앱이 사용자 대상 주력 UI입니다. `app.py`와 `src/ui/`의
Streamlit 화면은 내부 분석·검증 도구로 유지합니다. 신규 사용자 기능은
Next.js에 우선 구현하고 공통 계산은 Python 도메인 계층에서 재사용합니다.

## 시즌과 리그

`src/leagues.py`가 리그 식별자와 데이터 파일명 규칙을 관리합니다.
활성 시즌은 `FB_SEASON_START`로 지정하며 기본값은 `2025`입니다.
실제 날짜 기반 이적시장 상태는 `src/season_context.py`가 별도로 계산합니다.

시즌 전환 시 다음을 함께 변경·검증합니다.

1. 배포와 수집 환경의 `FB_SEASON_START`
2. 새 시즌 핵심 CSV 생성 여부
3. `scripts/validate_data.py`
4. 8개 리그 API 스모크 테스트
5. `data/home_all.json` 재계산

## 선택 인프라

Qdrant, Neo4j 또는 OpenAI 설정이 없더라도 기본 팀·선수·일정 기능은 동작해야
합니다. 선택 기능은 `available: false`와 명확한 사유를 반환해 단계적으로
기능 저하합니다.

## 운영 원칙

- 원본 데이터와 파생 DB를 구분합니다.
- 필수 데이터 오류는 조용히 무시하지 않고 품질 게이트에서 실패시킵니다.
- API 응답 변경에는 테스트 또는 명시적인 스키마 변경을 동반합니다.
- 데이터 수집 커밋과 제품 코드 변경은 가능한 한 분리합니다.
- `main` 배포 전 Python 테스트와 Next.js 빌드를 모두 통과시킵니다.
