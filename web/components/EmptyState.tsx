"use client";
// 사용 불가·데이터 없음·요청 실패를 한 가지 모양으로. 스켈레톤은 로딩 중에만, 결과가 없으면 반드시 이걸로.
// compact: 한 줄짜리(카드 안의 보조 블록이 비었을 때 큰 빈 상자로 자리를 차지하지 않게)
export default function EmptyState({ title, note, icon = "·", compact = false }: { title: string; note?: string; icon?: string; compact?: boolean }) {
  return (
    <div className={`empty-state${compact ? " compact" : ""}`} role="status">
      <div className="es-ico" aria-hidden="true">{icon}</div>
      <b>{title}</b>
      {note && <span>{note}</span>}
    </div>
  );
}
