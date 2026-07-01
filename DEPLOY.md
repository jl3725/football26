# 배포 가이드 — Vercel(프론트) + Railway(백엔드)

Streamlit Cloud(1개 서비스) 대신, 이제 **Next.js 프론트 + FastAPI 백엔드** 2개를
git 연동으로 배포한다. 데이터는 로컬 agent 가 매일 CSV 를 git push → 클라우드 자동 재배포.

```
브라우저 → Vercel(Next.js, /api/* 프록시) → Railway(FastAPI) → football.db(CSV에서 생성)
                                                     ▲ 매일 로컬 agent 가 CSV git push
```

---

## 1) 백엔드 — Railway

1. https://railway.app → **New Project → Deploy from GitHub repo** → `football26` 선택
2. Railway 가 자동 감지: `requirements.txt`(Python) + `Procfile`(start 명령)
   - Procfile: `python scripts/build_db.py && uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - Root Directory = **저장소 루트(기본값 그대로)** — api/·src/·scripts/·data/ 가 루트에 있음
3. (선택) Variables 에 `NIXPACKS_PYTHON_VERSION = 3.12` (기본으로도 대개 OK)
4. Deploy 완료 후 **Settings → Networking → Generate Domain** 으로 공개 URL 발급
   - 예: `https xxx.up.railway.app`
5. 확인: `https://xxx.up.railway.app/api/health` → `{"ok": true, ...}`

> 무료 사용량 한도가 있음. 상시 가동이 필요하면 Hobby 플랜 권장.

---

## 2) 프론트 — Vercel

1. https://vercel.com → **Add New → Project** → `football26` import
2. **Root Directory = `web`** ← 반드시 지정 (Next.js 앱이 web/ 안에 있음)
3. Framework Preset: **Next.js** (자동 감지)
4. **Environment Variables** 에 추가:
   - `API_BASE = https://xxx.up.railway.app`  (1단계 Railway URL, 끝 슬래시 없이)
5. Deploy → `https://football26-xxx.vercel.app` 발급
   - 프론트는 항상 `/api/*` 로 호출하고 Vercel 이 서버사이드로 Railway 에 프록시
     → 브라우저 입장에선 same-origin (CORS 불필요)

이후 **코드를 git push 하면 Vercel·Railway 가 자동 재배포**(예전 Streamlit Cloud 와 동일 감각).

---

## 3) 데이터 신선도 — 매일 자동 push

로컬 수집 agent(07:50~08:40)가 CSV/DB 를 갱신한 뒤, **08:50 에 git push** 하면
클라우드가 자동 재배포되며 최신 데이터를 반영한다.

한 번만 등록:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_data_push_agent.ps1
```
- git 자격증명이 캐시돼 있어야 함(이미 수동 push 가 되므로 보통 OK)
- `football.db` 는 .gitignore(파생) — 클라우드가 CSV 로 재생성하므로 push 안 함

일일 파이프라인:
`07:50 시장가치 · 08:00 부상 · 08:10 감독 · 08:20 뉴스 · 08:30 이적 · 08:40 DB재빌드 · 08:50 git push`

---

## 로컬 개발

- 백엔드:  `.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000`
- 프론트:  `cd web && npm run dev` (기본 `API_BASE` 없으면 127.0.0.1:8000 프록시)
- 전체 로컬(Streamlit + agent) 의존성:  `pip install -r requirements-agents.txt`
