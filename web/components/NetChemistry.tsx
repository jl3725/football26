"use client";
import { useMemo, useState } from "react";
import type { NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import Chemistry from "./Chemistry";
import Info from "./Info";
import { LINE_COLOR, LINE_KO, SvgAvatar, lastName } from "./NetShared";

// CHEMISTRY — 실제로 함께 그라운드에 있던 시간(라인업·교체)으로 만든 관계망. 선 굵기 = 함께 뛴 분,
// 가운데 = 많이 연결된 허브. 선수에 마우스를 올리면 그 선수의 파트너만 남긴다.
const W = 680, H = 470;

function layout(names: string[], edges: { a: string; b: string; minutes: number }[]) {
  const N = names.length;
  const idx: Record<string, number> = {};
  names.forEach((n, i) => (idx[n] = i));
  const deg = new Array(N).fill(0);
  for (const e of edges) { const i = idx[e.a], j = idx[e.b]; if (i != null && j != null) { deg[i] += e.minutes; deg[j] += e.minutes; } }
  const maxDeg = Math.max(1, ...deg);
  const maxM = Math.max(1, ...edges.map((e) => e.minutes));
  const pos = names.map((_, i) => ({ x: W / 2 + W * 0.32 * Math.cos((2 * Math.PI * i) / N), y: H / 2 + H * 0.32 * Math.sin((2 * Math.PI * i) / N) }));
  for (let it = 0; it < 320; it++) {
    const fx = new Array(N).fill(0), fy = new Array(N).fill(0);
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
      const d2 = dx * dx + dy * dy || 1, d = Math.sqrt(d2), f = 9000 / d2, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
    }
    for (const e of edges) {
      const i = idx[e.a], j = idx[e.b];
      if (i == null || j == null) continue;
      const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = 95 + (1 - e.minutes / maxM) * 140;
      const f = (d - L) * 0.012, ux = dx / d, uy = dy / d;
      fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
    }
    for (let i = 0; i < N; i++) {
      const g = 0.004 + 0.016 * (deg[i] / maxDeg);
      fx[i] += (W / 2 - pos[i].x) * g; fy[i] += (H / 2 - pos[i].y) * g;
      pos[i].x = Math.max(34, Math.min(W - 34, pos[i].x + Math.max(-14, Math.min(14, fx[i] * 0.85))));
      pos[i].y = Math.max(30, Math.min(H - 34, pos[i].y + Math.max(-14, Math.min(14, fy[i] * 0.85))));
    }
  }
  return { pos, idx, maxM };
}

export default function NetChemistry({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const [strong, setStrong] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const players = useMemo(() => Object.fromEntries(d.players.map((p) => [p.name, p])), [d]);
  const edges = d.chemistry.edges.filter((e) => (strong ? e.minutes >= 300 : e.minutes >= 150));
  const linked = new Set(edges.flatMap((e) => [e.a, e.b]));
  const nodes = d.chemistry.nodes.filter((n) => n.minutes >= 90 && linked.has(n.name));
  const loose = d.chemistry.nodes.filter((n) => n.minutes >= 90 && !linked.has(n.name));
  const g = useMemo(() => layout(nodes.map((n) => n.name), edges), [d, strong]); // eslint-disable-line react-hooks/exhaustive-deps
  const maxMin = Math.max(1, ...nodes.map((n) => n.minutes));
  const nbr = useMemo(() => {
    if (!hover) return null;
    const s = new Set([hover]);
    edges.forEach((e) => { if (e.a === hover) s.add(e.b); if (e.b === hover) s.add(e.a); });
    return s;
  }, [hover, edges]);
  const partners = hover ? edges.filter((e) => e.a === hover || e.b === hover).sort((a, b) => b.minutes - a.minutes).slice(0, 5) : [];
  if (!nodes.length) return <p className="net-empty">함께 뛴 기록이 아직 부족합니다</p>;

  return (
    <div className="net-chem">
      <div className="net-chem-main">
        <div className="net-toolbar">
          <div className="comp-seg chips5">
            <button className={!strong ? "active" : ""} onClick={() => setStrong(false)}>150분+ 연결</button>
            <button className={strong ? "active" : ""} onClick={() => setStrong(true)}>300분+ 강한 연결</button>
          </div>
          <span className="net-legend">
            {Object.entries(LINE_KO).map(([k, v]) => <span key={k}><i style={{ background: LINE_COLOR[k] }} />{v}</span>)}
            <span><i className="cap" />주장단</span>
            <Info label="관계망 보는 법">
              <p>실제로 함께 그라운드에 있던 시간(라인업·교체)으로 만든 관계망.</p>
              <ul>
                <li>선 굵기 = 함께 뛴 시간 · 원 크기 = 출전 시간</li>
                <li>가운데일수록 많이 연결된 허브</li>
                <li>선수를 누르거나 마우스를 올리면 함께 오래 뛴 파트너만 남습니다</li>
              </ul>
            </Info>
          </span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label="함께 뛴 시간 관계망 — 선이 굵을수록 오래 함께 뛰었고, 가운데일수록 많이 연결된 선수">
          {edges.map((e, k) => {
            const i = g.idx[e.a], j = g.idx[e.b];
            if (i == null || j == null) return null;
            const w = e.minutes / g.maxM;
            const on = nbr ? (e.a === hover || e.b === hover) : true;
            return <line key={k} x1={g.pos[i].x} y1={g.pos[i].y} x2={g.pos[j].x} y2={g.pos[j].y}
              stroke={on && nbr ? accent : hexA("#ffffff", 0.05 + w * 0.25)} strokeOpacity={on ? 1 : 0.15}
              strokeWidth={0.6 + w * 3.4} />;
          })}
          {nodes.map((n) => {
            const i = g.idx[n.name];
            const p = players[n.name];
            const r = 12 + 10 * Math.sqrt(n.minutes / maxMin);
            const cap = p?.captain_rank;
            return (
              <SvgAvatar key={n.name} x={g.pos[i].x} y={g.pos[i].y} r={r} photo={p?.photo} name={`${n.name} · ${n.minutes}분 · 허브 ${n.hub_rank}위`}
                ring={cap ? "#f6c945" : LINE_COLOR[p?.line || "MID"]} ringW={cap ? 3 : 2} dim={!!nbr && !nbr.has(n.name)}
                onEnter={() => setHover(n.name)} onLeave={() => setHover(null)}
                onClick={(e) => peek(e, { name: n.name, club: d.team, hint: { photo: p?.photo, ovr: p?.ovr ?? undefined, pos: p?.pos } })}>
                <text y={r + 11} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.85)} style={{ pointerEvents: "none" }}>{lastName(n.name)}</text>
              </SvgAvatar>
            );
          })}
        </svg>
        {loose.length > 0 && <p className="net-note">연결 약함 · {loose.map((n) => lastName(n.name)).join(", ")}</p>}
        <div className="net-hover">
          {hover ? (
            <>
              <b>{hover}</b> <em>허브 {d.chemistry.nodes.find((n) => n.name === hover)?.hub_rank}위 · 파트너</em>
              {partners.map((e) => <span key={e.a + e.b}>{e.a === hover ? e.b : e.a} <i>{e.minutes}분</i></span>)}
            </>
          ) : <em>{nodes.length}명 · 연결 {edges.length}개</em>}
        </div>
      </div>
      <div className="net-chem-side">
        <h4 className="net-h">PARTNERSHIPS <span>함께 뛴 시간 순</span></h4>
        <Chemistry team={d.team} accent={accent} />
      </div>
    </div>
  );
}
