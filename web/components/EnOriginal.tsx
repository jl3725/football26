"use client";
import { useState } from "react";

// 번역 기사 원제 — 기본은 'EN' 칩만(호버하면 원제), 누르면 원제 한 줄을 펼친다.
// 기계 번역이 승패·주어를 뒤집을 때 대조하려고 원제 줄을 늘 보였는데(뉴스·선수 뉴스·STORY), 기사마다 한 줄씩 늘어
// 글이 너무 많았다(2026-10-23 글 줄이기). 링크 카드 안에 들어가므로 버튼 대신 span + 클릭 전파 막기.
export default function EnOriginal({ text, ko }: { text?: string | null; ko?: string | null }) {
  const [open, setOpen] = useState(false);
  if (!text || text === ko) return null;
  const toggle = (e: React.SyntheticEvent) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); };
  return (
    <>
      <span role="button" tabIndex={0} className="en-chip" title={text} aria-label="원제 보기" aria-expanded={open}
        onClick={toggle} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") toggle(e); }}>EN</span>
      {open && <span className="en-orig">{text}</span>}
    </>
  );
}
