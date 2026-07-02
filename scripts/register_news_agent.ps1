param(
    [string]$TaskName = "football26-news-agent",
    [string]$DailyAt = "08:20"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell.exe).Source
$Script = Join-Path $Root "scripts\run_news_agent.ps1"

if (-not (Test-Path $Script)) {
    throw "News agent script not found: $Script"
}

# fetch_news_daily + fetch_transfer_buzz 파이프라인 실행
$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
