param([string]$Root)
# 매일 수집·DB재빌드 이후, 갱신된 data/ 파일을 git 에 커밋·푸시한다.
# → Railway 백엔드가 자동 재배포되며 최신 데이터를 반영(클라우드 신선도 유지).
# football.db 는 .gitignore(파생) — 클라우드가 CSV로 재생성하므로 push 대상 아님.
$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
Set-Location $Root

# 데이터 산출물만 스테이징 (코드 변경은 건드리지 않음)
git add -- "data/*.csv" "data/*.json" "data/news.db" "data/*.md" 2>$null

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "no data changes - skip"
    exit 0
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "chore(data): $stamp 일일 데이터 갱신"
git push
Write-Host "pushed data update $stamp"
