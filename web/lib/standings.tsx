"use client";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { Fixture, FixtureSide, TableRow } from "./api";
import { liveLabel, useLiveAll } from "./live";
import { liveTable, type LiveTableRow } from "./liveTable";
import { LEAGUES_ACTIVE } from "./leagues";

// 잠정 순위 한 곳 — 화면의 모든 순위·승점 표시(왼쪽 사이드바 · 팀 헤더 · 경기 카드 · 매치 프리뷰)가 이 공급자를 쓴다.
// 공식 순위표(매일 아침 match_refresh) + 아직 결과 파일에 없는 리그 경기(/api/standings-live)에 라이브 스코어(ESPN)를 더한다.
// 예전엔 몇몇 카드만 라이브였고 사이드바 순위는 다음 날 아침까지 그대로였다(2026-10-19 사용자: '적용할 때 영향 있는 곳은 일괄로').
// 새 화면에서 순위·승점을 보여 줄 때도 서버 값을 그대로 쓰지 말고 useStandings(league)·useLiveFixture(m) 를 거칠 것.
export const LEAGUE_OF_CODE: Record<string, string> = Object.fromEntries(LEAGUES_ACTIVE.map((l) => [l.espn, l.key]));
type Inputs = { table: TableRow[]; pending: Record<string, { home: string; away: string }> };
export type Standings = { rows: LiveTableRow[]; on: boolean; inPlay: boolean; byTeam: Map<string, LiveTableRow> };
const EMPTY: Standings = { rows: [], on: false, inPlay: false, byTeam: new Map() };

const cache = new Map<string, { at: number; p: Promise<Inputs> }>();
function load(league: string): Promise<Inputs> {
  const c = cache.get(league);
  if (c && Date.now() - c.at < 5 * 60_000) return c.p;
  const p = fetch(`/api/standings-live?league=${encodeURIComponent(league)}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
  p.catch(() => cache.delete(league));
  cache.set(league, { at: Date.now(), p });
  return p;
}

const Ctx = createContext<Record<string, Standings>>({});

export function StandingsProvider({ children }: { children: React.ReactNode }) {
  const live = useLiveAll();
  // 리그 경기가 진행 중이거나 막 끝난 리그만 받는다(평소엔 요청 없음 — Render 무료 서버 부담)
  const active = useMemo(() => [...new Set(Object.values(live).filter((e) => e.state !== "pre")
    .map((e) => LEAGUE_OF_CODE[e.comp]).filter(Boolean))].sort(), [live]);
  const key = active.join(",");
  const [inp, setInp] = useState<Record<string, Inputs>>({});
  useEffect(() => {
    let a = true;
    for (const lg of active) load(lg).then((d) => { if (a) setInp((p) => (p[lg] === d ? p : { ...p, [lg]: d })); }).catch(() => {});
    return () => { a = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const value = useMemo(() => {
    const out: Record<string, Standings> = {};
    for (const [lg, d] of Object.entries(inp)) {
      const lt = liveTable(d.table, d.pending, live, liveLabel);
      out[lg] = { ...lt, byTeam: new Map(lt.rows.map((r) => [r.team, r])) };
    }
    return out;
  }, [inp, live]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** 리그 잠정 순위(라이브 반영이 없으면 on=false — 공식 값 그대로 쓰면 된다). */
export function useStandings(league?: string | null): Standings {
  const all = useContext(Ctx);
  return (league && all[league]) || EMPTY;
}

/** 팀 한 줄 — 라이브로 바뀐 순위·승점(없으면 undefined). */
export function useLiveRow(team?: string | null, league?: string | null): LiveTableRow | undefined {
  const st = useStandings(league);
  return st.on && team ? st.byTeam.get(team) : undefined;
}

function overlay(s: FixtureSide, all: Record<string, Standings>): FixtureSide {
  const st = s.league ? all[s.league] : undefined;
  const r = st?.on ? st.byTeam.get(s.team) : undefined;
  if (!r) return s;
  // 최근 결과는 끝난 경기(FT)만 붙인다 — 진행 중 스코어를 W/L 로 굳혀 보이지 않게
  return { ...s, rank: r.rank, points: r.points, form: r.live?.state === "post" ? r.form : s.form };
}

/** 경기 카드 두 팀의 순위·승점을 잠정 순위로. */
export function useLiveFixture<T extends Fixture | null | undefined>(m: T): T {
  const all = useContext(Ctx);
  return useMemo(() => (m ? { ...m, home: overlay(m.home, all), away: overlay(m.away, all) } : m), [m, all]) as T;
}

/** 여러 팀(리그 섞임) — 순위·승점만 덮어쓴다. */
export function useLiveSides() {
  const all = useContext(Ctx);
  return (s: FixtureSide) => overlay(s, all);
}
