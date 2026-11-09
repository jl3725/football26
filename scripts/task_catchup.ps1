# 로컬 작업 '따라잡기' 트리거 — 절전에서 깨어남(전원 이벤트) · 로그온 때도 실행(2026-11-09).
#
# 노트북이 Modern Standby·최대 절전에 있는 동안 정해진 시각을 놓치면 '놓친 실행 시작'(StartWhenAvailable)이 늘 돌지는 않았다
# (11/06 18:15 대기 → 11/09 07:54 깨어남: sofascore-daily 11/07·11/08 분이 안 돎). 그래서 깨어난 뒤 3분·로그온 뒤 5분에 한 번 더
# 부르고, 실행 스크립트가 '최근에 끝까지 돈 적 있으면 건너뜀'(scripts/git_sync.ps1 Test-RecentRun)으로 중복을 막는다.
# 깨우기(WakeToRun)는 쓰지 않는다 — 가방 속 노트북을 깨우지 않게.
# 사용: . (Join-Path $PSScriptRoot "task_catchup.ps1") 뒤 $Trigger = @(<정해진 시각>) + (Get-CatchUpTriggers)

function Get-CatchUpTriggers {
    $cls = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
    $wake = $cls | New-CimInstance -ClientOnly
    $wake.Enabled = $true
    # Power-Troubleshooter 1 = '저전력 상태에서 돌아옴'(아침에 덮개 열기·최대 절전 복귀). 하루 수십 번인 Modern Standby 507 은 쓰지 않는다
    $wake.Subscription = "<QueryList><Query Id='0' Path='System'><Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]</Select></Query></QueryList>"
    $wake.Delay = "PT3M"
    $logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $logon.Delay = "PT5M"
    # 잠금 해제 — 이 노트북은 대부분 Modern Standby(Kernel-Power 507)로 깨어나 위 1번 이벤트가 없다(11/10 07:53 깨어남에 안 돎).
    # 사람이 다시 쓰기 시작하는 순간 = 네트워크도 붙어 있을 때(2026-11-10)
    $ucls = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
    $unlock = $ucls | New-CimInstance -ClientOnly
    $unlock.Enabled = $true
    $unlock.StateChange = 8                # TASK_SESSION_UNLOCK
    $unlock.UserId = "$env:USERDOMAIN\$env:USERNAME"
    $unlock.Delay = "PT2M"
    return @($wake, $logon, $unlock)
}
