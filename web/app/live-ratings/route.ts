import { NextResponse } from "next/server";
import type { JPPlayer, JPSide, JustPlayed } from "@/lib/justPlayed";

// 방금 경기 평점(JUST PLAYED) — 우리 팀의 진행 중·방금 끝난 경기를 FotMob 에서 찾아 선수별 실시간 평점을 준다.
// 경기 뒤 우리 데이터(OVR·LAST 5)에 들어가기까지 약 30분 — 그 사이 화면이 비지 않게(2026-10-29 사용자 '실시간 느낌').
// /live-scores 처럼 Vercel 이 직접 받아 Render 서버가 자고 있어도 된다. 팀 → FotMob 번호 표는 저장소의
// data/fotmob_team_ids.json(src/news_wires.fotmob_team_ids, 우리 클럽 표기 기준)을 GitHub 에서 6시간 캐시로.
//   GET /live-ratings?team=Arsenal → { match: null } | { match: {...}, players: [...] }
export const dynamic = "force-dynamic";

const UA = { "User-Agent": "Mozilla/5.0 (compatible; football26)" };
const IDS = "https://raw.githubusercontent.com/jl3725/football26/main/data/fotmob_team_ids.json";
const WINDOW_MS = 14 * 3600 * 1000;      // 킥오프 뒤 이만큼만 '방금 경기'(반영은 화면이 우리 데이터로 따로 판단)

const ymd = (d: Date) => `${d.getUTCFullYear()}${String(d.getUTCMonth() + 1).padStart(2, "0")}${String(d.getUTCDate()).padStart(2, "0")}`;
const clean = (s: unknown) => String(s ?? "").replace(/[‎‏]/g, "").replace("’", "'").trim();

async function teamIds(): Promise<Record<string, number>> {
  const r = await fetch(IDS, { next: { revalidate: 21600 } });
  return r.ok ? ((await r.json()).ids ?? {}) : {};
}

// /live-scores 와 같은 주소·같은 30초 캐시 — Vercel 데이터 캐시를 같이 쓴다
async function day(date: string): Promise<{ comp: string; m: any }[]> {
  const r = await fetch(`https://www.fotmob.com/api/data/matches?date=${date}&timezone=UTC`, { next: { revalidate: 30 }, headers: UA });
  if (!r.ok) return [];
  const j = await r.json();
  return (j.leagues ?? []).flatMap((lg: any) => (lg.matches ?? []).map((m: any) => ({ comp: String(lg.name ?? ""), m })));
}

// 선수 기록 묶음(Top stats·Attack…)을 제목 → 값 하나로(같은 항목이 여러 묶음에 겹친다 — src/fetch_fotmob_matches._stats 와 같은 규칙)
function flat(p: any): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const sec of p?.stats ?? []) for (const [t, s] of Object.entries<any>(sec?.stats ?? {})) if (!(t in out)) out[t] = s?.stat?.value ?? null;
  return out;
}

export async function GET(req: Request) {
  const team = new URL(req.url).searchParams.get("team") ?? "";
  const ids = await teamIds().catch(() => ({} as Record<string, number>));
  const tid = ids[team] ?? null;
  const none = (age: number) => NextResponse.json({ team, team_id: tid, match: null, players: [] } satisfies JustPlayed,
    { headers: { "Cache-Control": `public, s-maxage=${age}, stale-while-revalidate=${age}` } });
  if (!tid) return none(3600);

  const now = Date.now();
  // 한국 아침에 보면 유럽 경기는 UTC '어제' 저녁 — 어제·오늘 두 날짜
  const days = await Promise.allSettled([ymd(new Date(now - 86400000)), ymd(new Date(now))].map(day));
  const found = days.flatMap((d) => (d.status === "fulfilled" ? d.value : []))
    .filter(({ m }) => (m.home?.id === tid || m.away?.id === tid) && m.status?.started && !m.status?.cancelled)
    .filter(({ m }) => { const t = Date.parse(m.status?.utcTime ?? ""); return t <= now && now - t <= WINDOW_MS; })
    .sort((a, b) => Date.parse(b.m.status.utcTime) - Date.parse(a.m.status.utcTime));
  if (!found.length) return none(120);

  const { comp, m } = found[0];
  const live = !m.status?.finished;
  const r = await fetch(`https://www.fotmob.com/api/data/matchDetails?matchId=${m.id}`, { next: { revalidate: live ? 30 : 120 }, headers: UA });
  const j = r.ok ? await r.json() : {};
  const rev = new Map(Object.entries(ids).map(([k, v]) => [v, k]));
  const side = (t: any): JPSide => ({ id: Number(t?.id), name: String(t?.name ?? ""), score: t?.score ?? null, ours: rev.get(Number(t?.id)) ?? null });
  const players: JPPlayer[] = [];
  for (const [pid, p] of Object.entries<any>(j?.content?.playerStats ?? {})) {
    const s = flat(p);
    const rating = s["FotMob rating"] ?? null, minutes = s["Minutes played"] ?? null;
    if (rating == null && !minutes) continue;                  // 벤치·아직 안 뛴 선수
    players.push({ id: Number(p?.id ?? pid), name: String(p?.name ?? ""), team: Number(p?.teamId), rating, minutes,
      goals: Number(s["Goals"] ?? 0) || 0, assists: Number(s["Assists"] ?? 0) || 0, gk: !!p?.isGoalkeeper });
  }
  players.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  const st = m.status ?? {};
  const out: JustPlayed = {
    team, team_id: tid, players,
    match: { id: Number(m.id), kickoff: String(st.utcTime ?? ""), state: live ? "in" : "post", comp,
      clock: live ? clean(st.liveTime?.short) || "LIVE" : clean(st.reason?.short) || "FT", home: side(m.home), away: side(m.away) },
  };
  return NextResponse.json(out, { headers: { "Cache-Control": `public, s-maxage=${live ? 30 : 120}, stale-while-revalidate=60` } });
}
