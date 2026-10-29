# 배포 가이드 — Vercel(프론트) + Render(백엔드)

**Next.js 프론트 + FastAPI 백엔드**를 각각 git 연동으로 배포한다.
데이터는 GitHub Actions가 갱신하고, Render가 배포 시 SQLite를 재생성한다.

```
브라우저 → Vercel(Next.js, /api/* 프록시) → Render(FastAPI) → football.db(CSV에서 생성)
                                                    ▲ GitHub Actions가 데이터 갱신
```

---

## 1) 백엔드 — Render

1. https://render.com → **New → Blueprint** → `football26` repo 선택
   → repo 루트의 `render.yaml` 을 자동 인식(빌드/시작 명령 포함)
   - 또는 수동: New → Web Service → Build/Start 명령은 `render.yaml` 과 같게(빌드는 data-live 배포본을 받고
     `scripts/fetch_live_data.py`, 못 받으면 `scripts/build_db.py` 로 만든다)
2. 필요한 리소스와 콜드스타트 허용 여부에 맞는 plan 선택 → Deploy
3. 발급 URL 예: `https://football26-api.onrender.com`
4. 확인: `https://football26-api.onrender.com/api/health` → `{"ok": true, ...}`
5. **자동 배포는 끈다**(`render.yaml` `autoDeploy: false`, 대시보드 Settings → Build & Deploy → Auto-Deploy = No).
   배포는 `.github/workflows/deploy_backend.yml` 이 하루 한 번(백엔드 코드가 바뀐 날만, 경기 진행 중이면 끝난 뒤)과
   수동 실행(Actions → Deploy Backend → Run workflow)으로 한다. Settings → **Deploy Hook** 주소를 GitHub 저장소 비밀
   `RENDER_DEPLOY_HOOK` 에 넣어 둘 것. 데이터는 배포와 무관하게 서버가 data-live 에서 3분마다 받는다(`src/live_sync.py`).

> 다른 컨테이너 호스팅을 사용할 때도 build/start 명령과 환경변수는 동일하다.

---

## 2) 프론트 — Vercel

1. https://vercel.com → **Add New → Project** → `football26` import
2. **Root Directory = `web`** ← 반드시 지정 (Next.js 앱이 web/ 안에 있음)
3. Framework Preset: **Next.js** (자동 감지)
4. **Environment Variables** 에 추가:
   - `API_BASE = https://football26-api.onrender.com`  (1단계 Render URL, 끝 슬래시 없이)
5. Deploy → `https://football26-xxx.vercel.app` 발급
   - 프론트는 항상 `/api/*` 로 호출하고 Vercel 이 서버사이드로 Render 에 프록시
     → 브라우저 입장에선 same-origin (CORS 불필요)

이후 코드를 push하면 Vercel 은 자동 배포하고, Render(백엔드)는 위 Deploy Backend 워크플로가 배포한다.

---

## 3) 환경변수

Render에는 다음 값을 설정한다.

- `FB_SEASON_START=2026` (render.yaml 과 같은 값 — 시즌 전환 시 함께 변경)
- `ALLOWED_ORIGINS`: FastAPI에 직접 브라우저 접근을 허용할 때만 Vercel origin 지정
- `QDRANT_URL`, `QDRANT_API_KEY`: 벡터 기능 사용 시
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`: 그래프 기능 사용 시
- `OPENAI_API_KEY`, `SCOUT_TOKEN`: Ask Scout 사용 시

`SCOUT_TOKEN`은 OpenAI 비용이 발생하는 엔드포인트를 보호하므로 공개 배포에서
반드시 설정한다. 토큰 없이 공개하려면 `SCOUT_ALLOW_PUBLIC=true`를 별도로
지정해야 하지만 운영 환경에서는 권장하지 않는다.

## 4) 데이터 신선도

`.github/workflows/`의 예약 작업이 뉴스, 감독, 일정·순위·라인업과 홈 스냅샷을 매일
갱신하고, Transfermarkt·선수 시즌 스탯은 로컬 PC 작업(ARCHITECTURE.md 표 참고)이 갱신해
푸시합니다. 핵심 데이터는 커밋 전 `scripts/validate_data.py`로 검증됩니다.
`football.db`는 파생 파일이므로 Git에 올리지 않습니다.

데이터 커밋은 Render 를 재배포하지만, 프론트는 `web/vercel.json`의 `ignoreCommand`로
`web/` 변경이 없으면 빌드를 건너뜁니다.

---

## 로컬 개발

- 백엔드:  `.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000`
- 프론트:  `cd web && npm run dev` (기본 `API_BASE` 없으면 127.0.0.1:8000 프록시)
- 전체 로컬(Streamlit + agent) 의존성:  `pip install -r requirements-agents.txt`
