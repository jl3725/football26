"use client";
import { useState } from "react";
import type { Overview } from "@/lib/api";
import { hexA } from "@/lib/ui";
import SquadGraph from "./SquadGraph";

const LINE_COLOR: Record<string, string> = { ATT: "#ff6b6b", MID: "#f4cf5e", DEF: "#4a86ff", GK: "#4fc27f" };
const BANDS = [90, 85, 80, 75, 70, 60];

export default function RatingsBoard({ ov, accent }: { ov: Overview; accent: string }) {
  const [view, setView] = useState<"network" | "scatter">("network");
  const sr = ov.squad_ratings || [];
  if (sr.length === 0) return null;

  const W = 360, H = 240, padL = 26, padB = 22, padT = 12, padR = 12;
  const AGE0 = 15, AGE1 = 38, O0 = 48, O1 = 99;
  const x = (a: number) => padL + (Math.max(AGE0, Math.min(AGE1, a)) - AGE0) / (AGE1 - AGE0) * (W - padL - padR);
  const y = (o: number) => H - padB - (Math.max(O0, Math.min(O1, o)) - O0) / (O1 - O0) * (H - padB - padT);
  const avg = Math.round(sr.reduce((a, p) => a + p.ovr, 0) / sr.length);

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}>스쿼드 {view === "network" ? "네트워크" : "평가"}
          <span className="rating-note">· {view === "network" ? "함께 뛴 조합" : "나이 대비 OVR/POT"}</span></h3>
        <div style={{ display: "inline-flex", gap: 2, padding: 3, borderRadius: 9, background: hexA("#ffffff", 0.05), border: `1px solid ${hexA(accent, 0.15)}` }}>
          {([["network", "네트워크"], ["scatter", "산점도"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setView(v)} style={{ padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none", background: view === v ? accent : "transparent", color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{l}</button>
          ))}
        </div>
      </div>
      {view === "network" ? <SquadGraph team={ov.team} accent={accent} /> : (
      <><svg viewBox={`0 0 ${W} ${H}`} className="ovr-scatter" preserveAspectRatio="xMidYMid meet">
        {/* 피크 나이 구간 24–29 음영 */}
        <rect x={x(24)} y={padT} width={x(29) - x(24)} height={H - padB - padT} fill="rgba(255,255,255,0.035)" />
        {/* OVR 밴드 그리드 */}
        {BANDS.map((b) => (
          <g key={b}>
            <line x1={padL} x2={W - padR} y1={y(b)} y2={y(b)} stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
            <text x={padL - 4} y={y(b) + 3} textAnchor="end" className="sc-lbl">{b}</text>
          </g>
        ))}
        {/* 나이 축 */}
        {[16, 20, 24, 28, 32, 36].map((a) => (
          <text key={a} x={x(a)} y={H - padB + 14} textAnchor="middle" className="sc-lbl">{a}세</text>
        ))}
        {/* 선수: OVR→POT 성장여지 선 + 점 */}
        {sr.map((p, i) => {
          const cx = x(p.age), cyO = y(p.ovr), cyP = y(p.pot);
          const c = LINE_COLOR[p.line] || "#8a94a8";
          const r = 3 + Math.min(3, (p.minutes / 1200) * 3);
          return (
            <g key={i}>
              {p.pot > p.ovr && <line x1={cx} x2={cx} y1={cyO} y2={cyP} stroke={c} strokeOpacity="0.45" strokeDasharray="2 2" />}
              {p.pot > p.ovr && <circle cx={cx} cy={cyP} r="2" fill="none" stroke={c} strokeOpacity="0.7" />}
              <circle cx={cx} cy={cyO} r={r} fill={c} fillOpacity="0.9">
                <title>{`${p.player} · ${p.age}세 · OVR ${p.ovr}${p.pot > p.ovr ? ` → POT ${p.pot}` : ""} · ${p.minutes}′`}</title>
              </circle>
            </g>
          );
        })}
        {/* 팀 평균선 */}
        <line x1={padL} x2={W - padR} y1={y(avg)} y2={y(avg)} stroke={accent} strokeDasharray="4 3" strokeWidth="1.5" />
        <text x={W - padR} y={y(avg) - 4} textAnchor="end" className="sc-lbl" style={{ fill: accent, fontWeight: 700 }}>팀 {avg}</text>
      </svg>
      <div className="sc-legend">
        <span><i style={{ background: LINE_COLOR.ATT }} />공격</span>
        <span><i style={{ background: LINE_COLOR.MID }} />미드</span>
        <span><i style={{ background: LINE_COLOR.DEF }} />수비</span>
        <span><i style={{ background: LINE_COLOR.GK }} />GK</span>
        <span className="sc-pot">○┄ 위쪽 = POT(성장여지)</span>
      </div></>)}
    </div>
  );
}
