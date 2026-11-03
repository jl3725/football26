// 출장 정지 표시 — 빨간 카드 모양. 부상은 각 화면의 ✚ 그대로(2026-11-03 사용자: 다우먼 출장 정지가 ✚·'부상'으로 보였다).
// badge = 베스트 XI 빌더 사진 모서리(부상 + 원 배지 자리)
export function SusCard({ badge = false }: { badge?: boolean }) {
  return <span className={badge ? "abs-card abs-badge" : "abs-card"} title="출장 정지" aria-label="출장 정지" role="img" />;
}
