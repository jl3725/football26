"use client";
import { useEffect, useState } from "react";
import { getTeamSeason, type PointsPath, type ProfileAxis, type ResultMatch, type TeamSeason } from "@/lib/api";
import { compLabel, compTone, lgEn, liftHex, splitKst } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";
import { Crest } from "./MatchCard";
import SectionHead from "./SectionHead";
import { Skel } from "./Skeleton";

// 팀 Overview 상단 — '지금 이 팀이 어떤가'. /api/team-season(30분 캐시)
//   SEASON SNAPSHOT: 순위·승점·득실·xG + 누적 승점 흐름(1위·4위 비교선) + 최근 5경기(누르면 경기 리뷰)
//   SEASON PROFILE : 경기 내용 지수(50=리그 평균)를 리그 순위·근거 숫자와 함께 — 레이더 숫자만으론 오해가 생겼다

export function useTeamSeason(team: string, league: string) {
  const [d, setD] = useState<TeamSeason | null | undefined>(undefined);
  useEffect(() => {
    let a = true; setD(undefined);
    getTeamSeason(team, league).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team, league]);
  return d;
}

// 누적 승점 흐름 — 우리 팀(굵게) vs 1위·4위(점선)
export function useNarrow(q = "(max-width: 640px)") {
  const [n, setN] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(q);
    const f = () => setN(m.matches);
    f(); m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, [q]);
  return n;
}

function PointsChart({ me, refs, color }: { me: PointsPath; refs: PointsPath[]; color: string }) {
  // 폰에선 그림을 좁게 그려(viewBox) 글자가 6px 로 줄어들지 않게
  const narrow = useNarrow();
  const W = narrow ? 340 : 560, H = narrow ? 180 : 190, L = 26, R = narrow ? 96 : 120, T = 12, B = 24;
  const all = [me, ...refs].filter((p) => p.path.length);
  const n = Math.max(1, ...all.map((p) => p.path.length));
  const max = Math.max(3, ...all.map((p) => p.path[p.path.length - 1] ?? 0));
  const x = (i: number) => L + (n === 1 ? 0 : (i / (n - 1)) * (W - L - R));
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const line = (p: number[]) => p.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const ticks = Array.from(new Set([0, Math.round(max / 2), max]));
  // 끝 라벨이 겹치지 않게 아래로 밀기
  const ends = all.map((p) => ({ t: p.team, y: y(p.path[p.path.length - 1] ?? 0) })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 15) ends[k].y = ends[k - 1].y + 15;
  const endY: Record<string, number> = Object.fromEntries(ends.map((e) => [e.t, e.y]));
  return (
    <svg className="ts5-chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`${me.team} 누적 승점 ${me.path[me.path.length - 1] ?? 0}점, ${refs.map((r) => `${r.label} ${r.team} ${r.path[r.path.length - 1] ?? 0}점`).join(", ")}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="ts5-gl" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" className="ts5-tick">{t}</text>
        </g>
      ))}
      <text x={L} y={H - 6} className="ts5-tick">1R</text>
      <text x={W - R} y={H - 6} textAnchor="end" className="ts5-tick">{n}R</text>
      {refs.map((r) => r.path.length > 0 && (
        <g key={r.team} className="ts5-ref">
          <path d={line(r.path)} />
          <text x={x(r.path.length - 1) + 8} y={endY[r.team] + 4}>{r.label} {r.team.split(" ").slice(-1)[0]} {r.path[r.path.length - 1]}</text>
        </g>
      ))}
      {me.path.length > 0 && (
        <g>
          <path d={line(me.path)} className="ts5-me" style={{ stroke: color }} />
          {me.path.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={i === me.path.length - 1 ? 4.5 : 2.5} style={{ fill: color }} />)}
          <text x={x(me.path.length - 1) + 8} y={endY[me.team] + 4} className="ts5-me-t" style={{ fill: color }}>{me.path[me.path.length - 1]}점</text>
        </g>
      )}
    </svg>
  );
}

