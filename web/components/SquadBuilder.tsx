"use client";
import { useMemo, useState } from "react";
import { type PlayerCard } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";

type Slot = { line: string; x: number; y: number };
const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const last = (n: string) => n.split(" ").slice(-1)[0];

// 포메이션 = 슬롯(라인·좌표). y: 0=공격(위) … 100=GK(아래), x=폭.
const FORMATIONS: Record<string, Slot[]> = {
  "4-3-3": [{ line: "GK", x: 50, y: 92 },
    { line: "DEF", x: 16, y: 72 }, { line: "DEF", x: 39, y: 76 }, { line: "DEF", x: 61, y: 76 }, { line: "DEF", x: 84, y: 72 },
    { line: "MID", x: 28, y: 50 }, { line: "MID", x: 50, y: 54 }, { line: "MID", x: 72, y: 50 },
    { line: "ATT", x: 20, y: 24 }, { line: "ATT", x: 50, y: 16 }, { line: "ATT", x: 80, y: 24 }],
  "4-4-2": [{ line: "GK", x: 50, y: 92 },
    { line: "DEF", x: 16, y: 73 }, { line: "DEF", x: 39, y: 76 }, { line: "DEF", x: 61, y: 76 }, { line: "DEF", x: 84, y: 73 },
    { line: "MID", x: 16, y: 48 }, { line: "MID", x: 39, y: 50 }, { line: "MID", x: 61, y: 50 }, { line: "MID", x: 84, y: 48 },
    { line: "ATT", x: 38, y: 18 }, { line: "ATT", x: 62, y: 18 }],
  "4-2-3-1": [{ line: "GK", x: 50, y: 92 },
    { line: "DEF", x: 16, y: 73 }, { line: "DEF", x: 39, y: 76 }, { line: "DEF", x: 61, y: 76 }, { line: "DEF", x: 84, y: 73 },
    { line: "MID", x: 35, y: 58 }, { line: "MID", x: 65, y: 58 },
    { line: "MID", x: 24, y: 34 }, { line: "MID", x: 50, y: 32 }, { line: "MID", x: 76, y: 34 },
    { line: "ATT", x: 50, y: 14 }],
  "3-5-2": [{ line: "GK", x: 50, y: 92 },
    { line: "DEF", x: 28, y: 75 }, { line: "DEF", x: 50, y: 77 }, { line: "DEF", x: 72, y: 75 },
    { line: "MID", x: 10, y: 52 }, { line: "MID", x: 34, y: 50 }, { line: "MID", x: 50, y: 54 }, { line: "MID", x: 66, y: 50 }, { line: "MID", x: 90, y: 52 },
    { line: "ATT", x: 40, y: 18 }, { line: "ATT", x: 60, y: 18 }],
  "3-4-3": [{ line: "GK", x: 50, y: 92 },
    { line: "DEF", x: 28, y: 75 }, { line: "DEF", x: 50, y: 77 }, { line: "DEF", x: 72, y: 75 },
    { line: "MID", x: 18, y: 50 }, { line: "MID", x: 40, y: 52 }, { line: "MID", x: 60, y: 52 }, { line: "MID", x: 82, y: 50 },
    { line: "ATT", x: 20, y: 20 }, { line: "ATT", x: 50, y: 16 }, { line: "ATT", x: 80, y: 20 }],
};

