"use client";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { getTracking, type TrackAlert, type Tracking } from "./api";
import { useShortlist } from "./shortlist";

// TRACKING — SHORTLIST(영입 후보) 소식 한 곳. Signals 맨 위 칸 · 팀 탭의 Inbox 숫자 · 작업대 카드가 같은 응답을 나눠 쓴다
// (세 곳이 따로 부르면 같은 계산을 세 번). 후보 목록이 같으면 5분 동안 같은 요청을 다시 쓰지 않는다.
const TTL = 5 * 60 * 1000;
const memo = new Map<string, { at: number; p: Promise<Tracking> }>();

function load(team: string, items: { player: string; club: string; league: string }[], lg?: string): Promise<Tracking> {
  const slim = items.map(({ player, club, league }) => ({ player, club, league }));
  const k = team + "|" + (lg ?? "") + "|" + JSON.stringify(slim);
  const hit = memo.get(k);
  if (hit && Date.now() - hit.at < TTL) return hit.p;
  // 한 번 다시 — 전체 홈은 무거운 요청과 같이 나가 서버가 깨는 중이면 프록시가 끊겼다(2026-10-23 QA '소식을 못 불러왔어요')
  const p = getTracking(team, slim, lg)
    .catch(() => new Promise<void>((r) => setTimeout(r, 8000)).then(() => getTracking(team, slim, lg)));
  memo.set(k, { at: Date.now(), p });
  p.catch(() => memo.delete(k));
  return p;
}

// 읽음 — INBOX 와 같은 방식(이 브라우저에만, 팀별)
const RKEY = (team: string) => `trk-read:${team}`;
const EVT = "trk-read-change";
const EMPTY = new Set<string>();
const rcache = new Map<string, { raw: string | null; val: Set<string> }>();

function readSet(team: string): Set<string> {
  if (!team) return EMPTY;
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(RKEY(team)); } catch { return EMPTY; }
  const hit = rcache.get(team);
  if (hit && hit.raw === raw) return hit.val;
  let val = EMPTY;
  try { val = raw ? new Set(JSON.parse(raw) as string[]) : EMPTY; } catch { val = EMPTY; }
  rcache.set(team, { raw, val });
  return val;
}

function writeSet(team: string, ids: Set<string>) {
  try { window.localStorage.setItem(RKEY(team), JSON.stringify([...ids].slice(-400))); } catch { /* 저장 못 해도 화면은 그대로 */ }
  window.dispatchEvent(new Event(EVT));
}

const NEW_DAYS = 7;
const recent = (d: string) => {
  if (!d) return true;                     // 날짜 없는 소식(이적 완료)은 읽을 때까지 NEW
  const t = Date.parse(d);
  return !Number.isNaN(t) && Date.now() - t <= NEW_DAYS * 86400000;
};

export const trackKey = (player: string, club: string) => `${player}|${club}`;

// league — 전체 홈 TRACKING 요약처럼 지금 리그가 아닌 팀(★ 내 팀)을 볼 때. 없으면 지금 리그
export function useTracking(team: string, league?: string) {
  const { items } = useShortlist(team);
  const [data, setData] = useState<Tracking | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!team || !items.length) { setData(null); setLoading(false); return; }
    let a = true;
    setLoading(true);
    load(team, items, league).then((d) => a && setData(d)).catch(() => a && setData(null)).finally(() => a && setLoading(false));
    return () => { a = false; };
  }, [team, items, league]);
  const read = useSyncExternalStore(
    (cb) => { window.addEventListener(EVT, cb); window.addEventListener("storage", cb); return () => { window.removeEventListener(EVT, cb); window.removeEventListener("storage", cb); }; },
    () => readSet(team), () => EMPTY);
  const isNew = useCallback((a: TrackAlert) => !read.has(a.id) && recent(a.date), [read]);
  const mark = useCallback((id: string) => { const cur = readSet(team); if (!cur.has(id)) writeSet(team, new Set([...cur, id])); }, [team]);
  const markAll = useCallback((ids: string[]) => writeSet(team, new Set([...readSet(team), ...ids])), [team]);
  const nNew = data ? data.alerts.filter(isNew).length : 0;
  return { items, data, loading, isNew, nNew, mark, markAll };
}
