"use client";
import { useEffect, useState } from "react";
import { getFixtures, type Fixture } from "@/lib/api";
import MatchCard from "./MatchCard";
import { BIG, compLabel, ddayLabel } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";

// 리그 탭 '이번 주 경기' — 위: 그 리그 빅매치 강조 카드, 아래: 날짜별 전 경기(소속 팀의 유럽대회 포함).
// 일정은 클라우드 daily_data 가 매일 갱신, 순위·폼·D-day 는 열 때 계산(src/match_center.py).

function Row({ m, league, onPick }: { m: Fixture; league: string; onPick: (t: string, lg?: string) => void }) {
  const big = m.big >= BIG;
  const preview = useMatchPreview();
  const side = (s: Fixture["home"]) => (
    <button className="lf-team" disabled={!s.league} onClick={(e) => { e.stopPropagation(); if (s.league) onPick(s.team, s.league); }}>
      {s.logo ? <img src={s.logo} alt="" /> : <span className="lf-ph" style={{ background: s.color }} />}
      <span className="lf-name">{s.team}</span>
      {s.rank && s.league === league ? <em>{s.rank}</em> : null}
    </button>
  );
  return (
    <div className={`lf-row${big ? " big" : ""}${preview ? " clickable" : ""}`} onClick={() => preview?.(m)} title="매치 프리뷰">
      <span className="lf-time">{m.kst.split(" ")[1] ?? ""}</span>
      <div className="lf-match">{side(m.home)}<span className="lf-vs">vs</span>{side(m.away)}</div>
      <span className="lf-side">
        {!m.comp_code.endsWith(".1") && <span className={`lf-comp${m.comp_code === "uefa.champions" ? " ucl" : ""}`}>{compLabel(m)}</span>}
        {big && <span className="lf-big" title={m.tags.join(" · ")}>BIG</span>}
      </span>
    </div>
  );
}

export default function LeagueFixtures({ league, accent, onPick }:
  { league: string; accent: string; onPick: (t: string, lg?: string) => void }) {
  const [d, setD] = useState<{ big: Fixture[]; matches: Fixture[] } | null>(null);
  useEffect(() => {
    let a = true; setD(null);
    getFixtures(7, league, 3).then((x) => a && setD({ big: x.big, matches: x.matches ?? [] })).catch(() => a && setD({ big: [], matches: [] }));
    return () => { a = false; };
  }, [league]);
  if (!d || d.matches.length === 0) return null;

  const days: { label: string; d: number; items: Fixture[] }[] = [];
  for (const m of d.matches) {
    const label = m.kst.split(" ")[0];
    const last = days[days.length - 1];
    if (last && last.label === label) last.items.push(m);
    else days.push({ label, d: m.d_day, items: [m] });
  }
  return (
    <div className="lf" style={{ ["--tc" as any]: accent }}>
      {d.big.length > 0 && (
        <div className="mc-grid" style={{ marginBottom: 12 }}>
          {d.big.map((m, i) => <MatchCard key={m.event_id ?? i} m={m} onPick={(t, lg) => lg && onPick(t, lg)} />)}
        </div>
      )}
      <div className="card lf-list">
        {days.map((g) => (
          <div className="lf-day" key={g.label}>
            <div className="lf-day-h">{g.label}<span>{ddayLabel(g.d)}</span></div>
            {g.items.map((m, i) => <Row key={m.event_id ?? i} m={m} league={league} onPick={onPick} />)}
          </div>
        ))}
      </div>
    </div>
  );
}
