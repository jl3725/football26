"use client";
import { useStandings } from "@/lib/standings";
import { useState } from "react";
import type { Team, NextSeason } from "@/lib/api";
import { showNextSeason, type Phase } from "@/lib/season";
import { usePins } from "@/lib/pins";
import { TIER_LABEL, leagueInfo, leagueLabel, leagueName } from "@/lib/leagues";
import { useLeagueGroups } from "@/lib/leagueMap";

// 다음 시즌 라벨 (현재 "YY/YY" → 한 해 뒤). 시즌 문구는 박아 두지 않는다 — scripts/check_season_literals.py
function nextSeasonLabel(cur: string): string {
  const m = cur.match(/(\d{2})\s*\/\s*(\d{2})/);
  if (!m) return "";
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
  teams, sel, onSelect, seasonLabel = "", next = null, atHome = false, onHome,
  league = "EPL", onLeague, phase, onPickTeam,
}: {
  teams: Team[]; sel: string; onSelect: (t: string) => void;
  seasonLabel?: string; next?: NextSeason | null; phase?: Phase;
  atHome?: boolean; onHome?: () => void;
  league?: string; onLeague?: (l: string) => void;
  onPickTeam?: (team: string, league: string) => void;
}) {
  const { pins } = usePins();
  const groups = useLeagueGroups();
  const [pickedTab, setSeasonTab] = useState<"next" | "cur">("next"); // 오프시즌엔 새 시즌 먼저
  // 시즌 중에는 '다음 시즌' 탭이 현재 시즌과 같아 숨기고 현재 순위만(단계 로딩 전에도 깜빡임 없이 현재 순위)
  const hasNext = !!phase && showNextSeason({ phase });
  const seasonTab = hasNext ? pickedTab : "cur";
  const nextLabel = next?.season_label || nextSeasonLabel(seasonLabel);
  const total = teams.length;
  const leagueTitle = leagueName(league);

  // 현재 데이터 시즌: 순위순 — 리그 경기 중·직후엔 잠정 순위(lib/standings: 공식 순위 + 라이브 스코어)
  const ls = useStandings(league);
  const curShown = teams.map((t) => {
    const r = ls.on ? ls.byTeam.get(t.name) : undefined;
    return r ? { ...t, rank: r.rank, points: r.points, live: r.live, move: r.move } : { ...t, live: undefined, move: 0 };
  }).sort((a, b) => a.rank - b.rank);
  // 다음 시즌: 감지된 실제 로스터(승격/강등 반영), 알파벳순. 없으면 현재 팀 폴백.
  const nextShown = (next?.teams?.length
    ? next.teams
    : teams.map((t) => ({ name: t.name, color: t.color, logo: t.logo, promoted: false }))
  ).slice().sort((a, b) => a.name.localeCompare(b.name));

  return (
    <aside id="primary-navigation" className="side">
      <div className="brand">
        <div className="brand-orb" aria-hidden="true"><span /><span /></div>
        <div>
          <div className="brand-name">SCOUT<span>.AI</span></div>
          <div className="brand-sub">Decision intelligence</div>
        </div>
        <span className="brand-version">26</span>
      </div>

      <div className="competition-picker">
        <label htmlFor="competition-select">Competition</label>
        <div className="competition-select-wrap">
          <span className="competition-mark" aria-hidden="true" />
          <select
            id="competition-select"
            value={league}
            onChange={(event) => onLeague?.(event.target.value)}
            aria-label="리그 선택"
          >
            {/* 홈 리그 지도와 같은 묶음 — 티어는 서버가 리그 수준으로 매김, 2부 리그는 1부 바로 뒤 ↳ */}
            {([1, 2, 3] as const).map((t) => (
              <optgroup key={t} label={TIER_LABEL[t]}>
                {groups[t].filter((l) => !l.soon).flatMap((l) => [l, ...l.subs.map((s) => ({ ...s, sub: true }))]).map((l) => (
                  <option key={l.key} value={l.key}>{"sub" in l ? "↳ " : `${leagueInfo(l.key)?.flag ?? ""} `}{l.short}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <span className="competition-chevron" aria-hidden="true">⌄</span>
        </div>
      </div>

      <button className={`home-nav${atHome ? " active" : ""}`} onClick={() => onHome?.()} aria-current={atHome ? "page" : undefined}>
        <span className="home-nav-mark" />
        <span className="home-nav-txt">
          <span className="home-nav-t">리그 홈</span>
          <span className="home-nav-sub">{league === "EPL" ? "PREMIER LEAGUE" : leagueLabel(league)}</span>
        </span>
        <span className="home-nav-dot" />
      </button>

      {/* 내 팀 — 팀 화면 ☆ 로 고정(이 브라우저에만 저장). 리그가 달라도 한 번에 이동 */}
      {pins.length > 0 && (
        <div className="side-pins">
          <div className="side-label">내 팀</div>
          {pins.map((p) => (
            <button key={p.team} className={`team-btn pin${p.team === sel && !atHome ? " active" : ""}`}
              onClick={() => onPickTeam?.(p.team, p.league)}>
              <span className="rankchip pin-star">★</span>
              {p.logo ? <img src={p.logo} alt="" /> : <span style={{ width: 22 }} />}
              <span className="tn">{p.team}</span>
            </button>
          ))}
        </div>
      )}

      {hasNext && (
        <div className="side-tabs">
          <button className={seasonTab === "next" ? "active" : ""} onClick={() => setSeasonTab("next")}>{nextLabel}</button>
          <button className={seasonTab === "cur" ? "active" : ""} onClick={() => setSeasonTab("cur")}>{seasonLabel}</button>
        </div>
      )}
      <div className="side-label">
        {leagueTitle} · {seasonTab === "next" ? `${nextLabel} (개막 전)` : seasonLabel}
        {seasonTab === "cur" && ls.on && <span className={`side-live${ls.inPlay ? " in" : ""}`} title="공식 순위(매일 아침 갱신) 전 — 진행 중·끝난 경기 스코어를 더한 잠정 순위">{ls.inPlay && <i className="live-dot" />}LIVE 잠정</span>}
      </div>

      <div className="team-scroll">
        {seasonTab === "cur"
          ? curShown.map((t) => {
              const z = zoneOf(t.rank, total);
              return (
                <button key={t.name}
                  className={`team-btn ${z.cls}${t.name === sel ? " active" : ""}`}
                  onClick={() => onSelect(t.name)}
                  aria-current={t.name === sel ? "page" : undefined}
                  style={t.name === sel ? { ["--tc" as any]: t.color } : undefined}>
                  <span className="rankchip">{t.rank}</span>
                  {t.logo ? <img src={t.logo} alt="" /> : <span style={{ width: 22 }} />}
                  <span className="tn">{t.name}</span>
                  {t.move ? <span className={`side-mv ${t.move > 0 ? "up" : "dn"}`} title={`잠정 순위 ${Math.abs(t.move)}계단 ${t.move > 0 ? "상승" : "하락"}`}>{t.move > 0 ? "▲" : "▼"}{Math.abs(t.move)}</span> : null}
                  <span className={`pts${t.live ? " lv" : ""}`} title={t.live ? `${t.live.label} ${t.live.gf}-${t.live.ga} 반영(잠정)` : undefined}>
                    {t.live?.state === "in" && <i className="live-dot" />}{t.points}</span>
                </button>
              );
            })
          : nextShown.map((t) => (
              <button key={t.name}
                className={`team-btn${t.name === sel ? " active" : ""}`}
                onClick={() => onSelect(t.name)}
                aria-current={t.name === sel ? "page" : undefined}
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
            : "개막 전 · 알파벳순"}
        </div>
      )}
    </aside>
  );
}
