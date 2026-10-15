"use client";
import { createContext, useContext, useEffect, useState } from "react";
import type { Fixture } from "./api";

// 라이브 스코어 공급자 — /live-scores(Vercel 서버 라우트, ESPN 30초 캐시)를 주기적으로 받아 event_id → 상태.
// 진행 중 경기가 있으면 30초, 없으면 2분마다. 탭이 숨겨져 있으면 쉬었다가 돌아오면 바로 다시 받는다.
export type LiveSide = { name: string; score: string | null; logo: string; winner: boolean; color?: string };
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

// 일정 파일에 아직 없는 경기(라이브 띠에만 있는 경기)를 매치 서랍에 열 때 쓰는 최소 Fixture — 우리 리그 정보 없음
const WD = ["일", "월", "화", "수", "목", "금", "토"];
export function fixtureFromLive(e: LiveEvent): Fixture {
  const t = new Date(Date.parse(e.date) + 9 * 3600 * 1000);   // KST 표기(UTC 기준 날짜 함수로 읽는다)
  const hh = String(t.getUTCHours()).padStart(2, "0"), mm = String(t.getUTCMinutes()).padStart(2, "0");
  const side = (s: LiveSide) => ({ team: s.name, league: null, rank: null, points: null, logo: s.logo, color: s.color || "#8a94a8", ovr: null, form: [] });
  return {
    event_id: e.id, comp_code: e.comp, comp: e.comp, kickoff: e.date, date: t.toISOString().slice(0, 10),
    kst: `${t.getUTCMonth() + 1}/${t.getUTCDate()}(${WD[t.getUTCDay()]}) ${hh}:${mm}`, d_day: 0,
    home: side(e.home), away: side(e.away), big: 0, tags: [],
  };
}
