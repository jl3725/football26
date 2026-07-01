param(
    [string]$TaskName = "football26-market-value-agent",
    [string]$DailyAt = "07:50"
)

# 매일 07:50 (다른 수집 이전) 시장가치 스냅샷 + 직전 대비 변동 기록.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\snapshot_market_values.py"

if (-not (Test-Path $Python)) { throw "Python executable not found: $Python" }
if (-not (Test-Path $Script)) { throw "snapshot script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
