param([string]$Root)
# 프로필 자동수집 파이프라인 (데일리 08:10) — 위키백과 기반, 수기 없음:
#   1) sync_manager_profiles  — 감독 교체 감지 + 이름/사진/부임일 갱신
#                                (교체 시 낡은 bio/tactics 를 비워 재수집 대상으로 만듦)
#   2) enrich_manager_profiles — 감독 본인 위키에서 bio(한국어)·전술/포메이션 자동 수집
#   3) enrich_team_profiles    — 구단 위키 요약으로 팀 설명 자동 수집
#                                (--only-missing: 신규·교체분만, 전체 재수집 낭비 방지)
$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Resolve-Path (Join-Path $PSScriptRoot "..") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "[profiles-agent] 1/3 sync_manager_profiles --write"
& $Python (Join-Path $Root "src\sync_manager_profiles.py") --write
Write-Host "[profiles-agent] 2/3 enrich_manager_profiles --write --only-missing"
& $Python (Join-Path $Root "src\enrich_manager_profiles.py") --write --only-missing --sleep 1.5
Write-Host "[profiles-agent] 3/4 enrich_team_profiles --write --only-missing"
& $Python (Join-Path $Root "src\enrich_team_profiles.py") --write --only-missing --sleep 1.5
Write-Host "[profiles-agent] 4/6 detect_season_teams --write (EPL)"
& $Python (Join-Path $Root "src\detect_season_teams.py") --write
Write-Host "[profiles-agent] 5/6 fetch_laliga_managers (감독 + 26/27 팀)"
& $Python (Join-Path $Root "src\fetch_laliga_managers.py")
Write-Host "[profiles-agent] 6/7 detect_season_teams --league LaLiga --write (승격팀 감지)"
& $Python (Join-Path $Root "src\detect_season_teams.py") --league LaLiga --write
Write-Host "[profiles-agent] 7/7 detect_manager_changes --league LaLiga --write (감독 교체 감지)"
& $Python (Join-Path $Root "src\detect_manager_changes.py") --league LaLiga --write
Write-Host "[profiles-agent] done"
