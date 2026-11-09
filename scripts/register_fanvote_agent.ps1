param(
    [string]$TaskName = "football26-fanvote-agent"
)
# 로컬 팬 투표 작업 등록 — 매일 10:30·18:30 (Sofascore 팬 승부 예측 투표, scripts/run_fanvote_agent.ps1, 1~5분).
# 깨어남·로그온 때도 한 번 더(scripts/task_catchup.ps1) — 6시간 안에 돈 적 있으면 스크립트가 건너뜀(2026-11-09).
# 예전엔 손으로 등록해 등록 스크립트가 없었다.
# 해제: Unregister-ScheduledTask -TaskName football26-fanvote-agent -Confirm:$false
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\run_fanvote_agent.ps1"
if (-not (Test-Path $Script)) { throw "agent script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
. (Join-Path $PSScriptRoot "task_catchup.ps1")
$Trigger = @((New-ScheduledTaskTrigger -Daily -At "10:30"), (New-ScheduledTaskTrigger -Daily -At "18:30")) + (Get-CatchUpTriggers)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName (매일 10:30·18:30 · 깨어남·로그온 따라잡기)"
