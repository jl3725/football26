# 배포 가이드 — Vercel(프론트) + Railway(백엔드)

Streamlit Cloud(1개 서비스) 대신, 이제 **Next.js 프론트 + FastAPI 백엔드** 2개를
git 연동으로 배포한다. 데이터는 로컬 agent 가 매일 CSV 를 git push → 클라우드 자동 재배포.

```
브라우저 → Vercel(Next.js, /api/* 프록시) → Render(FastAPI) → football.db(CSV에서 생성)
                                                    ▲ 매일 로컬 agent 가 CSV git push
```

---

## 1) 백엔드 — Render (무료 권장)

Railway 는 무료 상시 티어가 없어졌다(트라이얼→유료). **Render 무료 웹서비스**를 쓴다.
카드 불필요·만료 없음. 단 15분 미사용 시 sleep → 다음 요청 때 콜드스타트(~30-60s).

1. https://render.com → **New → Blueprint** → `football26` repo 선택
   → repo 루트의 `render.yaml` 을 자동 인식(빌드/시작 명령 포함)
   - 또는 수동: New → Web Service → Build `pip install -r requirements.txt`,
     Start `python scripts/build_db.py && uvicorn api.main:app --host 0.0.0.0 --port $PORT`
2. Plan = **Free** 선택 → Deploy
3. 발급 URL 예: `https://football26-api.onrender.com`
4. 확인: `https://football26-api.onrender.com/api/health` → `{"ok": true, ...}`

> 대안(무료): **Hugging Face Spaces**(Docker Space 로 FastAPI), 상시성 필요하면 Railway/Render 유료($5~).

---

## 2) 프론트 — Vercel

1. https://vercel.com → **Add New → Project** → `football26` import
2. **Root Directory = `web`** ← 반드시 지정 (Next.js 앱이 web/ 안에 있음)
3. Framework Preset: **Next.js** (자동 감지)
4. **Environment Variables** 에 추가:
   - `API_BASE = https://football26-api.onrender.com`  (1단계 Render URL, 끝 슬래시 없이)
5. Deploy → `https://football26-xxx.vercel.app` 발급
   - 프론트는 항상 `/api/*` 로 호출하고 Vercel 이 서버사이드로 Railway 에 프록시
     → 브라우저 입장에선 same-origin (CORS 불필요)

이후 **코드를 git push 하면 Vercel·Railway 가 자동 재배포**(예전 Streamlit Cloud 와 동일 감각).

---

## 3) 데이터 신선도 — 매일 자동 push

로컬 수집 agent(07:50~08:40)가 CSV/DB 를 갱신한 뒤, **08:50 에 git push** 하면
Render(백엔드)가 자동 재배포되며 최신 데이터를 반영한다.

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
