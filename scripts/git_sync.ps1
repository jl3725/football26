# 로컬 agent 공용 git 동기화 — 클라우드 scripts/ci_push.sh 와 같은 규칙(2026-11-02).
#
# 예전엔 스크립트마다 'git pull --rebase' 한 줄이었다. 다른 작업이 같은 데이터 파일(players_full·home_all 등)을 먼저 고치면
# 충돌로 멈춰 저장소를 'rebase 중' 상태로 남겼고, 다음 실행은 시작 pull 실패 → 중단으로 끝나 로컬 수집분이 며칠씩 안 올라갔다
# (10/28 주간 빌드, 10/30~11/2 Sofascore 평점 일일 갱신).
#   1) 보통 pull --rebase → 2) 충돌이면 되돌리고 충돌 칸은 이번 수집 값으로(-X theirs: rebase 에선 다시 얹는 내 커밋 쪽),
#      다른 줄은 양쪽 변경을 다 살린다 → 3) 그래도 안 되면 되돌리고 실패(저장소를 rebase 중으로 남기지 않는다)
# 사용: . (Join-Path $PSScriptRoot "git_sync.ps1") 뒤 Sync-Main / Push-Main "태그"
# git 출력은 Out-Host 로 — 함수 반환값에 섞이면 늘 참으로 읽힌다.

function Sync-Main {
    git pull --rebase --autostash origin main | Out-Host
    if ($LASTEXITCODE -eq 0) { return $true }
    git rebase --abort 2>$null | Out-Host
    git fetch origin main | Out-Host
    git rebase -X theirs --autostash origin/main | Out-Host
    if ($LASTEXITCODE -eq 0) { return $true }
    git rebase --abort 2>$null | Out-Host
    return $false
}

function Push-Main([string]$Tag) {
    for ($i = 1; $i -le 3; $i++) {
        if (Sync-Main) {
            git push origin HEAD:main | Out-Host
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        Start-Sleep -Seconds (5 * $i)
    }
    Write-Host "[$Tag] push 실패 — 다음 실행 때 함께 push 됨"
    return $false
}
