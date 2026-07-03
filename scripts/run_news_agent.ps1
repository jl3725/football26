param([string]$Root)
# 뉴스 파이프라인 (데일리 08:20):
#   1) fetch_news_daily    — 팀별 ESPN/Guardian/BBC 뉴스 수집·번역 (news.db 누적)
#   2) fetch_transfer_buzz — 이적 속보/루머 피드(Guardian·BBC RSS) 수집·번역·분류 → data/transfer_buzz.csv
$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "[news-agent] 1/4 fetch_news_daily (EPL+LaLiga)"
& $Python (Join-Path $Root "scripts\fetch_news_daily.py") --all
Write-Host "[news-agent] 2/4 fetch_transfer_buzz EPL"
& $Python (Join-Path $Root "src\fetch_transfer_buzz.py")
Write-Host "[news-agent] 3/4 fetch_transfer_buzz LaLiga (Marca)"
& $Python (Join-Path $Root "src\fetch_transfer_buzz.py") --league LaLiga
Write-Host "[news-agent] 4/4 fetch_wc (2026 월드컵 · 진행 중)"
& $Python (Join-Path $Root "src\fetch_wc.py")
Write-Host "[news-agent] done"
