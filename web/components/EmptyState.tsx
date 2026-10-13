"use client";
// 사용 불가·데이터 없음·요청 실패를 한 가지 모양으로. 스켈레톤은 로딩 중에만, 결과가 없으면 반드시 이걸로.
export default function EmptyState({ title, note, icon = "·" }: { title: string; note?: string; icon?: string }) {
  return (
    <div className="empty-state" role="status">
      <div className="es-ico" aria-hidden="true">{icon}</div>
      <b>{title}</b>
      {note && <span>{note}</span>}
    </div>
  );
}
