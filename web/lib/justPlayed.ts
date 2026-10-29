"use client";
import { useEffect, useState } from "react";
import { foldName, type PlayerDetail } from "./api";

// 방금 경기 평점(JUST PLAYED) — /live-ratings(Vercel 서버 라우트, FotMob 경기 평점)를 팀 단위로 받는다.
// 진행 중이면 30초, 끝났으면 2분, 경기가 없으면 5분마다. 탭이 숨겨져 있으면 쉬었다가 돌아오면 바로.
// 같은 팀을 여러 곳(선수 화면·경기 카드·PlayerPeek)이 보면 한 번만 받는다(25초 묶음).
// 우리 데이터(OVR·LAST 5)에 그 경기가 들어오면 화면은 이 값을 내리고 원래 값을 쓴다(reflected).
export type JPSide = { id: number; name: string; score: number | null; ours: string | null };
export type JPPlayer = { id: number; name: string; team: number; rating: number | null; minutes: number | null;
  goals: number; assists: number; gk: boolean };
export type JPMatch = { id: number; kickoff: string; state: "in" | "post"; clock: string; comp: string; home: JPSide; away: JPSide };
export type JustPlayed = { team: string; team_id: number | null; match: JPMatch | null; players: JPPlayer[] };

const MEMO = new Map<string, { at: number; p: Promise<JustPlayed | null> }>();

function load(team: string): Promise<JustPlayed | null> {
  const hit = MEMO.get(team);
  if (hit && Date.now() - hit.at < 25000) return hit.p;
  const p = fetch(`/live-ratings?team=${encodeURIComponent(team)}`, { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  MEMO.set(team, { at: Date.now(), p });
  return p;
}

export function useJustPlayed(team?: string | null, enabled = true): JustPlayed | null {
  const [v, setV] = useState<JustPlayed | null>(null);
  useEffect(() => {
    setV(null);
    if (!team || !enabled) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const x = await load(team);
      if (!alive) return;
      setV(x);
      const next = x?.match?.state === "in" ? 30000 : x?.match ? 120000 : 300000;
      if (!document.hidden) timer = setTimeout(tick, next);
    };
    const vis = () => { if (!document.hidden) { clearTimeout(timer); tick(); } };
    tick();
    document.addEventListener("visibilitychange", vis);
    return () => { alive = false; clearTimeout(timer); document.removeEventListener("visibilitychange", vis); };
  }, [team, enabled]);
  return v;
}

const lastName = (s: string) => foldName(s).split(/\s+/).pop() ?? "";

// 이 선수의 경기 기록 — FotMob 번호(서버 player_detail.fotmob_id)로, 번호가 없으면 이름(같은 팀에서 이름 같음 → 성이 같은 한 명)
export function findPlayer(jp: JustPlayed | null, who: { fotmob_id?: number | null; player: string }): JPPlayer | null {
  if (!jp?.match) return null;
  if (who.fotmob_id) return jp.players.find((p) => p.id === who.fotmob_id) ?? null;
  const mine = jp.players.filter((p) => p.team === jp.team_id);
  const f = foldName(who.player);
  const exact = mine.find((p) => foldName(p.name) === f);
  if (exact) return exact;
  const sur = mine.filter((p) => lastName(p.name) === lastName(who.player));
  return sur.length === 1 ? sur[0] : null;
}

// 우리 데이터에 이미 들어왔나 — SEASON LOG(출전 경기)나 LAST 5 에 킥오프 ±36시간 안 경기가 있으면(시간이 아니라 데이터 기준)
export function reflected(jp: JustPlayed | null, d: Pick<PlayerDetail, "season_log" | "recent">): boolean {
  if (!jp?.match || jp.match.state !== "post") return false;
  const t = Date.parse(jp.match.kickoff);
  const near = (date: string) => Math.abs(Date.parse(`${date.slice(0, 10)}T12:00:00Z`) - t) <= 36 * 3600 * 1000;
  return (d.season_log?.matches ?? []).some((m) => m.minutes > 0 && near(m.date)) || (d.recent?.matches ?? []).some((m) => near(m.date));
}

// 팀 안 평점 순위(같으면 공동)
export function teamRank(jp: JustPlayed, p: JPPlayer): { rank: number; tie: boolean } | null {
  if (p.rating == null) return null;
  const xs = jp.players.filter((x) => x.team === p.team && x.rating != null);
  return { rank: 1 + xs.filter((x) => (x.rating as number) > (p.rating as number)).length,
    tie: xs.filter((x) => x.rating === p.rating).length > 1 };
}

export const sideName = (s: JPSide) => s.ours ?? s.name;
