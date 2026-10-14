"use client";
import { useMemo, useState } from "react";
import type { RaceTeam, ResultMatch, TableGap, WatchMatch } from "@/lib/api";
import { colorsClose, compLabel, compTone, ddayLabel, lgEn, liftHex, splitKst } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";
import { Crest } from "./MatchCard";

// 홈 '지금' 섹션들 — /api/hub/pulse(요청 시 계산·30분 캐시, 일정·결과는 daily_data 가 매일 갱신)
type Pick = (team: string, league?: string) => void;

// ── RESULTS: 최근 결과 띠(방송 하단 자막처럼 천천히 흐름, 마우스를 올리면 멈춤) ──
export function ResultsTicker({ results, onPick }: { results: ResultMatch[]; onPick: Pick }) {
  if (!results.length) return null;
  const item = (m: ResultMatch, k: string) => {
    const hw = m.home.goals > m.away.goals, aw = m.away.goals > m.home.goals;
    return (
      <span className={`tk5-item${m.upset ? " upset" : ""}`} key={k} title={m.upset || `${m.kst}`}>
        <span className={`tk5-comp ${compTone(m.comp_code)}`}>{compLabel(m)}</span>
        <button className={`tk5-team${aw ? " lose" : ""}`} disabled={!m.home.league} onClick={() => m.home.league && onPick(m.home.team, m.home.league)}>
          <Crest s={m.home} size={18} />{m.home.team}
        </button>
        <b className="tk5-score"><span className={hw ? "w" : ""}>{m.home.goals}</span>–<span className={aw ? "w" : ""}>{m.away.goals}</span></b>
        <button className={`tk5-team${hw ? " lose" : ""}`} disabled={!m.away.league} onClick={() => m.away.league && onPick(m.away.team, m.away.league)}>
          {m.away.team}<Crest s={m.away} size={18} />
        </button>
        {m.upset && <span className="bdg warn">UPSET</span>}
      </span>
    );
  };
  return (
    <div className="tk5" aria-label="최근 경기 결과">
      <span className="tk5-label">RESULTS<em>최근 3일</em></span>
      <div className="tk5-viewport">
        <div className="tk5-track" style={{ animationDuration: `${Math.max(40, results.length * 5)}s` }}>
          {results.map((m, i) => item(m, `a${i}`))}
          <span aria-hidden="true" className="tk5-dup">{results.map((m, i) => item(m, `b${i}`))}</span>
        </div>
      </div>
    </div>
  );
}

