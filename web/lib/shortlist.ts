"use client";
import { useCallback, useSyncExternalStore } from "react";

// SHORTLIST — 이적 작업대에 고정한 후보(팀별, 이 브라우저에만). 사실(OVR·이적료·계약)은 저장하지 않고
// 열 때마다 /api/workspace 가 다시 계산한다 — 저장해 두면 며칠 뒤 옛 숫자가 남는다.
export type ShortItem = { player: string; club: string; league: string; added: string };
const EVT = "shortlist-change";
const key = (team: string) => `shortlist:${team}`;
const EMPTY: ShortItem[] = [];
const cache = new Map<string, { raw: string | null; val: ShortItem[] }>();

function read(team: string): ShortItem[] {
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(key(team)); } catch { return EMPTY; }
  const hit = cache.get(team);
  if (hit && hit.raw === raw) return hit.val;           // 같은 배열을 돌려줘야 useSyncExternalStore 가 무한 갱신하지 않는다
  let val: ShortItem[] = EMPTY;
  try { val = raw ? (JSON.parse(raw) as ShortItem[]) : EMPTY; } catch { val = EMPTY; }
  cache.set(team, { raw, val });
  return val;
}

function write(team: string, items: ShortItem[]) {
  try { window.localStorage.setItem(key(team), JSON.stringify(items)); } catch { /* 저장 못 해도 화면은 그대로 */ }
  window.dispatchEvent(new Event(EVT));
}

export const MAX_SHORTLIST = 12;

export function useShortlist(team: string) {
  const items = useSyncExternalStore(
    (cb) => { window.addEventListener(EVT, cb); window.addEventListener("storage", cb); return () => { window.removeEventListener(EVT, cb); window.removeEventListener("storage", cb); }; },
    () => read(team), () => EMPTY);
  const has = useCallback((player: string, club: string) => items.some((x) => x.player === player && x.club === club), [items]);
  const toggle = useCallback((it: Omit<ShortItem, "added">) => {
    const cur = read(team);
    const on = cur.some((x) => x.player === it.player && x.club === it.club);
    write(team, on ? cur.filter((x) => !(x.player === it.player && x.club === it.club))
      : [...cur, { ...it, added: new Date().toISOString().slice(0, 10) }].slice(-MAX_SHORTLIST));
    return !on;
  }, [team]);
  const remove = useCallback((player: string, club: string) => write(team, read(team).filter((x) => !(x.player === player && x.club === club))), [team]);
  return { items, has, toggle, remove };
}
