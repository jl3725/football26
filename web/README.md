# Football26 Web

Football26의 사용자 대상 주력 UI입니다. Next.js App Router 기반 SPA이며
FastAPI의 `/api/*`를 사용합니다.

## 실행

프로젝트 루트에서 FastAPI를 먼저 시작합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

다른 터미널에서:

```powershell
cd web
npm install
npm run dev
```

기본 개발 주소는 `http://localhost:3000`입니다. `next.config.mjs`가 API를
`API_BASE`로 프록시하며, 미설정 시 `http://127.0.0.1:8000`을 사용합니다.

## 구조

- `app/page.tsx`: 전역 화면 상태와 탭 라우팅
- `components/`: 기능별 화면 컴포넌트
- `lib/api.ts`: API 타입과 fetch 함수
- `lib/ui.ts`: 공통 UI 유틸리티

## 검증

```powershell
npm run build
```

프로덕션 빌드에는 TypeScript 검사와 정적 페이지 생성 검사가 포함됩니다.
