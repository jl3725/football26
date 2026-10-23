"use client";

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import dynamic from "next/dynamic";
import { useTracking } from "@/lib/tracking";
import { getTeams, getNextTeams, getOverview, getContext, getRecommend, getDiscover, setActiveLeague, type Team, type NextSeason, type Overview, type Context } from "@/lib/api";
import { accent as toAccent } from "@/lib/ui";
import Sidebar from "@/components/Sidebar";
import StatusBar from "@/components/StatusBar";
import TabBar, { TABS, type TabKey } from "@/components/TabBar";
import GlobalSearch from "@/components/GlobalSearch";
import ScoutDock from "@/components/ScoutDock";
import { PeekProvider } from "@/components/PlayerPeek";
import { MatchPreviewProvider } from "@/components/MatchPreview";
import { LiveProvider } from "@/lib/live";
import { StandingsProvider } from "@/lib/standings";
import { SkelTab } from "@/components/Skeleton";
import { DEFAULT_TEAM, LEAGUE_TABS, leagueLabel as leagueLabelOf, leagueName as leagueNameOf } from "@/lib/leagues";

// 화면별 코드 나누기 — 홈·팀 탭은 열 때 받는다(첫 화면 JS 를 줄여 모바일에서 덜 무겁게, 2026-10-22).
// 첫 화면이 뜬 뒤 쉬는 시간에 나머지도 미리 받아 탭을 눌렀을 때 기다리지 않게 한다(prefetchViews — 같은 import 라 덩어리 하나).
const skel = () => <SkelTab />;
const HomeDashboard = dynamic(() => import("@/components/HomeDashboard"), { loading: skel });
const OverviewTab = dynamic(() => import("@/components/OverviewTab"), { loading: skel });
const SignalsTab = dynamic(() => import("@/components/SignalsTab"), { loading: skel });
const AnalyticsTab = dynamic(() => import("@/components/AnalyticsTab"), { loading: skel });
const SquadTab = dynamic(() => import("@/components/SquadTab"), { loading: skel });
const NetworkTab = dynamic(() => import("@/components/NetworkTab"), { loading: skel });
const ScheduleTab = dynamic(() => import("@/components/ScheduleTab"), { loading: skel });
const PlayerTab = dynamic(() => import("@/components/PlayerTab"), { loading: skel });
const TransferTab = dynamic(() => import("@/components/TransferTab"), { loading: skel });
const NewsTab = dynamic(() => import("@/components/NewsTab"), { loading: skel });
const VIEWS = [
  () => import("@/components/HomeDashboard"), () => import("@/components/OverviewTab"), () => import("@/components/SignalsTab"),
  () => import("@/components/AnalyticsTab"), () => import("@/components/SquadTab"), () => import("@/components/NetworkTab"),
  () => import("@/components/ScheduleTab"), () => import("@/components/PlayerTab"), () => import("@/components/TransferTab"),
  () => import("@/components/NewsTab"),
];

function prefetchViews() {
  const run = () => { for (const load of VIEWS) load().catch(() => {}); };
  const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number };
  if (w.requestIdleCallback) w.requestIdleCallback(run, { timeout: 6000 });
  else setTimeout(run, 3000);
}