function RecentRow({ m, team }: { m: ResultMatch; team: string }) {
  const preview = useMatchPreview();
  const home = m.home.team === team;
  const me = home ? m.home : m.away, op = home ? m.away : m.home;
  const res = me.goals > op.goals ? "W" : me.goals < op.goals ? "L" : "D";
  return (
    <button className="ts5-res" onClick={() => preview?.(m)} disabled={!m.event_id} title="경기 리뷰 보기">
      <i className={`ts5-wdl ${res}`}>{res}</i>
      <span className="ts5-op"><Crest s={op} size={20} /><b>{op.team}</b><em>{home ? "H" : "A"}</em></span>
      <span className={`bdg ${compTone(m.comp_code)} ts5-comp`}>{compLabel(m)}</span>
      <b className="ts5-score">{me.goals}–{op.goals}</b>
      <em className="ts5-date">{splitKst(m.kst).date}</em>
    </button>
  );
}

export function SeasonSnapshot({ d, team, league, color }: { d: TeamSeason | null | undefined; team: string; league: string; color: string }) {
  const c = liftHex(color || "#e0475b");
  if (d === undefined) return <section className="card h5-card"><Skel h={260} r={12} /></section>;
  if (!d || !d.standing) return null;
  const s = d.standing;
  const lead = d.refs.find((r) => r.label === "1위");
  const gap = lead ? (lead.path[lead.path.length - 1] ?? 0) - s.points : 0;
  return (
    <section className="card h5-card ts5">
      <SectionHead title="SEASON SNAPSHOT" kr="이번 시즌 현황" meta={`${lgEn(league)} · 리그 ${s.played}경기`} />
      <div className="ts5-grid">
        <div className="ts5-main">
          <div className="ts5-kpis">
            <div><em>POSITION</em><b>{s.rank}<small>/{d.n}</small></b><span>{s.rank === 1 ? "선두" : `1위와 ${gap}점 차`}</span></div>
            <div><em>POINTS</em><b>{s.points}</b><span>{s.won}승 {s.drawn}무 {s.lost}패</span></div>
            <div><em>GOALS</em><b>{s.gf}<small>:{s.ga}</small></b><span>득실 {s.gd > 0 ? `+${s.gd}` : s.gd}</span></div>
            <div><em>xG / GAME</em><b>{d.xg_pg != null ? d.xg_pg.toFixed(2) : "—"}</b><span>{d.str_rank ? `전력 ${d.str_rank}위` : "경기당 기대 득점"}</span></div>
          </div>
          <PointsChart me={d.path} refs={d.refs} color={c} />
          <p className="ts5-note">누적 승점 흐름 · 점선 = 1위·4위(챔피언스리그권) 팀</p>
        </div>
        <div className="ts5-recent">
          <div className="ts5-sub">LAST 5 <span>최근 5경기 · 전 대회 · 누르면 경기 리뷰</span></div>
          {d.recent.length ? d.recent.map((m, i) => <RecentRow key={m.event_id ?? i} m={m} team={team} />)
            : <p className="pv-empty">최근 경기 기록 없음</p>}
        </div>
      </div>
    </section>
  );
}

export function SeasonProfile({ axes }: { axes: ProfileAxis[] }) {
  if (!axes.length) return <p className="pv-empty">시즌 경기 기록이 아직 부족합니다</p>;
  return (
    <div className="sp5">
      {axes.map((a) => {
        const third = a.rank <= Math.ceil(a.n / 3) ? "top" : a.rank > a.n - Math.ceil(a.n / 3) ? "low" : "mid";
        return (
          <div className={`sp5-row ${third}`} key={a.key}>
            <div className="sp5-l"><b>{a.en}</b><span>{a.kr}{a.hint ? ` · ${a.hint}` : ""}</span></div>
            <div className="sp5-bar" title="50 = 리그 평균"><i /><span style={{ width: `${Math.max(3, a.value)}%` }} /></div>
            <div className="sp5-v"><b>{a.value}</b><em>{a.rank}위<small>/{a.n}</small></em></div>
          </div>
        );
      })}
      <p className="sp5-note">리그 안 상대 지수(50 = 리그 평균, 가운데 선) · 시즌 초에는 표본이 적어 50 쪽으로 보정됩니다.</p>
    </div>
  );
}
