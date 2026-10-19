param(
    [string]$TaskName = "football26-sofascore-daily"
)
# 로컬 Sofascore 일일 작업 등록 — 매일 11:40(수요일은 스크립트가 건너뜀: 12:30 주간 전체 빌드와 겹치지 않게).
# 선수 시즌 평점·출전(Sofascore)만, 약 10~15분 — scripts/run_sofascore_daily.ps1
# 해제: Unregister-ScheduledTask -TaskName football26-sofascore-daily -Confirm:$false
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\run_sofascore_daily.ps1"
if (-not (Test-Path $Script)) { throw "agent script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At "11:40"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName (매일 11:40, 수요일 제외)"
