"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getHomeAll, getFixtures, getHubPulse, getLeagueLab, fmtEur, feeLabel, type HomeAll, type Fixture, type HubMover, type HubPulse, type LeagueLab, type Trend } from "@/lib/api";
import { ResultsTicker, WatchGrid, OverUnder, InjuryImpact } from "./HubPulse";
import LeagueFocus from "./LeagueFocus";
import { MatchRecap } from "./MatchReview";
import PredictionLeague from "./PredictionLeague";
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
import { MeaningTag } from "./Meaning";
import { SS_NOTE, ovrMeaning, ssMeaning } from "@/lib/meaning";

// 무료 서버(Render)가 잠들었다 깨는 중이면 첫 요청이 시간 초과될 수 있어 15초 뒤 한 번만 더 시도한다.
function retryOnce<T>(f: () => Promise<T>, waitMs = 15000): Promise<T> {
  return f().catch(() => new Promise<T>((res, rej) => setTimeout(() => f().then(res, rej), waitMs)));
}

// 전 리그 홈(디자인 v5) — '오늘 무엇을 봐야 하나' 순서로:
//   이번 주 최대 빅매치(크게) + 요약 숫자 → 빅매치 3 → 무엇이 바뀌었나 · 리그 순위 → 빅딜 · 주의 보드 → 이적 소식 · 감독 교체.
// 데이터: /api/home/all(배포 시 미리 계산) + /api/fixtures(매일 갱신 일정).

type Pick = (team: string, league?: string) => void;
type Row = {
  key: string; player: string; club: string; club_logo: string; league: string; photo: string;
  sub: string; why: ReactNode; ovr?: number; trend?: Trend; right?: ReactNode;
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
        {r.photo ? <img src={r.photo} alt="" /> : r.club_logo ? <img className="logo" src={r.club_logo} alt="" /> : <span />}
      </button>
      <button className="pr5-who" onClick={() => onPick(r.club, r.league)} title={`${r.club} 팀 화면`}>
        <b>{r.player}</b>
        <span>{r.club_logo && <img src={r.club_logo} alt="" />}{r.sub}</span>
      </button>
      <span className="pr5-why">{r.why}</span>
      {r.right ?? (r.ovr != null && <OvrCell ovr={r.ovr} trend={r.trend} />)}
    </div>
  );
}

// OVR 숫자 + 등급 단어(OVR GUIDE 와 같은 띠·색) — 숫자만으로는 82 가 어느 정도인지 안 읽혔다
function OvrCell({ ovr, trend }: { ovr: number; trend?: Trend }) {
  const mn = ovrMeaning(ovr);
  return (
    <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }} title={`OVR ${ovr} · ${mn.label}`}>
      <span className="pr5-ovr" style={{ color: mn.c }}>{ovr}{trend && <TrendArrow t={trend} ovr={ovr} />}</span>
      <span style={{ font: "600 9.5px/1 var(--font-ui)", color: mn.c, whiteSpace: "nowrap" }}>{mn.label}</span>
    </span>
  );
}

