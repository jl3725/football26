"use client";
import type { Placement } from "@/lib/api";

const KIND_COLOR: Record<string, string> = { GK: "#37c98a", DEF: "#4c8ef0", MID: "#e0a53a", FWD: "#e2564f" };

function lastName(name: string): string {
  if (!name || name === "—") return "—";
  const parts = name.split(" ");
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function initials(name: string): string {
  if (!name || name === "—" || name === "영입 필요") return "?";
  const p = name.split(" ").filter(Boolean);
  if (p.length >= 2) return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

// SVG 배경(잔디+라인) + HTML 토큰(둥근 얼굴). clipPath 미사용 → id 충돌·렌더 불안정 없음.
export default function Pitch({ placements, accent }: { placements: Placement[]; formation?: string; accent?: string; idKey?: string }) {
  return (
    <div className="pitch2">
      <svg viewBox="0 0 100 108" className="pitch2-bg" preserveAspectRatio="none">
        <rect x="0" y="0" width="100" height="108" fill="#0f3020" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x="0" y={i * 18} width="100" height="9" fill={i % 2 ? "rgba(255,255,255,0.02)" : "transparent"} />
        ))}
        <g stroke="rgba(255,255,255,0.16)" strokeWidth="0.4" fill="none">
          <rect x="4" y="4" width="92" height="100" />
          <line x1="4" y1="54" x2="96" y2="54" />
          <circle cx="50" cy="54" r="9" />
          <rect x="28" y="4" width="44" height="14" />
          <rect x="28" y="90" width="44" height="14" />
          <rect x="40" y="4" width="20" height="6" />
          <rect x="40" y="98" width="20" height="6" />
        </g>
      </svg>
      {placements.map((p, i) => {
        const c = KIND_COLOR[p.kind] || "#888";
        const left = 4 + (p.x / 100) * 92;          // viewBox width 100 → %
        const top = ((4 + (p.y / 100) * 100) / 108) * 100;
        return (
          <div className="ptok" key={i} style={{ left: `${left}%`, top: `${top}%` }}>
            <div className="ptok-face" style={{ borderColor: c }}>
              {p.photo
                ? <img src={p.photo} alt="" />
                : <span className="ptok-init" style={{ background: `linear-gradient(135deg, ${c}44, #10151e)`, color: "#eef2f8" }}>{initials(p.player)}</span>}
              {p.ovr != null && <span className="ptok-ovr" style={{ background: c }}>{p.ovr}</span>}
            </div>
            <div className="ptok-name">{lastName(p.player)}</div>
          </div>
        );
      })}
    </div>
  );
}
