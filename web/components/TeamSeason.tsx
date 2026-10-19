"use client";
import { useEffect, useState } from "react";
import { getTeamSeason, type GoalMix, type GoalMixPart, type PointsPath, type ProfileAxis, type ResultMatch, type TeamSeason } from "@/lib/api";
import { compLabel, compTone, lgEn, liftHex, splitKst } from "@/lib/match";
import { idxMeaning, rankMeaning } from "@/lib/meaning";
import { useLiveAll, liveLabel, type LiveEvent } from "@/lib/live";
import { liveTable } from "@/lib/liveTable";
import { MeaningTag, ScaleLegend } from "./Meaning";
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

function PointsChart({ me, refs, color, prov }: { me: PointsPath; refs: PointsPath[]; color: string; prov?: { pts: number; live: boolean } | null }) {
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
          {me.path.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={i === me.path.length - 1 && !prov ? 4.5 : 2.5} style={{ fill: color }} />)}
          {prov ? (
            <g className={`ts5-prov${prov.live ? " live" : ""}`}>
              <line x1={x(me.path.length - 1)} y1={y(me.path[me.path.length - 1])} x2={x(me.path.length)} y2={y(prov.pts)}
                style={{ stroke: color }} strokeDasharray="4 3" strokeWidth={2.2} />
              <circle cx={x(me.path.length)} cy={y(prov.pts)} r={5} fill="none" style={{ stroke: color }} strokeWidth={2} />
              <text x={x(me.path.length) + 8} y={y(prov.pts) + 4} className="ts5-me-t" style={{ fill: color }}>{prov.pts}점 {prov.live ? "LIVE" : "잠정"}</text>
            </g>
          ) : (
            <text x={x(me.path.length - 1) + 8} y={endY[me.team] + 4} className="ts5-me-t" style={{ fill: color }}>{me.path[me.path.length - 1]}점</text>
          )}
        </g>
      )}
    </svg>
  );
}

function RecentRow({ m, team, live }: { m: ResultMatch; team: string; live?: LiveEvent }) {
  const preview = useMatchPreview();
  const home = m.home.team === team;
  const me = home ? m.home : m.away, op = home ? m.away : m.home;
  const res = me.goals > op.goals ? "W" : me.goals < op.goals ? "L" : "D";
  return (
    <button className={`ts5-res${live ? ` is-live ${live.state}` : ""}`} onClick={() => preview?.(m)} disabled={!m.event_id}
      title={live ? (live.state === "in" ? "진행 중 — 라이브 스코어" : "방금 끝난 경기 — 공식 반영 전(잠정)") : "경기 리뷰 보기"}>
      {live ? <i className={`ts5-wdl live ${live.state === "in" ? "in" : res}`}>{live.state === "in" ? liveLabel(live) : res}</i>
        : <i className={`ts5-wdl ${res}`}>{res}</i>}
      <span className="ts5-op"><Crest s={op} size={20} /><b>{op.team}</b><em>{home ? "H" : "A"}</em></span>
      <span className={`bdg ${compTone(m.comp_code)} ts5-comp`}>{compLabel(m)}</span>
      <b className="ts5-score">{me.goals}–{op.goals}</b>
      <em className="ts5-date">{splitKst(m.kst).date}</em>
    </button>
  );
}

