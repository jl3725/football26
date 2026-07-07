param([string]$Root)
# 로컬 = 소비 전용. 클라우드(GitHub Actions)가 수집·커밋한 최신 데이터를 받아
# football.db 를 재빌드만 한다. 로컬 수집·commit·push 없음 → origin 과 충돌 없음.
$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "[pull-agent] git pull --rebase --autostash origin main"
git pull --rebase --autostash origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "[pull-agent] pull 실패(로컬 변경 충돌 가능) — rebase 중단"
    git rebase --abort 2>$null
    git stash list 2>$null
    exit 1
}

Write-Host "[pull-agent] build_db.py (football.db 재빌드)"
& $Python (Join-Path $Root "scripts\build_db.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[pull-agent] build_db 실패 — uvicorn 이 DB 를 잠갔을 수 있음(개발 중이면 정상). pull 은 완료됨."
}

# 루머 KG 갱신 — 클라우드가 수집한 최신 transfer_rumors_*.csv 를 로컬 Neo4j RUMORED_WITH 로 적재.
# KG 는 로컬 전용이라 여기서만 갱신. Neo4j 미가동 시 best-effort skip.
Write-Host "[pull-agent] rumor_eval.sync_to_kg (Neo4j RUMORED_WITH 갱신)"
& $Python -c "import sys; sys.path.insert(0,'src'); import rumor_eval; print('[rumor-kg]', rumor_eval.sync_to_kg(), '건')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[pull-agent] rumor KG 적재 skip (Neo4j 미가동 — docker compose up 후 재시도)"
}
Write-Host "[pull-agent] done"
