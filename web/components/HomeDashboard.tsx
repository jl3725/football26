"use client";
import { useEffect, useState, type ReactNode } from "react";
import { feeLabel, getHome, getLeagueLab, type Fixture, type Home, type LeagueLab } from "@/lib/api";
import LeagueFocus from "./LeagueFocus";
import { ResultsTicker, WatchGrid } from "./HubPulse";
import { MatchRecap } from "./MatchReview";
import WorldCup from "./WorldCup";
import AllDashboard from "./AllDashboard";
import { Skel, SkelCards } from "./Skeleton";
import { phaseOf, seasonStatusText } from "@/lib/season";
import LeagueFixtures from "./LeagueFixtures";
import SectionHead from "./SectionHead";
import WeeklyDigest from "./WeeklyDigest";

const ESPN_CODE: Record<string, string> = { EPL: "eng.1", LaLiga: "esp.1", SerieA: "ita.1", Bundesliga: "ger.1", Ligue1: "fra.1",
  LigaPortugal: "por.1", Eredivisie: "ned.1", BelgianProLeague: "bel.1" };
const eurM = (v: number) => (v >= 1e6 ? `€${Math.round(v / 1e6)}M` : v > 0 ? `€${Math.round(v / 1e3)}K` : "€0");

// 섹션 머리 — 영어 제목 + 작은 한글 보조(디자인 v5 공통형)
function Sec({ en, kr, right }: { en: string; kr: string; accent?: string; right?: ReactNode }) {
  return <SectionHead title={en} kr={kr} right={right} />;
}

type LeagueOpt = { key: string; label: string };

// 결과 파일에 아직 없는 최근·오늘 리그 경기(lab.pending) → 방금 끝난(FT) 경기를 MATCH RECAP 에 바로 올리기 위한 Fixture
function pendingFixtures(lab: LeagueLab, league: string): Fixture[] {
  const row = (n: string) => (lab.table ?? []).find((t) => t.team === n);
  const side = (n: string) => {
    const t = row(n);
    return { team: n, league, rank: t?.rank ?? null, points: t?.points ?? null, logo: t?.logo ?? "", color: "", ovr: t?.ovr ?? null, form: t?.form ?? [] };
  };
  return Object.entries(lab.pending ?? {}).map(([id, p]) => ({
    event_id: id, comp_code: ESPN_CODE[league] ?? "", comp: "", kickoff: "", kst: "", date: "", d_day: 0,
    home: side(p.home), away: side(p.away), big: 0, tags: [],
  }));
}