export function SeasonSnapshot({ d, team, league, color }: { d: TeamSeason | null | undefined; team: string; league: string; color: string }) {
  const c = liftHex(color || "#e0475b");
  const live = useLiveAll();
  const liveRows = liveTable(d?.table, d?.pending, live, liveLabel);
  // LAST 5 맨 앞 — 이 팀의 미반영 경기(전 대회) 중 진행 중·방금 끝난 것
  const liveRecent: { m: ResultMatch; e: LiveEvent }[] = (d?.team_pending ?? []).flatMap((f) => {
    const e = f.event_id ? live[f.event_id] : undefined;
    if (!e || e.state === "pre") return [];
    return [{ m: { ...f, home: { ...f.home, goals: Number(e.home.score ?? 0) }, away: { ...f.away, goals: Number(e.away.score ?? 0) }, upset: "" } as unknown as ResultMatch, e }];
  });
  if (d === undefined) return <section className="card h5-card"><Skel h={260} r={12} /></section>;
  if (!d || !d.standing) return null;
  // 공식 결과(매일 아침) 전 라이브 스코어로 순위·승점·전적·LAST 5 를 덮어쓴다(/live-scores, ESPN 30초)
  const lv = liveRows;
  const mine = lv.rows.find((r) => r.team === team);
  const base = d.standing;
  const s = mine?.live ? { ...base, rank: mine.rank, played: mine.played, won: mine.won, drawn: mine.drawn, lost: mine.lost,
    gf: mine.gf, ga: mine.ga, gd: mine.gd, points: mine.points } : base;
  const lead = d.refs.find((r) => r.label === "1위");
  const leadPts = lv.rows[0]?.live && lv.rows[0].team !== team ? lv.rows[0].points : (lead ? (lead.path[lead.path.length - 1] ?? 0) : 0);
  const gap = Math.max(0, leadPts - s.points);
  return (
    <section className="card h5-card ts5">
      <SectionHead title="SEASON SNAPSHOT" kr="이번 시즌 현황"
        meta={mine?.live ? <span className="lv5-meta"><i className="live-dot" />{mine.live.state === "in" ? `LIVE ${mine.live.label} · 지금 스코어로 순위 반영` : "방금 끝난 경기 잠정 반영"} · {lgEn(league)} {s.played}경기</span>
          : `${lgEn(league)} · 리그 ${s.played}경기`} />
      <div className="ts5-grid">
        <div className="ts5-main">
          <div className="ts5-kpis">
            <div><em>POSITION</em><b style={{ color: rankMeaning(s.rank, d.n).c }}>{s.rank}<small>/{d.n}</small>
              {mine?.live && mine.move ? <i className={`lv5-mv ${mine.move > 0 ? "up" : "down"}`}>{mine.move > 0 ? "▲" : "▼"}{Math.abs(mine.move)}</i> : null}</b>
              <span>{s.rank === 1 ? "선두" : `1위와 ${gap}점 차`}</span></div>
            <div><em>POINTS</em><b>{s.points}</b><span>{s.won}승 {s.drawn}무 {s.lost}패</span></div>
            <div><em>GOALS</em><b>{s.gf}<small>:{s.ga}</small></b><span>득점:실점 · 득실 {s.gd > 0 ? `+${s.gd}` : s.gd}</span></div>
            <div title="xG = 슈팅 위치·상황으로 본 '기대 득점'. 높을수록 좋은 찬스를 많이 만든다">
              <em>xG / GAME</em>
              <b style={d.xg_rank ? { color: rankMeaning(d.xg_rank, d.n).c } : undefined}>{d.xg_pg != null ? d.xg_pg.toFixed(2) : "—"}</b>
              <span>{d.xg_rank ? `리그 ${d.xg_rank}위${d.xg_avg != null ? ` · 평균 ${d.xg_avg.toFixed(2)}` : ""}` : "경기당 기대 득점"}</span>
            </div>
          </div>
          <PointsChart me={d.path} refs={d.refs} color={c}
            prov={mine?.live ? { pts: mine.points, live: mine.live.state === "in" } : null} />
          <p className="ts5-note">누적 승점 흐름 · 점선 = 1위·4위(챔피언스리그권) 팀{d.str_rank ? ` · 선수 평점(OVR)으로 본 전력은 리그 ${d.str_rank}위` : ""}</p>
        </div>
        <div className="ts5-recent">
          <div className="ts5-sub">LAST 5 <span>최근 5경기 · 전 대회 · 누르면 경기 리뷰</span></div>
          {liveRecent.map(({ m, e }) => <RecentRow key={"lv" + m.event_id} m={m} team={team} live={e} />)}
          {d.recent.length ? d.recent.filter((m) => !liveRecent.some((x) => x.m.event_id === m.event_id))
            .slice(0, Math.max(0, 5 - liveRecent.length)).map((m, i) => <RecentRow key={m.event_id ?? i} m={m} team={team} />)
            : !liveRecent.length && <p className="pv-empty">최근 경기 기록 없음</p>}
        </div>
      </div>
    </section>
  );
}

