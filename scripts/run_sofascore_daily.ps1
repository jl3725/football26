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
. (Join-Path $PSScriptRoot "git_sync.ps1")   # Sync-Main · Push-Main(충돌이면 -X theirs, scripts/ci_push.sh 와 같은 규칙)
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
if (-not (Sync-Main)) {
    Write-Host "[sofascore-daily] pull 실패 — 중단"
    Finish 1
}

$Season = (& $Python -c "import sys; sys.path.insert(0, 'src'); from leagues import SEASON; print(SEASON)").Trim()
Write-Host "[sofascore-daily] 시즌 $Season Sofascore 평점 갱신 시작"
# 실패한 리그는 build_season 이 2분 뒤 한 번 더 받는다(Sofascore 가 브라우저 세션을 끊는 일 — 2026-10-19 리그 1)
# 단계마다 실행 원장 data/ops/runs/local-sofascore-daily.jsonl 에 남는다(DATA STATUS 화면)
$env:LEDGER_RUNNER = "local-sofascore-daily"
# StatBunker(세트피스·PK·규율, EPL·라리가·세리에A)도 여기서 매일 — 클라우드 IP 는 403(2026-11-03), 주 1회면 2~4경기 늦었다
& $Python scripts\build_season.py --only sofascore,merge_sofascore,statbunker
$BuildCode = $LASTEXITCODE

# 히트맵 따라잡기 — 주간 빌드(수)가 실패한 리그(분데스리가·벨기에 2026-10-28 '시즌 id 못 찾음')는 다음 수요일까지 옛 히트맵이었다.
# 파일이 8일 넘게 안 바뀐 풀 리그만 여기서 다시 받는다(리그당 10~20분이라 평소엔 0개)
$Stale = @()
foreach ($lg in ((& $Python scripts\league_keys.py --full).Trim() -split " ")) {
    $hm = if ($lg -eq "EPL") { "data\player_heatmaps_$Season.csv" } else { "data\player_heatmaps_${lg}_$Season.csv" }
    if (-not (Test-Path $hm) -or ((Get-Date) - (Get-Item $hm).LastWriteTime).TotalDays -gt 8) { $Stale += $lg }
}
if ($Stale.Count -gt 0) {
    Write-Host "[sofascore-daily] 히트맵 따라잡기: $($Stale -join ', ')"
    & $Python scripts\build_season.py --only heatmaps --no-retry @Stale
}

& $Python scripts\build_db.py | Out-Null
& $Python scripts\validate_data.py --no-optional
if ($LASTEXITCODE -ne 0) {
    Write-Host "[sofascore-daily] validate_data 실패 — 커밋하지 않음(변경은 작업 트리에 남김)"
    Finish 1
}
& $Python scripts\precompute_hub.py

$Paths = @("data/players_sofascore_stats_*$Season.csv", "data/players_full_*$Season.csv", "data/home_all.json",
           "data/player_heatmaps_*$Season.csv", "data/sofascore_season_ids.json", "data/statbunker_*$Season.csv",
           "data/ops/runs/local-sofascore-daily.jsonl")
$Paths = @($Paths | Where-Object { Test-Path $_ })   # 없는 경로가 섞이면 git add 가 통째로 실패한다
git add -- $Paths
git diff --cached --quiet -- $Paths
if ($LASTEXITCODE -eq 0) {
    Write-Host "[sofascore-daily] 변경 없음 — 커밋 생략"
} else {
    $msg = "chore(data): Sofascore 평점 일일 갱신 — 시즌 $Season [skip ci]"
    if ($BuildCode -ne 0) { $msg += "`n`n일부 리그 실패 — logs/season-$Season-*.log 참고" }
    git commit -m $msg -- $Paths
    $pushed = Push-Main "sofascore-daily"
}
Write-Host "[sofascore-daily] done (build exit $BuildCode)"
Finish $BuildCode
