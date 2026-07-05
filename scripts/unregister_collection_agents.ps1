# 로컬 수집 작업 해제 — 이제 수집은 GitHub Actions(클라우드)가 전담.
# 로컬에서 중복 수집·push 하면 origin 과 충돌하므로 아래 작업들을 제거한다.
# (되돌리려면 각 register_*.ps1 을 다시 실행)
# 로컬 동기화는 register_pull_agent.ps1(football26-pull-agent)가 담당.
$ErrorActionPreference = "SilentlyContinue"

$tasks = @(
    "football26-news-agent",
    "football26-transfers-agent",
    "football26-manager-agent",
    "football26-manager-change-agent",
    "football26-market-value-agent",
    "football26-transfermarkt-injury-agent",
    "football26-schedule-agent",
    "football26-wc-agent",
    "football26-data-push-agent",
    "football26-db-rebuild-agent"
)

foreach ($t in $tasks) {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Write-Host "removed  $t"
    } else {
        Write-Host "skip     $t (없음)"
    }
}
Write-Host ""
Write-Host "로컬 수집 작업 해제 완료 — 수집=GitHub Actions, 로컬 동기화=football26-pull-agent"