// 리그 목록·기본 팀·이름은 lib/leagues.ts 한 곳

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
  const [urlPlayer, setUrlPlayer] = useState("");           // Player 탭에서 고른 선수 — 주소에 남겨 공유·새로고침 유지
  const [homeView, setHomeView] = useState<"all" | "league" | "INTL">("all");   // 전체 홈 · 리그 홈 · 국가대표
  const [intlComp, setIntlComp] = useState<string | undefined>(undefined);       // ?wc=1(예전 링크) → 월드컵 기록
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

  // 화면 상태 ↔ 주소 — 새로고침·링크 공유·뒤로가기 유지. 서버 렌더와 어긋나지 않게 첫 렌더 뒤에 주소를 읽는다.
  //   /                       전체 홈            /?league=LaLiga        라리가 리그 홈        /?wc=1  월드컵
  //   /?league=LaLiga&team=Barcelona&tab=squad   팀 화면 · &tab=player&player=Lamine%20Yamal 선수
  // 예전엔 리그 홈이 주소에 없어 새로고침·뒤로 가기·사이드바 '리그 홈'이 모두 전체 홈으로 갔다(2026-10-20 점검).
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
        const pl = p.get("player");                       // ?tab=player&player=Bukayo Saka — 선수 바로 열기(공유 링크·QA)
        setPendingPlayer(pl ?? ""); setUrlPlayer(pl ?? "");
      } else {
        setSel(DEFAULT_TEAM[l] ?? ""); setHome(true);
        setHomeView(p.get("intl") || p.get("wc") ? "INTL" : p.has("league") ? "league" : "all");
        setIntlComp(p.get("wc") ? "fifa.world" : p.get("comp") ?? undefined);
      }
    };
    apply();
    setUrlReady(true);
    prefetchViews();
    window.addEventListener("popstate", apply);
    return () => window.removeEventListener("popstate", apply);
  }, []);
  useEffect(() => {
    if (!urlReady) return;
    const p = new URLSearchParams();
    if (home) {
      if (homeView === "league") p.set("league", league);        // 리그 홈은 EPL 도 주소에 남긴다
      else if (homeView === "INTL") p.set("intl", "1");
    } else {
      if (league !== "EPL") p.set("league", league);
      if (sel) {
        p.set("team", sel);
        if (tab !== "overview") p.set("tab", tab);
        if (tab === "player" && urlPlayer) p.set("player", urlPlayer);
        // 스카우팅 리포트가 열려 있으면 공유 링크에 남긴다(PlayerTab 이 열고 닫을 때 report=1 을 넣고 뺀다)
        if (tab === "player" && new URLSearchParams(window.location.search).get("report") === "1") p.set("report", "1");
      }
    }
    const qs = p.toString() ? `?${p.toString()}` : "";
    if (window.location.search !== qs) window.history.pushState(null, "", qs || window.location.pathname);
  }, [urlReady, league, home, homeView, sel, tab, urlPlayer]);

  useEffect(() => {
    if (!urlReady) return;
    setActiveLeague(league); // 모든 fetcher 기본 리그 갱신
    getTeams().then(setTeams).catch(() => {});
    getNextTeams().then(setNextS).catch(() => {});
    getContext().then(setCtx).catch(() => {});
  }, [league, urlReady]);
  // Recruit 탭의 무거운 계산(추천·탐색)은 그 탭에 마우스를 올리거나 포커스·터치할 때 미리 요청 — 누르는 사이 서버가 계산.
  // 예전엔 팀 화면마다 2.5초 뒤 무조건 보내서, 배포 직후 빈 캐시에서 Overview 요청들과 0.1 CPU 를 다퉈
  // 개요가 17~28초 걸렸고(2026-10-22 측정), 탐색은 top=40 이라 탭이 쓰는 top=150 캐시도 못 데웠다.
  const warmed = useRef<Set<string>>(new Set());
  const onTabIntent = (k: TabKey) => {
    if (k !== "transfer" || !sel || warmed.current.has(`${league}|${sel}`)) return;
    warmed.current.add(`${league}|${sel}`);
    getRecommend(sel).catch(() => {});
    getDiscover(sel, { top: 150 }).catch(() => {});                // RecruitPool 첫 요청과 같은 주소
  };
  useEffect(() => {
    if (!urlReady || !sel) return;
    let alive = true;
    setLoading(true); setOvErr(false);
    getOverview(sel)
      .then((d) => { if (alive) { setOv(d); setLoading(false); } })
      .catch(() => { if (alive) { setOv(null); setOvErr(true); setLoading(false); } });
    return () => { alive = false; };
  }, [sel, urlReady]);

  // 팀 색은 팀 화면에서만 — 전체·리그 홈은 브랜드 색(예전엔 홈도 마지막 팀(아스날) 빨강으로 물들었다)
  const accent = !home && ov ? toAccent(ov.color) : "#ff4d5e";
  const tracking = useTracking(home ? "" : sel);   // Inbox 탭 숫자 = 읽지 않은 영입 후보 소식(Signals 맨 위 TRACKING 과 같은 응답)
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
    setHome(false); setSel(club); setPendingPlayer(player); setUrlPlayer(player); setTab("player"); setNavOpen(false);
  };
  const leagueName = leagueNameOf(league);
  const leagueLabel = leagueLabelOf(league);
  const switchLeague = (l: string) => {
    if (l === league) { setHome(true); setHomeView("league"); setNavOpen(false); return; }
    setActiveLeague(l);
    setLeagueSel(l);
    setSel(DEFAULT_TEAM[l] ?? "");
    setHome(true);
    setHomeView("league");                                 // 리그를 고르면 그 리그 홈으로(전체 홈이 아니라)
    setNavOpen(false);
  };

  function renderTab() {
    if (!urlReady) return <SkelTab />;
    if (home) return <HomeDashboard accent={accent} onPickTeam={pickTeam} onPickLeagueTeam={pickLeagueTeam}
      leagueLabel={leagueLabel} league={league} leagues={LEAGUE_TABS} onLeague={switchLeague}
      view={homeView} onView={setHomeView} initialIntlComp={intlComp} />;
    if (ovErr) return (
      <div className="nodata-card">
        <div className="nodata-emoji">{isPromoted ? "🆙" : "📭"}</div>
        <h3>{sel}</h3>
        <p>{isPromoted
          ? `${leagueName} 승격팀 · 개막 후 수집`
          : "이 구단의 데이터가 아직 없습니다."}</p>
      </div>
    );
    if (tab === "overview") return ov ? <OverviewTab key={sel} ov={ov} accent={accent} /> : <SkelTab />;
    const props = { team: sel, accent };
    switch (tab) {
      case "signals": return <SignalsTab key={sel} {...props} />;
      case "analytics": return <AnalyticsTab key={sel} {...props} />;
      case "squad": return <SquadTab key={sel} {...props} />;
      case "network": return <NetworkTab key={sel} {...props} />;
      case "schedule": return <ScheduleTab key={sel} {...props} />;
      case "player": return <PlayerTab key={sel} team={sel} accent={accent} initialPlayer={pendingPlayer} onPlayer={setUrlPlayer} />;
      case "transfer": return <TransferTab key={sel} {...props} />;
      case "news": return <NewsTab key={sel} {...props} />;
      default: return null;
    }
  }

  const seasonLabel = ctx ? ctx.data_season : "";
  const win = ctx?.window;

  return (
    <PeekProvider onOpenPlayer={(club, lg, p) => pickPlayer(club, lg, p)} onOpenTeam={(club, lg) => pickLeagueTeam(club, lg)}>
    <LiveProvider>
    <StandingsProvider>
    <MatchPreviewProvider>
    <div className={`app${navOpen ? " nav-open" : ""}${home ? " at-home" : ""}`} style={{ ["--accent" as any]: accent }}>
      <div className="app-atmosphere" aria-hidden="true" />
      <button className="nav-scrim" aria-label="메뉴 닫기" onClick={() => setNavOpen(false)} />
      <Sidebar teams={teams} sel={sel}
        onSelect={(t) => { setSel(t); setNavOpen(false); if (home) { setHome(false); setTab("overview"); } }}
        seasonLabel={seasonLabel} next={nextS} phase={ctx?.window?.phase} atHome={home && homeView === "league"} onHome={() => {
          setHome(true);
          setHomeView("league");                             // 사이드바 '리그 홈' = 지금 리그의 홈(전체 홈 아님)
          setNavOpen(false);
        }}
        league={league} onLeague={switchLeague} onPickTeam={pickLeagueTeam} />
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

          <header className={`workspace-header${home ? " is-home" : ""}`}>
            {/* 홈은 대시보드가 자기 제목을 갖는다('오늘의 축구'·리그 이름) — 여기선 검색만 */}
            {!home && <div className="workspace-context">
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
            </div>}
            <div className="global-search-wrap">
              <span className="search-caption">GLOBAL DATABASE</span>
              <GlobalSearch accent={accent} onPickPlayer={pickPlayer} onPickTeam={pickLeagueTeam} />
            </div>
          </header>

          {!home && <TabBar active={tab} accent={accent} onIntent={onTabIntent} badges={{ signals: tracking.nNew }} onChange={(k) => {
            // 탭 전환을 부드럽게 — View Transitions API(크롬·엣지·사파리 18+), 미지원·움직임 줄이기 설정이면 즉시
            type VT = { ready?: Promise<void>; finished?: Promise<void>; updateCallbackDone?: Promise<void> };
            const d = document as Document & { startViewTransition?: (cb: () => void) => VT };
            const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            if (d.startViewTransition && !reduce) {
              // 탭을 빠르게 연달아 누르면 앞 전환이 '건너뜀'으로 끝난다 — 정상 동작이라 조용히 넘긴다(콘솔 오류 방지)
              const vt = d.startViewTransition(() => flushSync(() => setTab(k)));
              for (const pr of [vt?.ready, vt?.finished, vt?.updateCallbackDone]) pr?.catch(() => {});
            } else setTab(k);
          }} />}

          <div className="content" key={home ? "home" : tab}>
            {renderTab()}
          </div>
        </div>
      </main>

      {/* 전역 AI 어시스턴트 — 어느 탭/팀에서도 우하단 버블(⌘K)로 열림, 컨텍스트=현재 팀 */}
      <ScoutDock team={home ? "" : sel} league={league} accent={accent} onNavigate={pickLeagueTeam} />
    </div>
    </MatchPreviewProvider>
    </StandingsProvider>
    </LiveProvider>
    </PeekProvider>
  );
}
