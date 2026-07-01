"use client";
import { useEffect, useState } from "react";
import { getSignals, type Signal } from "@/lib/api";

const TONE: Record<string, string> = { good: "#4fc27f", bad: "#e07070", warn: "#e0a53a", info: "#6aa6e0" };

export default function OverviewSignals({ team }: { team: string }) {
  const [sigs, setSigs] = useState<Signal[]>([]);
  useEffect(() => { let a = true; getSignals(team, "EPL", 20).then((d) => a && setSigs(d.signals.filter((s) => s.type !== "contract" && s.type !== "resign"))).catch(() => {}); return () => { a = false; }; }, [team]);
  if (sigs.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>🔔 최근 감지된 변화</h3>
      <div className="ov-sig">
        {sigs.slice(0, 6).map((s, i) => (
          <span className="ov-sig-chip" key={i} style={{ borderLeftColor: TONE[s.tone] || "#888" }}>
            {s.icon} {s.player && <span className="p">{s.player.split(" ").slice(-1)[0]}</span>}
            <span className="d">{s.title}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