// ── MATCHES TO WATCH: 리그 안의 승부처(순위가 붙은 경기) ──
export function WatchGrid({ items, onPick }: { items: WatchMatch[]; onPick: Pick }) {
  const preview = useMatchPreview();
  if (!items.length) return null;
  return (
    <div className="wt5-grid">
      {items.map((m) => {
        const { date, time } = splitKst(m.kst);
        return (
          <div className="wt5" key={m.event_id ?? m.home.team + m.away.team} role="button" tabIndex={0}
            onClick={() => preview?.(m)} onKeyDown={(e) => { if (e.key === "Enter") preview?.(m); }}>
            <div className="wt5-top">
              <span className="bdg neutral">{lgEn(m.league)}</span>
              <span className="wt5-when">{date} {time}</span>
              <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>
            </div>
            {[m.home, m.away].map((s) => (
              <button className="wt5-team" key={s.team} onClick={(e) => { e.stopPropagation(); if (s.league) onPick(s.team, s.league); }}>
                <Crest s={s} size={26} />
                <b>{s.team}</b>
                <span className="wt5-rank">{s.rank}위</span>
                <span className="wt5-pts">{s.points}<em>점</em></span>
              </button>
            ))}
            <div className="wt5-why">
              {m.why.map((t, i) => <span key={t} className={i === 0 ? "lead" : ""}>{t}</span>)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── TITLE RACE: 상위 4팀 누적 승점 선 그래프 ──
const PALETTE = ["#ff4d5e", "#5b7cff", "#f4cf5e", "#68e0a5"];
export function TitleRace({ teams, onPick, league }: { teams: RaceTeam[]; onPick: Pick; league: string }) {
  const W = 640, H = 250, L = 30, R = 96, T = 14, B = 26;
  const games = Math.max(1, ...teams.map((t) => t.points.length));
  const maxP = Math.max(3, ...teams.map((t) => t.points[t.points.length - 1] ?? 0));
  const yMax = Math.ceil((maxP + 1) / 5) * 5;
  const x = (i: number) => L + (i / games) * (W - L - R);
  const y = (p: number) => T + (1 - p / yMax) * (H - T - B);
  const colors = useMemo(() => {
    const out: string[] = [];
    teams.forEach((t, i) => {
      let c = liftHex(t.color || PALETTE[i]);
      if (out.some((o) => colorsClose(o, c))) c = PALETTE.find((p) => !out.some((o) => colorsClose(o, p))) ?? PALETTE[i];
      out.push(c);
    });
    return out;
  }, [teams]);
  // 끝 라벨이 겹치지 않게 아래로 밀기
  const ends = teams.map((t, i) => ({ i, y: y(t.points[t.points.length - 1] ?? 0) })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 22) ends[k].y = ends[k - 1].y + 22;
  const endY = Object.fromEntries(ends.map((e) => [e.i, e.y]));
  const leader = teams[0]?.points[teams[0].points.length - 1] ?? 0;
  return (
    <div className="tr5">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="상위 4팀 누적 승점 추이">
        {Array.from({ length: yMax / 5 + 1 }, (_, k) => k * 5).map((p) => (
          <g key={p}><line x1={L} x2={W - R} y1={y(p)} y2={y(p)} className="tr5-grid" /><text x={L - 8} y={y(p) + 4} className="tr5-yl">{p}</text></g>
        ))}
        {Array.from({ length: games }, (_, k) => k + 1).map((g) => (
          <text key={g} x={x(g)} y={H - 8} className="tr5-xl">{g}</text>
        ))}
        {teams.map((t, i) => {
          const pts = [0, ...t.points];
          const d = pts.map((p, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
          const lx = x(pts.length - 1), ly = y(pts[pts.length - 1]);
          return (
            <g key={t.team} className="tr5-line" style={{ ["--d" as any]: `${i * 0.12}s` }}>
              <path d={d} stroke={colors[i]} pathLength={1} />
              <circle cx={lx} cy={ly} r={4} fill={colors[i]} />
              <line x1={lx + 6} x2={W - R + 6} y1={ly} y2={endY[i]} stroke={colors[i]} className="tr5-lead" />
              <image href={t.logo} x={W - R + 10} y={endY[i] - 9} width={18} height={18} />
              <text x={W - R + 34} y={endY[i] + 5} className="tr5-pts" fill={colors[i]}>{pts[pts.length - 1]}</text>
            </g>
          );
        })}
      </svg>
      <div className="tr5-legend">
        {teams.map((t, i) => {
          const p = t.points[t.points.length - 1] ?? 0;
          return (
            <button key={t.team} onClick={() => onPick(t.team, league)}>
              <i style={{ background: colors[i] }} /><b>{t.team}</b><span>{i === 0 ? `${p}점` : `-${leader - p}`}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── OVER / UNDER: 팀 전력 순위 대비 실제 순위 ──
export function OverUnder({ over, under, onPick }: { over: TableGap[]; under: TableGap[]; onPick: Pick }) {
  const [tab, setTab] = useState<"over" | "under">("over");
  const rows = (tab === "over" ? over : under).slice(0, 7);
  return (
    <>
      <div className="tabs5" role="tablist">
        <button role="tab" aria-selected={tab === "over"} className={tab === "over" ? "on" : ""} onClick={() => setTab("over")}>OVERPERFORM</button>
        <button role="tab" aria-selected={tab === "under"} className={tab === "under" ? "on" : ""} onClick={() => setTab("under")}>UNDERPERFORM</button>
      </div>
      <div className="pr5-list">
        {rows.map((g) => (
          <button className="ou5" key={g.league + g.team} onClick={() => onPick(g.team, g.league)}>
            {g.logo ? <img src={g.logo} alt="" /> : <span className="ou5-ph" />}
            <span className="ou5-who">
              <b>{g.team}</b>
              <span>{lgEn(g.league)} {g.rank}위 · 전력 {g.str_rank}위{tab === "under" && g.hot_seat && g.manager ? ` · ${g.manager}` : ""}</span>
            </span>
            {tab === "under" && g.hot_seat && <span className="bdg warn">HOT SEAT</span>}
            <span className={`td ${g.gap > 0 ? "up" : "down"}`}>{g.gap > 0 ? "▲" : "▼"}{Math.abs(g.gap)}</span>
          </button>
        ))}
        {rows.length === 0 && <p className="empty5">해당 팀 없음</p>}
      </div>
    </>
  );
}
