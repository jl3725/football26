param([string]$Root)
# 로컬 시즌 빌드 agent (주 1회) — 선수 시즌 스탯·라인업·히트맵을 다시 만들어 data 만 commit·push.
#
# FBref·Sofascore 는 브라우저(seleniumbase UC)가 필요하고 Transfermarkt 는 GH 러너를 막아서
# 선수 스탯 체인은 이 PC 에서만 돌릴 수 있다(scripts/build_season.py — 리그×16단계, 약 1.5시간).
# 순위·일정·라인업 증분은 GH daily_data 가 매일 따로 갱신한다.
#
# 커밋은 활성 시즌 데이터 파일 + 홈 스냅샷으로만 한정 — 작업 중인 코드 변경이 섞이지 않는다.
# 로그: logs/season-agent-YYYYMMDD.log (단계별 상세는 logs/season-<시즌>-YYYYMMDD.log)
$ErrorActionPreference = "Continue"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir ("season-agent-{0:yyyyMMdd}.log" -f (Get-Date))) -Append | Out-Null

function Finish([int]$code) {
    Stop-Transcript | Out-Null
    exit $code
}

Write-Host "[season-agent] $(Get-Date -Format s) git pull"
git pull --rebase --autostash origin main
if ($LASTEXITCODE -ne 0) {
    git rebase --abort 2>$null
    Write-Host "[season-agent] pull 실패(로컬 충돌 가능) — 중단"
    Finish 1
}

$Season = (& $Python -c "import sys; sys.path.insert(0, 'src'); from leagues import SEASON; print(SEASON)").Trim()
Write-Host "[season-agent] 시즌 $Season 빌드 시작"
& $Python scripts\build_season.py
$BuildCode = $LASTEXITCODE

# 품질 게이트 → 홈 스냅샷 재생성
& $Python scripts\build_db.py | Out-Null
& $Python scripts\validate_data.py --no-optional
if ($LASTEXITCODE -ne 0) {
    Write-Host "[season-agent] validate_data 실패 — 커밋하지 않음(변경은 작업 트리에 남김)"
    Finish 1
}
& $Python scripts\precompute_hub.py

$Paths = @("data/*_$Season.csv", "data/home_all.json")
git add -- $Paths
git diff --cached --quiet -- $Paths
if ($LASTEXITCODE -eq 0) {
    Write-Host "[season-agent] 변경 없음 — 커밋 생략"
} else {
    $msg = "chore(data): 시즌 $Season 주간 빌드 — 선수 스탯·라인업·히트맵 [skip ci]"
    if ($BuildCode -ne 0) { $msg += "`n`n일부 단계 실패 — logs/season-$Season-*.log 참고" }
    git commit -m $msg -- $Paths
    $pushed = $false
    for ($i = 1; $i -le 3 -and -not $pushed; $i++) {
        git pull --rebase --autostash origin main
        if ($LASTEXITCODE -eq 0) { git push origin HEAD:main; $pushed = ($LASTEXITCODE -eq 0) }
        if (-not $pushed) { Start-Sleep -Seconds 5 }
    }
    if (-not $pushed) { Write-Host "[season-agent] push 실패 — 다음 실행 때 함께 push 됨" }
}
Write-Host "[season-agent] done (build exit $BuildCode)"
Finish $BuildCode
