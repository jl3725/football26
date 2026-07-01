param(
    [string]$TaskName = "football26-db-rebuild-agent",
    [string]$DailyAt = "08:40"
)

# 매일 수집 에이전트(부상 08:00 · 감독 08:10 · 뉴스 08:20 · 이적 08:30) 이후
# 08:40 에 CSV → football.db 통합을 재실행해 DB 를 최신 상태로 유지한다.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\build_db.py"

if (-not (Test-Path $Python)) { throw "Python executable not found: $Python" }
if (-not (Test-Path $Script)) { throw "build_db script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
