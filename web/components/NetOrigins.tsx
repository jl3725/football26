"use client";
import { useMemo } from "react";
import type { NetworkData, NetPlayer } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { ACQ, SvgAvatar, initials, lastName } from "./NetShared";
import Info from "./Info";

// ORIGINS — 스쿼드가 어떻게 만들어졌나. 입단 연도별로 쌓은 타임라인(테두리 색 = 영입 방식) + 출신 리그.
const LG_LABEL: Record<string, string> = { EPL: "Premier League", LaLiga: "La Liga", SerieA: "Serie A", Bundesliga: "Bundesliga",
  Ligue1: "Ligue 1", LigaPortugal: "Liga Portugal", Eredivisie: "Eredivisie", BelgianProLeague: "Belgian Pro League",
  ACADEMY: "Academy · 유스", OTHER: "기타 리그" };
const fee = (v: number) => (v >= 1e6 ? `€${Math.round(v / 1e6)}M` : v > 0 ? `€${Math.round(v / 1e3)}K` : "");

export default function NetOrigins({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const byName = useMemo(() => Object.fromEntries(d.players.map((p) => [p.name, p])), [d]);
  const now = new Date().getFullYear();
  // 12년보다 오래된 입단은 한 칸으로 묶는다
  const cut = now - 11;
  const cols = useMemo(() => {
    const m = new Map<number, NetPlayer[]>();
    for (const t of d.origins.timeline) {
      const y = Math.max(cut, t.year);
      const arr = m.get(y) ?? [];
      t.players.forEach((n) => byName[n] && arr.push(byName[n]));
      m.set(y, arr);
    }
    const years = [...m.keys()];
    const lo = Math.min(...years, now - 4);
    const out: { year: number; ps: NetPlayer[] }[] = [];
    for (let y = lo; y <= now; y++) out.push({ year: y, ps: (m.get(y) ?? []).sort((a, b) => b.minutes - a.minutes) });
    return out;
  }, [d, byName, cut, now]);
  const undated = d.players.filter((p) => !p.origin.year);
  const maxStack = Math.max(4, ...cols.map((c) => c.ps.length));
  const CW = 62, R = 14, GAP = 31, PAD = 26;
  const W = Math.max(560, cols.length * CW + PAD * 2), H = Math.min(9, maxStack) * GAP + 64;
  const base = H - 30;
  const acqKeys = Object.keys(ACQ).filter((k) => (d.origins.acq[k] ?? 0) > 0);
  const maxSrc = Math.max(1, ...d.origins.sources.map((s) => s.n));

  return (
    <div className="net-orig">
      <h4 className="net-h">SQUAD BUILD <span>입단 연도별</span>
        <Info label="스쿼드 구성 보는 법">
          <ul>
            <li>열 = 입단 연도 · 오래된 입단은 첫 칸에 묶음</li>
            <li>테두리 색 = 영입 방식 · 금색 점 = 주장단</li>
            <li>선수를 누르면 상세</li>
          </ul>
        </Info>
      </h4>
      <div className="net-legend wrap">
        {acqKeys.map((k) => <span key={k}><i style={{ background: ACQ[k].c }} />{ACQ[k].ko} <b>{d.origins.acq[k]}</b></span>)}
      </div>
      <div className="net-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" style={{ minWidth: Math.min(W, 900) }} role="img"
          aria-label="현재 스쿼드의 입단 연도 타임라인 — 영입 방식별 색">
          <line x1={PAD} y1={base} x2={W - PAD} y2={base} stroke={hexA("#ffffff", 0.18)} />
          {cols.map((c, i) => {
            const x = PAD + CW / 2 + i * CW;
            return (
              <g key={c.year}>
                <text x={x} y={base + 18} textAnchor="middle" fontSize="10.5" fill={hexA("#ffffff", c.year === now ? 0.95 : 0.55)}
                  fontWeight={c.year === now ? 700 : 400}>{c.year === cut && cols[0].year === cut ? `≤${c.year}` : c.year}</text>
                {c.ps.slice(0, 9).map((p, k) => {
                  const o = ACQ[p.origin.acq] ?? ACQ.unknown;
                  return (
                    <SvgAvatar key={p.name} x={x} y={base - 20 - k * GAP} r={R} photo={p.photo}
                      name={`${p.name} · ${o.ko}${p.origin.from_club ? ` ← ${p.origin.from_club}` : ""}${p.origin.fee_text ? ` · ${p.origin.fee_text}` : ""}`}
                      ring={o.c} ringW={2.4} onClick={(e) => peek(e, { name: p.name, club: d.team, hint: { photo: p.photo, ovr: p.ovr ?? undefined, pos: p.pos } })}>
                      {p.captain_rank ? <circle cx={R * 0.75} cy={-R * 0.75} r={4.5} fill="#f6c945" /> : null}
                    </SvgAvatar>
                  );
                })}
                {c.ps.length > 9 && <text x={x} y={base - 20 - 9 * GAP + 4} textAnchor="middle" fontSize="10" fill={hexA("#fff", 0.6)}>+{c.ps.length - 9}</text>}
              </g>
            );
          })}
        </svg>
      </div>
      {undated.length > 0 && (
        <div className="net-undated" title="TM 스쿼드 명단에서 입단일을 찾지 못한 선수 — 최근 등록·유스 승격 등">
          <span className="lbl">입단일 확인 중 {undated.length}<Info label="입단일 확인 중"><p>TM 스쿼드 명단에서 입단일을 찾지 못한 선수 — 최근 등록·유스 승격 등.</p></Info></span>
          {undated.slice(0, 10).map((p) => (
            <button key={p.name} className="chip hoverable" onClick={(e) => peek(e, { name: p.name, club: d.team, hint: { photo: p.photo, ovr: p.ovr ?? undefined, pos: p.pos } })}>
              {p.photo ? <img src={p.photo} alt="" /> : <i>{initials(p.name)}</i>}{lastName(p.name)}
            </button>
          ))}
          {undated.length > 10 && <em>+{undated.length - 10}</em>}
        </div>
      )}

      <div className="net-orig-grid">
        <div>
          <h4 className="net-h">SOURCES <span>어디서 왔나 · 유스 포함</span></h4>
          {d.origins.sources.map((s) => (
            <div key={s.league} className="net-src-row" title={s.players.join(", ")}>
              <span className="l">{LG_LABEL[s.league] ?? s.league}</span>
              <span className="bar"><i style={{ width: `${(s.n / maxSrc) * 100}%`, background: s.league === "ACADEMY" ? ACQ.academy.c : accent }} /></span>
              <b>{s.n}</b><em>{fee(s.fee_eur)}</em>
            </div>
          ))}
          {d.origins.sources.length === 0 && <p className="net-empty">출신 기록이 없습니다</p>}
        </div>
        <div>
          <h4 className="net-h">RECENT ARRIVALS <span>최근 두 이적창 영입</span></h4>
          <div className="net-arr">
            {d.players.filter((p) => p.origin.year && p.origin.year >= now - 1 && ["transfer", "loan", "free"].includes(p.origin.acq))
              .sort((a, b) => (b.origin.fee_eur ?? 0) - (a.origin.fee_eur ?? 0)).slice(0, 10).map((p) => (
                <button key={p.name} className="net-arr-row hoverable" onClick={(e) => peek(e, { name: p.name, club: d.team, hint: { photo: p.photo, ovr: p.ovr ?? undefined, pos: p.pos } })}>
                  {p.photo ? <img src={p.photo} alt="" /> : <span className="net-cap-ph sm" />}
                  <span><b>{p.name}</b><em>← {p.origin.from_club ?? "?"}</em></span>
                  <i style={{ color: ACQ[p.origin.acq]?.c }}>{p.origin.fee_text || ACQ[p.origin.acq]?.ko}</i>
                </button>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
