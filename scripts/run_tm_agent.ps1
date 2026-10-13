param([string]$Root, [switch]$Weekly)
# 로컬 Transfermarkt 수집 agent — 수집 후 data 만 commit·push.
#
# 2026-07-15경부터 Transfermarkt(AWS WAF)이 GitHub Actions 러너(데이터센터 IP)에 202 챌린지를
# 반환해 클라우드 수집이 불가능해졌다(TLS 위장으로도 우회 불가 — 2026-10 진단). 그래서 TM 계열
# 수집만 이 PC(일반 회선)에서 돌린다. 나머지(ESPN 일정·위키 감독·뉴스 등)는 계속 GH Actions 담당.
#
#   기본    : 이적(transfers) · 현재 부상(injuries) · 계약(contracts) · 이적 루머(rumors) — 8개 리그
#             + 시장가치 스냅샷(snapshot_market_values, 네트워크 없음)
#   -Weekly : 선수별 통산 부상 이력(tm_injury_history) — 선수 페이지 수천 개라 주 1회(약 1.5시간)
#
# 커밋은 TM 산출물 경로로만 한정(git commit -- <paths>) — 작업 중인 코드 변경이 섞이지 않는다.
# 로그: logs/tm-agent[-weekly]-YYYYMMDD.log
$ErrorActionPreference = "Continue"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Tag = if ($Weekly) { "tm-agent-weekly" } else { "tm-agent" }
Start-Transcript -Path (Join-Path $LogDir ("{0}-{1:yyyyMMdd}.log" -f $Tag, (Get-Date))) -Append | Out-Null

function Finish([int]$code) {
    Stop-Transcript | Out-Null
    exit $code
}

Write-Host "[$Tag] $(Get-Date -Format s) git pull"
git pull --rebase --autostash origin main
if ($LASTEXITCODE -ne 0) {
    git rebase --abort 2>$null
    Write-Host "[$Tag] pull 실패(로컬 충돌 가능) — 중단"
    Finish 1
}

if ($Weekly) {
    $Steps = @(
        @{ Name = "injury_history"; Args = @("src\fetch_tm_injury_history.py") }
    )
    $Paths = @("data/tm_injury_history_*.csv")
    $Subject = "통산 부상 이력"
} else {
    $Steps = @(
        @{ Name = "transfers";    Args = @("src\fetch_transfers.py") },
        @{ Name = "injuries";     Args = @("src\fetch_transfermarkt_injuries.py") },
        @{ Name = "contracts";    Args = @("src\sync_transfermarkt_contracts.py", "--write") },
        @{ Name = "rumors";       Args = @("src\fetch_transfer_rumors.py") },
        @{ Name = "market_value"; Args = @("scripts\snapshot_market_values.py") }
    )
    $Paths = @("data/transfers_*.csv", "data/transfermarkt_*.csv", "data/transfer_rumors_*.csv",
               "data/players_*.csv", "data/market_value_*.csv")
    $Subject = "이적·부상·계약·루머"
}

$Leagues = @("EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague")
$Failed = @()
foreach ($lg in $Leagues) {
    $env:FB_LEAGUE = $lg
    foreach ($step in $Steps) {
        Write-Host "[$Tag] ── $($step.Name) $lg"
        & $Python @($step.Args)
        if ($LASTEXITCODE -ne 0) { $Failed += "$($step.Name) $lg" }
    }
}
Remove-Item Env:FB_LEAGUE -ErrorAction SilentlyContinue

# 품질 게이트 — 핵심 데이터 계약이 깨지면 커밋하지 않고 TM 산출물 변경을 되돌린다.
& $Python scripts\validate_data.py --no-optional
if ($LASTEXITCODE -ne 0) {
    Write-Host "[$Tag] validate_data 실패 — TM 산출물 변경 폐기"
    git checkout -- $Paths 2>$null
    Finish 1
}

git add -- $Paths
git diff --cached --quiet -- $Paths
if ($LASTEXITCODE -eq 0) {
    Write-Host "[$Tag] 변경 없음 — 커밋 생략"
} else {
    $msg = "chore(data): TM 로컬 수집 — $Subject [skip ci]"
    if ($Failed.Count -gt 0) { $msg += "`n`n실패: " + ($Failed -join ", ") }
    git commit -m $msg -- $Paths
    $pushed = $false
    for ($i = 1; $i -le 3 -and -not $pushed; $i++) {
        git pull --rebase --autostash origin main
        if ($LASTEXITCODE -eq 0) { git push origin HEAD:main; $pushed = ($LASTEXITCODE -eq 0) }
        if (-not $pushed) { Start-Sleep -Seconds 5 }
    }
    if (-not $pushed) { Write-Host "[$Tag] push 실패 — 다음 실행 때 함께 push 됨" }
}

if ($Failed.Count -gt 0) {
    Write-Host "[$Tag] 실패 $($Failed.Count)건: $($Failed -join ', ')"
    Finish 1
}
Write-Host "[$Tag] done"
Finish 0
