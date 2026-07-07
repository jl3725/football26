"use client";
import { useState } from "react";
import type { Team, NextSeason } from "@/lib/api";

// 리그 티어 — 리그 확장 시 여기 배열에만 추가.
//   TIER S = 빅5 · TIER A = 유럽 강호 · 원석 발굴(TALENT) = 셀링/유망주 공급 리그
type LeagueBtn = { k: string; label: string; soon?: boolean };
const TIER_S: LeagueBtn[] = [
  { k: "EPL", label: "🏴 EPL" }, { k: "LaLiga", label: "🇪🇸 La Liga" },
  { k: "SerieA", label: "🇮🇹 Serie A" }, { k: "Bundesliga", label: "🇩🇪 Bundesliga" },
  { k: "Ligue1", label: "🇫🇷 Ligue 1" },
];
const TIER_A: LeagueBtn[] = [
  { k: "Eredivisie", label: "🇳🇱 Eredivisie" }, { k: "LigaPortugal", label: "🇵🇹 Liga Portugal" },
];
const TIER_TALENT: LeagueBtn[] = [
  { k: "BelgianProLeague", label: "🇧🇪 Belgian Pro" },
  { k: "Austria", label: "🇦🇹 Austria", soon: true },
  { k: "Brazil", label: "🇧🇷 Brazil", soon: true },
  { k: "Argentina", label: "🇦🇷 Argentina", soon: true },
];

// 다음 시즌 라벨 ("25/26" → "26/27")
function nextSeasonLabel(cur: string): string {
  const m = cur.match(/(\d{2})\s*\/\s*(\d{2})/);
  if (!m) return "26/27";
  const a = (parseInt(m[1], 10) + 1) % 100;
  const b = (parseInt(m[2], 10) + 1) % 100;
  return `${String(a).padStart(2, "0")}/${String(b).padStart(2, "0")}`;
}

// 리그 순위 → 진출권/강등 존. EPL 기준(잉글랜드 5 UCL 보유 시즌).
function zoneOf(rank: number, total: number): { cls: string; tag: string } {
  if (total >= 6 && rank >= total - 2) return { cls: "z-rel", tag: "강등" };
  if (rank === 1) return { cls: "z-title", tag: "우승" };
  if (rank <= 5) return { cls: "z-ucl", tag: "UCL" };
  if (rank === 6) return { cls: "z-uel", tag: "UEL" };
  if (rank === 7) return { cls: "z-ecl", tag: "ECL" };
  return { cls: "", tag: "" };
}

