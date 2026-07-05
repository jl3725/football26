param(
    [string]$TaskName = "football26-pull-agent"
)
# 로컬 동기화 작업 등록 — 클라우드가 수집한 최신 데이터를 로그온 시 + 하루 4회 받아
# football.db 재빌드. (로컬 수집 작업은 unregister_collection_agents.ps1 로 해제)
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\pull_and_rebuild.ps1"

if (-not (Test-Path $Script)) { throw "pull script not found: $Script" }

$Argument = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument $Argument -WorkingDirectory $Root

# 매일 09/13/17/21시 (콤마 없이 줄바꿈 = 배열). AtLogOn 트리거는 비관리자 세션에서
# Access denied(0x80070005) 유발할 수 있어 제외 — 데일리 4회로 충분.
$triggers = @(
    New-ScheduledTaskTrigger -Daily -At "09:00"
    New-ScheduledTaskTrigger -Daily -At "13:00"
    New-ScheduledTaskTrigger -Daily -At "17:00"
    New-ScheduledTaskTrigger -Daily -At "21:00"
)

$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $triggers -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName (매일 09/13/17/21시)"
