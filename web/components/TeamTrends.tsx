"use client";
import { rankMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import { useEffect, useRef, useState } from "react";
import { getTeamTrends, type TeamTrends, type TrendMatch, type TrendPct } from "@/lib/api";
import { liftHex } from "@/lib/match";
import SectionHead from "./SectionHead";
import { Skel } from "./Skeleton";
import { useNarrow } from "./TeamSeason";

// 분석 탭 상단 — 실제 분석가가 먼저 보는 세 가지(/api/team-trends, 1시간 캐시)
//   MATCH TRENDS     : 경기별 xG(5대 리그 리그 경기) 또는 슈팅 득·실 + 실제 득실, 최근 5경기 이동 평균
//   LEAGUE PERCENTILE: 리그 경기 기준 경기당 평균을 리그 팀들과 비교(높을수록 좋은 쪽으로 정렬된 백분위)
//   GOAL TIMING      : 15분 단위 득점·실점(전 대회)

export function useTeamTrends(team: string) {
  const [d, setD] = useState<TeamTrends | null | undefined>(undefined);
  useEffect(() => {
    let a = true; setD(undefined);
    getTeamTrends(team).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team]);
  return d;
}

const COMP_SHORT: Record<string, string> = { "uefa.champions": "UCL", "uefa.europa": "UEL", "uefa.europa.conf": "UECL" };
const compShort = (c: string) => (c.endsWith(".1") ? "" : COMP_SHORT[c] ?? "CUP");

// 경기별 막대 — 위쪽 = 우리 팀(xG 또는 슈팅), 아래쪽 = 상대. 점 = 실제 득·실점. 선 = 최근 5경기 이동 평균
function MatchTrendChart({ ms, useXg, color }: { ms: TrendMatch[]; useXg: boolean; color: string }) {
  const val = (m: TrendMatch, mine: boolean) => (useXg ? (mine ? m.xg : m.xga) : (mine ? m.shots : m.opp_shots));
  const rows = ms.filter((m) => val(m, true) != null && val(m, false) != null);
  const narrow = useNarrow();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (box.current) box.current.scrollLeft = box.current.scrollWidth; }, [rows.length, narrow]);   // 최신 경기부터 보이게
  if (rows.length < 2) return <p className="pv-empty">경기 기록이 아직 부족합니다</p>;
  // 데스크톱: 최소 폭 960(경기가 적어도 글자가 커지지 않게), 많으면 경기당 44 + 가로 스크롤
  // 폰: 경기당 56 단위로 그려 한 화면에 5~6경기, 넘치면 가로 스크롤(끝 = 최신)
  const W = narrow ? Math.max(340, rows.length * 56) : Math.max(960, rows.length * 44), H = 272, L = 44, R = 10, mid = 122, half = 92;
  const max = Math.max(useXg ? 2 : 15, ...rows.flatMap((m) => [val(m, true)!, val(m, false)!, useXg ? m.gf : 0, useXg ? m.ga : 0]));
  const bw = (W - L - R) / rows.length;
  const h = (v: number) => (v / max) * half;
  const roll = (mine: boolean) => rows.map((_, i) => {
    const w = rows.slice(Math.max(0, i - 4), i + 1).map((m) => val(m, mine)!);
    return w.reduce((a, b) => a + b, 0) / w.length;
  });
  const rf = roll(true), ra = roll(false);
  const path = (arr: number[], up: boolean) => arr.map((v, i) => `${i ? "L" : "M"}${(L + bw * i + bw / 2).toFixed(1)},${(up ? mid - h(v) : mid + h(v)).toFixed(1)}`).join(" ");
  const unit = useXg ? "xG" : "슈팅";
  return (
    <div className="tt5-scroll" ref={box}>
      <svg className="tt5-chart" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: narrow ? W : Math.min(W, 900) }} role="img"
        aria-label={`경기별 ${unit} 득·실, 최근 5경기 평균 득 ${rf[rf.length - 1].toFixed(2)} 실 ${ra[ra.length - 1].toFixed(2)}`}>
        <line x1={L} x2={W - R} y1={mid} y2={mid} className="tt5-axis" />
        <text x={4} y={mid - half + 8} className="tt5-tick">{useXg ? max.toFixed(1) : Math.round(max)}</text>
        <text x={4} y={mid - 4} className="tt5-tick">{unit} 득</text>
        <text x={4} y={mid + 14} className="tt5-tick">{unit} 실</text>
        {rows.map((m, i) => {
          const x = L + bw * i, f = val(m, true)!, a = val(m, false)!;
          return (
            <g key={m.event_id}>
              <title>{`${m.date} ${m.home_away === "H" ? "vs" : "@"} ${m.opponent} ${m.gf}-${m.ga} · ${unit} ${f.toFixed(useXg ? 2 : 0)} : ${a.toFixed(useXg ? 2 : 0)}`}</title>
              <rect x={x + bw * 0.18} y={mid - h(f)} width={bw * 0.64} height={Math.max(1, h(f))} rx={3} style={{ fill: color }} className="tt5-for" />
              <rect x={x + bw * 0.18} y={mid} width={bw * 0.64} height={Math.max(1, h(a))} rx={3} className="tt5-ag" />
              {useXg && <circle cx={x + bw / 2} cy={mid - h(m.gf)} r={3.6} className="tt5-goal" />}
              {useXg && <circle cx={x + bw / 2} cy={mid + h(m.ga)} r={3.6} className="tt5-goal ag" />}
              <text x={x + bw / 2} y={H - 24} textAnchor="middle" className={`tt5-res ${m.result}`}>{m.gf}-{m.ga}</text>
              <text x={x + bw / 2} y={H - 8} textAnchor="middle" className="tt5-op">{compShort(m.comp_code) || m.opponent.split(" ")[0].slice(0, 6)}</text>
            </g>
          );
        })}
        <path d={path(rf, true)} className="tt5-roll" style={{ stroke: color }} />
        <path d={path(ra, false)} className="tt5-roll ag" />
      </svg>
    </div>
  );
}

