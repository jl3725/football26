"use client";
import { useState } from "react";
import type { NetNational } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar } from "./NetShared";
import Info from "./Info";

// 대표팀 동료 — 우리 선수가 든 2026 월드컵 명단의 나머지가 어느 클럽에 흩어져 있나.
// 가운데 국기, 둘레 = 클럽(원 크기 = 그 클럽의 대표팀 선수 수), 우리 클럽은 강조.
const W = 640, H = 330, CX = W / 2, CY = H / 2;

export default function NetNational({ nat, name, team, accent }: { nat: NetNational; name: string; team: string; accent: string }) {
  const peek = usePeek();
  const clubs = nat.clubs.filter((c) => c.club !== "OTHER");
  const other = nat.clubs.find((c) => c.club === "OTHER");
  const [sel, setSel] = useState<string>(team);
  const pts = clubs.slice(0, 16).map((c, i, arr) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / arr.length;
    return { c, x: CX + 255 * Math.cos(a), y: CY + 128 * Math.sin(a), r: 15 + 4 * Math.min(6, c.n) };
  });
  const byPlayer = Object.fromEntries(nat.players.map((p) => [p.player, p]));
  const cur = nat.clubs.find((c) => c.club === sel) ?? clubs[0];
  return (
    <div className="net-natweb">
      <h4 className="net-h">NATIONAL TEAM WEB <span>WC 명단 {nat.players.length}명 · 우리 {nat.n_ours}명</span>
        <Info wide label="대표팀 동료 보는 법">
          <p>{name} 2026 월드컵 명단 {nat.players.length}명 — 우리 {nat.n_ours}명 · {clubs.length}개 클럽{other ? ` · 8개 리그 밖 ${other.n}명` : ""}.</p>
          <ul>
            <li>가운데 = 국기 · 둘레 = 대표 선수의 소속 클럽</li>
            <li>원 크기·숫자 = 그 클럽의 대표 선수 수 · 우리 클럽 강조</li>
            <li>클럽을 누르면 명단</li>
          </ul>
        </Info>
      </h4>
      <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label={`${name} 대표팀 선수의 소속 클럽 분포`}>
        {pts.map(({ c, x, y }) => (
          <line key={c.club} x1={CX} y1={CY} x2={x} y2={y} stroke={c.club === team ? accent : hexA("#ffffff", 0.12)}
            strokeWidth={0.8 + c.n * 0.9} strokeOpacity={c.club === sel || c.club === team ? 0.95 : 0.6} />
        ))}
        <SvgAvatar x={CX} y={CY} r={30} photo={nat.flag} fit="cover" name={name} ring={hexA("#ffffff", 0.4)} />
        {pts.map(({ c, x, y, r }) => (
          <SvgAvatar key={c.club} x={x} y={y} r={r} photo={c.logo} fit="logo" name={`${c.club} · ${c.n}명`}
            ring={c.club === team ? accent : c.club === sel ? "#ffffff" : hexA("#ffffff", 0.22)} ringW={c.club === team || c.club === sel ? 3 : 1.5}
            onClick={() => setSel(c.club)}>
            <g transform={`translate(${r * 0.72},${-r * 0.72})`}><circle r={8} fill={c.club === team ? accent : "#2a3342"} />
              <text textAnchor="middle" dy="0.35em" fontSize="9" fontWeight={800} fill={c.club === team ? "#0a0d12" : "#e6ebf2"}>{c.n}</text></g>
            <text y={r + 11} textAnchor="middle" fontSize="9" fill={hexA("#ffffff", 0.75)} stroke="#0c1016" strokeWidth={3} paintOrder="stroke"
              style={{ pointerEvents: "none" }}>{c.club.length > 13 ? c.club.slice(0, 12) + "…" : c.club}</text>
          </SvgAvatar>
        ))}
      </svg>
      {cur && (
        <div className="net-natweb-sel">
          <div className="net-nat-head">{cur.logo && <img src={cur.logo} alt="" />}<b>{cur.club === "OTHER" ? "8개 리그 밖" : cur.club}</b><em>{name} 대표 {cur.n}명</em></div>
          <div className="net-nat-list">
            {cur.players.map((n) => {
              const p = byPlayer[n];
              return (
                <button key={n} className={`net-arr-row hoverable${p?.ours ? " ours" : ""}`}
                  onClick={(e) => peek(e, { name: n, club: p?.club || team, hint: { photo: p?.photo || undefined, ovr: p?.ovr ?? undefined } })}>
                  {p?.photo ? <img src={p.photo} alt="" /> : <span className="net-cap-ph sm" />}
                  <span><b>{n}</b><em>{p?.pos}{p?.ovr ? ` · ${p.ovr}` : ""}</em></span>
                </button>
              );
            })}
          </div>
          {other && cur.club !== "OTHER" && <button className="net-more" onClick={() => setSel("OTHER")}>8개 리그 밖 {other.n}명 보기</button>}
        </div>
      )}
    </div>
  );
}
