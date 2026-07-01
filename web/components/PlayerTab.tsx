"use client";
import { useEffect, useState } from "react";
import { getPlayers, getPlayerDetail, getSimilar, fmtEur, type Players, type PlayerDetail, type SimilarResult } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";
import Radar from "./Radar";

function Bar({ label, pct, raw, accent }: { label: string; pct: number; raw: number; accent: string }) {
  const c = pct >= 80 ? "#5ec98a" : pct >= 60 ? "#6aa6e0" : pct >= 40 ? "#caa64e" : "#d98169";
  return (
    <div className="pm">
      <div className="pm-top"><span>{label}</span><b style={{ color: c }}>{pct}</b></div>
      <div className="pm-bar"><span style={{ width: `${pct}%`, background: c }} /></div>
    </div>
  );
}

function Detail({ team, player, accent }: { team: string; player: string; accent: string }) {
  const [d, setD] = useState<PlayerDetail | null>(null);
  const [sim, setSim] = useState<SimilarResult[]>([]);
  useEffect(() => {
    let a = true; setD(null); setSim([]);
    getPlayerDetail(team, player).then((x) => a && setD(x)).catch(() => {});
    getSimilar(player).then((x) => a && setSim(x.results)).catch(() => {});
    return () => { a = false; };
  }, [team, player]);
  if (!d) return <div className="card"><div className="loading">불러오는 중…</div></div>;
  const t = tier(d.ovr);
  return (
    <div className="card pd-card">
      <div className="pd-head" style={{ background: `linear-gradient(120deg, ${hexA(d.color, 0.28)}, transparent)` }}>
        {d.photo ? <img className="pd-photo" src={d.photo} alt="" /> : <span className="pd-photo ph" />}
        <div style={{ flex: 1 }}>
          <div className="pd-name">{d.player}</div>
          <div className="pd-meta">{d.pos} · {d.age}세 · {d.nationality}</div>
          <div className="pd-meta">{d.minutes.toLocaleString()}′ · {d.goals}G {d.assists}A · {fmtEur(d.value_eur)}</div>
        </div>
        <div className="pd-ovr" style={{ color: t.light, borderColor: hexA(t.light, 0.5) }}>
          <div className="teko" style={{ fontSize: 46, lineHeight: .8 }}>{d.ovr}</div>
          <div style={{ fontSize: 9, letterSpacing: 1, color: "var(--muted)" }}>OVR</div>
        </div>
      </div>
      {d.badges.length > 0 && (
        <div className="pd-badges">
          {d.badges.map((b, i) => (
            <span className="pd-badge" key={i} style={{ borderColor: hexA(accent, 0.5) }}>
              {b.medal} {b.label} <em style={{ color: accent }}>리그 #{b.rank}</em>
            </span>
          ))}
        </div>
      )}
      <div className="pd-body">
        <div className="pd-cats">
          {d.categories.map((c, i) => (
            <div className="pd-cat" key={i}>
              <div className="pd-cat-head">
                <span>{c.name}</span>
                <b style={{ color: tier(c.avg).light }}>{c.avg}</b>
              </div>
              {c.metrics.map((m, j) => <Bar key={j} label={m.label} pct={m.pct} raw={m.raw} accent={accent} />)}
            </div>
          ))}
        </div>
        <div className="pd-radar"><Radar data={d.radar} color={accent} /></div>
      </div>
      {sim.length > 0 && (
        <div className="pd-similar">
          <div className="pd-sim-title">🔍 스타일 유사 선수</div>
          <div className="pd-sim-list">
            {sim.map((s, i) => (
              <div className="pd-sim-row" key={i}>
                {s.logo ? <img src={s.logo} alt="" /> : <span className="pd-sim-logo" />}
                <span className="pd-sim-name">{s.player}</span>
                <span className="pd-sim-squad">{s.squad}</span>
                <span className="pd-sim-score" style={{ color: accent }}>{s.score}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PlayerTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Players | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    let a = true;
    setData(null); setSel(null);
    getPlayers(team).then((d) => { if (a) { setData(d); setSel(d.players[0]?.player ?? null); } }).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;

  return (
    <div className="fade player-layout">
      <div className="pl-grid">
        {data.players.map((p) => {
          const t = tier(p.ovr);
          return (
            <button key={p.player} className={`pl-card${sel === p.player ? " active" : ""}`}
              onClick={() => setSel(p.player)}
              style={sel === p.player ? { borderColor: accent } : undefined}>
              <span className="pl-ovr" style={{ color: t.light }}>{p.ovr}</span>
              {p.photo ? <img className="pl-photo" src={p.photo} alt="" /> : <span className="pl-photo ph" />}
              <div className="pl-name">{p.player}</div>
              <div className="pl-pos">{p.pos} · {p.age}</div>
            </button>
          );
        })}
      </div>
      <div className="pl-detail">
        {sel && <Detail team={team} player={sel} accent={accent} />}
      </div>
    </div>
  );
}
