"use client";
import { useEffect, useMemo, useState } from "react";
import { getSquadGraph, type SquadGraphData, type SGNode } from "@/lib/api";
import { hexA } from "@/lib/ui";

const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const LINE_KO: Record<string, string> = { GK: "GK", DEF: "수비", MID: "미드", ATT: "공격" };
const W = 620, H = 400;

// 코히전 force 레이아웃(의존성 없음): 함께 뛴 관계로 자연 군집, 연결 많은 허브가 중앙.
// 포지션이 아니라 케미/중심성을 표현 — 포메이션 뷰와 구분됨. useMemo 에서 즉시.
function layout(nodes: SGNode[], edges: { a: string; b: string; matches: number }[]) {
  const N = nodes.length;
  const idx: Record<string, number> = {};
  nodes.forEach((n, i) => (idx[n.id] = i));
  // 연결 강도(가중 degree) — 허브일수록 중심으로 강하게 당김
  const deg = new Array(N).fill(0);
  for (const e of edges) { const i = idx[e.a], j = idx[e.b]; if (i != null && j != null) { deg[i] += e.matches; deg[j] += e.matches; } }
  const maxDeg = Math.max(1, ...deg);
  const pos = nodes.map((_, i) => ({
    x: W / 2 + W * 0.30 * Math.cos((2 * Math.PI * i) / N),
    y: H / 2 + H * 0.30 * Math.sin((2 * Math.PI * i) / N),
  }));
  const maxM = Math.max(1, ...edges.map((e) => e.matches));
  for (let it = 0; it < 300; it++) {
    const fx = new Array(N).fill(0), fy = new Array(N).fill(0);
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
      const d2 = dx * dx + dy * dy || 1, d = Math.sqrt(d2), f = 2600 / d2, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
    }
    for (const e of edges) {   // 강한 조합일수록 가깝게
      const i = idx[e.a], j = idx[e.b];
      if (i == null || j == null) continue;
      const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = 45 + (1 - e.matches / maxM) * 90;
      const f = (d - L) * 0.025, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
    }
    for (let i = 0; i < N; i++) {
      const g = 0.006 + 0.032 * (deg[i] / maxDeg);   // 연결 많은 허브 → 중앙, 주변부 선수는 바깥
      fx[i] += (W / 2 - pos[i].x) * g; fy[i] += (H / 2 - pos[i].y) * g;
      pos[i].x += Math.max(-14, Math.min(14, fx[i] * 0.85));
      pos[i].y += Math.max(-14, Math.min(14, fy[i] * 0.85));
      pos[i].x = Math.max(30, Math.min(W - 30, pos[i].x));
      pos[i].y = Math.max(22, Math.min(H - 22, pos[i].y));
    }
  }
  return { pos, idx, maxM };
}

export default function SquadGraph({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<SquadGraphData | null>(null);
  useEffect(() => { let a = true; setD(null); getSquadGraph(team).then((x) => a && setD(x)).catch(() => a && setD(null)); return () => { a = false; }; }, [team]);

  const g = useMemo(() => {
    if (!d || !d.nodes?.length) return null;
    const { pos, idx, maxM } = layout(d.nodes, d.edges);
    return { pos, idx, maxM };
  }, [d]);

  if (!d) return <div className="loading">불러오는 중…</div>;
  if (!d.available) return <div className="mgr-meta">네트워크 비활성 — {d.reason || "그래프 스택 필요"}</div>;
  if (!d.nodes.length || !g) return <div className="mgr-meta">함께 뛴 데이터 부족</div>;

  const rr = (n: SGNode) => 7 + Math.max(0, Math.min(1, ((n.rating ?? 6) - 6) / 1.6)) * 7;   // 반지름 by 평점

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {d.edges.map((e, k) => {
          const i = g.idx[e.a], j = g.idx[e.b];
          if (i == null || j == null) return null;
          const w = e.matches / g.maxM;
          return <line key={k} x1={g.pos[i].x} y1={g.pos[i].y} x2={g.pos[j].x} y2={g.pos[j].y}
            stroke={hexA("#ffffff", 0.06 + w * 0.22)} strokeWidth={0.5 + w * 2.5} />;
        })}
        {d.nodes.map((n, i) => {
          const c = LINE_COLOR[n.line] || "#8a94a8";
          return (
            <g key={i} transform={`translate(${g.pos[i].x},${g.pos[i].y})`}>
              <circle r={rr(n)} fill={hexA(c, 0.9)} stroke={hexA("#000", 0.3)} strokeWidth="1" />
              <text y={rr(n) + 11} textAnchor="middle" fontSize="10" fill={hexA("#ffffff", 0.85)}
                style={{ pointerEvents: "none" }}>{n.name.split(" ").slice(-1)[0]}</text>
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 6, fontSize: 10.5, opacity: 0.7 }}>
        {Object.entries(LINE_KO).map(([k, ko]) => (
          <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: LINE_COLOR[k], display: "inline-block" }} />{ko}
          </span>
        ))}
        <span style={{ opacity: 0.55 }}>· 선=함께 뛴 경기(굵을수록 많음) · 중앙=연결 많은 핵심 · 원 크기=평점</span>
      </div>
    </div>
  );
}
