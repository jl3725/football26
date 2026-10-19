param([string]$Root)
# 로컬 Sofascore 일일 agent — 선수 시즌 평점·출전(Sofascore)만 매일 다시 받아 선수 표에 덧붙이고 data 만 commit·push.
#
# 예전엔 주 1회(수 12:30, run_season_agent.ps1 전체 빌드)만 받아 평점이 최대 7일 늦었다(2026-10-19 중간 점검).
# Sofascore 는 클라우드 IP 가 막혀 이 PC 에서만 받을 수 있다. 단계: build_season.py --only sofascore,merge_sofascore
# (리그당 1~2분, merge 는 기존 players_full 에 Sofascore 열만 덧붙이는 비파괴 병합 — TM 사진·계약은 그대로).
# 수요일은 주간 전체 빌드가 같은 일을 하므로 건너뛴다. 커밋은 Sofascore·선수 표·홈 스냅샷으로만 한정.
# 로그: logs/sofascore-daily-YYYYMMDD.log
$ErrorActionPreference = "Continue"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir ("sofascore-daily-{0:yyyyMMdd}.log" -f (Get-Date))) -Append | Out-Null

function Finish([int]$code) {
    Stop-Transcript | Out-Null
    exit $code
}

if ((Get-Date).DayOfWeek -eq [System.DayOfWeek]::Wednesday) {
    Write-Host "[sofascore-daily] 수요일 — 주간 전체 빌드(season-weekly)가 대신 받음, 건너뜀"
    Finish 0
}

Write-Host "[sofascore-daily] $(Get-Date -Format s) git pull"
git pull --rebase --autostash origin main
if ($LASTEXITCODE -ne 0) {
    git rebase --abort 2>$null
    Write-Host "[sofascore-daily] pull 실패(로컬 충돌 가능) — 중단"
    Finish 1
}

$Season = (& $Python -c "import sys; sys.path.insert(0, 'src'); from leagues import SEASON; print(SEASON)").Trim()
Write-Host "[sofascore-daily] 시즌 $Season Sofascore 평점 갱신 시작"
& $Python scripts\build_season.py --only sofascore,merge_sofascore
$BuildCode = $LASTEXITCODE

& $Python scripts\build_db.py | Out-Null
& $Python scripts\validate_data.py --no-optional
if ($LASTEXITCODE -ne 0) {
    Write-Host "[sofascore-daily] validate_data 실패 — 커밋하지 않음(변경은 작업 트리에 남김)"
    Finish 1
}
& $Python scripts\precompute_hub.py

$Paths = @("data/players_sofascore_stats_*$Season.csv", "data/players_full_*$Season.csv", "data/home_all.json")
git add -- $Paths
git diff --cached --quiet -- $Paths
if ($LASTEXITCODE -eq 0) {
    Write-Host "[sofascore-daily] 변경 없음 — 커밋 생략"
} else {
    $msg = "chore(data): Sofascore 평점 일일 갱신 — 시즌 $Season [skip ci]"
    if ($BuildCode -ne 0) { $msg += "`n`n일부 리그 실패 — logs/season-$Season-*.log 참고" }
    git commit -m $msg -- $Paths
    $pushed = $false
    for ($i = 1; $i -le 3 -and -not $pushed; $i++) {
        git pull --rebase --autostash origin main
        if ($LASTEXITCODE -eq 0) { git push origin HEAD:main; $pushed = ($LASTEXITCODE -eq 0) }
        if (-not $pushed) { Start-Sleep -Seconds 5 }
    }
    if (-not $pushed) { Write-Host "[sofascore-daily] push 실패 — 다음 실행 때 함께 push 됨" }
}
Write-Host "[sofascore-daily] done (build exit $BuildCode)"
Finish $BuildCode
