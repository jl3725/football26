"use client";
import { createContext, useContext, useEffect, useState } from "react";

// 라이브 스코어 공급자 — /live-scores(Vercel 서버 라우트, ESPN 30초 캐시)를 주기적으로 받아 event_id → 상태.
// 진행 중 경기가 있으면 30초, 없으면 2분마다. 탭이 숨겨져 있으면 쉬었다가 돌아오면 바로 다시 받는다.
export type LiveSide = { name: string; score: string | null; logo: string; winner: boolean };
export type LiveEvent = { id: string; comp: string; date: string; state: "pre" | "in" | "post"; detail: string; clock: string; home: LiveSide; away: LiveSide };

const Ctx = createContext<Record<string, LiveEvent>>({});

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [map, setMap] = useState<Record<string, LiveEvent>>({});
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      let next = 120000;
      try {
        const r = await fetch("/live-scores", { cache: "no-store" });
        if (r.ok) {
          const j = await r.json();
          if (alive) setMap(j.events ?? {});
          if (Object.values(j.events ?? {}).some((e: any) => e.state === "in")) next = 30000;
        }
      } catch { /* 네트워크 오류 — 다음 주기에 다시 */ }
      if (alive && !document.hidden) timer = setTimeout(load, next);
    };
    const vis = () => { if (!document.hidden) { clearTimeout(timer); load(); } };
    load();
    document.addEventListener("visibilitychange", vis);
    return () => { alive = false; clearTimeout(timer); document.removeEventListener("visibilitychange", vis); };
  }, []);
  return <Ctx.Provider value={map}>{children}</Ctx.Provider>;
}

export const useLiveAll = () => useContext(Ctx);
export function useLive(id?: string | null): LiveEvent | undefined {
  const m = useContext(Ctx);
  return id ? m[id] : undefined;
}

// 화면 표기 — 진행 중: 'LIVE 67'' / 하프타임 'HT' / 종료: 'FT'
export function liveLabel(e: LiveEvent): string {
  if (e.state === "post") return /pen|aet/i.test(e.detail) ? e.detail : "FT";
  const d = e.detail || e.clock;
  return /half/i.test(d) || d === "HT" ? "HT" : (e.clock || d);
}
