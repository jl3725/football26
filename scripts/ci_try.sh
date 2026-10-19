#!/usr/bin/env bash
# 수집 단계 실행 래퍼 (GitHub Actions 전용).
#
# 한 리그·한 수집기가 실패해도 나머지 수집과 커밋은 계속 진행하되, 실패를 삼키지 않고
# $COLLECT_FAILURES 에 기록한다. 워크플로 마지막 단계(scripts/ci_report.sh)가 이 파일을
# 보고 실패 목록을 요약에 남긴 뒤 워크플로를 실패 처리한다.
# (이전의 `cmd || echo "실패"` 패턴은 실패를 숨겨 7~10월 내내 "success" 로 보였다.)
#
# 성공·실패 모두 실행 원장(data/ops/runs/<워크플로>.jsonl, src/run_ledger.py)에 한 줄 남긴다 —
# DATA STATUS 화면과 watchdog 이 읽는다. 원장 기록이 실패해도 수집 결과에는 영향 없음.
#
# 사용: scripts/ci_try.sh "라벨" python src/fetch_x.py --args
#       FB_LEAGUE=LaLiga scripts/ci_try.sh "injuries LaLiga" python src/fetch_y.py
set -u
label="$1"
shift
t0=$(date +%s)
"$@"
code=$?
python "$(dirname "$0")/../src/run_ledger.py" add "${LEDGER_RUNNER:-}" "$label" "$code" "$(( $(date +%s) - t0 ))" \
  || echo "::notice::실행 원장 기록 실패(${label}) — 수집과 무관"
if [ "$code" -eq 0 ]; then
  exit 0
fi
echo "::warning title=수집 실패::${label} (exit ${code})"
echo "${label} (exit ${code})" >> "${COLLECT_FAILURES:-/tmp/collect_failures.txt}"
exit 0
