"use client";
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent as RKeyboardEvent, type MouseEvent as RMouseEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

// ⓘ 도움말 — 공식·기준·출처처럼 '궁금할 때만' 보는 글은 화면에 늘어놓지 않고 여기로(2026-10-21 사용자: "글이 너무 많다,
// 부가설명·공식 로직을 일일이 나열하지 말고 호버로"). PC 는 마우스를 올리면, 모바일은 누르면 열린다.
// 설명창은 body 로 띄워(portal) 카드 overflow 에 잘리지 않고, 화면 가장자리 16px 안으로 위치를 맞춘다.
// 호버는 진짜 마우스(pointerType === "mouse")일 때만 — 터치 노트북은 탭이 호환 mouseenter + click 을 같이 보내
// '열렸다 바로 닫히는' 문제가 있었다. 호버로 연 상태에서 누르면 고정(pin), 고정된 창은 바깥 누르기·Esc·스크롤·크기 변경으로 닫힌다.
// 키 입력은 부모로 새지 않게 — 경기 카드(role=button) 안의 ⓘ 에서 Enter 가 카드를 열거나, Esc 가 매치 서랍까지 닫지 않도록.
const GAP = 8, EDGE = 16;

export default function Info({ children, label = "설명 보기", wide = false, className = "" }: {
  children: ReactNode; label?: string; wide?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; above: boolean } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const how = useRef<"hover" | "click" | null>(null);   // 어떻게 열렸나 — 호버로 연 것만 마우스가 떠나면 닫힌다
  const id = useId();

  const place = useCallback(() => {
    const b = btn.current?.getBoundingClientRect();
    const t = tip.current;
    if (!b || !t) return;
    const w = t.offsetWidth, h = t.offsetHeight;
    const vw = window.innerWidth, vh = window.innerHeight;
    const left = Math.min(Math.max(EDGE, b.left + b.width / 2 - w / 2), vw - EDGE - w);
    const below = b.bottom + GAP + h <= vh - EDGE || b.top - GAP - h < EDGE;
    const top0 = below ? b.bottom + GAP : b.top - GAP - h;
    const top = Math.max(EDGE, Math.min(top0, vh - EDGE - h));   // 긴 설명도 화면 안으로(넘치면 창 안에서 스크롤)
    setPos({ left, top, above: !below });
  }, []);

  const clearTimer = () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };

  useEffect(() => {
    if (!open) { setPos(null); how.current = null; return; }
    place();
    const away = (e: PointerEvent) => {
      const n = e.target as Node;
      if (!btn.current?.contains(n) && !tip.current?.contains(n)) setOpen(false);
    };
    // 캡처 단계에서 먼저 받아 Esc 를 여기서 끝낸다 — 매치 서랍(window keydown)이 같이 닫히지 않게
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation(); e.stopImmediatePropagation();
      setOpen(false);
    };
    // 설명창 안 스크롤(긴 설명)은 닫지 않는다
    const scroll = (e: Event) => {
      const t = e.target;
      if (t instanceof Node && tip.current?.contains(t)) return;
      setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key, true);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key, true);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open, place]);

  useEffect(() => clearTimer, []);

  const enter = (e: RPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    clearTimer();
    if (!open) { how.current = "hover"; setOpen(true); }
  };
  const leave = (e: RPointerEvent) => {
    if (e.pointerType !== "mouse" || how.current !== "hover") return;
    clearTimer();
    timer.current = setTimeout(() => { timer.current = null; if (how.current === "hover") setOpen(false); }, 120);
  };
  const click = (e: RMouseEvent) => {
    e.stopPropagation();
    clearTimer();
    if (open && how.current === "hover") { how.current = "click"; return; }   // 호버로 연 창을 누르면 고정
    if (open) { setOpen(false); return; }
    how.current = "click"; setOpen(true);
  };
  // 설명창(portal)의 클릭도 React 트리로는 부모 카드까지 올라간다 → 창 안 클릭은 여기서 멈춘다(아래 onClick).
  // Esc 는 통과 — 닫힌 ⓘ 에 초점이 있어도 서랍 Esc 는 그대로(열린 창의 Esc 는 위 캡처 리스너가 먼저 끝낸다)
  const keyDown = (e: RKeyboardEvent) => { if (e.key !== "Escape") e.stopPropagation(); };

  return (
    <>
      <button ref={btn} type="button" className={`info-i ${className}`} aria-label={label} aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={click} onPointerEnter={enter} onPointerLeave={leave} onKeyDown={keyDown}>i</button>
      {open && typeof document !== "undefined" && createPortal(
        <div ref={tip} id={id} role="tooltip" className={`info-tip${wide ? " wide" : ""}${pos?.above ? " above" : ""}`}
          style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: 0 }} onPointerEnter={enter} onPointerLeave={leave}
          onClick={(e) => e.stopPropagation()}>
          {children}
        </div>, document.body)}
    </>
  );
}