export default function SquadBuilder({ players, accent }: { players: PlayerCard[]; accent: string }) {
  const [formation, setFormation] = useState("4-3-3");
  const [overrides, setOverrides] = useState<Record<number, string>>({});
  const [pick, setPick] = useState<number | null>(null);   // 교체 대상 슬롯

  const slots = FORMATIONS[formation];
  const { xi, bench, teamOvr } = useMemo(() => {
    const byLine: Record<string, PlayerCard[]> = {};
    for (const p of players) (byLine[p.line] ||= []).push(p);
    for (const k in byLine) byLine[k].sort((a, b) => b.ovr - a.ovr);
    const used = new Set(Object.values(overrides));
    const cur: Record<string, number> = { GK: 0, DEF: 0, MID: 0, ATT: 0 };
    const xi = slots.map((s, i) => {
      if (overrides[i]) return players.find((p) => p.player === overrides[i]) || null;
      const pool = byLine[s.line] || [];
      while (cur[s.line] < pool.length && used.has(pool[cur[s.line]].player)) cur[s.line]++;
      const p = pool[cur[s.line]];
      if (p) { cur[s.line]++; used.add(p.player); return p; }
      return null;
    });
    const inXI = new Set(xi.filter(Boolean).map((p) => p!.player));
    const bench = players.filter((p) => !inXI.has(p.player)).sort((a, b) => b.ovr - a.ovr);
    const rated = xi.filter(Boolean) as PlayerCard[];
    const teamOvr = rated.length ? Math.round(rated.reduce((s, p) => s + p.ovr, 0) / rated.length) : 0;
    return { xi, bench, teamOvr };
  }, [players, slots, overrides]);

  const pickList = pick != null
    ? [...players].filter((p) => !xi.some((x, i) => i !== pick && x?.player === p.player))
        .sort((a, b) => (a.line === slots[pick].line ? -1 : 1) - (b.line === slots[pick].line ? -1 : 1) || b.ovr - a.ovr)
    : [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div style={{ display: "inline-flex", gap: 3, padding: 3, borderRadius: 9, background: hexA("#ffffff", 0.05) }}>
          {Object.keys(FORMATIONS).map((f) => (
            <button key={f} onClick={() => { setFormation(f); setOverrides({}); setPick(null); }}
              style={{ padding: "5px 11px", borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none",
                background: formation === f ? accent : "transparent", color: formation === f ? "#0a0a0a" : "inherit", opacity: formation === f ? 1 : 0.6 }}>{f}</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          {Object.keys(overrides).length > 0 && (
            <button onClick={() => setOverrides({})} style={{ fontSize: 11, padding: "4px 9px", borderRadius: 6, border: "none", background: hexA("#fff", 0.08), color: "inherit", cursor: "pointer", opacity: 0.7 }}>자동 XI 복원</button>
          )}
          <span style={{ fontSize: 11, opacity: 0.55 }}>팀 XI</span>
          <span style={{ fontSize: 24, fontWeight: 800, color: tier(teamOvr).light, lineHeight: 1 }}>{teamOvr}</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* 피치 */}
        <div style={{ position: "relative", flex: "1 1 320px", maxWidth: 440, aspectRatio: "68 / 92",
          background: "linear-gradient(180deg, #0f2a1c, #0c1f16)", borderRadius: 12, border: `1px solid ${hexA("#fff", 0.08)}` }}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
            <g stroke="rgba(255,255,255,0.13)" strokeWidth="0.4" fill="none">
              <line x1="0" y1="50" x2="100" y2="50" /><circle cx="50" cy="50" r="11" />
              <rect x="26" y="0.5" width="48" height="16" /><rect x="26" y="83.5" width="48" height="16" />
            </g>
          </svg>
          {slots.map((s, i) => {
            const p = xi[i]; const col = LINE_COLOR[s.line] || "#8a94a8";
            return (
              <button key={i} onClick={() => setPick(pick === i ? null : i)}
                style={{ position: "absolute", left: `${s.x}%`, top: `${s.y}%`, transform: "translate(-50%,-50%)",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 2, border: "none", background: "transparent", cursor: "pointer", width: 62 }}>
                <div style={{ position: "relative" }}>
                  {p?.photo
                    ? <img src={p.photo} alt="" style={{ width: 40, height: 40, borderRadius: "50%", objectFit: "cover", border: `2px solid ${pick === i ? accent : hexA(col, 0.85)}` }} />
                    : <span style={{ width: 40, height: 40, borderRadius: "50%", background: hexA(col, 0.25), display: "grid", placeItems: "center", fontSize: 10, border: `2px solid ${hexA(col, 0.5)}` }}>{s.line}</span>}
                  {p && <span style={{ position: "absolute", bottom: -3, right: -5, fontSize: 10, fontWeight: 800, color: "#0a0a0a", background: tier(p.ovr).light, borderRadius: 5, padding: "0 3px" }}>{p.ovr}</span>}
                </div>
                <span style={{ fontSize: 9.5, fontWeight: 600, color: "#fff", textShadow: "0 1px 2px #000", whiteSpace: "nowrap", maxWidth: 62, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {p ? last(p.player) : "―"}
                </span>
              </button>
            );
          })}
        </div>

        {/* 교체 피커 or 벤치 */}
        <div style={{ flex: "1 1 220px", minWidth: 200 }}>
          {pick != null ? (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>{slots[pick].line} 슬롯 · 교체 선수 선택
                <button onClick={() => setPick(null)} style={{ marginLeft: 8, fontSize: 10.5, padding: "2px 8px", borderRadius: 6, border: "none", background: hexA("#fff", 0.08), color: "inherit", cursor: "pointer", opacity: 0.7 }}>취소</button></div>
              <div style={{ maxHeight: 380, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
                {pickList.map((p) => (
                  <button key={p.player} onClick={() => { setOverrides((o) => ({ ...o, [pick]: p.player })); setPick(null); }}
                    style={{ display: "flex", alignItems: "center", gap: 9, padding: "6px 9px", borderRadius: 8, border: "none", background: hexA("#fff", 0.03), color: "inherit", cursor: "pointer", textAlign: "left" }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: LINE_COLOR[p.line] || "#888" }} />
                    {p.photo ? <img src={p.photo} alt="" style={{ width: 26, height: 26, borderRadius: "50%", objectFit: "cover" }} /> : <span style={{ width: 26 }} />}
                    <span style={{ flex: 1, fontSize: 12, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.player}</span>
                    <span style={{ fontSize: 10.5, opacity: 0.5 }}>{p.pos}</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: tier(p.ovr).light }}>{p.ovr}</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8, opacity: 0.8 }}>벤치 · {bench.length}명 <span style={{ fontWeight: 400, opacity: 0.55, fontSize: 10.5 }}>(피치 슬롯 클릭 → 교체)</span></div>
              <div style={{ maxHeight: 380, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
                {bench.map((p) => (
                  <div key={p.player} style={{ display: "flex", alignItems: "center", gap: 9, padding: "5px 9px", borderRadius: 8, background: hexA("#fff", 0.02) }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: LINE_COLOR[p.line] || "#888" }} />
                    {p.photo ? <img src={p.photo} alt="" style={{ width: 24, height: 24, borderRadius: "50%", objectFit: "cover" }} /> : <span style={{ width: 24 }} />}
                    <span style={{ flex: 1, fontSize: 11.5, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.player}</span>
                    <span style={{ fontSize: 10, opacity: 0.5 }}>{p.pos}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: tier(p.ovr).light }}>{p.ovr}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
