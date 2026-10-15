"use client";
import { useMemo, useState } from "react";
import type { NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar, lastName } from "./NetShared";

// TIES — 지난 시즌 라인업(함께 선발 5경기+)으로 본 '전 소속 동료'. 왼쪽 = 우리 선수, 오른쪽 = 그 동료가 지금 뛰는 클럽.
// 주황 = 영입생이 전 소속에서 함께 뛴 동료, 파랑 = 작년 우리 팀 동료가 떠나 지금 뛰는 곳. 재회 = 다른 팀에서 함께 뛰다 지금 우리 팀.
const KIND = { former: { c: "#f0a35a", ko: "영입생의 전 소속 동료" }, alumni: { c: "#6aa6e0", ko: "작년 우리 팀 동료(떠남)" } } as const;

export default function NetTies({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const ti = d.ties;
  const [sel, setSel] = useState<string | null>(ti.clubs[0]?.club ?? null);
  const photo = useMemo(() => Object.fromEntries(d.players.map((p) => [p.name, p.photo])), [d]);
  const clubs = ti.clubs.slice(0, 12);
  const ours = useMemo(() => {
    const s = new Map<string, number>();
    clubs.forEach((c) => c.ties.forEach((t) => s.set(t.ours, (s.get(t.ours) ?? 0) + t.starts)));
    return [...s.entries()].sort((a, b) => b[1] - a[1]).map(([n]) => n).slice(0, 14);
  }, [clubs]);
  if (!ti.clubs.length && !ti.reunions.length) return <p className="net-empty">지난 시즌 라인업으로 이어진 다른 클럽 동료가 없습니다</p>;
  const W = 700, RowL = 38, RowR = 44;
  const H = Math.max(ours.length * RowL, clubs.length * RowR) + 40;
  const ly = (i: number) => 24 + i * ((H - 48) / Math.max(1, ours.length - 1 || 1));
  const ry = (i: number) => 24 + i * ((H - 48) / Math.max(1, clubs.length - 1 || 1));
  const li = Object.fromEntries(ours.map((n, i) => [n, i]));
  const cur = clubs.find((c) => c.club === sel);
  const maxS = Math.max(1, ...clubs.flatMap((c) => c.ties.map((t) => t.starts)));

  return (
    <div className="net-ties">
      <div className="net-toolbar">
        <h4 className="net-h">EX-TEAMMATES <span>지난 시즌 함께 선발 5경기+ · 동료 {ti.n_ties}명 · {ti.n_clubs}개 클럽</span></h4>
        <span className="net-legend">{Object.values(KIND).map((k) => <span key={k.ko}><i style={{ background: k.c }} />{k.ko}</span>)}</span>
      </div>
      {ti.reunions.length > 0 && (
        <div className="net-reunion">
          <b>REUNION <span>재회</span></b>
          {ti.reunions.map((r) => <span key={r.ours + r.mate}>{r.ours} · {r.mate} <em>{r.from_club}에서 {r.starts}경기 함께 → 지금 같은 팀</em></span>)}
        </div>
      )}
      {clubs.length > 0 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label="우리 선수와 지난 시즌 동료가 지금 뛰는 클럽의 연결">
          {clubs.map((c, ci) => c.ties.map((t, k) => {
            const i = li[t.ours];
            if (i == null) return null;
            const x1 = 130, y1 = ly(i), x2 = W - 150, y2 = ry(ci);
            const on = !sel || sel === c.club;
            return <path key={c.club + k} d={`M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`} fill="none"
              stroke={KIND[t.kind === "alumni" ? "alumni" : "former"].c} strokeOpacity={on ? 0.85 : 0.12} strokeWidth={0.8 + (t.starts / maxS) * 4} />;
          }))}
          {ours.map((n, i) => (
            <SvgAvatar key={n} x={110} y={ly(i)} r={14} photo={photo[n]} name={n} ring={hexA("#ffffff", 0.3)}
              onClick={(e) => peek(e, { name: n, club: d.team, hint: { photo: photo[n] } })}>
              <text x={-20} textAnchor="end" dy="0.35em" fontSize="10.5" fill={hexA("#ffffff", 0.85)} style={{ pointerEvents: "none" }}>{lastName(n)}</text>
            </SvgAvatar>
          ))}
          {clubs.map((c, ci) => (
            <SvgAvatar key={c.club} x={W - 130} y={ry(ci)} r={sel === c.club ? 19 : 16} photo={c.logo} fit="logo" name={`${c.club} · 동료 ${c.ties.length}명`}
              ring={sel === c.club ? accent : hexA("#ffffff", 0.22)} ringW={sel === c.club ? 3 : 1.5} onClick={() => setSel(c.club)}>
              <text x={24} dy="0.35em" fontSize="10.5" fill={hexA("#ffffff", sel === c.club ? 0.95 : 0.75)} style={{ pointerEvents: "none" }}>
                {c.club.length > 16 ? c.club.slice(0, 15) + "…" : c.club} <tspan fill={hexA("#ffffff", 0.45)}>{c.ties.length}</tspan></text>
            </SvgAvatar>
          ))}
        </svg>
      )}
      {cur && (
        <div className="net-link-sel">
          <div className="net-nat-head">{cur.logo && <img src={cur.logo} alt="" />}<b>{cur.club}</b><em>{cur.league ?? ""} · 우리 선수와 함께 뛴 동료 {cur.ties.length}명</em></div>
          <div className="net-tie-list">
            {cur.ties.map((t) => (
              <button key={t.ours + t.mate} className="net-tie hoverable" onClick={(e) => peek(e, { name: t.mate, club: cur.club, hint: { photo: t.mate_photo || undefined, ovr: t.mate_ovr ?? undefined } })}>
                {t.ours_photo ? <img src={t.ours_photo} alt="" /> : <span className="net-cap-ph sm" />}
                <span className="net-tie-mid" style={{ color: KIND[t.kind === "alumni" ? "alumni" : "former"].c }}>
                  <i>{t.starts}경기 함께</i><em>{t.from_club}{t.links && t.links > 1 ? ` · 우리 선수 ${t.links}명과` : ""}</em></span>
                {t.mate_photo ? <img src={t.mate_photo} alt="" /> : <span className="net-cap-ph sm" />}
                <span className="net-tie-n"><b>{lastName(t.ours)} ↔ {t.mate}</b><em>{t.mate_ovr ? `OVR ${t.mate_ovr}` : ""}</em></span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
