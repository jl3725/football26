"use client";
import type { ReactNode } from "react";
import Info from "./Info";

// 섹션 머리 공통형 — 영어 대문자 제목(크게) + 한글 보조(작게) + 범위·개수 메타 + 오른쪽 동작.
// 제목은 영어 위주가 사용자 선호(디자인 v5 에서 한글 제목으로 바꿨다가 되돌림).
export function Chevron() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m9 18 6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// info = 공식·기준·출처 같은 부가 설명(ⓘ 호버·탭) — 화면에 늘어놓지 않는다
export default function SectionHead({ title, kr, meta, info, action, onAction, right }: {
  title: string; kr?: string; meta?: ReactNode; info?: ReactNode; action?: string; onAction?: () => void; right?: ReactNode;
}) {
  return (
    <div className="sh">
      <div className="sh-l">
        <h2 className="sh-t">{title}</h2>
        {kr ? <span className="sh-kr">{kr}</span> : null}
        {meta ? <span className="sh-m">{meta}</span> : null}
        {/* ⓘ 는 메타 뒤 — kr 과 meta 사이에 끼면 '.sh-kr + .sh-m' 구분점(·)이 사라진다 */}
        {info ? <Info label={`${title} 설명`}>{info}</Info> : null}
      </div>
      {right ?? (action && onAction ? <button className="sh-a" onClick={onAction}>{action}<Chevron /></button> : null)}
    </div>
  );
}
