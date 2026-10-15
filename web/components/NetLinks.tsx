"use client";
import { useState } from "react";
import type { NetLink, NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar } from "./NetShared";

// LINKS — 이 팀을 가운데 둔 클럽 관계망. 선 종류 = 관계(영입·방출·떠난 선수가 지금 뛰는 클럽·이적설), 굵기 = 건수.
const W = 700, H = 450, CX = W / 2, CY = H / 2;
const KINDS: { k: keyof Pick<NetLink, "in" | "out" | "alumni" | "rumor_in" | "rumor_out">; en: string; ko: string; c: string; dash?: string }[] = [
  { k: "in", en: "IN", ko: "영입", c: "#4fc27f" },
  { k: "out", en: "OUT", ko: "방출", c: "#ff6b7d" },
  { k: "alumni", en: "ALUMNI", ko: "떠난 선수 현 소속", c: "#6aa6e0" },
  { k: "rumor_in", en: "RUMOR IN", ko: "영입설", c: "#f4cf5e", dash: "4 4" },
  { k: "rumor_out", en: "RUMOR OUT", ko: "이적설", c: "#e8a25c", dash: "4 4" },
];
// 연결 점수(src/team_network.links) = 영입·방출 건당 2 + 떠난 선수가 지금 뛰는 곳 1.5 + 이적설 0.8 — 높을수록 가까운 클럽
const WEIGHT_NOTE = "연결 점수 = 영입·방출 건당 2 + 떠난 선수(현 소속) 1.5 + 이적설 0.8 · 높을수록 가까운 클럽";
const short = (s: string) => (s.length > 14 ? s.split(" ").slice(0, 2).join(" ").slice(0, 14) : s);

export default function NetLinks({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const clubs = d.links.clubs;
  const [sel, setSel] = useState<string | null>(clubs[0]?.club ?? null);
  if (!clubs.length) return <p className="net-empty">연결된 클럽 기록이 없습니다</p>;
  const maxW = Math.max(1, ...clubs.map((c) => c.weight));
  const pts = clubs.map((c, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / clubs.length;
    const rr = 1 - 0.18 * (c.weight / maxW);                // 가까운 클럽일수록 안쪽
    return { c, x: CX + 285 * rr * Math.cos(a), y: CY + 178 * rr * Math.sin(a) };
  });
  const cur = clubs.find((c) => c.club === sel);
  return (
    <div className="net-links">
      <div className="net-toolbar">
        <h4 className="net-h">CLUB WEB <span>최근 두 이적창 · 떠난 선수가 지금 뛰는 클럽 · 이적설 — {d.links.n_clubs}개 클럽 중 상위 {clubs.length}</span></h4>
        <span className="net-legend">{KINDS.map((k) => <span key={k.k}><i style={{ background: k.c }} />{k.ko}</span>)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label="클럽 관계망 — 선 색은 관계 종류, 굵기는 건수">
        {pts.map(({ c, x, y }) => {
          const kinds = KINDS.filter((k) => c[k.k].length > 0);
          return kinds.map((k, ki) => {
            const off = (ki - (kinds.length - 1) / 2) * 16;
            const mx = (CX + x) / 2, my = (CY + y) / 2, dx = x - CX, dy = y - CY, L = Math.hypot(dx, dy) || 1;
            const qx = mx - (dy / L) * off, qy = my + (dx / L) * off;
            const on = !sel || sel === c.club;
            return <path key={c.club + k.k} d={`M${CX},${CY} Q${qx},${qy} ${x},${y}`} fill="none" stroke={k.c}
              strokeOpacity={on ? 0.85 : 0.18} strokeWidth={1.2 + c[k.k].length * 1.1} strokeDasharray={k.dash} />;
          });
        })}
        <SvgAvatar x={CX} y={CY} r={36} photo={d.logo} fit="logo" name={d.team} ring={accent} ringW={3} />
        {pts.map(({ c, x, y }) => (
          <SvgAvatar key={c.club} x={x} y={y} r={sel === c.club ? 25 : 21} photo={c.logo} fit="logo" name={`${c.club} · 연결 점수 ${c.weight}`}
            ring={sel === c.club ? accent : hexA("#ffffff", 0.22)} ringW={sel === c.club ? 3 : 1.5} onClick={() => setSel(c.club)}>
            <text y={(sel === c.club ? 25 : 21) + 12} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", sel === c.club ? 0.95 : 0.7)}
              style={{ pointerEvents: "none" }}>{short(c.club)}</text>
          </SvgAvatar>
        ))}
      </svg>
      {cur && (
        <div className="net-link-sel">
          <div className="net-nat-head">
            {cur.logo && <img src={cur.logo} alt="" />}
            <b>{cur.club}</b><em title={WEIGHT_NOTE}>{cur.league ?? "8개 리그 밖"} · 연결 점수 {cur.weight}</em>
          </div>
          <p className="net-note" style={{ fontSize: 11, color: "var(--muted-2)", margin: "2px 0 8px" }}>{WEIGHT_NOTE}</p>
          <div className="net-link-cols">
            {KINDS.filter((k) => cur[k.k].length > 0).map((k) => (
              <div key={k.k} className="net-link-col">
                <h5 style={{ color: k.c }}>{k.en} <span>{k.ko}</span></h5>
                {cur[k.k].map((m, i) => (
                  <button key={m.player + i} className="net-arr-row hoverable"
                    onClick={(e) => peek(e, { name: m.player, club: k.k === "alumni" || k.k === "out" || k.k === "rumor_in" ? cur.club : d.team, hint: { photo: m.photo || undefined } })}>
                    {m.photo ? <img src={m.photo} alt="" /> : <span className="net-cap-ph sm" />}
                    <span><b>{m.player}</b><em>{m.fee_text || (m.ovr ? `OVR ${m.ovr}` : m.prob ? `${m.prob}%` : m.window || "")}</em></span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
