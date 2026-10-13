param(
    [string]$TaskName = "football26-season-weekly"
)
# 로컬 시즌 빌드 작업 등록 — 매주 수요일 12:30 (TM 주간 작업 월 12:30 과 안 겹치게).
# 선수 스탯 체인(FBref·Sofascore·Understat·TM 시장가치·라인업·히트맵, 약 1.5시간) — scripts/run_season_agent.ps1
# 해제: Unregister-ScheduledTask -TaskName football26-season-weekly -Confirm:$false
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\run_season_agent.ps1"
if (-not (Test-Path $Script)) { throw "agent script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At "12:30"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName (매주 수 12:30)"
