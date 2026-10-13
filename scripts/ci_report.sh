#!/usr/bin/env bash
# scripts/ci_try.sh 가 남긴 실패 목록을 Step Summary 에 쓰고, 하나라도 있으면 exit 1.
# 커밋 단계 뒤에 `if: always()` 로 둔다 — 성공한 수집분은 이미 커밋된 상태로 실패를 알린다.
set -u
f="${COLLECT_FAILURES:-/tmp/collect_failures.txt}"
if [ ! -s "$f" ]; then
  echo "모든 수집 단계 성공"
  exit 0
fi
n=$(wc -l < "$f")
{
  echo "### 실패한 수집 단계 (${n})"
  sed 's/^/- /' "$f"
} >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"
echo "실패 ${n}건:"
cat "$f"
exit 1
