"use client";
import { useEffect, useRef, useState } from "react";

// 숫자가 0에서 목표값까지 올라가며 나타난다(0.7초, ease-out). 움직임 줄이기 설정이면 바로 최종값.
export default function CountUp({ value, format = (v) => Math.round(v).toLocaleString() }:
  { value: number; format?: (v: number) => string }) {
  const [v, setV] = useState(value);
  const raf = useRef<number>(0);
  useEffect(() => {
    if (typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(value); return; }
    const t0 = performance.now(), dur = 700;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur);
      setV(value * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [value]);
  return <>{format(v)}</>;
}
