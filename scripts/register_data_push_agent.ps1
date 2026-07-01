param(
    [string]$TaskName = "football26-data-push-agent",
    [string]$DailyAt = "08:50"
)

# 매일 08:50 (수집 07:50~08:30 + DB재빌드 08:40 이후) 갱신 데이터를 git push.
# → Vercel/Railway 클라우드 자동 재배포로 최신 데이터 반영.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pwsh = (Get-Command powershell.exe).Source
$Script = Join-Path $Root "scripts\push_data.ps1"

if (-not (Test-Path $Script)) { throw "push_data script not found: $Script" }

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Registered $TaskName at $DailyAt"
