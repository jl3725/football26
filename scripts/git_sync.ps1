# 로컬 agent 공용 git 동기화 — 클라우드 scripts/ci_push.sh 와 같은 규칙(2026-11-02).
#
# 예전엔 스크립트마다 'git pull --rebase' 한 줄이었다. 다른 작업이 같은 데이터 파일(players_full·home_all 등)을 먼저 고치면
# 충돌로 멈춰 저장소를 'rebase 중' 상태로 남겼고, 다음 실행은 시작 pull 실패 → 중단으로 끝나 로컬 수집분이 며칠씩 안 올라갔다
# (10/28 주간 빌드, 10/30~11/2 Sofascore 평점 일일 갱신).
#   0) 앞 실행이 남긴 보관본 충돌(unmerged) 정리(Repair-Unmerged) → 1) 보통 pull --rebase → 2) 충돌이면 되돌리고 충돌 칸은 이번 수집 값으로(-X theirs: rebase 에선 다시 얹는 내 커밋 쪽),
#      다른 줄은 양쪽 변경을 다 살린다 → 3) 그래도 안 되면 되돌리고 실패(저장소를 rebase 중으로 남기지 않는다)
# 사용: . (Join-Path $PSScriptRoot "git_sync.ps1") 뒤 Sync-Main / Push-Main "태그"
# git 출력은 Out-Host 로 — 함수 반환값에 섞이면 늘 참으로 읽힌다.

function Repair-Unmerged {
    # 자동 보관(autostash)을 다시 얹다 충돌해 남은 파일 — 'unmerged' 가 남으면 그 뒤 모든 로컬 수집의 pull 이 실패했다
    # (10/31 · 11/03 팬 투표 · Sofascore 평점이 그동안 안 올라감). data/ 아래 파일은 올라온 값(HEAD)이 기준 — 로컬 수정은 평가 실행 등
    # 이 PC 산출물이고 각 수집기는 자기 산출물을 pull 전에 이미 커밋한다. 코드 파일 충돌은 건드리지 않고 실패(손으로 정리).
    $files = @(git diff --name-only --diff-filter=U 2>$null | Where-Object { $_ })
    if ($files.Count -eq 0) { return $true }
    $other = @($files | Where-Object { -not $_.StartsWith("data/") })
    if ($other.Count -gt 0) {
        Write-Host "[git-sync] 코드 파일 충돌 — 손으로 정리 필요: $($other -join ', ')"
        return $false
    }
    foreach ($f in $files) { git checkout HEAD -- $f 2>$null | Out-Host }
    git reset -q 2>$null | Out-Host
    $top = (git stash list -n 1 2>$null | Out-String)
    if ($top -match "autostash") { git stash drop 2>$null | Out-Host }
    Write-Host "[git-sync] 충돌 정리(올라온 값으로): $($files -join ', ')"
    return $true
}

function Sync-Main {
    # 선수 표 CSV 칸 단위 병합 드라이버(.gitattributes merge=csvcells, scripts/csv_cell_merge.py) — 줄 단위 병합이 다른 작업의 칸을 덮었다(11/02)
    git config merge.csvcells.name "players csv cell merge" | Out-Host
    git config merge.csvcells.driver "python scripts/csv_cell_merge.py %O %A %B" | Out-Host
    if (-not (Repair-Unmerged)) { return $false }            # 앞 실행이 남긴 충돌부터
    git pull --rebase --autostash origin main | Out-Host
    $pulled = ($LASTEXITCODE -eq 0)
    if (-not (Repair-Unmerged)) { return $false }            # 보관본을 다시 얹다 난 충돌
    if ($pulled) { return $true }
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
