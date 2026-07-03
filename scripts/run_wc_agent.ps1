param([string]$Root)
# 월드컵 수집(로컬 폴백) — 하루 2회(08:00·12:00) 실행용.
#   1) fetch_wc            — 경기·득점·도움·조별·스쿼드 (ESPN 순수 API)
#   2) fetch_fifa_ranking  — FIFA 랭킹(월드컵 탭 상단, 실시간 예상의 기준점수)
$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "[wc-agent] 1/2 fetch_wc"
& $Python (Join-Path $Root "src\fetch_wc.py")
Write-Host "[wc-agent] 2/2 fetch_fifa_ranking"
& $Python (Join-Path $Root "src\fetch_fifa_ranking.py")
Write-Host "[wc-agent] done"
