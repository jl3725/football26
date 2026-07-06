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
import DatabaseTab from "@/components/DatabaseTab";
import TransferTab from "@/components/TransferTab";
import NewsTab from "@/components/NewsTab";

const LEAGUE_TABS = [{ key: "EPL", label: "EPL" }, { key: "LaLiga", label: "LA LIGA" }, { key: "SerieA", label: "SERIE A" }, { key: "Bundesliga", label: "BUNDESLIGA" }, { key: "Ligue1", label: "LIGUE 1" }, { key: "LigaPortugal", label: "LIGA PORTUGAL" }];

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
  const pickTeam = (t: string) => { setHome(false); setSel(t); setTab("overview"); };
  // 리그를 함께 받아 필요 시 리그 전환 후 팀 선택 (월드컵 탭에서 타 리그 클럽 클릭용)
  const pickLeagueTeam = (t: string, lg?: string) => {
    if (lg && lg !== league) { setActiveLeague(lg); setLeagueSel(lg); }
    setHome(false); setSel(t); setTab("overview");
  };
  const DEFAULT_TEAM: Record<string, string> = { EPL: "Arsenal", LaLiga: "Barcelona", SerieA: "Inter", Bundesliga: "Bayern Munich", Ligue1: "PSG", LigaPortugal: "Sporting CP" };
  const leagueName = league === "LaLiga" ? "La Liga" : league === "SerieA" ? "Serie A" : league === "Bundesliga" ? "Bundesliga" : league === "Ligue1" ? "Ligue 1" : league === "LigaPortugal" ? "Liga Portugal" : "Premier League";
  const leagueLabel = league === "LaLiga" ? "LA LIGA" : league === "SerieA" ? "SERIE A" : league === "Bundesliga" ? "BUNDESLIGA" : league === "Ligue1" ? "LIGUE 1" : league === "LigaPortugal" ? "LIGA PORTUGAL" : "EPL";
  const switchLeague = (l: string) => {
    if (l === league) return;
    setActiveLeague(l);
    setLeagueSel(l);
    setSel(DEFAULT_TEAM[l] ?? "");
    setHome(true);
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
    if (tab === "overview") return ov ? <OverviewTab key={sel} ov={ov} accent={accent} /> : <div className="loading">불러오는 중…</div>;
    const props = { team: sel, accent };
    switch (tab) {
      case "signals": return <SignalsTab key={sel} {...props} />;
      case "analytics": return <AnalyticsTab key={sel} {...props} />;
      case "squad": return <SquadTab key={sel} {...props} />;
      case "schedule": return <ScheduleTab key={sel} {...props} />;
      case "player": return <PlayerTab key={sel} {...props} />;
      case "database": return <DatabaseTab key="db" {...props} />;
      case "transfer": return <TransferTab key={sel} {...props} />;
      case "news": return <NewsTab key={sel} {...props} />;
      default: return null;
    }
  }

  const seasonLabel = ctx ? ctx.data_season : "25/26";
  const win = ctx?.window;

  return (
    <div className="app">
      <Sidebar teams={teams} sel={sel}
        onSelect={(t) => { setSel(t); if (home) { setHome(false); setTab("overview"); } }}
        seasonLabel={seasonLabel} next={nextS} atHome={home} onHome={() => setHome(true)}
        league={league} onLeague={switchLeague} />
      <main className="main">
        <StatusBar accent={accent} ctx={ctx} />
        <div className="topbar">
          <div className="tb-team">
            {home
              ? <><span>🏠 리그 홈</span><span className="tb-sep">/</span><span className="tb-tab">{leagueName}</span></>
              : <>{ov?.logo && <img src={ov.logo} alt="" />}<span>{sel}</span><span className="tb-sep">/</span><span className="tb-tab">{meta.label}</span></>}
          </div>
          {!home && (
            <div className="tb-live">
              <span className="livedot" />
              {win?.is_open ? `${win.label} ${win.kr ?? ""} 이적시장 OPEN` : `${seasonLabel} 시즌`}
            </div>
          )}
        </div>

        {!home && <TabBar active={tab} onChange={setTab} accent={accent} />}

        <div className="content" key={home ? "home" : tab}>
          {renderTab()}
        </div>
      </main>
    </div>
  );
}
