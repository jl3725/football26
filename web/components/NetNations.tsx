"use client";
import { useMemo, useState } from "react";
import type { NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar } from "./NetShared";
import NetNational from "./NetNational";

// NATIONS — 국적(REPRESENTS) 버블: 크기 = 선수 수, 국기·FIFA 랭킹, 금색 점 = 2026 월드컵 명단 인원.
const W = 680, H = 380;

function pack(sizes: number[]) {
  const placed: { x: number; y: number; r: number }[] = [];
  sizes.forEach((r, i) => {
    if (i === 0) { placed.push({ x: W / 2, y: H / 2, r }); return; }
    for (let t = 0; t < 4000; t++) {
      const a = t * 0.31, d = 6 + t * 0.9;
      const x = W / 2 + d * Math.cos(a) * 1.35, y = H / 2 + d * Math.sin(a);
      if (x - r < 6 || x + r > W - 6 || y - r < 6 || y + r > H - 22) continue;
      if (placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + r + 16)) { placed.push({ x, y, r }); return; }
    }
    placed.push({ x: -999, y: -999, r });                   // 못 넣으면 숨김(아래 목록에는 남음)
  });
  return placed;
}

export default function NetNations({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const cs = d.nations.countries;
  const firstNat = cs.find((c) => d.national?.[c.name] || Object.values(d.national ?? {}).some((x) => x.fifa_name === c.name));
  const [sel, setSel] = useState<string | null>((firstNat ?? cs[0])?.name ?? null);
  const byName = useMemo(() => Object.fromEntries(d.players.map((p) => [p.name, p])), [d]);
  const sizes = cs.map((c) => 18 + 13 * Math.sqrt(c.players.length));
  const pos = useMemo(() => pack(sizes), [d]); // eslint-disable-line react-hooks/exhaustive-deps
  const cur = cs.find((c) => c.name === sel);
  // 대표팀 동료 데이터(월드컵 명단 기준)는 월드컵 표기·FIFA 표기 어느 쪽으로든 찾는다
  const natOf = (n: string) => d.national?.[n] ?? Object.values(d.national ?? {}).find((x) => x.fifa_name === n);
  if (!cs.length) return <p className="net-empty">국적 정보가 없습니다</p>;
  return (
    <div className="net-nat">
      <div className="net-toolbar">
        <h4 className="net-h">NATIONAL WEB <span>{d.nations.n}개국 · 2026 월드컵 명단 {d.nations.wc_total}명 · 원 크기 = 선수 수</span></h4>
        <span className="net-legend"><span><i className="cap" />월드컵 명단</span></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label="국적별 선수 수 버블 — 국기와 FIFA 랭킹">
        {cs.map((c, i) => {
          const p = pos[i];
          if (p.x < 0) return null;
          const on = sel === c.name;
          return (
            <SvgAvatar key={c.name} x={p.x} y={p.y} r={p.r} photo={c.flag} fit="cover" name={`${c.name} · ${c.players.length}명${c.rank ? ` · FIFA ${c.rank}위` : ""}`}
              ring={on ? accent : hexA("#ffffff", 0.25)} ringW={on ? 3 : 1.5} onClick={() => setSel(c.name)}>
              {c.wc > 0 && <g transform={`translate(${p.r * 0.7},${-p.r * 0.7})`}>
                <circle r={8} fill="#f6c945" /><text textAnchor="middle" dy="0.35em" fontSize="8.5" fontWeight={800} fill="#151515">{c.wc}</text></g>}
            </SvgAvatar>
          );
        })}
        {cs.map((c, i) => {
          const p = pos[i];
          if (p.x < 0) return null;
          const on = sel === c.name;
          return <text key={c.name + "-l"} x={p.x} y={p.y + p.r + 12} textAnchor="middle" fontSize="10" fill={hexA("#ffffff", on ? 0.95 : 0.75)}
            fontWeight={on ? 700 : 500} stroke="#0c1016" strokeWidth={3} paintOrder="stroke" style={{ pointerEvents: "none" }}>{c.name} {c.players.length}</text>;
        })}
      </svg>
      {cur && (
        <div className="net-nat-sel">
          <div className="net-nat-head">
            {cur.flag && <img src={cur.flag} alt="" />}
            <b>{cur.name}</b>
            <em>{cur.players.length}명{cur.rank ? ` · FIFA 랭킹 ${cur.rank}위` : ""}{cur.wc ? ` · 월드컵 명단 ${cur.wc}명` : ""}</em>
          </div>
          <div className="net-nat-list">
            {cur.players.map((n) => {
              const p = byName[n];
              return (
                <button key={n} className="net-arr-row hoverable" onClick={(e) => peek(e, { name: n, club: d.team, hint: { photo: p?.photo, ovr: p?.ovr ?? undefined, pos: p?.pos } })}>
                  {p?.photo ? <img src={p.photo} alt="" /> : <span className="net-cap-ph sm" />}
                  <span><b>{n}</b><em>{p?.pos}{p?.ovr ? ` · ${p.ovr}` : ""}</em></span>
                  {p?.wc && <i style={{ color: "#f6c945" }}>WC</i>}
                </button>
              );
            })}
          </div>
          {natOf(cur.name) && <NetNational nat={natOf(cur.name)!} name={cur.name} team={d.team} accent={accent} />}
        </div>
      )}
    </div>
  );
}
