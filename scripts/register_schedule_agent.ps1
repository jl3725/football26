param(
    [string]$TaskName = "football26-schedule-agent",
    [string]$DailyAt = "07:45"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "src\fetch_schedule.py"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}
if (-not (Test-Path $Script)) {
    throw "Schedule fetch script not found: $Script"
}

# 인자 없이 실행 → 25/26 + 26/27 둘 다 갱신 (26/27 픽스처·컵 추첨이 시즌 진행 중 채워짐)
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
