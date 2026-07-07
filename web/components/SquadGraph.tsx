"use client";
import { useEffect, useMemo, useState } from "react";
import { getSquadGraph, type SquadGraphData, type SGNode } from "@/lib/api";
import { hexA } from "@/lib/ui";

const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const LINE_KO: Record<string, string> = { GK: "GK", DEF: "수비", MID: "미드", ATT: "공격" };
const W = 620, H = 400;

// 라인별 수직 밴드(피치처럼: 공격 위 → GK 아래) — 같은 라인이 뭉치게.
const LINE_Y: Record<string, number> = { ATT: 0.22, MID: 0.45, DEF: 0.68, GK: 0.88 };

// 경량 force 레이아웃(의존성 없음) + 라인 밴드 앵커. useMemo 에서 즉시.
function layout(nodes: SGNode[], edges: { a: string; b: string; matches: number }[]) {
  const N = nodes.length;
  const idx: Record<string, number> = {};
  nodes.forEach((n, i) => (idx[n.id] = i));
  // 초기 위치 = 라인 밴드 y + 라인 내 가로 분산
  const byLine: Record<string, number> = {};
  const pos = nodes.map((n) => {
    const k = (byLine[n.line] = (byLine[n.line] || 0) + 1);
    return { x: W / 2 + (k % 2 ? 1 : -1) * k * 28, y: (LINE_Y[n.line] ?? 0.45) * H };
  });
  const maxM = Math.max(1, ...edges.map((e) => e.matches));
  for (let it = 0; it < 240; it++) {
    const fx = new Array(N).fill(0), fy = new Array(N).fill(0);
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
      const d2 = dx * dx + dy * dy || 1, d = Math.sqrt(d2), f = 2400 / d2, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
    }
    for (const e of edges) {   // 함께 뛴 조합 = 가로로 당김(세로는 밴드가 지배)
      const i = idx[e.a], j = idx[e.b];
      if (i == null || j == null) continue;
      const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = 50 + (1 - e.matches / maxM) * 80;
      const f = (d - L) * 0.02, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f * 0.35; fx[j] -= ux * f; fy[j] -= uy * f * 0.35;
    }
    for (let i = 0; i < N; i++) {
      fy[i] += ((LINE_Y[nodes[i].line] ?? 0.45) * H - pos[i].y) * 0.14;   // 라인 밴드로 강하게
      fx[i] += (W / 2 - pos[i].x) * 0.006;                                 // 가로 중심 약하게
      pos[i].x += Math.max(-14, Math.min(14, fx[i] * 0.85));
      pos[i].y += Math.max(-10, Math.min(10, fy[i] * 0.85));
      pos[i].x = Math.max(30, Math.min(W - 30, pos[i].x));
      pos[i].y = Math.max(20, Math.min(H - 20, pos[i].y));
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
        <span style={{ opacity: 0.55 }}>· 선=함께 뛴 경기(굵을수록 많음) · 원 크기=평점</span>
      </div>
    </div>
  );
}
