"use client";
import { hexA } from "@/lib/ui";

const W = 380, H = 246;

// 값(0-100) → 한 계열 열기 색(보라 → 코랄 → 호박 → 흰빛, magma 계열) + 알파(밀도).
// 예전 초록→빨강 무지개는 색이 많아 싸 보였고, 색각 이상이면 초록·빨강 구분도 어렵다(디자인 v5).
const STOPS: [number, number[]][] = [[0, [72, 26, 120]], [0.35, [168, 50, 120]], [0.6, [255, 92, 94]], [0.82, [255, 170, 90]], [1, [255, 240, 200]]];
export function heat(v: number): string {
  const t = Math.max(0, Math.min(1, v / 100));
  let i = 0;
  while (i < STOPS.length - 2 && t > STOPS[i + 1][0]) i++;
  const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1];
  const k = (t - t0) / (t1 - t0 || 1);
  const c = c0.map((x, j) => Math.round(x + (c1[j] - x) * k));
  const a = 0.16 + t * 0.7;
  return `rgba(${c[0]},${c[1]},${c[2]},${a.toFixed(3)})`;
}

// 순수 렌더 — 히트 그리드(블러) + 피치 라인. dots: 팀 대형용 선택 오버레이.
export default function HeatmapPitch({ grid, gw, gh, id = "hm", dots }: {
  grid: number[]; gw: number; gh: number; id?: string;
  dots?: { x: number; y: number; label: string; color: string }[];
}) {
  const cw = W / gw, ch = H / gh;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 470, background: "linear-gradient(180deg, #0f1914, #0b130f)", borderRadius: 12, display: "block" }}>
      <defs><filter id={`${id}-blur`} x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7" /></filter></defs>
      <g filter={`url(#${id}-blur)`}>
        {grid.map((v, idx) => {
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
      {/* 팀 대형: 선수 centroid 점 */}
      {dots?.map((d, i) => (
        <g key={i} transform={`translate(${d.x / 100 * W},${d.y / 100 * H})`}>
          <circle r="9" fill={hexA(d.color, 0.9)} stroke="#0b130f" strokeWidth="1.5" />
          <text y="3.5" textAnchor="middle" fontSize="8.5" fontWeight={700} fill="#0b130f" style={{ pointerEvents: "none" }}>{d.label}</text>
        </g>
      ))}
      <text x={W - 8} y={15} textAnchor="end" fontSize="9.5" fill={hexA("#ffffff", 0.4)}>공격 →</text>
    </svg>
  );
}
