param(
    [string]$TaskName = "football26-manager-change-agent",
    [string]$DailyAt = "08:10"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell.exe).Source
$Script = Join-Path $Root "scripts\run_manager_agent.ps1"

if (-not (Test-Path $Script)) {
    throw "Manager agent script not found: $Script"
}

# sync(교체감지) → enrich(위키 bio/전술 자동수집) 파이프라인 실행
$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
