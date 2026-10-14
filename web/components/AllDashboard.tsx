"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getHomeAll, getFixtures, fmtEur, feeLabel, type HomeAll, type Fixture, type HubMover, type Trend } from "@/lib/api";
import { Skel, SkelCards } from "./Skeleton";
import CountUp from "./CountUp";
import MatchCard, { MatchHero } from "./MatchCard";
import SectionHead from "./SectionHead";
import { TrendArrow } from "./Trend";
import { usePeek } from "./PlayerPeek";
import { usePins } from "@/lib/pins";
import { lgEn } from "@/lib/match";
import { seasonLongLabel, seasonStatusText } from "@/lib/season";
import SeasonOpener from "./SeasonOpener";

// 전 리그 홈(디자인 v5) — '오늘 무엇을 봐야 하나' 순서로:
//   이번 주 최대 빅매치(크게) + 요약 숫자 → 빅매치 3 → 무엇이 바뀌었나 · 리그 순위 → 빅딜 · 주의 보드 → 이적 소식 · 감독 교체.
// 데이터: /api/home/all(배포 시 미리 계산) + /api/fixtures(매일 갱신 일정).

type Pick = (team: string, league?: string) => void;
type Row = {
  key: string; player: string; club: string; club_logo: string; league: string; photo: string;
  sub: string; why: string; ovr?: number; trend?: Trend; right?: ReactNode;
};

