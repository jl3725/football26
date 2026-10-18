"use client";
import { useMemo, useState } from "react";
import type { HubBoot, InjuryImpactRow, RaceTeam, ResultMatch, TableGap, TotsPlayer, TotsSub, WatchMatch } from "@/lib/api";
import Pitch from "./Pitch";
import { usePeek } from "./PlayerPeek";
import { colorsClose, compLabel, compTone, ddayLabel, lgEn, liftHex, splitKst } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";
import { Crest, PredictBar } from "./MatchCard";
import { useLiveAll, liveLabel, fixtureFromLive, type LiveEvent } from "@/lib/live";
import { SS_NOTE, TONE, ssMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";

// 홈 '지금' 섹션들 — /api/hub/pulse(요청 시 계산·30분 캐시, 일정·결과는 daily_data 가 매일 갱신)
type Pick = (team: string, league?: string) => void;

// ── RESULTS: 최근 결과 띠(방송 하단 자막처럼 천천히 흐름, 마우스를 올리면 멈춤) ──
export function ResultsTicker({ results, onPick, comps }: { results: ResultMatch[]; onPick: Pick; comps?: string[] }) {
  // 하루 갱신 결과 + 라이브(진행 중·방금 끝난 경기, ESPN) — 아직 일정 파일에 안 들어온 경기를 앞에
  const live = useLiveAll();
  const preview = useMatchPreview();   // 스코어를 누르면 경기 리뷰(매치 서랍)
  const known = new Set(results.map((r) => r.event_id));
  const cutoff = Date.now() - 20 * 3600 * 1000;
  const extra = Object.values(live)
    .filter((e) => e.state !== "pre" && !known.has(e.id) && Date.parse(e.date) >= cutoff && (!comps || comps.includes(e.comp)))
    .sort((a, b) => (a.state === "in" ? 0 : 1) - (b.state === "in" ? 0 : 1) || Date.parse(b.date) - Date.parse(a.date));
  if (!results.length && !extra.length) return null;
  const liveItem = (e: LiveEvent, k: string, dup = false) => {
    const hw = e.home.winner, aw = e.away.winner;
    return (
      <button className={`tk5-item tk5-btn${e.state === "in" ? " live" : ""}`} key={k} tabIndex={dup ? -1 : undefined}
        onClick={() => preview?.(fixtureFromLive(e))} title="경기 리뷰 보기">
        <span className={`tk5-comp ${e.comp === "uefa.champions" ? "ucl" : e.comp.startsWith("uefa.europa") ? "uel" : ""}`}>
          {e.state === "in" ? <><i className="live-dot" />{liveLabel(e)}</> : liveLabel(e)}
        </span>
        <span className={`tk5-team${aw ? " lose" : ""}`}>{e.home.logo && <img className="crest" src={e.home.logo} alt="" style={{ width: 18, height: 18 }} />}{e.home.name}</span>
        <b className="tk5-score"><span className={hw ? "w" : ""}>{e.home.score ?? 0}</span>–<span className={aw ? "w" : ""}>{e.away.score ?? 0}</span></b>
        <span className={`tk5-team${hw ? " lose" : ""}`}>{e.away.name}{e.away.logo && <img className="crest" src={e.away.logo} alt="" style={{ width: 18, height: 18 }} />}</span>
      </button>
    );
  };
  const item = (m: ResultMatch, k: string, dup = false) => {
    const hw = m.home.goals > m.away.goals, aw = m.away.goals > m.home.goals;
    return (
      <span className={`tk5-item${m.upset ? " upset" : ""}`} key={k} title={m.upset || `${m.kst}`}>
        <span className={`tk5-comp ${compTone(m.comp_code)}`}>{compLabel(m)}</span>
        <button className={`tk5-team${aw ? " lose" : ""}`} disabled={!m.home.league} tabIndex={dup ? -1 : undefined} onClick={() => m.home.league && onPick(m.home.team, m.home.league)}>
          <Crest s={m.home} size={18} />{m.home.team}
        </button>
        <button className="tk5-score" disabled={!m.event_id} tabIndex={dup ? -1 : undefined} onClick={() => preview?.(m)} title="경기 리뷰 보기">
          <span className={hw ? "w" : ""}>{m.home.goals}</span>–<span className={aw ? "w" : ""}>{m.away.goals}</span>
        </button>
        <button className={`tk5-team${hw ? " lose" : ""}`} disabled={!m.away.league} tabIndex={dup ? -1 : undefined} onClick={() => m.away.league && onPick(m.away.team, m.away.league)}>
          {m.away.team}<Crest s={m.away} size={18} />
        </button>
        {m.upset && <span className="bdg warn">UPSET</span>}
      </span>
    );
  };
  return (
    <div className="tk5" aria-label="최근 경기 결과">
      <span className="tk5-label">{extra.some((e) => e.state === "in") ? <><i className="live-dot" />LIVE</> : "RESULTS"}<em>최근 3일</em></span>
      <div className="tk5-viewport">
        <div className="tk5-track" style={{ animationDuration: `${Math.max(40, (results.length + extra.length) * 5)}s` }}>
          {extra.map((e, i) => liveItem(e, `la${i}`))}
          {results.map((m, i) => item(m, `a${i}`))}
          <span aria-hidden="true" className="tk5-dup">{extra.map((e, i) => liveItem(e, `lb${i}`, true))}{results.map((m, i) => item(m, `b${i}`, true))}</span>
        </div>
      </div>
    </div>
  );
}

// ── MATCHES TO WATCH: 리그 안의 승부처(순위가 붙은 경기) ──
export function WatchGrid({ items, onPick }: { items: WatchMatch[]; onPick: Pick }) {
  const preview = useMatchPreview();
  const live = useLiveAll();
  if (!items.length) return null;
  return (
    <div className="wt5-grid">
      {items.map((m) => {
        const { date, time } = splitKst(m.kst);
        const lv = m.event_id ? live[m.event_id] : undefined;
        const played = lv && lv.state !== "pre";
        return (
          <div className="wt5" key={m.event_id ?? m.home.team + m.away.team} role="button" tabIndex={0}
            onClick={() => preview?.(m)} onKeyDown={(e) => { if (e.key === "Enter") preview?.(m); }}>
            <div className="wt5-top">
              <span className="bdg neutral">{lgEn(m.league)}</span>
              <span className="wt5-when">{date} {time}</span>
              {lv?.state === "in" ? <span className="bdg live"><i />LIVE {liveLabel(lv)}</span>
                : lv?.state === "post" ? <span className="bdg ft">{liveLabel(lv)}</span>
                : <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>}
            </div>
            {[m.home, m.away].map((s, i) => (
              <button className="wt5-team" key={s.team} onClick={(e) => { e.stopPropagation(); if (s.league) onPick(s.team, s.league); }}>
                <Crest s={s} size={26} />
                <b>{s.team}</b>
                <span className="wt5-rank">{s.rank}위</span>
                {played
                  ? <span className={`wt5-goal${(i === 0 ? lv!.home.winner : lv!.away.winner) ? " w" : ""}`}>{(i === 0 ? lv!.home.score : lv!.away.score) ?? 0}</span>
                  : <span className="wt5-pts">{s.points}<em>점</em></span>}
              </button>
            ))}
            <PredictBar m={m} slim />
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

// ── GOLDEN BOOT: 리그 득점 순위(선두 대비 막대) ──
export function GoldenBoot({ rows, onPick }: { rows: HubBoot[]; onPick: Pick }) {
  const peek = usePeek();
  if (!rows.length) return <p className="empty5">득점 기록 없음</p>;
  const lead = rows[0].goals || 1;
  return (
    <div className="gb5">
      {rows.map((r, i) => (
        <div className="gb5-row" key={r.player + r.club}>
          <span className="pr5-rk">{i + 1}</span>
          <button className="pr5-ph peekable" onClick={(e) => peek(e, { name: r.player, club: r.club, league: r.league })} aria-label={`${r.player} 미리보기`}>
            {r.photo ? <img src={r.photo} alt="" /> : r.club_logo ? <img className="logo" src={r.club_logo} alt="" /> : <span />}
          </button>
          <button className="gb5-who" onClick={() => onPick(r.club, r.league)}>
            <b>{r.player}</b>
            <span className="gb5-bar"><i style={{ width: `${(r.goals / lead) * 100}%` }} /></span>
            <em>{r.club_logo && <img src={r.club_logo} alt="" />}{r.club}{r.xg != null ? ` · xG ${r.xg.toFixed(1)}` : ""}{r.mpg ? ` · ${r.mpg}분당 1골` : ""}</em>
          </button>
          <span className="gb5-n">
            <b>{r.goals}</b>
            {r.xg != null ? (() => {
              // 골 − xG: +면 기대 득점(슈팅 위치·상황으로 본 평균 선수의 골)보다 많이 넣음 — 'xG' 약어만으로는 뜻이 안 읽혔다
              const d = Math.round((r.goals - r.xg) * 10) / 10;
              const c = d >= 1 ? TONE.good.c : d <= -1 ? TONE.weak.c : undefined;
              return (
                <small style={{ fontFamily: "var(--font-ui)", letterSpacing: 0, whiteSpace: "nowrap", ...(c ? { color: c } : {}) }}
                  title={`기대 득점(xG) ${r.xg.toFixed(1)}골 — ${d === 0 ? "기대만큼" : d > 0 ? `${d.toFixed(1)}골 많이` : `${Math.abs(d).toFixed(1)}골 적게`} 넣음 · xG 는 슈팅 위치·상황으로 본 '평균적인 선수라면 넣었을 골'`}>
                  {d === 0 ? "기대만큼" : <>기대보다 {d > 0 ? "+" : "−"}{Math.abs(d).toFixed(1)}골</>}
                </small>
              );
            })() : <small>{r.assists}A</small>}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── TEAM OF THE SEASON: 데이터로 고른 포메이션 경기장 + 명단 + 교체 명단(SUBS) ──
// 포메이션은 4-3-3 고정이 아니라 잘하는 선수가 가장 많이 들어가는 형태(api _team_of_season). 예전의 자리별
// '다음 후보' 대신 남은 상위 선수를 벤치(SUBS)로 — 2026-10-19 사용자 요청.
const ROLE_KO: Record<string, string> = { GK: "GK", CB: "CB", LB: "LB", RB: "RB", DM: "DM", CM: "CM", AM: "AM", LW: "LW", RW: "RW", ST: "ST" };
export function TeamOfSeason({ players, league, formation, subs = [] }: { players: TotsPlayer[]; league: string; formation?: string | null; subs?: TotsSub[] }) {
  const peek = usePeek();
  const placements = players.map((p) => ({ slot: p.slot, player: p.player, x: p.x, y: p.y, kind: p.kind, ovr: Math.round(p.rating * 10) / 10, photo: p.photo, club: p.club }));
  // 골키퍼부터 수비·미드·공격 순(경기장 아래 → 위), 같은 줄은 왼쪽부터
  const list = [...players].sort((a, b) => (b.y - a.y) || (a.x - b.x));
  const label = (s: string) => s.replace(/^[LR](CB|CM|ST|DM|AM)$/, "$1").replace(/^C(AM)$/, "$1");
  return (
    <div className="tots5">
      <div className="tots5-pitch">
        {formation && <div className="tots5-form"><b>{formation}</b><span>시즌 평점으로 고른 포메이션</span></div>}
        <Pitch placements={placements} metric="평점" />
      </div>
      <div className="tots5-list">
        {list.map((p) => (
          <button key={p.slot} className="tots5-row" onClick={(e) => peek(e, { name: p.player, club: p.club, league })}>
            <span className="tots5-slot">{label(p.slot)}</span>
            {p.club_logo ? <img src={p.club_logo} alt="" /> : <span className="tots5-ph" />}
            <span className="tots5-who">
              <b>{p.player}</b>
              <em>{p.minutes}분{p.goals || p.assists ? ` · ${p.goals ?? 0}골 ${p.assists ?? 0}도움` : ""}
                {p.role && label(p.slot) !== p.role && !(p.slot.endsWith("WB") || p.slot.endsWith("M")) ? ` · 원래 ${ROLE_KO[p.role] ?? p.role}` : ""}</em>
            </span>
            <span className="tots5-r" title={SS_NOTE}>{p.rating.toFixed(2)}</span>
            <MeaningTag sm m={ssMeaning(p.rating)} title={SS_NOTE} />
          </button>
        ))}
        {subs.length > 0 && (
          <div className="tots5-subs">
            <div className="tots5-subs-h">SUBS <span>교체 명단 · 베스트 XI 다음으로 평점 높은 선수</span></div>
            <div className="tots5-subs-grid">
              {subs.map((s) => (
                <button key={s.player} className="tots5-sub" onClick={(e) => peek(e, { name: s.player, club: s.club, league })}
                  title={`${s.player} · ${s.club} · ${s.minutes}분${s.goals || s.assists ? ` · ${s.goals}골 ${s.assists}도움` : ""}`}>
                  <span className="tots5-sub-role">{ROLE_KO[s.role] ?? s.role}</span>
                  {s.club_logo ? <img src={s.club_logo} alt="" /> : <span className="tots5-ph" />}
                  <b>{s.player.split(" ").slice(-1)[0]}</b>
                  <em style={{ color: ssMeaning(s.rating).c }}>{s.rating.toFixed(2)}</em>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── INJURY IMPACT: 부상으로 줄어든 베스트 XI 평균 전력 ──
export function InjuryImpact({ rows, onPick }: { rows: InjuryImpactRow[]; onPick: Pick }) {
  if (!rows.length) return <p className="empty5">눈에 띄는 부상 타격 없음</p>;
  const max = Math.max(...rows.map((r) => r.loss), 0.1);
  return (
    <div className="ii5">
      {rows.slice(0, 7).map((r) => (
        <button className="ii5-row" key={r.league + r.team} onClick={() => onPick(r.team, r.league)}>
          {r.logo ? <img src={r.logo} alt="" /> : <span className="ou5-ph" />}
          <span className="ii5-who">
            <b>{r.team}<em>{lgEn(r.league)}</em></b>
            <span>결장 {r.n}명{r.key.length ? ` · ${r.key.join(", ")}` : ""}</span>
          </span>
          <span className="ii5-bar"><i style={{ width: `${(r.loss / max) * 100}%` }} /></span>
          <span className="td down" title={`부상·결장으로 베스트 XI 평균 OVR 이 ${r.loss.toFixed(1)} 내려감`}>
            <small style={{ font: "600 10px/1 var(--font-ui)", color: "var(--muted-2)", marginRight: 4 }}>팀 OVR</small>−{r.loss.toFixed(1)}
          </span>
        </button>
      ))}
    </div>
  );
}