export default function HomeDashboard({ accent, onPickTeam, onPickLeagueTeam, leagueLabel = "EPL",
  league = "EPL", leagues = [], onLeague, view, onView }: {
  accent: string; onPickTeam: (t: string) => void; onPickLeagueTeam?: (t: string, league?: string) => void;
  leagueLabel?: string; league?: string; leagues?: LeagueOpt[]; onLeague?: (l: string) => void;
  view?: "all" | "league" | "WC"; onView?: (v: "all" | "league" | "WC") => void;   // 페이지가 주소와 함께 관리
}) {
  const [h, setH] = useState<Home | null>(null);
  const [own, setOwn] = useState<"all" | "league" | "WC">("all");   // 전체 · 리그 홈 · 월드컵(페이지가 안 넘기면 자체 상태)
  const comp = view ?? own;
  const setComp = (v: "all" | "league" | "WC") => { setOwn(v); onView?.(v); };
  const [lab, setLab] = useState<LeagueLab | null>(null);              // 리그 분석 랩(결과·주목할 매치·순위표·베스트 XI …)
  // leagueLabel 변경(리그 전환) 시 재조회 — getHome 은 모듈 활성리그(_league) 사용
  useEffect(() => { let a = true; setH(null); getHome().then((d) => a && setH(d)).catch(() => {}); return () => { a = false; }; }, [leagueLabel]);
  useEffect(() => {
    if (comp !== "league") return;
    let a = true; setLab(null);
    getLeagueLab(league).then((d) => a && setLab(d)).catch(() => {});
    return () => { a = false; };
  }, [league, comp]);

  // 전체(통합) + 모든 리그 + WC 를 홈에서 바로 전환하는 탭(리그 홈은 다리그 허브)
  const opts: LeagueOpt[] = leagues.length ? leagues : [{ key: league, label: leagueLabel }];
  const pickTL = onPickLeagueTeam ?? ((t: string) => onPickTeam(t));
  const switcher = (
    <div className="comp-seg chips5">
      <button className={comp === "all" ? "active" : ""} onClick={() => setComp("all")}>전체</button>
      {opts.map((l) => {
        const on = comp === "league" && league === l.key;
        return (
          <button key={l.key} className={on ? "active" : ""}
            onClick={() => { setComp("league"); onLeague?.(l.key); }}>{l.label}</button>
        );
      })}
      <button className={`wc${comp === "WC" ? " active" : ""}`} onClick={() => setComp("WC")} title="2026 월드컵"><span className="wc-dot" />WC 26</button>
    </div>
  );

  if (comp === "all") return (
    <div className="fade home"><AllDashboard accent={accent} onPick={pickTL} switcher={switcher} /></div>
  );
  if (comp === "WC") return (
    <div className="fade home"><div className="wc-topbar">{switcher}</div><WorldCup accent={accent} onPickTeam={pickTL} /></div>
  );
  if (!h) return (
    <div className="fade home skel-wrap">
      <div className="wc-topbar">{switcher}</div>
      <Skel h={140} r={18} style={{ marginBottom: 16 }} />
      <SkelCards n={6} />
    </div>
  );

  const nextLabel = h.roster_next?.season_label || h.window.label;
  const inSeason = phaseOf(h.window) === "in_season";
  const deals = h.transfers.top_deals;
  const feat = deals[0];
  const maxSpend = Math.max(1, ...h.transfers.net_spend.map((n) => n.spend));

  return (
    <div className="fade home">
      {/* ── HERO ── */}
      <div className="hx" style={{ ["--tc" as any]: accent }}>
        <div className="hx-glow" style={{ background: `radial-gradient(60% 120% at 85% 0%, ${accent}44, transparent 70%)` }} />
        <div className="hx-top">
          {switcher}
          <div className="hx-live">
            <span className="livedot" />
            {h.window.is_open ? `${h.window.label} ${h.window.kr ?? ""} 이적시장 OPEN` : `${h.season} 시즌`}
          </div>
        </div>

        <div className="hx-kicker">{inSeason ? `${h.season} SEASON${h.window.is_open ? " · TRANSFER WINDOW" : ""}` : `${nextLabel} SEASON · TRANSFER WINDOW`}</div>
        <h1 className="hx-title">{leagueLabel === "EPL" ? "PREMIER LEAGUE" : leagueLabel}</h1>
        <div className="hx-meta">{seasonStatusText(h.window, h.season, nextLabel)}</div>

        <div className="kpis">
          <div className="kpi"><div className="kpi-n teko" style={{ color: accent }}>{eurM(h.kpi.spend)}</div><div className="kpi-l">이적 총지출</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.deals}</div><div className="kpi-l">영입 건수</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.mgr_changes}</div><div className="kpi-l">감독 교체</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.injuries}</div><div className="kpi-l">부상 변동</div></div>
        </div>
      </div>

      {lab && <div style={{ marginTop: 18 }}><ResultsTicker results={lab.results ?? []} onPick={(t, lg) => pickTL(t, lg)} comps={[ESPN_CODE[league] ?? ""]} /></div>}

      {/* ── 이번 주 경기(매치 센터) — 시즌 중엔 이적보다 먼저. 빅매치는 강조 카드 + 목록 배지 ── */}
      <Sec en="THIS WEEK" kr="이번 주 경기" accent={accent} />
      <LeagueFixtures league={league} accent={accent} onPick={(t, lg) => pickTL(t, lg)} />

      {lab && (lab.results ?? []).length > 0 && (
        <>
          <Sec en="MATCH RECAP" kr="경기 리뷰" />
          <MatchRecap results={lab.results!} extra={pendingFixtures(lab, league)} />
        </>
      )}

      {lab && (lab.watch ?? []).length > 0 && (
        <>
          <Sec en="MATCHES TO WATCH" kr="주목할 매치" />
          <WatchGrid items={lab.watch!} onPick={(t, lg) => pickTL(t, lg)} />
        </>
      )}

      {/* ── 이번 주에 바뀐 것: 폼 ▲▼ · 부상 변동 · 뉴스 언급 · 루머 · A매치 (규칙 기반 주간 요약) ── */}
      <Sec en="WEEKLY DIGEST" kr="이번 주 요약" />
      <WeeklyDigest league={league} />

      {/* ── 리그 집중: 전체 순위표 · 우승 경쟁 · 전력 대비 · 베스트 XI · 득점왕 · 기대값 · 도움왕 · 팀 스타일 · 볼 위닝 · 부상 타격 ── */}
      <Sec en="LEAGUE FOCUS" kr="리그 집중" />
      <LeagueFocus league={league} lab={lab} onPick={(t, lg) => pickTL(t, lg)} full />

      {/* ── 이적 속보 (LIVE 피드) ── */}
      {h.buzz && h.buzz.length > 0 && (
        <>
          <Sec en="TRANSFER WIRE" kr="이적 속보" accent={accent}
            right={<span className="wire-live"><span className="wc-dot" />LIVE</span>} />
          <div className="card">
            <div className="wire">
              {h.buzz.slice(0, 12).map((b, i) => (
                <a className="wire-row" key={i} href={b.link || undefined} target="_blank" rel="noreferrer">
                  <span className={`wire-tag ${b.tier}`}>{b.tier === "agreed" ? "합의" : "루머"}</span>
                  <div className="wire-mid">
                    <b>{b.title}</b>
                    <span>{[b.source, b.published ? b.published.slice(5) : ""].filter(Boolean).join(" · ")}</span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── 이적시장 ── */}
      <Sec en="TRANSFER MARKET" kr="이적 시장" accent={accent} />
      <div className="home-grid">
        <div className="card">
          {feat && (
            <button className="feat" onClick={() => onPickTeam(feat.to)} style={{ ["--tc" as any]: accent }}>
              <div className="feat-tag">최대어</div>
              <div className="feat-row">
                {feat.photo ? <img className="feat-photo" src={feat.photo} alt="" />
                  : feat.to_logo && <img className="feat-logo" src={feat.to_logo} alt="" />}
                <div className="feat-mid">
                  <div className="feat-name">{feat.player}</div>
                  <div className="feat-move">{feat.from} <span className="feat-arr">→</span> {feat.to}</div>
                </div>
                <div className="feat-fee teko" style={{ color: accent }}>{feeLabel(feat.fee_eur, feat.fee_text)}</div>
              </div>
            </button>
          )}
          <div className="rows">
            {deals.slice(1, 6).map((d, i) => (
              <button className="row2" key={i} onClick={() => onPickTeam(d.to)}>
                <span className="row2-idx">{i + 2}</span>
                {d.photo ? <img className="row2-photo" src={d.photo} alt="" />
                  : d.to_logo ? <img src={d.to_logo} alt="" /> : <span className="ph22" />}
                <div className="row2-mid"><b>{d.player}</b><span>{d.from} → {d.to}</span></div>
                <span className="row2-r teko">{feeLabel(d.fee_eur, d.fee_text)}</span>
              </button>
            ))}
            {deals.length === 0 && <div className="mgr-meta">이번 창 영구이적 없음</div>}
          </div>
        </div>

        <div className="card">
          <div className="card-h">순지출 랭킹</div>
          <div className="rows">
            {h.transfers.net_spend.slice(0, 7).map((n) => (
              <button className="netx" key={n.team} onClick={() => onPickTeam(n.team)}>
                {n.logo ? <img src={n.logo} alt="" /> : <span className="ph22" />}
                <span className="netx-team">{n.team}</span>
                <span className="netx-track"><span className="netx-fill" style={{ width: `${(n.spend / maxSpend) * 100}%`, background: accent }} /></span>
                <span className="netx-val teko">{eurM(n.spend)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── 자동 감지 ── */}
      <Sec en="LIVE SIGNALS" kr="자동 감지" accent={accent}
        right={<span className="sec-count">{h.signals.length}</span>} />
      <div className="card">
        <div className="sig-grid">
          {h.signals.slice(0, 8).map((s, i) => (
            <button className={`sigx ${s.tone}`} key={i} onClick={() => s.team && onPickTeam(s.team)}>
              {s.photo
                ? <span className="sigx-av"><img src={s.photo} alt="" /><em>{s.icon}</em></span>
                : <span className="sigx-ic">{s.icon}</span>}
              <div className="sigx-mid">
                <b>{s.title}</b>
                <span>{[s.player, s.detail].filter(Boolean).join(" · ")}</span>
              </div>
              {s.logo && <img className="sigx-logo" src={s.logo} alt="" />}
            </button>
          ))}
        </div>
      </div>

      {/* ── 감독 교체 ── */}
      {h.manager_changes.length > 0 && (
        <>
          <Sec en="THE DUGOUT" kr="감독 교체" accent={accent}
            right={<span className="sec-count">{h.manager_changes.length}</span>} />
          <div className="mgr-rail">
            {h.manager_changes.map((c, i) => (
              <button className="mgx" key={i} onClick={() => onPickTeam(c.team)}>
                {c.photo ? <img className="mgx-photo" src={c.photo} alt="" /> : <span className="mgx-ph" />}
                {c.logo && <img className="mgx-logo" src={c.logo} alt="" />}
                <div className="mgx-name">{c.current.replace(/\s*\(interim\)/i, "")}</div>
                <div className="mgx-prev">
                  {c.previous_photo && <img className="mgx-prev-photo" src={c.previous_photo} alt="" />}
                  ← {c.previous.replace(/\s*\(interim\)/i, "")}
                </div>
                <div className="mgx-meta">{[c.formation, c.changed_at].filter(Boolean).join(" · ")}</div>
              </button>
            ))}
          </div>
        </>
      )}

      {/* ── 뉴스 · 순위 ── */}
      <Sec en="LATEST" kr="뉴스 · 승격·강등" accent={accent} />
      <div className="home-grid">
        <div className="card">
          <div className="card-h">헤드라인</div>
          <div className="rows">
            {h.news.length === 0 && <div className="mgr-meta">뉴스 없음</div>}
            {h.news.slice(0, 6).map((n, i) => (
              <a className="newx" key={i} href={n.link || undefined} target="_blank" rel="noreferrer">
                {n.image ? <img src={n.image} alt="" /> : <span className="newx-ph" />}
                <div className="newx-mid"><b>{n.headline}</b><span>{[n.team, n.source].filter(Boolean).join(" · ")}</span></div>
              </a>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h">승격 · 강등</div>
          <div className="stx-foot" style={{ marginTop: 0 }}>
            {nextLabel} 승격 <b style={{ color: "#4fc27f" }}>{h.roster_next?.promoted?.join(", ") || "-"}</b>
            <br />강등 <b style={{ color: "#e0556b" }}>{h.roster_next?.relegated?.join(", ") || "-"}</b>
          </div>
        </div>
      </div>
    </div>
  );
}
