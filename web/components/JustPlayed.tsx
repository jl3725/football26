"use client";
// JUST PLAYED — 경기 중·방금 끝난 경기의 FotMob 평점을 우리 데이터(OVR·LAST 5)에 들어오기 전까지 바로 보여 준다.
// 2026-10-29 사용자 '실시간 느낌' — 경기 뒤 반영까지 약 30분, 그 사이 선수 화면·경기 카드가 비지 않게. 평가 문장 없이 사실만
// (점수·평점·골·도움·출전 분·팀 내 순위), 해석은 반영 뒤 SCOUT TAKE. 원천: web/app/live-ratings(Vercel → FotMob, Render 무관).
import type { Fixture, PlayerDetail } from "@/lib/api";
import type { LiveEvent } from "@/lib/live";
import { useJustPlayed, findPlayer, reflected, teamRank, sideName, type JustPlayed, type JPPlayer } from "@/lib/justPlayed";
import { ssMeaning } from "@/lib/meaning";
import { fmToSs } from "./FormPair";
import type { PeekReq } from "./PlayerPeek";
import Info from "./Info";

const tone = (r: number | null) => ssMeaning(r != null ? fmToSs(r) : null);

// 이 선수의 방금 경기 — 보여 줄 게 없으면 null(경기 없음·출전 안 함·이미 반영)
function usePlayerJP(d: PlayerDetail | null) {
  const jp = useJustPlayed(d?.team ?? null, !!d);
  if (!d || !jp?.match) return null;
  const p = findPlayer(jp, { fotmob_id: d.fotmob_id, player: d.player });
  if (!p || (p.rating == null && !p.minutes) || reflected(jp, d)) return null;
  return { jp, p, m: jp.match };
}

function Score({ jp }: { jp: JustPlayed }) {
  const m = jp.match!;
  return (
    <span className="jp5-score">
      {sideName(m.home)} <b>{m.home.score ?? 0}–{m.away.score ?? 0}</b> {sideName(m.away)}
      <em className={m.state === "in" ? "in" : ""}>{m.state === "in" ? m.clock : "FT"}</em>
    </span>
  );
}

export default function JustPlayedStrip({ d }: { d: PlayerDetail }) {
  const x = usePlayerJP(d);
  if (!x) return null;
  const { jp, p, m } = x;
  const live = m.state === "in";
  const rk = teamRank(jp, p);
  const t = tone(p.rating);
  return (
    <section className={`jp5 ${live ? "live" : "ft"}`} aria-label={live ? "경기 중 실시간 평점" : "방금 끝난 경기 평점"}>
      <div className="jp5-h">
        {live && <i className="live-dot" aria-hidden="true" />}
        <b>{live ? "LIVE" : "JUST PLAYED"}</b>
        <span>{live ? "실시간 평점" : "방금 경기"}{m.comp ? ` · ${m.comp}` : ""}</span>
        <Info label="방금 경기 기준">
          <p><b>FotMob 경기 평점</b> — 경기 중 30초마다, 끝난 뒤 2분마다 받는 값.</p>
          <p>OVR·LAST 5·SEASON LOG 에는 경기 약 30분 뒤 반영되고, 반영되면 이 줄은 사라집니다.</p>
        </Info>
      </div>
      <div className="jp5-m">
        <Score jp={jp} />
        {p.rating != null && (
          <span className="jp5-rt" title={`FotMob ${p.rating.toFixed(1)} · ${t.label}`}>
            <small>평점</small><b style={{ color: t.c, background: t.bg }}>{p.rating.toFixed(1)}</b>
          </span>
        )}
      </div>
      <div className="jp5-chips">
        {p.goals > 0 && <span className="good">{p.goals}골</span>}
        {p.assists > 0 && <span className="good">{p.assists}도움</span>}
        {rk && rk.rank <= 3 && <span>팀 내 평점 {rk.tie ? "공동 " : ""}{rk.rank}위</span>}
        {!live && p.minutes ? <span>{p.minutes}′</span> : null}
      </div>
      {!live && <p className="jp5-note">OVR·LAST 5 반영 전 — 경기 약 30분 뒤 자동 반영</p>}
    </section>
  );
}

// PlayerPeek 한 줄 — 'LIVE 67' · 평점 7.6 · 1골' / '방금 경기 · Arsenal 2–0 Crystal Palace · 평점 8.4'
export function JustPlayedLine({ d }: { d: PlayerDetail | null }) {
  const x = usePlayerJP(d);
  if (!x) return null;
  const { p, m } = x;
  const live = m.state === "in";
  const t = tone(p.rating);
  const ga = [p.goals ? `${p.goals}골` : "", p.assists ? `${p.assists}도움` : ""].filter(Boolean).join(" ");
  return (
    <div className={`peek-jp${live ? " live" : ""}`}>
      <span>{live ? <><i className="live-dot" aria-hidden="true" />LIVE {m.clock}</> : "JUST PLAYED"}</span>
      <p>
        {sideName(m.home)} {m.home.score ?? 0}–{m.away.score ?? 0} {sideName(m.away)}
        {p.rating != null && <> · 평점 <b style={{ color: t.c }}>{p.rating.toFixed(1)}</b></>}
        {ga && <> · {ga}</>}
      </p>
    </div>
  );
}

// 경기 카드 — 진행 중·종료 경기의 평점 상위 3명(양 팀). 경기 전 카드는 받지 않는다
export function useTopRated(m: Fixture, lv?: LiveEvent): { jp: JustPlayed; top: JPPlayer[] } | null {
  const played = !!lv && lv.state !== "pre";
  const team = m.home.league ? m.home.team : m.away.league ? m.away.team : null;
  const jp = useJustPlayed(team, played);
  if (!played || !jp?.match) return null;
  if (Math.abs(Date.parse(jp.match.kickoff) - Date.parse(m.kickoff)) > 3 * 3600 * 1000) return null;   // 다른 경기
  const top = jp.players.filter((p) => p.rating != null).slice(0, 3);
  return top.length ? { jp, top } : null;
}

// onPeek = usePeek() — PlayerPeek 이 JustPlayedLine 을 불러 쓰므로 여기서 PlayerPeek 을 직접 부르지 않는다(순환 import)
export function TopRated({ jp, top, onPeek }: { jp: JustPlayed; top: JPPlayer[];
  onPeek?: (e: React.MouseEvent, req: PeekReq) => void }) {
  const m = jp.match!;
  const sideOf = (tid: number) => (tid === m.home.id ? m.home : m.away);
  return (
    <div className="tr5" onClick={(e) => e.stopPropagation()}>
      <div className="tr5-h"><b>TOP RATED</b><span>{m.state === "in" ? "실시간 평점" : "경기 평점"} · FotMob</span></div>
      {top.map((p, i) => {
        const s = sideOf(p.team);
        const t = tone(p.rating);
        const ga = [p.goals ? `${p.goals}G` : "", p.assists ? `${p.assists}A` : ""].filter(Boolean).join(" ");
        return (
          <button className="tr5-row" key={p.id} disabled={!s.ours || !onPeek} title={s.ours ? `${p.name} 선수 카드` : p.name}
            onClick={(e) => { e.stopPropagation(); if (s.ours) onPeek?.(e, { name: p.name, club: s.ours }); }}>
            <span className="tr5-n">{i + 1}</span>
            <span className="tr5-who">{p.name}<small>{sideName(s)}</small></span>
            <span className="tr5-ev">{ga}</span>
            <b style={{ color: t.c, background: t.bg }}>{(p.rating as number).toFixed(1)}</b>
          </button>
        );
      })}
    </div>
  );
}
