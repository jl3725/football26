param([string]$Root)
# 로컬 팬 투표 agent — Sofascore 팬 승부 예측 투표만 수집해 data/fan_votes.csv 를 commit·push.
#
# 2026-10-15: Transfermarkt 수집은 클라우드(.github/workflows/tm_data.yml)로 옮겼다. Sofascore 는 클라우드 IP 를
# 브라우저로도 막아(진단 scripts/diag_sources.py) 이 PC 에 남긴 유일한 하루 작업이다(사용자 결정: '그거 하나는 남겨두죠').
# 작업 스케줄러가 창 없이(-WindowStyle Hidden) 실행한다. 로그: logs/fanvote-agent-YYYYMMDD.log
$ErrorActionPreference = "Continue"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir ("fanvote-agent-{0:yyyyMMdd}.log" -f (Get-Date))) -Append | Out-Null
function Finish([int]$code) { Stop-Transcript | Out-Null; exit $code }

git pull --rebase --autostash origin main
if ($LASTEXITCODE -ne 0) { git rebase --abort 2>$null; Write-Host "[fanvote] pull 실패 — 중단"; Finish 1 }

$t0 = Get-Date
& $Python src\fetch_fan_votes.py
$code = $LASTEXITCODE
$failed = ($code -ne 0)
# 실행 원장(DATA STATUS 화면·watchdog) — 이 PC 가 꺼져 있으면 기록이 끊겨 '지연'으로 보인다
& $Python src\run_ledger.py add local-fanvote "fanvote" $code ([int]((Get-Date) - $t0).TotalSeconds)

$Paths = @("data/fan_votes.csv", "data/ops/runs/local-fanvote.jsonl")
$Paths = @($Paths | Where-Object { Test-Path $_ })   # 없는 경로가 섞이면 git add 가 통째로 실패한다
git add -- $Paths
git diff --cached --quiet -- $Paths
if ($LASTEXITCODE -ne 0) {
    git commit -m "chore(data): 팬 투표(Sofascore) 로컬 수집 [skip ci]" -- $Paths
    for ($i = 1; $i -le 3; $i++) {
        git pull --rebase --autostash origin main
        if ($LASTEXITCODE -eq 0) { git push origin HEAD:main; if ($LASTEXITCODE -eq 0) { break } }
        Start-Sleep -Seconds 5
    }
}
if ($failed) { Finish 1 }
Finish 0
