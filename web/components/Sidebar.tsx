"use client";
import { useState } from "react";
import type { Team } from "@/lib/api";

export default function Sidebar({
  teams, sel, onSelect, seasonLabel = "25/26",
}: { teams: Team[]; sel: string; onSelect: (t: string) => void; seasonLabel?: string }) {
  const [q, setQ] = useState("");
  const shown = teams.filter((t) => t.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <aside className="side">
      <div className="brand">
        <div className="brand-orb" />
        <div>
          <div className="brand-name">SCOUT<span style={{ color: "var(--accent)" }}>.AI</span></div>
          <div className="brand-sub">Football Intelligence</div>
        </div>
      </div>

      <div className="search">
        <span>⌕</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="구단 검색…" />
      </div>

      <div className="side-label">Premier League · {seasonLabel}</div>
      <div className="team-scroll">
        {shown.map((t) => (
          <button key={t.name}
            className={`team-btn${t.name === sel ? " active" : ""}`}
            onClick={() => onSelect(t.name)}
            style={t.name === sel ? { ["--tc" as any]: t.color } : undefined}>
            <span className="rankchip">{t.rank}</span>
            {t.logo ? <img src={t.logo} alt="" /> : <span style={{ width: 22 }} />}
            <span className="tn">{t.name}</span>
            <span className="pts">{t.points}</span>
          </button>
        ))}
        {shown.length === 0 && <div className="empty">검색 결과 없음</div>}
      </div>
    </aside>
  );
}