function fmtV(p: TrendPct) {
  return p.fmt === "pct" ? `${p.value.toFixed(1)}%` : p.fmt === "f1" ? p.value.toFixed(1) : p.value.toFixed(2);
}

function Percentiles({ ps }: { ps: TrendPct[] }) {
  return (
    <div className="lp5">
      {ps.map((p) => {
        const mn = rankMeaning(p.rank, p.n);   // 20팀 리그에서 '상위 1%' 보다 '리그 최상위'가 자연스럽다
        const avg = p.fmt === "pct" ? `${p.league_avg.toFixed(1)}%` : String(p.league_avg);
        return (
          <div className={`lp5-row t-${mn.tone}`} key={p.key} title={`리그 평균 ${avg} · 리그 ${p.rank}위/${p.n}`}>
            <div className="lp5-l"><b>{p.en}</b><span>{p.kr} · 리그 평균 {avg}</span></div>
            <div className="lp5-bar"><i /><span style={{ width: `${Math.max(3, p.pct)}%`, background: mn.bar }} /></div>
            <div className="lp5-v"><b style={{ color: mn.c }}>{fmtV(p)}</b><MeaningTag m={mn} sm /><em>{p.rank}위<small>/{p.n}</small></em></div>
          </div>
        );
      })}
    </div>
  );
}

function GoalTiming({ t, color }: { t: NonNullable<TeamTrends["timing"]>; color: string }) {
  const max = Math.max(1, ...t.scored, ...t.conceded);
  const tot = (a: number[]) => a.reduce((x, y) => x + y, 0);
  const late = t.scored[5] + t.conceded[5] ? `76분 이후 ${t.scored[5]}득 ${t.conceded[5]}실` : "";
  return (
    <div className="gt5">
      {t.buckets.map((b, i) => (
        <div className="gt5-col" key={b}>
          <div className="gt5-up"><span style={{ height: `${(t.scored[i] / max) * 100}%`, background: color }} /><b>{t.scored[i] || ""}</b></div>
          <div className="gt5-lb">{b}{i === 2 || i === 5 ? "+" : ""}</div>
          <div className="gt5-dn"><span style={{ height: `${(t.conceded[i] / max) * 100}%` }} /><b>{t.conceded[i] || ""}</b></div>
        </div>
      ))}
      <p className="gt5-note">위 = 득점 {tot(t.scored)} · 아래 = 실점 {tot(t.conceded)} · 전 대회 {t.games}경기{late ? ` · ${late}` : ""}</p>
    </div>
  );
}

export default function TeamTrendsBoard({ team, color }: { team: string; color: string }) {
  const d = useTeamTrends(team);
  const c = liftHex(color || "#e0475b");
  const [mode, setMode] = useState<"xg" | "shots">("xg");
  if (d === undefined) return <section className="card h5-card" style={{ marginTop: 16 }}><Skel h={260} r={12} /></section>;
  if (!d || !d.available) return null;
  const useXg = d.has_xg && mode === "xg";
  const lgOnly = d.matches.filter((m) => m.comp_code.endsWith(".1"));
  const xgMs = d.matches.filter((m) => m.xg != null);
  const sum = (a: (number | null)[]) => a.reduce<number>((x, y) => x + (y ?? 0), 0);
  const xgDiff = xgMs.length ? sum(xgMs.map((m) => m.gf)) - sum(xgMs.map((m) => m.xg)) : null;
  return (
    <>
      <section className="card h5-card" style={{ marginTop: 16 }}>
        <SectionHead title="MATCH TRENDS" kr="경기별 흐름"
          meta={useXg ? "막대 = xG(리그 경기·Understat) · 점 = 실제 골 · 선 = 최근 5경기 평균" : "막대 = 슈팅(ESPN) · 선 = 최근 5경기 평균"}
          right={d.has_xg ? (
            <div className="seg5 seg5-head">
              <button className={mode === "xg" ? "on" : ""} onClick={() => setMode("xg")}>xG</button>
              <button className={mode === "shots" ? "on" : ""} onClick={() => setMode("shots")}>SHOTS</button>
            </div>) : null} />
        <MatchTrendChart ms={useXg ? xgMs : d.matches} useXg={useXg} color={c} />
        {useXg && xgDiff != null && (
          <p className="tt5-note">
            리그 {xgMs.length}경기 실제 득점 − xG = <b className={xgDiff >= 0 ? "up" : "down"}>{xgDiff >= 0 ? "+" : ""}{xgDiff.toFixed(1)}</b>
            {Math.abs(xgDiff) >= 2 ? (xgDiff > 0 ? " — 기대보다 많이 넣는 중(결정력·운이 좋음)" : " — 기회 대비 득점이 적음(결정력 부진·운)") : " — 기대치와 비슷"}
          </p>
        )}
      </section>
      <div className="grid" style={{ marginTop: 16 }}>
        <section className="card">
          <SectionHead title="LEAGUE PERCENTILE" kr="리그 백분위" meta={`리그 ${lgOnly.length}경기 · 경기당 평균 · 막대 = 리그 안 위치`} />
          {d.percentiles.length ? <Percentiles ps={d.percentiles} /> : <p className="pv-empty">리그 경기 기록이 아직 부족합니다</p>}
        </section>
        <section className="card">
          <SectionHead title="GOAL TIMING" kr="득실 시간대" meta="15분 단위" />
          {d.timing ? <GoalTiming t={d.timing} color={c} /> : null}
        </section>
      </div>
    </>
  );
}
