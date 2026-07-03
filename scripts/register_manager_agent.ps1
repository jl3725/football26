param(
    [string]$TaskName = "football26-manager-agent",
    [string]$DailyAt = "07:15"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "src\fetch_laliga_managers.py"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}
if (-not (Test-Path $Script)) {
    throw "LaLiga manager fetch script not found: $Script"
}

# LaLiga 감독 프로필 자동 갱신 (EPL 은 sync_manager_profiles 별도 경로).
# 현재 추적 시즌(tracking_season_title) 위키 감독표를 매일 반영 → 감독 교체 자동 추적.
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
