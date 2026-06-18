param(
    [string]$TaskName = "football26-transfermarkt-injury-agent",
    [string]$DailyAt = "08:00"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "src\fetch_transfermarkt_injuries.py"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}
if (-not (Test-Path $Script)) {
    throw "Injury sync script not found: $Script"
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
