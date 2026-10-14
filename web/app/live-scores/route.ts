import { NextResponse } from "next/server";

// 라이브 스코어 — ESPN scoreboard 를 Vercel 서버 라우트가 30초 캐시로 대신 받아 온다.
// Render 백엔드가 잠들어 있어도 화면은 실시간(설계도 '2 · 실시간' 단계). 일정·순위의 하루 갱신과 별개로,
// 화면은 경기 카드의 event_id(ESPN id)로 이 결과를 덮어써서 '진행 중 67'' · 'FT 3-4' 를 바로 보여 준다.
// (/api/* 는 백엔드로 프록시되므로 경로를 /live-scores 로 분리)
export const dynamic = "force-dynamic";

const CODES = [
  "eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "por.1", "ned.1", "bel.1",
  "uefa.champions", "uefa.europa", "uefa.europa.conf",
  "eng.fa", "eng.league_cup", "esp.copa_del_rey", "ita.coppa_italia", "ger.dfb_pokal", "fra.coupe_de_france",
];

type Side = { name: string; score: string | null; logo: string; winner: boolean };
export type LiveEvent = { id: string; comp: string; date: string; state: "pre" | "in" | "post"; detail: string; clock: string; home: Side; away: Side };

const ymd = (d: Date) => `${d.getUTCFullYear()}${String(d.getUTCMonth() + 1).padStart(2, "0")}${String(d.getUTCDate()).padStart(2, "0")}`;

async function board(code: string, date: string): Promise<LiveEvent[]> {
  const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${code}/scoreboard?dates=${date}`, { next: { revalidate: 30 } });
  if (!r.ok) return [];
  const j = await r.json();
  return (j.events ?? []).map((e: any) => {
    const c = e.competitions?.[0] ?? {};
    const side = (ha: string): Side => {
      const x = (c.competitors ?? []).find((t: any) => t.homeAway === ha) ?? {};
      return { name: x.team?.shortDisplayName ?? x.team?.displayName ?? "", score: x.score ?? null, logo: x.team?.logo ?? "", winner: !!x.winner };
    };
    return {
      id: String(e.id), comp: code, date: e.date, state: e.status?.type?.state ?? "pre",
      detail: e.status?.type?.shortDetail ?? "", clock: e.status?.displayClock ?? "", home: side("home"), away: side("away"),
    } as LiveEvent;
  });
}

export async function GET() {
  const now = new Date();
  // 한국 아침에 보면 유럽 경기는 UTC '어제' 저녁 — 어제·오늘 두 날짜
  const dates = [ymd(new Date(now.getTime() - 86400000)), ymd(now)];
  const jobs = CODES.flatMap((c) => dates.map((d) => board(c, d)));
  const res = await Promise.allSettled(jobs);
  const events: Record<string, LiveEvent> = {};
  for (const r of res) if (r.status === "fulfilled") for (const e of r.value) events[e.id] = e;
  return NextResponse.json(
    { updated: now.toISOString(), events },
    { headers: { "Cache-Control": "public, s-maxage=30, stale-while-revalidate=30" } },
  );
}
