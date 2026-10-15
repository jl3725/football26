"use client";
import { useMemo, useState } from "react";
import type { NetSpell, NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar, lastName } from "./NetShared";

// MANAGER — 감독 커리어(위키 인포박스: 감독·선수 경력) 타임라인 + 같은 클럽을 거친 현직 감독 네트워크 + 전 팀에서 함께 온 선수.
export default function NetManager({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const m = d.manager;
  const [sel, setSel] = useState<string | null>(m.network?.[0]?.manager ?? null);
  const now = new Date().getFullYear();
  const logoOf = useMemo(() => {
    const o: Record<string, string> = {};
    [...(m.managed ?? []), ...(m.played ?? [])].forEach((s) => { if (s.logo) o[s.club] = s.logo; });
    return o;
  }, [m]);
  if (!m.available) return <p className="net-empty">감독 경력 정보를 찾지 못했습니다(위키백과 인포박스 없음){m.name ? ` — ${m.name}` : ""}</p>;

  const spells = [...(m.managed ?? []), ...(m.played ?? [])].filter((s) => s.start);
  const y0 = Math.min(...spells.map((s) => s.start as number), now - 6), y1 = now + 1;
  const W = 760, PADL = 70, PADR = 20, X = (y: number) => PADL + ((y - y0) / (y1 - y0)) * (W - PADL - PADR);
  const assign = (list: NetSpell[]) => {
    const rows: number[] = [];
    return list.filter((s) => s.start).map((s) => {
      const a = s.start as number, b = s.end == null ? now + 1 : s.end === s.start ? s.end + 0.6 : s.end;
      let r = 0;
      while (rows[r] != null && rows[r] > a + 0.01) r++;
      rows[r] = b;
      return { s, a, b, r };
    });
  };
  const mRows = assign(m.managed ?? []), pRows = assign(m.played ?? []);
  const nM = Math.max(1, ...mRows.map((x) => x.r + 1)), nP = Math.max(1, ...pRows.map((x) => x.r + 1));
  const MH = 22, PH = 14, TOP = 26, GAP = 34;
  const H = TOP + nM * (MH + 8) + GAP + nP * (PH + 8) + 26;
  const pBase = TOP + nM * (MH + 8) + GAP;
  const lane = (rowsOf: ReturnType<typeof assign>, base: number, color: string, h: number) => {
    return rowsOf.map(({ s, a, b, r }, i) => {
      const y = base + r * (h + 8);
      const cur = s.end == null;
      return (
        <g key={i}>
          <title>{`${s.club} ${s.start}–${s.end ?? "현재"}${s.role ? ` (${s.role})` : ""}${s.loan ? " (임대)" : ""}`}</title>
          <rect x={X(a)} y={y} width={Math.max(6, X(b) - X(a))} height={h} rx={h / 2} fill={color}
            fillOpacity={cur ? 1 : s.role || s.loan ? 0.35 : 0.65} stroke={cur ? "#fff" : "none"} strokeWidth={1} />
          {s.logo && <image href={s.logo} x={X(a) + 3} y={y + h / 2 - 7} width={14} height={14} />}
          <text x={X(a) + (s.logo ? 20 : 4)} y={y + h / 2} dy="0.35em" fontSize="9.5" fill={cur ? "#0a0d12" : "#e8edf3"} fontWeight={cur ? 800 : 600}
            style={{ pointerEvents: "none" }}>{X(b) - X(a) > 70 ? s.club : ""}</text>
        </g>
      );
    });
  };
  const ticks: number[] = [];
  for (let y = Math.ceil(y0 / 5) * 5; y <= y1; y += 5) ticks.push(y);

  const net = (m.network ?? []).slice(0, 12);
  const short = (n: string) => (n.length <= 14 ? n : lastName(n));
  const shared = [...new Set(net.flatMap((n) => n.shared.map((s) => s.club)))].slice(0, 10);
  const RW = 700, RH = 420, cx = RW / 2, cy = RH / 2;
  const cpos = Object.fromEntries(shared.map((c, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / shared.length;
    return [c, { x: cx + 150 * Math.cos(a), y: cy + 105 * Math.sin(a) }];
  }));
  const mpos = net.map((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * (i + 0.5)) / net.length;
    return { n, x: cx + 300 * Math.cos(a), y: cy + 185 * Math.sin(a) };
  });
  const cur = net.find((n) => n.manager === sel);

  return (
    <div className="net-mgr">
      <div className="net-mgr-head">
        {m.photo ? <img src={m.photo} alt="" /> : <span className="net-cap-ph" />}
        <div>
          <em>MANAGER · 감독</em>
          <b>{m.name}</b>
          <span>{[m.nationality, m.appointed ? `부임 ${m.appointed}` : ""].filter(Boolean).join(" · ")}</span>
          <div className="net-chips">
            <i>감독 {new Set((m.managed ?? []).map((s) => s.club)).size}개 클럽</i>
            {(m.played ?? []).length > 0 && <i>선수 {new Set((m.played ?? []).map((s) => s.club)).size}개 클럽</i>}
            {m.n_network ? <i>같은 클럽을 거친 현직 감독 {m.n_network}명</i> : null}
          </div>
        </div>
      </div>

      <h4 className="net-h">CAREER <span>위쪽 = 감독 · 아래쪽 = 선수 경력 · 흰 테두리 = 현재</span></h4>
      <div className="net-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" style={{ minWidth: 640 }} role="img" aria-label={`${m.name} 감독·선수 경력 타임라인`}>
          {ticks.map((t) => <g key={t}><line x1={X(t)} y1={18} x2={X(t)} y2={H - 18} stroke={hexA("#ffffff", 0.06)} />
            <text x={X(t)} y={H - 4} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.45)}>{t}</text></g>)}
          <text x={8} y={TOP + MH / 2} dy="0.35em" fontSize="9.5" fill={hexA("#ffffff", 0.55)} letterSpacing="1">MANAGER</text>
          <text x={8} y={pBase + PH / 2} dy="0.35em" fontSize="9.5" fill={hexA("#ffffff", 0.55)} letterSpacing="1">PLAYER</text>
          {lane(mRows, TOP, "#5b8def", MH)}
          {lane(pRows, pBase, "#7f8a9c", PH)}
        </svg>
      </div>

      {net.length > 0 && (
        <>
          <h4 className="net-h">COACHING NETWORK <span>같은 클럽을 감독·선수로 거친 현직 감독(8개 리그) {m.n_network}명 중 연결 많은 {net.length}명 — 가운데 = {short(m.name || "")}</span></h4>
          <svg viewBox={`0 0 ${RW} ${RH}`} className="net-svg" role="img" aria-label="같은 클럽을 거친 현직 감독 관계망">
            {shared.map((c) => <line key={c} x1={cx} y1={cy} x2={cpos[c].x} y2={cpos[c].y} stroke={hexA("#ffffff", 0.4)} strokeWidth={1.6} />)}
            {mpos.map(({ n, x, y }) => n.shared.filter((s) => cpos[s.club]).map((s) => (
              <line key={n.manager + s.club} x1={x} y1={y} x2={cpos[s.club].x} y2={cpos[s.club].y}
                stroke={s.theirs === "managed" ? "#f6c945" : "#7f8a9c"} strokeOpacity={!sel || sel === n.manager ? 0.8 : 0.12}
                strokeWidth={sel === n.manager ? 2.4 : 1.2} strokeDasharray={s.theirs === "played" ? "3 3" : undefined} />
            )))}
            <SvgAvatar x={cx} y={cy} r={30} photo={m.photo} name={m.name || ""} ring={accent} ringW={3} />
            {shared.map((c) => (
              <SvgAvatar key={c} x={cpos[c].x} y={cpos[c].y} r={15} photo={logoOf[c]} fit="logo" name={c} ring={hexA("#ffffff", 0.25)} ringW={1.2}>
                <text y={26} textAnchor="middle" fontSize="9" fill={hexA("#ffffff", 0.75)} stroke="#0c1016" strokeWidth={3} paintOrder="stroke"
                  style={{ pointerEvents: "none" }}>{c.length > 14 ? c.slice(0, 13) + "…" : c}</text>
              </SvgAvatar>
            ))}
            {mpos.map(({ n, x, y }) => (
              <SvgAvatar key={n.manager} x={x} y={y} r={sel === n.manager ? 20 : 16} photo={n.photo} fit="cover" name={`${n.manager} · ${n.team}`}
                ring={sel === n.manager ? "#f6c945" : hexA("#ffffff", 0.3)} ringW={sel === n.manager ? 3 : 1.5} onClick={() => setSel(n.manager)}>
                <text y={(sel === n.manager ? 20 : 16) + 11} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.82)} stroke="#0c1016"
                  strokeWidth={3} paintOrder="stroke" style={{ pointerEvents: "none" }}>{short(n.manager)}</text>
              </SvgAvatar>
            ))}
          </svg>
          <div className="net-legend" style={{ marginTop: 4 }}>
            <span><i style={{ background: "#f6c945" }} />그 클럽 감독 경력</span><span><i style={{ background: "#7f8a9c" }} />그 클럽 선수 경력(점선)</span>
          </div>
          {cur && (
            <div className="net-link-sel">
              <div className="net-nat-head">{cur.photo && <img src={cur.photo} alt="" />}<b>{cur.manager}</b>
                <em>{cur.team} · {cur.league}</em>{cur.logo && <img src={cur.logo} alt="" style={{ borderRadius: 0, objectFit: "contain" }} />}</div>
              <div className="net-chips">
                {cur.shared.map((s) => <i key={s.club}>{s.club} — {lastName(m.name || "")} {s.mine === "managed" ? "감독" : "선수"} · {lastName(cur.manager)} {s.theirs === "managed" ? "감독" : "선수"}</i>)}
              </div>
            </div>
          )}
        </>
      )}

      {(m.brought ?? []).length > 0 && (
        <div style={{ marginTop: 14 }}>
          <h4 className="net-h">BROUGHT IN <span>감독의 직전 팀에서 함께 온 선수</span></h4>
          <div className="net-arr">
            {(m.brought ?? []).map((n) => {
              const p = d.players.find((x) => x.name === n);
              return (
                <button key={n} className="net-arr-row hoverable" onClick={(e) => peek(e, { name: n, club: d.team, hint: { photo: p?.photo } })}>
                  {p?.photo ? <img src={p.photo} alt="" /> : <span className="net-cap-ph sm" />}
                  <span><b>{n}</b><em>← {p?.prev_squad}</em></span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
