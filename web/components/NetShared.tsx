"use client";
import { useId, type ReactNode } from "react";
import { surname } from "@/lib/names";

// NETWORK 탭 공통 — 선 색·영입 방식 색, SVG 안 선수 사진 원형 아바타.
export const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
export const LINE_KO: Record<string, string> = { GK: "GK", DEF: "수비", MID: "미드", ATT: "공격" };
export const ACQ: Record<string, { c: string; en: string; ko: string }> = {
  academy: { c: "#4fc27f", en: "ACADEMY", ko: "유스" },
  transfer: { c: "#6aa6e0", en: "TRANSFER", ko: "이적" },
  loan: { c: "#f4cf5e", en: "LOAN", ko: "임대" },
  free: { c: "#c792ea", en: "FREE", ko: "자유계약" },
  return: { c: "#7fd1d8", en: "RETURN", ko: "임대 복귀" },
  signed: { c: "#8a94a8", en: "SIGNED", ko: "영입(이전)" },
  unknown: { c: "#5d6676", en: "N/A", ko: "미상" },
};

export const initials = (n: string) => n.split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
export const lastName = surname;   // 짧은 이름 한 곳(lib/names) — 'van Dijk'·'Mac Allister'

export function SvgAvatar({ x, y, r, photo, name, ring, ringW = 2, dim = false, fit = "face", onClick, onEnter, onLeave, children }: {
  x: number; y: number; r: number; photo?: string; name: string; ring: string; ringW?: number; dim?: boolean;
  fit?: "face" | "cover" | "logo";
  onClick?: (e: React.MouseEvent) => void; onEnter?: () => void; onLeave?: () => void; children?: ReactNode;
}) {
  const id = "a" + useId().replace(/[^a-zA-Z0-9]/g, "");
  return (
    <g transform={`translate(${x},${y})`} className="net-node" style={{ cursor: onClick ? "pointer" : "default", opacity: dim ? 0.22 : 1 }}
      onClick={onClick} onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <title>{name}</title>
      <defs><clipPath id={id}><circle r={r} /></clipPath></defs>
      <circle r={r} fill="#18202c" />
      {photo
        ? fit === "logo"
          ? <image href={photo} x={-r * 0.68} y={-r * 0.68} width={r * 1.36} height={r * 1.36} preserveAspectRatio="xMidYMid meet" />
          : <image href={photo} x={-r} y={-r} width={r * 2} height={fit === "face" ? r * 2.3 : r * 2} clipPath={`url(#${id})`}
              preserveAspectRatio={fit === "face" ? "xMidYMin slice" : "xMidYMid slice"} />
        : <text textAnchor="middle" dy="0.35em" fontSize={r * 0.72} fill="#c9d1dd" fontWeight={700}>{initials(name)}</text>}
      <circle r={r} fill="none" stroke={ring} strokeWidth={ringW} />
      {children}
    </g>
  );
}
