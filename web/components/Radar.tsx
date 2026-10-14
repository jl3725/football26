"use client";
import { hexA } from "@/lib/ui";

export default function Radar({ data, color }: { data: { axis: string; value: number }[]; color: string }) {
  const cx = 150, cy = 150, R = 100, N = data.length || 1;
  const pt = (i: number, r: number): [number, number] => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / N;
    return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
  };
  const rings = [0.25, 0.5, 0.75, 1];
  const clamp = (v: number) => Math.max(0, Math.min(100, v));
  const poly = data.map((d, i) => pt(i, (clamp(d.value) / 100) * R).join(",")).join(" ");
  return (
    <svg viewBox="0 0 300 300" width="100%" height="270" style={{ overflow: "visible", maxWidth: 380, display: "block", margin: "0 auto" }}>
      <defs>
        <radialGradient id="radfill" cx="50%" cy="50%" r="70%">
          <stop offset="0%" stopColor={hexA(color, 0.42)} />
          <stop offset="100%" stopColor={hexA(color, 0.12)} />
        </radialGradient>
      </defs>
      {rings.map((rr, k) => (
        <polygon key={k} points={data.map((_, i) => pt(i, rr * R).join(",")).join(" ")}
          fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
      ))}
      {data.map((_, i) => {
        const [x, y] = pt(i, R);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(255,255,255,0.05)" />;
      })}
      <polygon points={poly} fill="url(#radfill)" stroke={color} strokeWidth={2}
        style={{ transition: "all .5s cubic-bezier(.2,.8,.2,1)" }} />
      {data.map((d, i) => {
        const [vx, vy] = pt(i, (clamp(d.value) / 100) * R);
        const [lx, ly] = pt(i, R + 22);
        return (
          <g key={i}>
            <circle cx={vx} cy={vy} r={3.2} fill={color} />
            {/* 축소 표시돼도 읽히게 — viewBox 300 기준 12.5/15 (예전 10/11 은 실제 8px 대) */}
            <text x={lx} y={ly - 2} fontSize={12.5} fill="#9aa4b8" textAnchor="middle" dominantBaseline="middle"
              style={{ fontFamily: "var(--font-label)", fontWeight: 600 }} letterSpacing={0.3}>{d.axis}</text>
            <text x={lx} y={ly + 13} fontSize={15} fill="#e8edf6" textAnchor="middle" style={{ fontFamily: "var(--font-num)", fontWeight: 700 }}>{d.value}</text>
          </g>
        );
      })}
    </svg>
  );
}
