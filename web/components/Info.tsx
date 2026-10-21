"use client";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// ⓘ 도움말 — 공식·기준·출처처럼 '궁금할 때만' 보는 글은 화면에 늘어놓지 않고 여기로(2026-10-21 사용자: "글이 너무 많다,
// 부가설명·공식 로직을 일일이 나열하지 말고 호버로"). PC 는 마우스를 올리면, 모바일은 누르면 열린다.
// 설명창은 body 로 띄워(portal) 카드 overflow 에 잘리지 않고, 화면 가장자리 16px 안으로 위치를 맞춘다.
const GAP = 8, EDGE = 16;

export default function Info({ children, label = "설명 보기", wide = false, className = "" }: {
  children: ReactNode; label?: string; wide?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; above: boolean } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();

  const place = useCallback(() => {
    const b = btn.current?.getBoundingClientRect();
    const t = tip.current;
    if (!b || !t) return;
    const w = t.offsetWidth, h = t.offsetHeight;
    const vw = window.innerWidth, vh = window.innerHeight;
    const left = Math.min(Math.max(EDGE, b.left + b.width / 2 - w / 2), vw - EDGE - w);
    const below = b.bottom + GAP + h <= vh - EDGE || b.top - GAP - h < EDGE;
    setPos({ left, top: below ? b.bottom + GAP : b.top - GAP - h, above: !below });
  }, []);

  useEffect(() => {
    if (!open) { setPos(null); return; }
    place();
    const away = (e: PointerEvent) => {
      const n = e.target as Node;
      if (!btn.current?.contains(n) && !tip.current?.contains(n)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const close = () => setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open, place]);

  const canHover = () => typeof window !== "undefined" && window.matchMedia?.("(hover: hover)").matches;
  const enter = () => { if (!canHover()) return; if (timer.current) clearTimeout(timer.current); setOpen(true); };
  const leave = () => { if (!canHover()) return; timer.current = setTimeout(() => setOpen(false), 120); };

  return (
    <>
      <button ref={btn} type="button" className={`info-i ${className}`} aria-label={label} aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} onMouseEnter={enter} onMouseLeave={leave}>i</button>
      {open && typeof document !== "undefined" && createPortal(
        <div ref={tip} id={id} role="tooltip" className={`info-tip${wide ? " wide" : ""}${pos?.above ? " above" : ""}`}
          style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: 0 }} onMouseEnter={enter} onMouseLeave={leave}>
          {children}
        </div>, document.body)}
    </>
  );
}
