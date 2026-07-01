# SCOUT.AI Web (Next.js + FastAPI POC)

Streamlit 대비 "앱 느낌"(SPA)을 검증하기 위한 Overview 탭 프로토타입.
데이터는 기존 `data/football.db`(→ `src/datastore.py`)를 그대로 재사용한다.

## 실행 (터미널 2개)

**1) API (FastAPI, 포트 8000)** — 프로젝트 루트에서:
```
.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

**2) Web (Next.js, 포트 3000)** — `web/` 에서:
```
npm install    # 최초 1회
npm run dev
```

브라우저에서 http://localhost:3000 접속.
`next.config.mjs` 의 rewrites 가 `/api/*` 를 8000 으로 프록시하므로 CORS 신경 안 써도 됨.

## 구조
- `app/page.tsx` — 사이드바(팀 선택) + Overview. 팀 클릭 시 **리로드 없이** 해당 부분만 갱신(앱 느낌 핵심).
- `lib/api.ts` — API 타입 + fetch 헬퍼.
- 백엔드 `api/main.py` — datastore 를 JSON 으로 노출. UI 프레임워크와 무관.
