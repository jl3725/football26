"use client";
import { useEffect, useMemo, useState } from "react";
import { getHeatmaps, type HeatmapData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import HeatmapPitch from "./HeatmapPitch";

const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };

// 스쿼드 전원 히트맵 집계 → 팀 점유 구역(합산) / 평균 대형(centroid). Analytics 팀 단위.
export default function TeamTerritory({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<HeatmapData | null>(null);
  const [view, setView] = useState<"territory" | "shape">("territory");
  useEffect(() => {
    let a = true; setD(null);
    getHeatmaps(team).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team]);

  const agg = useMemo(() => {
    if (!d || !d.players.length) return null;
    const { gw, gh } = d, n = gw * gh;
    const byMin = [...d.players].sort((a, b) => b.minutes - a.minutes);
    const sum = new Array(n).fill(0);
    for (const p of byMin.slice(0, 14)) p.grid.forEach((v, i) => (sum[i] += v));
    const mx = Math.max(1, ...sum);
    const territory = sum.map((v) => Math.round((v / mx) * 100));
    const dots = byMin.slice(0, 11).map((p) => {
      let sx = 0, sy = 0, sv = 0;
      p.grid.forEach((v, i) => { sx += (i % gw) * v; sy += Math.floor(i / gw) * v; sv += v; });
      if (!sv) return null;
      return { x: ((sx / sv + 0.5) / gw) * 100, y: ((sy / sv + 0.5) / gh) * 100,
        label: p.player.split(" ").slice(-1)[0].slice(0, 3),
        color: LINE_COLOR[p.line] || "#8a94a8" };
    }).filter(Boolean) as { x: number; y: number; label: string; color: string }[];
    return { gw, gh, territory, dots };
  }, [d]);

  if (!d) return <div className="loading">불러오는 중…</div>;
  if (!d.available || !agg) return <div className="mgr-meta">히트맵 데이터 없음 (Sofascore 미수집 리그)</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
        <div style={{ display: "inline-flex", gap: 2, padding: 3, borderRadius: 9, background: hexA("#ffffff", 0.05) }}>
          {([["territory", "점유 구역"], ["shape", "평균 대형"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setView(v)}
              style={{ padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none",
                background: view === v ? accent : "transparent", color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{l}</button>
          ))}
        </div>
      </div>
      <div style={{ maxWidth: 520, margin: "0 auto" }}>
        {view === "territory"
          ? <HeatmapPitch grid={agg.territory} gw={agg.gw} gh={agg.gh} id="team-terr" />
          : <HeatmapPitch grid={new Array(agg.gw * agg.gh).fill(0)} gw={agg.gw} gh={agg.gh} id="team-shape" dots={agg.dots} />}
      </div>
      <div style={{ marginTop: 8, fontSize: 10.5, opacity: 0.5, textAlign: "center" }}>
        {view === "territory" ? "주전 14인 히트맵 합산 — 팀이 실제 점유하는 구역" : "주전 11인 평균 위치(centroid) · 라인 색"} · Sofascore
      </div>
    </div>
  );
}