// 색·단어는 '값'으로 — 예전엔 리그 순위 3분위로 칠해 '52'(평균 근처)가 초록(상위)으로 보였다(2026-10-15 사용자 지적).
export function SeasonProfile({ axes }: { axes: ProfileAxis[] }) {
  if (!axes.length) return <p className="pv-empty">시즌 경기 기록이 아직 부족합니다</p>;
  return (
    <div className="sp5">
      {axes.map((a) => {
        const mn = idxMeaning(a.value);
        return (
          <div className={`sp5-row t-${mn.tone}`} key={a.key}>
            <div className="sp5-l"><b>{a.en}</b><span>{a.kr}{a.hint ? ` · ${a.hint}` : ""}</span></div>
            <div className="sp5-bar" title={`${a.value} — ${mn.label} (50 = 리그 평균)`}><i /><span style={{ width: `${Math.max(3, a.value)}%`, background: mn.bar }} /></div>
            <div className="sp5-v">
              <b style={{ color: mn.c }}>{a.value}</b>
              <MeaningTag m={mn} sm />
              <em>{a.rank}위<small>/{a.n}</small></em>
              {a.prev_rank != null && (() => {
                // 지난 시즌 대비는 순위로 — 지수는 시즌 초 표본 보정으로 50 쪽에 몰려 값 차이가 전부 '하락'으로 보였다
                const dr = a.prev_rank - a.rank;
                const tip = `지난 시즌 ${a.prev_rank}위 → 이번 ${a.rank}위${a.prev_hint ? ` · 지난 시즌 ${a.prev_hint}` : ""}`;
                return Math.abs(dr) >= 3
                  ? <span className={`sp5-d ${dr > 0 ? "up" : "down"}`} title={tip}>{dr > 0 ? "▲" : "▼"}{Math.abs(dr)}</span>
                  : <span className="sp5-d same" title={tip}>–</span>;
              })()}
            </div>
          </div>
        );
      })}
      <ScaleLegend kind="idx" lead="색·단어" />
      <p className="sp5-note">지수 = 리그 안 상대값(50 = 리그 평균, 막대 가운데 선) · N위 = 리그 순위 ·
        ▲▼ = 지난 시즌 같은 지표의 순위 대비(3계단 이상) · 시즌 초에는 표본이 적어 지수가 50 쪽으로 보정됩니다.</p>
    </div>
  );
}


// 득점 구성 — 오픈플레이·세트피스·PK 비중을 지난 시즌과 나란히(StatBunker). '세트피스 강점이 이번 시즌엔 아직' 같은 변화를 한눈에.
const MIX: [keyof GoalMixPart, string, string][] = [["open", "오픈플레이·크로스", "#6aa6e0"], ["set_piece", "세트피스", "#f4cf5e"], ["pen", "PK", "#c792ea"]];
export function GoalMixCompare({ mix }: { mix: GoalMix }) {
  const rows = ([["지난 시즌", mix.prev], ["이번 시즌", mix.cur]] as [string, GoalMixPart | null][]).filter(([, v]) => v && v.total > 0);
  if (!rows.length) return null;
  const share = (v: GoalMixPart, k: keyof GoalMixPart) => (v.total ? Math.round(((v[k] as number) / v.total) * 100) : 0);
  const notes: string[] = [];
  if (mix.prev && mix.cur && mix.prev.total && mix.cur.total) {
    for (const [k, l] of MIX) {
      const a = share(mix.prev, k), b = share(mix.cur, k);
      if (Math.abs(b - a) >= 10) notes.push(`${l} ${a}% → ${b}% ${b > a ? "▲" : "▼"}`);
    }
  }
  return (
    <div className="gmx">
      {rows.map(([label, v]) => (
        <div className="gmx-row" key={label}>
          <span className="gmx-l">{label}<em>{v!.total}골 · {v!.games}경기</em></span>
          <span className="gmx-bar">
            {MIX.map(([k, l, c]) => (v![k] as number) > 0 && (
              <i key={k} style={{ width: `${share(v!, k)}%`, background: c }} title={`${l} ${v![k]}골 (${share(v!, k)}%)`}>
                {share(v!, k) >= 12 ? `${v![k]}` : ""}
              </i>
            ))}
          </span>
        </div>
      ))}
      <div className="gmx-leg">{MIX.map(([, l, c]) => <span key={l}><i style={{ background: c }} />{l}</span>)}</div>
      {notes.length > 0 && <p className="gmx-note">{notes.join(" · ")}</p>}
    </div>
  );
}
