"use client";

import { useEffect, useState } from "react";
import { getTeams, getNextTeams, getOverview, getContext, setActiveLeague, type Team, type NextSeason, type Overview, type Context } from "@/lib/api";
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

  useEffect(() => {
    setActiveLeague(league); // 모든 fetcher 기본 리그 갱신
    getTeams().then(setTeams).catch(() => {});
    getNextTeams().then(setNextS).catch(() => {});
    getContext().then(setCtx).catch(() => {});
  }, [league]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setOvErr(false);
    getOverview(sel)
      .then((d) => { if (alive) { setOv(d); setLoading(false); } })
      .catch(() => { if (alive) { setOv(null); setOvErr(true); setLoading(false); } });
    return () => { alive = false; };
  }, [sel]);

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
  const DEFAULT_TEAM: Record<string, string> = { EPL: "Arsenal", LaLiga: "Barcelona", SerieA: "Inter", Bundesliga: "Bayern Munich", Ligue1: "PSG", LigaPortugal: "Sporting CP", Eredivisie: "PSV", BelgianProLeague: "Club Brugge" };
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

  const seasonLabel = ctx ? ctx.data_season : "25/26";
  const win = ctx?.window;

  return (
    <PeekProvider onOpenPlayer={(club, lg, p) => pickPlayer(club, lg, p)} onOpenTeam={(club, lg) => pickLeagueTeam(club, lg)}>
    <div className={`app${navOpen ? " nav-open" : ""}`} style={{ ["--accent" as any]: accent }}>
      <div className="app-atmosphere" aria-hidden="true" />
      <button className="nav-scrim" aria-label="메뉴 닫기" onClick={() => setNavOpen(false)} />
      <Sidebar teams={teams} sel={sel}
        onSelect={(t) => { setSel(t); setNavOpen(false); if (home) { setHome(false); setTab("overview"); } }}
        seasonLabel={seasonLabel} next={nextS} atHome={home} onHome={() => {
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
            <StatusBar accent={accent} ctx={ctx} />
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

          {!home && <TabBar active={tab} onChange={setTab} accent={accent} />}

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
