"use client";
import { useEffect, useState } from "react";
import SectionHead from "./SectionHead";
import { getSignals, type Signal } from "@/lib/api";
import Bar from "./Bar";

const TONE: Record<string, string> = { good: "#4fc27f", bad: "#e07070", warn: "#e0a53a", info: "#6aa6e0" };

export default function OverviewSignals({ team, accent = "#ff4d5e" }: { team: string; accent?: string }) {
  const [sigs, setSigs] = useState<Signal[]>([]);
  useEffect(() => { let a = true; getSignals(team, undefined, 20).then((d) => a && setSigs(d.signals.filter((s) => s.type !== "contract" && s.type !== "resign"))).catch(() => {}); return () => { a = false; }; }, [team]);
  if (sigs.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <SectionHead title="SIGNALS" kr="최근 감지된 변화" meta="시장가치 급등·급락 · 부상 · 이적" />
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