// 평점 + 뜻(Sofascore 평균 6.8~6.9 기준)
const rt = (r: number) => <>평점 {r.toFixed(2)} <MeaningTag sm m={ssMeaning(r)} title={SS_NOTE} /></>;

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
  const [fxToday, setFxToday] = useState<Fixture[]>([]);   // 오늘 경기 — 방금 끝난(FT) 경기를 MATCH RECAP 에 바로 올린다
  const [pulse, setPulse] = useState<HubPulse | null>(null);
  const [lab, setLab] = useState<LeagueLab | null>(null);
  const [mv, setMv] = useState<string>("up");
  const [mvMore, setMvMore] = useState(false);
  const [lg, setLg] = useState<string>("");
  const [watch, setWatch] = useState<"all" | "inj" | "con">("all");
  const [dealsMore, setDealsMore] = useState(false);
  const { pins } = usePins();
  const [opener, setOpener] = useState(false);
  const t0 = useRef(Date.now());
  useEffect(() => { let a = true; retryOnce(getHomeAll).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
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
  // 리그 분석 랩 — 고른 리그만 불러온다(서버 6시간 캐시)
  const focusLg = lg || d?.snapshots.find((x) => x.table.length > 0)?.league || "";
  useEffect(() => {
    if (!focusLg) return;
    let a = true; setLab(null);
    retryOnce(() => getLeagueLab(focusLg)).then((x) => a && setLab(x)).catch(() => {});
    return () => { a = false; };
  }, [focusLg]);
  // 빅매치 — 실패를 '빅매치 없음'으로 보이지 않게 따로 표시(서버가 깨어나는 중이면 시간 초과가 난다)
  const [fxErr, setFxErr] = useState(false);
  const [fxTry, setFxTry] = useState(0);
  useEffect(() => {
    let a = true; setFxErr(false);
    retryOnce(() => getFixtures(7))
      .then((x) => { if (a) { setFx(x.big); setFxToday([...x.big, ...x.today]); } })
      .catch(() => { if (a) { setFx([]); setFxErr(true); } });
    return () => { a = false; };
  }, [fxTry]);
  useEffect(() => { let a = true; retryOnce(getHubPulse).then((x) => a && setPulse(x)).catch(() => {}); return () => { a = false; }; }, []);

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
    sub: sub(p.club, p.pos), why: <>{`${basisTxt} ${p.ovr_prev} → ${p.ovr}`}{p.rating ? <> · {rt(p.rating)}</> : null}</>,
    ovr: p.ovr, trend: p.basis === "2w" ? { ovr_d: p.delta, form_d: null, ovr_prev: null } : { ovr_d: null, form_d: null, ovr_prev: p.ovr_prev },
  });
  const MV: { k: string; label: string; rows: Row[] }[] = [
    { k: "up", label: "RISERS", rows: (d.movers_up ?? []).map(moverRow) },
    { k: "down", label: "FALLERS", rows: (d.movers_down ?? []).map(moverRow) },
    { k: "form", label: "HOT FORM", rows: d.hot_form.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: <>평균 {rt(p.rating)}</>, ovr: p.ovr })) },
    { k: "prospect", label: "PROSPECTS", rows: d.prospects.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: <>{p.age}세 · {rt(p.rating)}</>, ovr: p.ovr })) },
    { k: "value", label: "VALUE PICKS", rows: d.value_picks.map((p) => ({ key: p.player + p.club, player: p.player, club: p.club, club_logo: p.club_logo, league: p.league, photo: p.photo, sub: sub(p.club, p.pos), why: <>시장가치 {fmtEur(p.value_eur)} · {rt(p.rating)}</>, ovr: p.ovr })) },
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

  // 같은 경기를 여러 섹션에 반복하지 않는다 — BIG MATCHES 의 PSG–Lyon·바르사–레알이 바로 아래 MATCHES TO WATCH 에
  // 또 나왔다(2026-10-20 점검). 빅매치에 오른 경기는 WATCH 에서 빼고, WATCH 의 이유(순위 승부처)는 빅매치 카드 태그로 합친다
  const watchById = new Map((pulse?.watch ?? []).filter((w) => w.event_id).map((w) => [w.event_id as string, w]));
  const withWhy = (m: Fixture): Fixture => {
    const w = m.event_id ? watchById.get(m.event_id) : undefined;
    return w ? { ...m, tags: Array.from(new Set([...(m.tags ?? []), ...w.why])) } : m;
  };
  const hero = fx && fx.length ? withWhy(fx[0]) : null;
  const rest = fx ? fx.slice(1, 4).map(withWhy) : [];
  const shownIds = new Set([hero, ...rest].map((m) => m?.event_id).filter(Boolean) as string[]);
  const watchRest = (pulse?.watch ?? []).filter((w) => !w.event_id || !shownIds.has(w.event_id));
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

      {pulse && <ResultsTicker results={pulse.results} onPick={onPick} />}

      <div className="h5-hero-row">
        {hero ? <MatchHero m={hero} onPick={(t, l) => l && onPick(t, l)} />
          : fx === null ? <Skel h={300} r={18} />
          : fxErr ? (
            <div className="card h5-hero-empty">
              경기 정보를 불러오지 못했습니다 — 서버가 깨어나는 중일 수 있어요(무료 서버는 15분 쉬면 잠들고, 깨는 데 1~2분).
              <button className="loan-more" style={{ marginLeft: 10 }} onClick={() => { setFx(null); setFxTry((n) => n + 1); }}>다시 시도</button>
            </div>
          )
          : <div className="card h5-hero-empty">이번 주에는 빅매치 기준(지수 35+)을 넘는 경기가 없습니다.</div>}
        {s && (
          <div className="h5-kpis">
            {([
              ["SUMMER SPEND", s.spend_eur, (v: number) => (v < 1e6 ? "€0" : fmtEur(v)), `여름 이적료 · ${d.leagues.length}개 리그`],
              ["SIGNINGS", s.signings, undefined, "영입 · 임대 제외"],
              ["MANAGER CHANGES", s.manager_changes, undefined, `이번 시즌 감독 교체 · 시즌 중 ${s.manager_changes_inseason ?? 0}`],
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

      {pulse && pulse.results.length + fxToday.length > 0 && (
        <MatchRecapSec results={pulse.results} extra={fxToday} />
      )}

      {/* 팬 투표 vs 우리 모델 — 누가 더 잘 맞히나 */}
      <PredictionLeague />

      {watchRest.length > 0 && (
        <section className="h5-sec">
          <SectionHead title="MATCHES TO WATCH" kr="주목할 매치" meta="리그별 순위 승부처 · 7일 이내 · 빅매치 제외" />
          <WatchGrid items={watchRest} onPick={onPick} />
        </section>
      )}

      {snap && (
        <section className="h5-sec">
          <SectionHead title="LEAGUE FOCUS" kr="리그 집중" meta="우승 경쟁 · 순위 · 베스트 XI · 득점왕"
            right={<div className="seg5 seg5-head">
              {snaps.map((x) => <button key={x.league} className={x.league === snap.league ? "on" : ""} onClick={() => setLg(x.league)}>{lgEn(x.league) || x.league_name}</button>)}
            </div>} />
          <LeagueFocus league={snap.league} lab={lab} onPick={onPick} />
        </section>
      )}

      <div className="h5-row">
        {curMv && (
          <section className="card h5-card">
            <SectionHead title="MOVERS" kr="선수 동향" meta={curMv.k === "up" || curMv.k === "down" ? `OVR · ${basisTxt} 대비` : "8개 리그"} />
            <Tabs items={MV.map((t) => ({ k: t.k, label: t.label }))} cur={curMv.k} onChange={(k) => { setMv(k); setMvMore(false); }} />
            <div className="pr5-list">{mvRows.map((r, i) => <PlayerRow key={r.key} r={r} rank={i + 1} onPick={onPick} />)}</div>
            {curMv.rows.length > 6 && <button className="more5" onClick={() => setMvMore((v) => !v)}>{mvMore ? "SHOW LESS" : `SHOW ${curMv.rows.length - 6} MORE`}</button>}
          </section>
        )}
        <section className="card h5-card h5-side">
          <SectionHead title="OVER / UNDER" kr="전력 대비 성적" meta="팀 OVR 순위 vs 실제 순위" />
          {pulse ? <OverUnder over={pulse.over} under={pulse.under} onPick={onPick} /> : <Skel h={260} r={12} />}
        </section>
      </div>

      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="INJURY IMPACT" kr="부상 타격" meta="부상자 때문에 줄어든 베스트 XI 평균 전력(팀 OVR)" />
          <InjuryImpact rows={d.injury_impact ?? []} onPick={onPick} />
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
          <SectionHead title="MANAGER MOVES" kr="감독 교체" meta={`시즌 중 ${d.manager_changes.filter((c) => c.in_season).length}건 · 최근 순`} />
          <div className="pr5-list">
            {d.manager_changes.slice(0, 7).map((c, i) => (
              <button className="mg5" key={i} onClick={() => onPick(c.team, c.league)}>
                {c.photo ? <img className="mg5-ph" src={c.photo} alt="" /> : c.logo ? <img className="mg5-ph logo" src={c.logo} alt="" /> : <span className="mg5-ph" />}
                <span className="mg5-who"><b>{c.current}</b><span>{c.logo && <img src={c.logo} alt="" />}{c.team} · {c.previous} 후임</span></span>
                <span className="mg5-date">{c.changed_at ? c.changed_at.slice(5).replace("-", ".") : (c.when_label ?? "")}</span>
              </button>
            ))}
            {d.manager_changes.length === 0 && <p className="empty5">감독 교체 없음</p>}
          </div>
        </section>
      </div>

      <section className="card h5-card">
        <SectionHead title="TRANSFER WIRE" kr="이적 소식" meta="최신순" />
        <div className="bz5-list">
          {d.buzz.slice(0, 10).map((b, i) => (
            <a className="bz5" key={i} href={b.link || undefined} target="_blank" rel="noopener noreferrer">
              <span className={`bdg ${b.tier === "agreed" ? "up" : "neutral"}`}>{b.tier === "agreed" ? "DONE" : "RUMOUR"}</span>
              <span className="bz5-t">{b.title}</span>
              <span className="bz5-src">{lgEn(b.league) || b.league_name} · {b.source}</span>
            </a>
          ))}
          {d.buzz.length === 0 && <p className="empty5">새 이적 소식 없음</p>}
        </div>
      </section>
    </div>
  );
}

// MATCH RECAP — 최근 주요 결과의 자동 리뷰 카드(결과가 하나도 없으면 섹션째 숨김)
function MatchRecapSec({ results, extra }: { results: HubPulse["results"]; extra: Fixture[] }) {
  return (
    <section className="h5-sec rc5-sec">
      <SectionHead title="MATCH RECAP" kr="경기 리뷰" meta="최근 주요 결과 · ESPN 기록 기반 자동 리포트" />
      <MatchRecap results={results} extra={extra} />
    </section>
  );
}
