"use client";
// 홈 리그 지도(전체 홈 맨 위) — TIER 1 카드(순위 1~3위 로고·승점, 2부 리그는 카드 아래 띠) · TIER 2 타일 · TIER 3 원.
// 2026-10-22 사용자와 기획: 리그 탭 한 줄(15개)이 잘리고 위계가 안 보이던 것. 글은 리그 이름·숫자만, 기준은 ⓘ 에.
// 티어는 서버가 리그 수준으로 매긴다(92·86 에서 자름 — src/league_level.py tier). TIER 3 원 크기·숫자 = 최근 두 시즌 빅5 구단이
// 그 리그에서 사 간 이적료 합(src/fetch_league_exports.py) — 리그 성격(육성·노장)과 상관없는 같은 잣대.
import { useLeagueGroups, type MapLeague } from "@/lib/leagueMap";
import Info from "./Info";

const feeM = (v: number) => `€${Math.round(v / 1e6)}M`;

function Crests({ l, pts, small }: { l: MapLeague; pts?: boolean; small?: boolean }) {
  return (
    <span className={`lm-crests${small ? " sm" : ""}`}>
      {l.top.map((t, i) => (
        <span key={t.team} className="lm-crest" title={`${i + 1}위 ${t.team}${t.pts != null ? ` · ${t.pts}점` : ""}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={t.logo} alt={t.team} loading="lazy" />
          {pts && t.pts != null && <i>{t.pts}</i>}
        </span>
      ))}
    </span>
  );
}

export default function LeagueMap({ current, onPick }: { current?: string; onPick: (league: string) => void }) {
  const g = useLeagueGroups();
  const on = (k: string) => (k === current ? " on" : "");
  return (
    <section className="lmap" aria-label="리그 지도">
      <div className="lm-tier t1">
        <div className="lm-lab">TIER 1<Info label="TIER 1 기준">리그 수준 92 이상(EPL=100). UEFA 협회 계수에서 계산해 계수가 바뀌면 자동으로 다시 매겨집니다. 2부 리그는 같은 나라 카드 아래에 붙습니다.</Info></div>
        <div className="lm-cards">
          {g[1].map((l) => (
            <div key={l.key} className="lm-cg">
              <button type="button" className={`lm-card${l.subs.length ? " has-sub" : ""}${on(l.key)}`} onClick={() => onPick(l.key)}>
                <span className="lm-name">{l.label}</span>
                <Crests l={l} pts />
              </button>
              {l.subs.map((s) => (
                <button key={s.key} type="button" className={`lm-sub${on(s.key)}`} onClick={() => onPick(s.key)}>
                  <span className="lm-sname">↳ {s.label}</span>
                  <Crests l={s} small />
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="lm-tier t2">
        <div className="lm-lab">TIER 2<Info label="TIER 2 기준">리그 수준 86~92.</Info></div>
        <div className="lm-tiles">
          {g[2].map((l) => (
            <button key={l.key} type="button" className={`lm-tile${on(l.key)}`} onClick={() => onPick(l.key)}>
              <span className="lm-name">{l.label}</span>
              <Crests l={l} small />
            </button>
          ))}
        </div>
      </div>

      <div className="lm-tier t3">
        <div className="lm-lab">TIER 3<Info label="TIER 3 기준과 원 크기">리그 수준 86 미만 + 비유럽 리그(잠정). 원 크기·숫자 = 최근 두 시즌 빅5 구단이 이 리그에서 사 간 선수들의 이적료 합(완전 이적, 임대 제외). 점선 원은 준비 중입니다.</Info></div>
        <div className="lm-orbs">
          {g[3].map((l) => {
            const fee = l.exports?.fee_eur ?? 0;
            const d = Math.min(132, Math.max(66, Math.round(Math.sqrt(fee / 1e6) * 7)));
            const tip = l.exports ? `빅5로 ${l.exports.n}명${l.exports.avg_age ? ` · 평균 ${l.exports.avg_age}세` : ""}` : undefined;
            const body = (
              <span className="lm-orb-in">
                {fee > 0 && <b>{feeM(fee)}</b>}
                {l.soon && <em>SOON</em>}
              </span>
            );
            return (
              <div key={l.key} className="lm-orb-item">
                {l.soon
                  ? <div className="lm-orb soon" style={{ ["--d" as string]: `${d}px` }} title={tip ? `${tip} · 준비 중` : "준비 중"}>{body}</div>
                  : <button type="button" className={`lm-orb${on(l.key)}`} style={{ ["--d" as string]: `${d}px` }} title={tip}
                      onClick={() => onPick(l.key)} aria-label={`${l.short}${fee ? ` 빅5 이적료 ${feeM(fee)}` : ""}`}>{body}</button>}
                <span className="lm-orb-name">{l.short}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
