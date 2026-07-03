param(
    [string]$TaskName = "football26-wc-agent",
    [string[]]$DailyAt = @("08:00", "12:00")
)

# 월드컵 수집(로컬 폴백) — 하루 2회(기본 08:00·12:00). 북중미 개최라 경기가 한국 오전에
# 몰려, 오전 결과를 빠르게 반영. 기본 자동화는 .github/workflows/daily_wc.yml(GH Actions).
# GH 가 막히거나 지연될 때 이 로컬 스케줄러 사용. fetch_wc + fetch_fifa_ranking 둘 다 실행.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Runner = Join-Path $Root "scripts\run_wc_agent.ps1"
if (-not (Test-Path $Runner)) { throw "WC agent runner not found: $Runner" }

$PS = (Get-Command powershell.exe).Source
$Action = New-ScheduledTaskAction -Execute $PS `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" -WorkingDirectory $Root
$Triggers = $DailyAt | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $($DailyAt -join ', ') (로컬 폴백 — 기본은 GH Actions daily_wc.yml)"
