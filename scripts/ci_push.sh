#!/usr/bin/env bash
# 데이터 커밋 푸시 — 수집 워크플로 공용(이미 git commit 한 뒤에 부른다).
#
# 예전 반복문(`git pull --rebase … && git push && break || sleep 5`)은 다른 워크플로가 같은 데이터 파일을 먼저 고쳐
# rebase 가 충돌하면 '충돌 중' 상태로 3번 다 실패하고도 단계가 성공으로 끝났다 — 그 실행의 수집 결과가 통째로 안 올라갔다
# (2026-10-24·25 TM Data 2번·Match Refresh 1번: players_full_Championship·SuperLig 충돌, 13개 리그 TM 수집분 유실).
#
#   1) 보통 rebase → push
#   2) 충돌이면 rebase 를 되돌리고, 충돌 칸은 이번 실행이 방금 수집한 값으로(-X theirs: rebase 에선 다시 얹는 우리 커밋 쪽)
#      다른 줄은 양쪽 변경을 다 살린다. 상대 워크플로가 고친 같은 줄은 그 워크플로 다음 실행이 다시 계산한다
#   3) 그래도 못 올리면 실패(빨간불) — 조용히 잃지 않는다
set -u
# 선수 표 CSV(players*.csv)는 칸 단위 병합 — 줄 단위 -X theirs 가 다른 작업이 바꾼 칸(주간 빌드 FBref·지난 시즌 기록)을
# 옛 값으로 덮었다(2026-11-02, .gitattributes · scripts/csv_cell_merge.py)
git config merge.csvcells.name "players csv cell merge"
git config merge.csvcells.driver "python scripts/csv_cell_merge.py %O %A %B"
for i in 1 2 3 4; do
  if git pull --rebase --autostash origin main; then
    git push && exit 0
  else
    echo "::notice title=데이터 커밋 충돌::다른 워크플로가 같은 파일을 먼저 고침 — 충돌 칸은 이번 수집 값으로 다시 얹는다(${i}/4)"
    git rebase --abort 2>/dev/null || true
    git fetch origin main && git rebase -X theirs --autostash origin/main && git push && exit 0
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((5 * i))
done
echo "::error title=데이터 커밋 실패::4번 시도해도 푸시 못 함 — 이번 실행의 수집 결과가 저장되지 않았다"
exit 1
