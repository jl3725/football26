#!/usr/bin/env bash
# Vercel "Ignored Build Step" — exit 0 = 빌드 생략, exit 1 = 빌드.
#
# 반드시 0 또는 1 로만 끝나야 한다. 직전 배포 커밋(VERCEL_GIT_PREVIOUS_SHA)이 얕은 클론에 없으면
# `git diff` 가 128 로 끝나고 Vercel 은 이를 오류로 처리해 배포 자체가 실패한다(2026-10-13 실제 사고 —
# 프론트가 10/12 버전에 멈춤). 판단이 불확실하면 항상 빌드한다.
prev="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -z "$prev" ] || ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  echo "[ignore] 직전 배포 커밋을 확인할 수 없음 → 빌드"
  exit 1
fi
if git diff --quiet "$prev" HEAD -- . 2>/dev/null; then
  echo "[ignore] ${prev:0:7}..HEAD 사이 web/ 변경 없음 → 빌드 생략"
  exit 0
fi
echo "[ignore] web/ 변경 있음 → 빌드"
exit 1