export default function Sidebar({
  teams, sel, onSelect, seasonLabel = "25/26", next = null, atHome = false, onHome,
  league = "EPL", onLeague,
}: {
  teams: Team[]; sel: string; onSelect: (t: string) => void;
  seasonLabel?: string; next?: NextSeason | null;
  atHome?: boolean; onHome?: () => void;
  league?: string; onLeague?: (l: string) => void;
}) {
  const [seasonTab, setSeasonTab] = useState<"next" | "cur">("next"); // 새 시즌 먼저
  const nextLabel = next?.season_label || nextSeasonLabel(seasonLabel);
  const total = teams.length;
  const leagueTitle = league === "LaLiga" ? "La Liga" : league === "SerieA" ? "Serie A" : league === "Bundesliga" ? "Bundesliga" : league === "Ligue1" ? "Ligue 1" : league === "LigaPortugal" ? "Liga Portugal" : league === "Eredivisie" ? "Eredivisie" : league === "BelgianProLeague" ? "Belgian Pro League" : "Premier League";

  // 25/26: 최종 순위순
  const curShown = [...teams].sort((a, b) => a.rank - b.rank);
  // 26/27: 감지된 실제 로스터(승격/강등 반영), 알파벳순. 없으면 현재 팀 폴백.
  const nextShown = (next?.teams?.length
    ? next.teams
    : teams.map((t) => ({ name: t.name, color: t.color, logo: t.logo, promoted: false }))
  ).slice().sort((a, b) => a.name.localeCompare(b.name));

  return (
    <aside className="side">
      <div className="brand">
        <div className="brand-orb" />
        <div>
          <div className="brand-name">SCOUT<span style={{ color: "var(--accent)" }}>.AI</span></div>
          <div className="brand-sub">Football Intelligence</div>
        </div>
      </div>

      <div className="league-tiers">
        <div className="tier-label tier-s">TIER&nbsp;S <em>빅5</em></div>
        <div className="league-seg">
          {TIER_S.map((l) => (
            <button key={l.k} className={league === l.k ? "active" : ""} onClick={() => onLeague?.(l.k)}>{l.label}</button>
          ))}
        </div>
        <div className="tier-label">TIER&nbsp;A <em>유럽 강호</em></div>
        <div className="league-seg">
          {TIER_A.map((l) => (
            <button key={l.k} className={league === l.k ? "active" : ""} onClick={() => onLeague?.(l.k)}>{l.label}</button>
          ))}
        </div>
        <div className="tier-label tier-talent">원석 발굴 <em>TALENT</em></div>
        <div className="league-seg">
          {TIER_TALENT.map((l) => l.soon
            ? <button key={l.k} className="soon" disabled title="곧 추가 예정">{l.label}</button>
            : <button key={l.k} className={league === l.k ? "active" : ""} onClick={() => onLeague?.(l.k)}>{l.label}</button>
          )}
        </div>
      </div>

      <button className={`home-nav${atHome ? " active" : ""}`} onClick={() => onHome?.()}>
        <span className="home-nav-mark" />
        <span className="home-nav-txt">
          <span className="home-nav-t">리그 홈</span>
          <span className="home-nav-sub">{league === "LaLiga" ? "LA LIGA" : league === "SerieA" ? "SERIE A" : league === "Bundesliga" ? "BUNDESLIGA" : league === "Ligue1" ? "LIGUE 1" : league === "LigaPortugal" ? "LIGA PORTUGAL" : league === "Eredivisie" ? "EREDIVISIE" : league === "BelgianProLeague" ? "BELGIUM" : "PREMIER LEAGUE"}</span>
        </span>
        <span className="home-nav-dot" />
      </button>

      <div className="side-tabs">
        <button className={seasonTab === "next" ? "active" : ""} onClick={() => setSeasonTab("next")}>{nextLabel}</button>
        <button className={seasonTab === "cur" ? "active" : ""} onClick={() => setSeasonTab("cur")}>{seasonLabel}</button>
      </div>
      <div className="side-label">
        {leagueTitle} · {seasonTab === "next" ? `${nextLabel} (개막 전)` : seasonLabel}
      </div>

      <div className="team-scroll">
        {seasonTab === "cur"
          ? curShown.map((t) => {
              const z = zoneOf(t.rank, total);
              return (
                <button key={t.name}
                  className={`team-btn ${z.cls}${t.name === sel ? " active" : ""}`}
                  onClick={() => onSelect(t.name)}
                  style={t.name === sel ? { ["--tc" as any]: t.color } : undefined}>
                  <span className="rankchip">{t.rank}</span>
                  {t.logo ? <img src={t.logo} alt="" /> : <span style={{ width: 22 }} />}
                  <span className="tn">{t.name}</span>
                  <span className="pts">{t.points}</span>
                </button>
              );
            })
          : nextShown.map((t) => (
              <button key={t.name}
                className={`team-btn${t.name === sel ? " active" : ""}`}
                onClick={() => onSelect(t.name)}
                style={t.name === sel ? { ["--tc" as any]: t.color } : undefined}>
                <span className="rankchip">·</span>
                {t.logo ? <img src={t.logo} alt="" /> : <span style={{ width: 22 }} />}
                <span className="tn">{t.name}</span>
                {t.promoted && <span className="promo-badge">승격</span>}
              </button>
            ))}
        {(seasonTab === "cur" ? curShown : nextShown).length === 0 && <div className="empty">검색 결과 없음</div>}
      </div>

      {seasonTab === "cur" && (
        <div className="zone-legend">
          <span><i className="z-dot z-title" />우승</span>
          <span><i className="z-dot z-ucl" />UCL</span>
          <span><i className="z-dot z-uel" />UEL</span>
          <span><i className="z-dot z-ecl" />ECL</span>
          <span><i className="z-dot z-rel" />강등</span>
        </div>
      )}
      {seasonTab === "next" && (
        <div className="side-note">
          {next?.promoted?.length
            ? <>개막 전 · 알파벳순 · <b style={{ color: "#4fc27f" }}>승격</b> {next.promoted.join(", ")} / <b style={{ color: "#e07070" }}>강등</b> {next.relegated.join(", ")}</>
            : "개막 전 · 알파벳순. 승격/강등 반영은 시즌 감지 후 갱신됩니다."}
        </div>
      )}
    </aside>
  );
}
