"use client";
// 홈 리그 지도·리그 런처·사이드바 리그 목록이 함께 쓰는 리그 묶음 — 서버(/api/league-map)가 리그 수준으로 매긴 티어를 쓰고,
// 받기 전에는 lib/leagues.ts 의 기본값으로 같은 모양을 만든다(화면이 비지 않게). 한 페이지에서 한 번만 받는다.
import { useEffect, useState } from "react";
import { getLeagueMap, type LeagueMapData, type LeagueMapExports, type LeagueMapTop } from "./api";
import { LEAGUE_LIST, leagueInfo } from "./leagues";

export type MapLeague = {
  key: string; label: string; short: string; level: number;
  top: LeagueMapTop[]; exports: LeagueMapExports | null; subs: MapLeague[]; soon?: boolean;
};
export type MapGroups = Record<1 | 2 | 3, MapLeague[]>;

let cache: Promise<LeagueMapData> | null = null;

export function useLeagueMap(): LeagueMapData | null {
  const [d, setD] = useState<LeagueMapData | null>(null);
  useEffect(() => {
    let alive = true;
    cache = cache ?? getLeagueMap().catch((e) => { cache = null; throw e; });
    cache.then((x) => alive && setD(x)).catch(() => {});
    return () => { alive = false; };
  }, []);
  return d;
}

export function groupLeagues(d: LeagueMapData | null): MapGroups {
  const items = d?.leagues ?? LEAGUE_LIST.filter((l) => !l.soon).map((l) => ({
    key: l.key, name: l.name, tier: l.parent ? null : l.tier, parent: l.parent ?? null, level: 0, top: [], exports: null,
  }));
  const make = (key: string, name: string, level: number, top: LeagueMapTop[], exports: LeagueMapExports | null, soon = false): MapLeague => {
    const info = leagueInfo(key);
    return { key, label: info?.label ?? name.toUpperCase(), short: info?.short ?? name, level, top, exports, subs: [], soon };
  };
  const byKey = new Map(items.map((it) => [it.key, make(it.key, it.name, it.level, it.top, it.exports)]));
  const g: MapGroups = { 1: [], 2: [], 3: [] };
  // 티어 안에서는 리그 수준 순(같으면 등록 순)
  [...items].sort((a, b) => b.level - a.level).forEach((it) => {
    const m = byKey.get(it.key)!;
    const parent = it.parent ? byKey.get(it.parent) : undefined;
    if (parent) parent.subs.push(m);
    else if (it.tier) g[it.tier].push(m);
  });
  const soon = d?.soon ?? LEAGUE_LIST.filter((l) => l.soon).map((l) => ({ key: l.key, name: l.name, tier: 3 as const, exports: null }));
  soon.forEach((s) => g[3].push(make(s.key, s.name, 0, [], s.exports, true)));
  return g;
}

export const useLeagueGroups = (): MapGroups => groupLeagues(useLeagueMap());
