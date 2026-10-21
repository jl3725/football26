"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";

// 긴 본문(위키 소개·AI 요약 등) — 기본 lines 줄만 보이고, 넘치면 '더 보기'로 펼친다(2026-10-21 사용자: 글이 너무 많다).
export default function Clamp({ text, lines = 2, className = "", style }: {
  text: string; lines?: number; className?: string; style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) setOver(el.scrollHeight > el.clientHeight + 2);
  }, [text, lines]);
  return (
    <div className={className} style={style}>
      <div ref={ref} className={open ? "" : "clamp-t"} style={open ? undefined : { WebkitLineClamp: lines }}>{text}</div>
      {(over || open) && (
        <button type="button" className="clamp-more" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "접기" : "더 보기"}
        </button>
      )}
    </div>
  );
}
