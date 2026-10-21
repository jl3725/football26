"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";

// 긴 본문(위키 소개·AI 요약 등) — 기본 lines 줄만 보이고, 넘치면 '더 보기'로 펼친다(2026-10-21 사용자: 글이 너무 많다).
// 폭이 바뀌면(창 크기·패널 열림·폰트 로딩) 넘침을 다시 잰다 — 처음 한 번만 재면 '더 보기'가 빠지거나 남는다.
export default function Clamp({ text, lines = 2, className = "", style }: {
  text: string; lines?: number; className?: string; style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => { if (!el.classList.contains("clamp-t")) return; setOver(el.scrollHeight > el.clientHeight + 2); };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    let w = el.clientWidth;
    const ro = new ResizeObserver(() => { if (el.clientWidth !== w) { w = el.clientWidth; measure(); } });
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, lines, open]);   // 펼친 동안엔 재지 않고(넘침 0), 접을 때 다시 잰다
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
