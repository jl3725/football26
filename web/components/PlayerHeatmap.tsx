"use client";
import { useEffect, useState } from "react";
import { getHeatmaps, type HeatmapData } from "@/lib/api";
import { hexA } from "@/lib/ui";

const W = 380, H = 246;

// 0(저)→140 green … 0 red(핫). 알파로 밀도 표현.
function heat(v: number): string {
  const h = (1 - v / 100) * 140;
  const a = 0.12 + (v / 100) * 0.72;
  return `hsla(${h}, 85%, 52%, ${a})`;
}

export default function PlayerHeatmap({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<HeatmapData | null>(null);
  const [sel, setSel] = useState(0);
  useEffect(() => {
    let a = true; setD(null); setSel(0);
    getHeatmaps(team).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team]);

  if (!d) return <div className="loading">불러오는 중…</div>;
  if (!d.available || !d.players.length) return <div className="mgr-meta">히트맵 데이터 없음 (Sofascore 미수집)</div>;

  const p = d.players[Math.min(sel, d.players.length - 1)];
  const { gw, gh } = d;
  const cw = W / gw, ch = H / gh;

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        {d.players.map((pl, i) => (
          <button key={i} onClick={() => setSel(i)}
            style={{ padding: "5px 10px", borderRadius: 8, fontSize: 11.5, fontWeight: 600, cursor: "pointer", border: "none",
              background: i === sel ? accent : hexA("#ffffff", 0.05), color: i === sel ? "#0a0a0a" : "inherit", opacity: i === sel ? 1 : 0.65 }}>
            {pl.player.split(" ").slice(-1)[0]}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 470, background: "#0c1c14", borderRadius: 12 }}>
          <defs><filter id="hmblur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7" /></filter></defs>
          <g filter="url(#hmblur)">
            {p.grid.map((v, idx) => {
              if (v < 6) return null;
              const col = idx % gw, row = Math.floor(idx / gw);
              return <rect key={idx} x={col * cw} y={row * ch} width={cw} height={ch} fill={heat(v)} />;
            })}
          </g>
          <g stroke={hexA("#ffffff", 0.26)} strokeWidth="1.2" fill="none">
            <rect x="2" y="2" width={W - 4} height={H - 4} rx="3" />
            <line x1={W / 2} y1="2" x2={W / 2} y2={H - 2} />
            <circle cx={W / 2} cy={H / 2} r="26" />
            <rect x="2" y={H / 2 - 46} width="52" height="92" />
            <rect x={W - 54} y={H / 2 - 46} width="52" height="92" />
          </g>
          <text x={W - 8} y={15} textAnchor="end" fontSize="9.5" fill={hexA("#ffffff", 0.4)}>공격 →</text>
        </svg>

        <div style={{ minWidth: 130 }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{p.player}</div>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 2 }}>{[p.pos, p.minutes ? `${p.minutes.toLocaleString()}′` : ""].filter(Boolean).join(" · ")}</div>
          <div style={{ fontSize: 11, opacity: 0.45, marginTop: 10 }}>시즌 누적 활동 구역</div>
          <div style={{ fontSize: 11, opacity: 0.45 }}>{p.n_points.toLocaleString()} 위치 표본</div>
          <div style={{ fontSize: 10, opacity: 0.35, marginTop: 8 }}>출처: Sofascore</div>
        </div>
      </div>
    </div>
  );
}
