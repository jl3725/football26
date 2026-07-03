param(
    [string]$TaskName = "football26-wc-agent",
    [string]$DailyAt = "15:20"
)

# 월드컵 일일 수집(로컬 폴백). 기본 자동화는 .github/workflows/daily_wc.yml(GH Actions,
# ESPN 순수 API라 러너에서 안정적·자동 커밋/배포). GH 가 막히면 이 로컬 스케줄러 사용.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "src\fetch_wc.py"

if (-not (Test-Path $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path $Script)) { throw "WC fetch script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt (로컬 폴백 — 기본은 GH Actions daily_wc.yml)"
