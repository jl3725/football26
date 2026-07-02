"use client";
import { useEffect, useState } from "react";
import { getSignals, type Signals, type Signal } from "@/lib/api";

const TONE: Record<string, string> = { good: "#4fc27f", bad: "#e07070", warn: "#e0a53a", info: "#6aa6e0" };

const GROUPS: { key: string; label: string; icon: string; types: string[] }[] = [
  { key: "injury", label: "부상", icon: "🚑", types: ["injury_new", "injury_return"] },
  { key: "youth", label: "유망주 · 육성", icon: "🌱", types: ["youth"] },
  { key: "risk", label: "리스크 · 노장", icon: "🩹", types: ["risk", "veteran"] },
  { key: "value", label: "시장가치", icon: "📈", types: ["value"] },
  { key: "manager", label: "감독", icon: "🎓", types: ["manager"] },
  { key: "contract", label: "계약 만료 임박", icon: "📄", types: ["contract"] },
  { key: "resign", label: "재계약 대상", icon: "✍️", types: ["resign"] },
];

function Row({ s, showTeam }: { s: Signal; showTeam: boolean }) {
  const c = TONE[s.tone] || "#8a94a8";
  return (
    <div className="sig-row" style={{ borderLeftColor: c }}>
      <span className="sig-icon">{s.icon}</span>
      {s.photo ? <img className="sig-photo" src={s.photo} alt="" /> : null}
      <div className="sig-body">
        <div className="sig-title">
          <b style={{ color: c }}>{s.title}</b>
          {s.player && <span className="sig-player">{s.player}</span>}
        </div>
        <div className="sig-detail">
          {showTeam && s.logo && <img className="sig-teamlogo" src={s.logo} alt="" />}
          {s.detail}
        </div>
      </div>
      {s.date && <span className="sig-date">{s.date.slice(5)}</span>}
    </div>
  );
}

export default function SignalsTab({ team, accent }: { team: string; accent: string }) {
  const [mine, setMine] = useState<Signals | null>(null);
  const [league, setLeague] = useState<Signals | null>(null);
  useEffect(() => {
    let a = true;
    setMine(null);
    getSignals(team).then((d) => a && setMine(d)).catch(() => {});
    getSignals("", "EPL", 50).then((d) => a && setLeague(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (!mine) return <div className="loading">불러오는 중…</div>;

  const byGroup = (g: typeof GROUPS[number]) => mine.signals.filter((s) => g.types.includes(s.type));
  const leagueEvents = league?.signals.filter((s) => ["injury_new", "injury_return", "manager", "value", "risk"].includes(s.type)) ?? [];

  return (
    <div className="fade">
      <div className="inbox-hd">
        <span className="scout-tag" style={{ color: accent }}>📥 AUTO-DETECT INBOX</span>
        <b>자동 감지 인박스</b>
        <span className="scout-d">부상·감독·시장가·유망주·계약 변화를 에이전트가 자동 수집</span>
        <span className="scout-cnt">{team} {mine.signals.length}건</span>
      </div>
      <div className="sig-cat-grid">
        {GROUPS.map((g) => {
          const items = byGroup(g);
          return (
            <div className="card sig-cat" key={g.key}>
              <h3>{g.icon} {g.label} <span className="sig-cat-n">{items.length}</span></h3>
              <div className="sig-list">
                {items.map((s, i) => <Row key={i} s={s} showTeam={false} />)}
                {items.length === 0 && <div className="sig-empty">감지된 항목 없음</div>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>🌐 리그 전체 · 최근 감지 (이적 제외)</h3>
        <div className="sig-list" style={{ maxHeight: 340 }}>
          {leagueEvents.slice(0, 24).map((s, i) => <Row key={i} s={s} showTeam={true} />)}
          {leagueEvents.length === 0 && <div className="sig-empty">최근 이벤트 없음</div>}
        </div>
      </div>
    </div>
  );
}
