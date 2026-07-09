"use client";
import { hexA } from "@/lib/ui";

const W = 380, H = 246;

// 값(0-100) → 초록(저)→빨강(핫) + 알파(밀도)
function heat(v: number): string {
  const h = (1 - v / 100) * 140;
  const a = 0.12 + (v / 100) * 0.72;
  return `hsla(${h}, 85%, 52%, ${a})`;
}

// 순수 렌더 — 히트 그리드(블러) + 피치 라인. dots: 팀 대형용 선택 오버레이.
export default function HeatmapPitch({ grid, gw, gh, id = "hm", dots }: {
  grid: number[]; gw: number; gh: number; id?: string;
  dots?: { x: number; y: number; label: string; color: string }[];
}) {
  const cw = W / gw, ch = H / gh;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 470, background: "#0c1c14", borderRadius: 12, display: "block" }}>
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
          <circle r="9" fill={hexA(d.color, 0.9)} stroke="#0c1c14" strokeWidth="1.5" />
          <text y="3.5" textAnchor="middle" fontSize="8.5" fontWeight={700} fill="#0c1c14" style={{ pointerEvents: "none" }}>{d.label}</text>
        </g>
      ))}
      <text x={W - 8} y={15} textAnchor="end" fontSize="9.5" fill={hexA("#ffffff", 0.4)}>공격 →</text>
    </svg>
  );
}
