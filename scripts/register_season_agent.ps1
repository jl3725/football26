param(
    [string]$TaskName = "football26-season-weekly"
)
# 로컬 시즌 빌드 작업 등록 — 매주 수요일 12:30 (TM 주간 작업 월 12:30 과 안 겹치게).
# 선수 스탯 체인(FBref·Sofascore·Understat·TM 시장가치·라인업·히트맵, 약 1.5시간) — scripts/run_season_agent.ps1
# 깨어남·로그온 때도 한 번 더(scripts/task_catchup.ps1) — 6일 안에 돈 적 있으면 스크립트가 건너뜀(2026-11-09). 창 없이 실행.
# 해제: Unregister-ScheduledTask -TaskName football26-season-weekly -Confirm:$false
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\run_season_agent.ps1"
if (-not (Test-Path $Script)) { throw "agent script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
. (Join-Path $PSScriptRoot "task_catchup.ps1")
$Trigger = @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At "12:30") + (Get-CatchUpTriggers)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName (매주 수 12:30 · 깨어남·로그온 따라잡기)"
