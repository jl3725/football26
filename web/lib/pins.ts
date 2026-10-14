"use client";
import { useCallback, useEffect, useState } from "react";

// 내 팀 고정 — 서버 없이 이 브라우저(localStorage)에만 둔다. 사이드바 '내 팀'과 홈 주의 보드가 먼저 보여 준다.
export type Pin = { team: string; league: string; logo?: string };
const KEY = "pins";
const EVT = "pins-change";
const MAX = 6;

function read(): Pin[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.filter((p) => p && p.team && p.league) : [];
  } catch {
    return [];
  }
}

export function usePins() {
  const [pins, setPins] = useState<Pin[]>([]);
  useEffect(() => {
    const sync = () => setPins(read());
    sync();
    window.addEventListener(EVT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(EVT, sync); window.removeEventListener("storage", sync); };
  }, []);
  const toggle = useCallback((p: Pin) => {
    const cur = read();
    const next = cur.some((x) => x.team === p.team) ? cur.filter((x) => x.team !== p.team) : [...cur, p].slice(-MAX);
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* 저장 불가(사생활 보호 모드)면 이번 화면에서만 */ }
    setPins(next);
    window.dispatchEvent(new Event(EVT));
  }, []);
  const isPinned = useCallback((team: string) => pins.some((x) => x.team === team), [pins]);
  return { pins, toggle, isPinned };
}
