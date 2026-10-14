"use client";
import type { ReactNode } from "react";

// 섹션 머리 공통형(디자인 v5) — 한글 제목 + 범위·개수 메타 + 오른쪽 동작. 영문 대문자 꼬리표는 쓰지 않는다.
export function Chevron() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m9 18 6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function SectionHead({ title, meta, action, onAction, right }: {
  title: string; meta?: ReactNode; action?: string; onAction?: () => void; right?: ReactNode;
}) {
  return (
    <div className="sh">
      <div className="sh-l">
        <h2 className="sh-t">{title}</h2>
        {meta ? <span className="sh-m">{meta}</span> : null}
      </div>
      {right ?? (action && onAction ? <button className="sh-a" onClick={onAction}>{action}<Chevron /></button> : null)}
    </div>
  );
}
