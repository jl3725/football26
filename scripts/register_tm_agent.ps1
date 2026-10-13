param(
    [string]$TaskName = "football26-tm-agent",
    [string]$WeeklyTaskName = "football26-tm-weekly"
)
# 로컬 Transfermarkt 수집 작업 등록 (TM 이 GH Actions 러너 IP 를 막아서 이 PC 에서만 수집 가능 —
# scripts/run_tm_agent.ps1 참고).
#   football26-tm-agent  : 매일 10:30 / 18:30 — 이적·현재 부상·계약·루머 (pull-agent 09/13/17/21시와 안 겹치게)
#   football26-tm-weekly : 매주 월 12:30 — 통산 부상 이력 (약 1.5시간)
# 해제: Unregister-ScheduledTask -TaskName football26-tm-agent,football26-tm-weekly -Confirm:$false
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell).Source
$Script = Join-Path $Root "scripts\run_tm_agent.ps1"

if (-not (Test-Path $Script)) { throw "agent script not found: $Script" }

function Register-Agent([string]$Name, [string]$ExtraArgs, $Triggers, [int]$LimitHours) {
    $Argument = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" $ExtraArgs".Trim()
    $Action = New-ScheduledTaskAction -Execute $Pwsh -Argument $Argument -WorkingDirectory $Root
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours $LimitHours) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers -Settings $Settings -Force | Out-Null
}

$daily = @(
    New-ScheduledTaskTrigger -Daily -At "10:30"
    New-ScheduledTaskTrigger -Daily -At "18:30"
)
Register-Agent $TaskName "" $daily 2
Write-Host "Registered $TaskName (매일 10:30 / 18:30)"

$weekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "12:30"
Register-Agent $WeeklyTaskName "-Weekly" $weekly 4
Write-Host "Registered $WeeklyTaskName (매주 월 12:30)"
