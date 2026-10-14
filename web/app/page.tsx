"use client";

import { useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { getTeams, getNextTeams, getOverview, getContext, getRecommend, getDiscover, setActiveLeague, type Team, type NextSeason, type Overview, type Context } from "@/lib/api";
import { accent as toAccent } from "@/lib/ui";
import Sidebar from "@/components/Sidebar";
import StatusBar from "@/components/StatusBar";
import TabBar, { TABS, type TabKey } from "@/components/TabBar";
import HomeDashboard from "@/components/HomeDashboard";
import OverviewTab from "@/components/OverviewTab";
import SignalsTab from "@/components/SignalsTab";
import AnalyticsTab from "@/components/AnalyticsTab";
import SquadTab from "@/components/SquadTab";
import ScheduleTab from "@/components/ScheduleTab";
import PlayerTab from "@/components/PlayerTab";
import GlobalSearch from "@/components/GlobalSearch";
import TransferTab from "@/components/TransferTab";
import ScoutDock from "@/components/ScoutDock";
import NewsTab from "@/components/NewsTab";
import { PeekProvider } from "@/components/PlayerPeek";
import { SkelTab } from "@/components/Skeleton";

const DEFAULT_TEAM: Record<string, string> = { EPL: "Arsenal", LaLiga: "Barcelona", SerieA: "Inter", Bundesliga: "Bayern Munich", Ligue1: "PSG", LigaPortugal: "Sporting CP", Eredivisie: "PSV", BelgianProLeague: "Club Brugge" };
const LEAGUE_TABS = [{ key: "EPL", label: "EPL" }, { key: "LaLiga", label: "LA LIGA" }, { key: "SerieA", label: "SERIE A" }, { key: "Bundesliga", label: "BUNDESLIGA" }, { key: "Ligue1", label: "LIGUE 1" }, { key: "LigaPortugal", label: "LIGA PORTUGAL" }, { key: "Eredivisie", label: "EREDIVISIE" }, { key: "BelgianProLeague", label: "BELGIUM" }];

export default function Page() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [nextS, setNextS] = useState<NextSeason | null>(null);
  const [sel, setSel] = useState<string>("Arsenal");
  const [tab, setTab] = useState<TabKey>("overview");
  const [home, setHome] = useState(true); // 첫 랜딩 = 리그 홈(전역)
  const [league, setLeagueSel] = useState("EPL");
  const [ov, setOv] = useState<Overview | null>(null);
  const [ctx, setCtx] = useState<Context | null>(null);
  const [loading, setLoading] = useState(false);
  const [ovErr, setOvErr] = useState(false);
  const [pendingPlayer, setPendingPlayer] = useState("");   // 전역 검색 딥링크용
  const [navOpen, setNavOpen] = useState(false);
  const [urlReady, setUrlReady] = useState(false);

  // 글꼴 프리셋(?font=sport|modern|classic) — 고르면 이 브라우저에 기억
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search).get("font");
      const f = q || localStorage.getItem("font") || "sport";
      if (q) localStorage.setItem("font", q);
      document.documentElement.dataset.font = f;
    } catch { document.documentElement.dataset.font = "sport"; }
  }, []);

  // 화면 상태 ↔ 주소(?league=LaLiga&team=Barcelona&tab=squad) — 새로고침·링크 공유·뒤로가기 유지.
  // 서버 렌더와 어긋나지 않게 첫 렌더 뒤에 주소를 읽고, 그 전에는 데이터를 부르지 않는다.
  useEffect(() => {
    const apply = () => {
      const p = new URLSearchParams(window.location.search);
      const lg = p.get("league") ?? "";
      const l = LEAGUE_TABS.some((x) => x.key === lg) ? lg : "EPL";
      const t = p.get("team");
      const tb = p.get("tab");
      setActiveLeague(l); setLeagueSel(l);
      if (t) {
        setSel(t); setHome(false);
        setTab(TABS.some((x) => x.key === tb) ? (tb as TabKey) : "overview");
      } else {
        setSel(DEFAULT_TEAM[l] ?? ""); setHome(true);
      }
    };
    apply();
    setUrlReady(true);
    window.addEventListener("popstate", apply);
    return () => window.removeEventListener("popstate", apply);
  }, []);
  useEffect(() => {
    if (!urlReady) return;
    const p = new URLSearchParams();
    if (league !== "EPL") p.set("league", league);
    if (!home && sel) { p.set("team", sel); if (tab !== "overview") p.set("tab", tab); }
    const qs = p.toString() ? `?${p.toString()}` : "";
    if (window.location.search !== qs) window.history.pushState(null, "", qs || window.location.pathname);
  }, [urlReady, league, home, sel, tab]);

  useEffect(() => {
    if (!urlReady) return;
    setActiveLeague(league); // 모든 fetcher 기본 리그 갱신
    getTeams().then(setTeams).catch(() => {});
    getNextTeams().then(setNextS).catch(() => {});
    getContext().then(setCtx).catch(() => {});
  }, [league, urlReady]);
  // Recruit 탭의 무거운 계산(추천·탐색)을 Overview 를 보는 사이 미리 요청 — 서버 캐시가 채워져 탭을 열면
  // 바로 뜬다(무료 서버 첫 계산 수 초). 팀을 빠르게 넘길 때 낭비하지 않게 2.5초 머문 경우만.
  useEffect(() => {
    if (!urlReady || !sel || home) return;
    const t = setTimeout(() => {
      getRecommend(sel).catch(() => {});
      getDiscover(sel, { top: 40 }).catch(() => {});
    }, 2500);
    return () => clearTimeout(t);
  }, [sel, home, urlReady]);
  useEffect(() => {
    if (!urlReady || !sel) return;
    let alive = true;
    setLoading(true); setOvErr(false);
    getOverview(sel)
      .then((d) => { if (alive) { setOv(d); setLoading(false); } })
      .catch(() => { if (alive) { setOv(null); setOvErr(true); setLoading(false); } });
    return () => { alive = false; };
  }, [sel, urlReady]);

  const accent = ov ? toAccent(ov.color) : "#ff4d5e";
  const meta = TABS.find((t) => t.key === tab)!;

  const isPromoted = !!nextS?.promoted?.includes(sel);
  const pickTeam = (t: string) => { setHome(false); setSel(t); setTab("overview"); setNavOpen(false); };
  // 리그를 함께 받아 필요 시 리그 전환 후 팀 선택 (월드컵 탭에서 타 리그 클럽 클릭용)
  const pickLeagueTeam = (t: string, lg?: string) => {
    if (lg && lg !== league) { setActiveLeague(lg); setLeagueSel(lg); }
    setHome(false); setSel(t); setTab("overview"); setNavOpen(false);
  };
  // 전역 검색: 선수 클릭 → 소속팀으로 이동 + Player 탭에 그 선수 카드 표시
  const pickPlayer = (club: string, lg: string, player: string) => {
    if (lg && lg !== league) { setActiveLeague(lg); setLeagueSel(lg); }
    setHome(false); setSel(club); setPendingPlayer(player); setTab("player"); setNavOpen(false);
  };
  const leagueName = league === "LaLiga" ? "La Liga" : league === "SerieA" ? "Serie A" : league === "Bundesliga" ? "Bundesliga" : league === "Ligue1" ? "Ligue 1" : league === "LigaPortugal" ? "Liga Portugal" : league === "Eredivisie" ? "Eredivisie" : league === "BelgianProLeague" ? "Belgian Pro League" : "Premier League";
  const leagueLabel = league === "LaLiga" ? "LA LIGA" : league === "SerieA" ? "SERIE A" : league === "Bundesliga" ? "BUNDESLIGA" : league === "Ligue1" ? "LIGUE 1" : league === "LigaPortugal" ? "LIGA PORTUGAL" : league === "Eredivisie" ? "EREDIVISIE" : league === "BelgianProLeague" ? "BELGIUM" : "EPL";
  const switchLeague = (l: string) => {
    if (l === league) return;
    setActiveLeague(l);
    setLeagueSel(l);
    setSel(DEFAULT_TEAM[l] ?? "");
    setHome(true);
    setNavOpen(false);
  };

  function renderTab() {
    if (!urlReady) return <SkelTab />;
    if (home) return <HomeDashboard accent={accent} onPickTeam={pickTeam} onPickLeagueTeam={pickLeagueTeam}
      leagueLabel={leagueLabel} league={league} leagues={LEAGUE_TABS} onLeague={switchLeague} />;
    if (ovErr) return (
      <div className="nodata-card">
        <div className="nodata-emoji">{isPromoted ? "🆙" : "📭"}</div>
        <h3>{sel}</h3>
        <p>{isPromoted
          ? `${nextS?.season_label ?? ""} 승격팀입니다. 프리미어리그 스탯·라인업은 시즌 시작 후 수집됩니다.`
          : "이 구단의 데이터가 아직 없습니다."}</p>
      </div>
    );
    if (tab === "overview") return ov ? <OverviewTab key={sel} ov={ov} accent={accent} /> : <SkelTab />;
    const props = { team: sel, accent };
    switch (tab) {
      case "signals": return <SignalsTab key={sel} {...props} />;
      case "analytics": return <AnalyticsTab key={sel} {...props} />;
      case "squad": return <SquadTab key={sel} {...props} />;
      case "schedule": return <ScheduleTab key={sel} {...props} />;
      case "player": return <PlayerTab key={sel} team={sel} accent={accent} initialPlayer={pendingPlayer} />;
      case "transfer": return <TransferTab key={sel} {...props} />;
      case "news": return <NewsTab key={sel} {...props} />;
      default: return null;
    }
  }

  const seasonLabel = ctx ? ctx.data_season : "";
  const win = ctx?.window;

  return (
    <PeekProvider onOpenPlayer={(club, lg, p) => pickPlayer(club, lg, p)} onOpenTeam={(club, lg) => pickLeagueTeam(club, lg)}>
    <div className={`app${navOpen ? " nav-open" : ""}`} style={{ ["--accent" as any]: accent }}>
      <div className="app-atmosphere" aria-hidden="true" />
      <button className="nav-scrim" aria-label="메뉴 닫기" onClick={() => setNavOpen(false)} />
      <Sidebar teams={teams} sel={sel}
        onSelect={(t) => { setSel(t); setNavOpen(false); if (home) { setHome(false); setTab("overview"); } }}
        seasonLabel={seasonLabel} next={nextS} phase={ctx?.window?.phase} atHome={home} onHome={() => {
          setHome(true);
          setNavOpen(false);
        }}
        league={league} onLeague={switchLeague} />
      <main className="main">
        <div className="workspace-shell">
          <div className="workspace-rail">
            <button
              className="mobile-nav-toggle"
              aria-label="구단 및 리그 메뉴 열기"
              aria-controls="primary-navigation"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <span /><span /><span />
            </button>
            <StatusBar accent={accent} ctx={ctx} league={league} />
          </div>

          <header className="workspace-header">
            <div className="workspace-context">
              <div className="workspace-kicker">
                <span className="context-pulse" />
                {home ? "LEAGUE INTELLIGENCE" : `${leagueLabel} · CLUB WORKSPACE`}
              </div>
              <div className="topbar">
                <div className="tb-team">
                  {!home && ov?.logo && <img src={ov.logo} alt="" />}
                  <div>
                    <h1>{home ? leagueName : sel}</h1>
                    <div className="tb-path">
                      <span>{home ? "Situation room" : leagueName}</span>
                      <span className="tb-sep">/</span>
                      <span className="tb-tab">{home ? `${seasonLabel} 운영 현황` : meta.label}</span>
                    </div>
                  </div>
                </div>
                <div className="tb-live">
                  <span className="livedot" />
                  {win?.is_open ? `${win.label} ${win.kr ?? ""} WINDOW` : `${seasonLabel} SEASON`}
                </div>
              </div>
            </div>
            <div className="global-search-wrap">
              <span className="search-caption">GLOBAL DATABASE</span>
              <GlobalSearch accent={accent} onPickPlayer={pickPlayer} onPickTeam={pickLeagueTeam} />
            </div>
          </header>

          {!home && <TabBar active={tab} accent={accent} onChange={(k) => {
            // 탭 전환을 부드럽게 — View Transitions API(크롬·엣지·사파리 18+), 미지원·움직임 줄이기 설정이면 즉시
            const d = document as Document & { startViewTransition?: (cb: () => void) => unknown };
            const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            if (d.startViewTransition && !reduce) d.startViewTransition(() => flushSync(() => setTab(k)));
            else setTab(k);
          }} />}

          <div className="content" key={home ? "home" : tab}>
            {renderTab()}
          </div>
        </div>
      </main>

      {/* 전역 AI 어시스턴트 — 어느 탭/팀에서도 우하단 버블(⌘K)로 열림, 컨텍스트=현재 팀 */}
      <ScoutDock team={home ? "" : sel} league={league} accent={accent} onNavigate={pickLeagueTeam} />
    </div>
    </PeekProvider>
  );
}