const TODAY_EN = () => {
  const d = new Date();
  return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} ${d.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase()}`;
};

function PlayerRow({ r, rank, onPick }: { r: Row; rank?: number; onPick: Pick }) {
  const peek = usePeek();
  return (
    <div className="pr5">
      {rank != null && <span className="pr5-rk">{rank}</span>}
      <button className="pr5-ph peekable" onClick={(e) => peek(e, { name: r.player, club: r.club, league: r.league })} aria-label={`${r.player} 미리보기`}>
        {r.photo ? <img src={r.photo} alt="" /> : <span />}
      </button>
      <button className="pr5-who" onClick={() => onPick(r.club, r.league)} title={`${r.club} 팀 화면`}>
        <b>{r.player}</b>
        <span>{r.club_logo && <img src={r.club_logo} alt="" />}{r.sub}</span>
      </button>
      <span className="pr5-why">{r.why}</span>
      {r.right ?? (r.ovr != null && <span className="pr5-ovr">{r.ovr}{r.trend && <TrendArrow t={r.trend} ovr={r.ovr} />}</span>)}
    </div>
  );
}

function Tabs<T extends string>({ items, cur, onChange }: { items: { k: T; label: string; n?: number }[]; cur: T; onChange: (k: T) => void }) {
  return (
    <div className="tabs5" role="tablist">
      {items.map((t) => (
        <button key={t.k} role="tab" aria-selected={cur === t.k} className={cur === t.k ? "on" : ""} onClick={() => onChange(t.k)}>
          {t.label}{t.n != null && <em>{t.n}</em>}
        </button>
      ))}
    </div>
  );
}

const sub = (club: string, pos?: string, extra?: string) => [club, pos, extra].filter(Boolean).join(" · ");
const POS_SHORT: Record<string, string> = {
  "Goalkeeper": "GK", "Centre-Back": "CB", "Left-Back": "LB", "Right-Back": "RB", "Defensive Midfield": "DM",
  "Central Midfield": "CM", "Attacking Midfield": "AM", "Left Midfield": "LM", "Right Midfield": "RM",
  "Left Winger": "LW", "Right Winger": "RW", "Second Striker": "SS", "Centre-Forward": "CF",
};
const posShort = (p: string) => POS_SHORT[p] ?? p;
const ddays = (until: string) => Math.round((new Date(until).getTime() - Date.now()) / 86400000);

export default function AllDashboard({ onPick, switcher }: { accent?: string; onPick: Pick; switcher?: ReactNode }) {
  const [d, setD] = useState<HomeAll | null>(null);
  const [fx, setFx] = useState<Fixture[] | null>(null);
  const [mv, setMv] = useState<string>("up");
  const [mvMore, setMvMore] = useState(false);
  const [lg, setLg] = useState<string>("");
  const [watch, setWatch] = useState<"all" | "inj" | "con">("all");
  const [dealsMore, setDealsMore] = useState(false);
  const { pins } = usePins();
  const [opener, setOpener] = useState(false);
  const t0 = useRef(Date.now());
  useEffect(() => { let a = true; getHomeAll().then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
  // 시즌 오프닝 — 브라우저 세션당 한 번. 데이터가 2.5초 넘게 늦으면(콜드스타트) 이미 기다린 사람에게 또 보여 주지 않는다.
  useEffect(() => {
    if (!d) return;
    try {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (!reduce && !sessionStorage.getItem("opener-seen") && Date.now() - t0.current < 2500) setOpener(true);
      sessionStorage.setItem("opener-seen", "1");
    } catch { /* 저장소 없음 — 오프닝 생략 */ }
  }, [d]);
  const closeOpener = useCallback(() => setOpener(false), []);
  useEffect(() => { let a = true; getFixtures(7).then((x) => a && setFx(x.big)).catch(() => a && setFx([])); return () => { a = false; }; }, []);

  const pinned = useMemo(() => new Set(pins.map((p) => p.team)), [pins]);

  if (!d) return (
    <div className="h5 skel-wrap">
      <Skel h={60} w={320} r={12} style={{ marginBottom: 20 }} />
      <Skel h={300} r={18} style={{ marginBottom: 24 }} />
      <SkelCards n={6} cols="repeat(auto-fill, minmax(320px, 1fr))" />
    </div>
  );

  // ── 무엇이 바뀌었나(OVR 변화 + 기존 스포트라이트 묶음) ──
  const basisTxt = d.movers_basis === "2w" ? "2주 전" : "지난 시즌";
  const moverRow = (p: HubMover): Row => ({
    key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo,
    sub: sub(p.club, p.pos), why: `${basisTxt} ${p.ovr_prev} → ${p.ovr}${p.rating ? ` · 평점 ${p.rating.toFixed(2)}` : ""}`,
    ovr: p.ovr, trend: p.basis === "2w" ? { ovr_d: p.delta, form_d: null, ovr_prev: null } : { ovr_d: null, form_d: null, ovr_prev: p.ovr_prev },
  });
  const MV: { k: string; label: string; rows: Row[] }[] = [
    { k: "up", label: "RISERS", rows: (d.movers_up ?? []).map(moverRow) },
    { k: "down", label: "FALLERS", rows: (d.movers_down ?? []).map(moverRow) },
    { k: "form", label: "HOT FORM", rows: d.hot_form.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: `평균 평점 ${p.rating.toFixed(2)}`, ovr: p.ovr })) },
    { k: "prospect", label: "PROSPECTS", rows: d.prospects.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: `${p.age}세 · 평점 ${p.rating.toFixed(2)}`, ovr: p.ovr })) },
    { k: "goal", label: "GOALS", rows: d.goal_leaders.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club), why: `${p.goals}골 ${p.assists}도움`, ovr: p.ovr })) },
    { k: "value", label: "VALUE PICKS", rows: d.value_picks.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: `시장가치 ${fmtEur(p.value_eur)} · 평점 ${p.rating.toFixed(2)}`, ovr: p.ovr })) },
    { k: "riser", label: "MARKET ▲", rows: d.risers.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club), why: `${fmtEur(p.value_eur)}`, right: <span className="td up">▲{p.pct}%</span> })) },
  ].filter((t) => t.rows.length > 0);
  const curMv = MV.find((t) => t.k === mv) ?? MV[0];

  // ── 리그 순위 ──
  const snaps = d.snapshots.filter((s) => s.table.length > 0);
  const snap = snaps.find((s) => s.league === lg) ?? snaps[0];
  const top = snap?.table[0]?.points || 1;

  // ── 주의 보드: 부상·복귀 + 계약 만료, 내 팀 먼저 ──
  type W = { key: string; player: string; club: string; club_logo: string; league: string; photo: string; sub: string; badge: string; tone: string; kind: "inj" | "con" };
  const W_ALL: W[] = [
    ...d.injuries.map((p): W => ({ key: "i" + p.player + p.date, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo,
      sub: sub(p.club, p.injury), badge: p.event === "return" ? "복귀" : "부상", tone: p.event === "return" ? "up" : "warn", kind: "inj" })),
    ...d.contracts.map((p): W => ({ key: "c" + p.player, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo,
      sub: sub(p.club, `OVR ${p.ovr}`, p.until ? `${p.until.slice(0, 7).replace("-", ".")} 만료` : ""), badge: p.until ? `D-${ddays(p.until)}` : "만료 임박", tone: "neutral", kind: "con" })),
  ];
  const wList = W_ALL.filter((w) => watch === "all" || w.kind === watch)
    .sort((a, b) => Number(pinned.has(b.club)) - Number(pinned.has(a.club)));

  const hero = fx && fx.length ? fx[0] : null;
  const rest = fx ? fx.slice(1, 4) : [];
  const s = d.summary;
  const mvRows = curMv ? curMv.rows.slice(0, mvMore ? 12 : 6) : [];

  return (
    <div className="h5 fade">
      {opener && (
        <SeasonOpener season={d.window?.label || seasonLongLabel(d.window?.data_season_id)} seasonLong={seasonLongLabel(d.window?.data_season_id)}
          crests={d.snapshots.filter((x) => x.table[0]?.logo).map((x) => ({ logo: x.table[0].logo, team: x.table[0].team, league: x.league }))}
          stats={s} match={hero} onDone={closeOpener} />
      )}
      <header className="h5-head">
        <div>
          <div className="h5-eyebrow">ALL LEAGUES · {seasonLongLabel(d.window?.data_season_id)} SEASON</div>
          <div className="h5-title-row">
            <h1 className="h5-title">GLOBAL DASHBOARD</h1>
            <button className="h5-replay" onClick={() => setOpener(true)} title="시즌 오프닝 다시 보기">▶ SEASON OPENER</button>
          </div>
          <p className="h5-sub">{TODAY_EN()} · {seasonStatusText(d.window, d.window?.label ?? "", d.window?.label ?? "")}{!d.window?.is_open ? " · 이적시장 마감" : ""}</p>
        </div>
        {switcher}
      </header>

      <div className="h5-hero-row">
        {hero ? <MatchHero m={hero} onPick={(t, l) => l && onPick(t, l)} />
          : fx === null ? <Skel h={300} r={18} /> : <div className="card h5-hero-empty">이번 주에는 빅매치 기준(지수 35+)을 넘는 경기가 없습니다.</div>}
        {s && (
          <div className="h5-kpis">
            {([
              ["SUMMER SPEND", s.spend_eur, (v: number) => (v < 1e6 ? "€0" : fmtEur(v)), `여름 이적료 · ${d.leagues.length}개 리그`],
              ["SIGNINGS", s.signings, undefined, "영입 · 임대 제외"],
              ["MANAGER CHANGES", s.manager_changes, undefined, "감독 교체 · 시즌 시작 후"],
              ["INJURED", s.injured, undefined, `현재 부상 결장 · ${d.leagues.length}개 리그`],
            ] as [string, number, ((v: number) => string) | undefined, string][]).map(([l, v, f, m]) => (
              <div className="kpi5" key={l}><span className="kpi5-l">{l}</span><b className="kpi5-v"><CountUp value={v} format={f} /></b><span className="kpi5-m">{m}</span></div>
            ))}
          </div>
        )}
      </div>

      {rest.length > 0 && (
        <section className="h5-sec">
          <SectionHead title="BIG MATCHES" kr="이번 주 빅매치" meta={`7일 이내 · ${fx!.length}경기`} />
          <div className="h5-grid3">{rest.map((m, i) => <MatchCard key={m.event_id ?? i} m={m} onPick={(t, l) => l && onPick(t, l)} />)}</div>
        </section>
      )}

      <div className="h5-row">
        {curMv && (
          <section className="card h5-card">
            <SectionHead title="MOVERS" kr="무엇이 바뀌었나" meta={curMv.k === "up" || curMv.k === "down" ? `OVR · ${basisTxt} 대비` : "8개 리그"} />
            <Tabs items={MV.map((t) => ({ k: t.k, label: t.label }))} cur={curMv.k} onChange={(k) => { setMv(k); setMvMore(false); }} />
            <div className="pr5-list">{mvRows.map((r, i) => <PlayerRow key={r.key} r={r} rank={i + 1} onPick={onPick} />)}</div>
            {curMv.rows.length > 6 && <button className="more5" onClick={() => setMvMore((v) => !v)}>{mvMore ? "SHOW LESS" : `SHOW ${curMv.rows.length - 6} MORE`}</button>}
          </section>
        )}
        {snap && (
          <section className="card h5-card h5-side">
            <SectionHead title="STANDINGS" kr="리그 순위" meta="1위와 승점 차" />
            <div className="seg5">
              {snaps.map((x) => <button key={x.league} className={x.league === snap.league ? "on" : ""} onClick={() => setLg(x.league)}>{lgEn(x.league) || x.league_name}</button>)}
            </div>
            <div className="st5">
              {snap.table.map((t) => (
                <button className="st5-row" key={t.rank} onClick={() => onPick(t.team, snap.league)}>
                  <span className="st5-rk">{t.rank}</span>
                  {t.logo ? <img src={t.logo} alt="" /> : <span className="st5-ph" />}
                  <span className="st5-nm">{t.team}</span>
                  <span className="st5-bar"><span style={{ width: `${Math.max(4, (t.points / top) * 100)}%` }} /></span>
                  <span className="st5-gap">{t.rank === 1 ? "—" : `-${top - t.points}`}</span>
                  <b className="st5-pts">{t.points}</b>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="TOP TRANSFERS" kr="여름 빅딜" meta="이적료 순" />
          <div className="dl5-list">
            {d.top_deals.slice(0, dealsMore ? 12 : 6).map((x, i) => (
              <button className="dl5" key={x.player + i} onClick={() => onPick(x.to, x.league)}>
                <span className="pr5-rk">{i + 1}</span>
                {x.photo ? <img className="dl5-ph" src={x.photo} alt="" /> : <span className="dl5-ph" />}
                <span className="dl5-who"><b>{x.player}</b>
                  <span className="dl5-route">{x.from || "—"}<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    {x.to_logo && <img src={x.to_logo} alt="" />}<em>{x.to}</em></span>
                </span>
                <span className="dl5-pos" title={x.pos}>{posShort(x.pos)}</span>
                <b className="dl5-fee">{feeLabel(x.fee_eur, x.fee_text)}</b>
              </button>
            ))}
            {d.top_deals.length === 0 && <p className="empty5">이번 창 영구 이적 없음</p>}
          </div>
          {d.top_deals.length > 6 && <button className="more5" onClick={() => setDealsMore((v) => !v)}>{dealsMore ? "SHOW LESS" : `SHOW ${d.top_deals.length - 6} MORE`}</button>}
        </section>

        <section className="card h5-card h5-side">
          <SectionHead title="WATCHLIST" kr="주의 보드" meta={pins.length ? "내 팀 먼저" : "팀 화면 ☆ 로 내 팀 고정"} />
          <Tabs items={[{ k: "all" as const, label: "ALL" }, { k: "inj" as const, label: "INJURIES" }, { k: "con" as const, label: "CONTRACTS" }]} cur={watch} onChange={setWatch} />
          <div className="pr5-list">
            {wList.slice(0, 7).map((w) => (
              <PlayerRow key={w.key} onPick={onPick}
                r={{ key: w.key, player: w.player, club: w.club, club_logo: w.club_logo, league: w.league, photo: w.photo, sub: w.sub, why: "",
                  right: <span className={`bdg ${w.tone}`}>{pinned.has(w.club) ? "★ " : ""}{w.badge}</span> }} />
            ))}
            {wList.length === 0 && <p className="empty5">표시할 항목이 없습니다.</p>}
          </div>
        </section>
      </div>

      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="TRANSFER WIRE" kr="이적 소식" meta="최신순" />
          <div className="bz5-list">
            {d.buzz.slice(0, 8).map((b, i) => (
              <a className="bz5" key={i} href={b.link || undefined} target="_blank" rel="noopener noreferrer">
                <span className={`bdg ${b.tier === "agreed" ? "up" : "neutral"}`}>{b.tier === "agreed" ? "DONE" : "RUMOUR"}</span>
                <span className="bz5-t">{b.title}</span>
                <span className="bz5-src">{lgEn(b.league) || b.league_name} · {b.source}</span>
              </a>
            ))}
            {d.buzz.length === 0 && <p className="empty5">새 이적 소식 없음</p>}
          </div>
        </section>
        <section className="card h5-card h5-side">
          <SectionHead title="MANAGER MOVES" kr="감독 교체" meta={`${d.manager_changes.length}건`} />
          <div className="pr5-list">
            {d.manager_changes.slice(0, 7).map((c, i) => (
              <button className="mg5" key={i} onClick={() => onPick(c.team, c.league)}>
                {c.photo ? <img className="mg5-ph" src={c.photo} alt="" /> : c.logo ? <img className="mg5-ph logo" src={c.logo} alt="" /> : <span className="mg5-ph" />}
                <span className="mg5-who"><b>{c.current}</b><span>{c.logo && <img src={c.logo} alt="" />}{c.team} · {c.previous} 후임</span></span>
                <span className="mg5-date">{c.changed_at.slice(5).replace("-", ".")}</span>
              </button>
            ))}
            {d.manager_changes.length === 0 && <p className="empty5">감독 교체 없음</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
