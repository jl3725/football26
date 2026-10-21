"use client";
import { useEffect, useMemo, useState } from "react";
import { getRumorMap, type RumorIn, type RumorLink, type RumorMap, type RumorOut, type RumorStage } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SvgAvatar } from "./NetShared";
import { Skel } from "./Skeleton";

// RUMOURS — 이적설 지도. 경쟁 구단 → 표적 → 우리 클럽 ← 우리 선수 → 관심 구단 흐름으로, 선 굵기 = 열기(0~100), 색 = 단계.
// 원천: Transfermarkt 루머(8개 리그) + 열린 이적시장 뉴스 루머(매체 적중률 가중) — /api/rumor-map, src/rumor_map.py.
// 2026-10-21 사용자: "KG 에 뉴스·가십 루머를 넣어 관계도를 넓히자" → "이적설 지도 넣고".
const STAGE: Record<RumorStage, { en: string; ko: string; c: string; dash?: string }> = {
  rumour: { en: "RUMOUR", ko: "루머(TM)", c: "#8d9ab0", dash: "5 4" },
  interest: { en: "INTEREST", ko: "관심", c: "#f4cf5e" },
  talks: { en: "TALKS", ko: "협상", c: "#e8a25c" },
  agreed: { en: "AGREED", ko: "합의", c: "#ff8a5c" },
  done: { en: "DONE", ko: "확정", c: "#4fc27f" },
  denied: { en: "DENIED", ko: "부인", c: "#ff6b7d", dash: "2 4" },
};
const W = 760, ROW = 58, TOP = 44, XR = 40, XT = 236, XC = 380, XO = 524, XS = 640, MAX_ROWS = 8;
const HEAT_NOTE = "열기 = TM 루머(확률 반영) + 기사 단계(관심 1 · 협상 1.6 · 합의 2.4 · 확정 3 · 부인 −0.8) × 매체 적중률, 최근일수록 크게(반감기 뉴스 14일 · TM 21일)";
const short = (s: string, n = 15) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const eur = (v?: number) => (v && v > 0 ? (v >= 1e6 ? `€${Math.round(v / 1e6)}M` : `€${Math.round(v / 1e3)}K`) : "");
type Sel = { kind: "in"; x: RumorIn } | { kind: "out"; x: RumorOut } | null;

function Sources({ l, stages }: { l: RumorLink; stages: RumorMap["stages"] }) {
  const sr = stages[l.stage];
  return (
    <div className="rm-src">
      {sr && l.stage !== "rumour" && (
        <p className="rm-rate">지난 닫힌 이적시장에서 <b>{STAGE[l.stage].ko}</b> 단계 보도가 실제 이적으로 이어진 비율 <b>{Math.round(sr.rate * 100)}%</b> ({sr.hits}/{sr.n})</p>
      )}
      {l.tm && (
        <div className="rm-src-row"><span className="rm-chip" style={{ ["--c" as string]: STAGE.rumour.c }}>TM</span>
          <span>Transfermarkt 루머{l.tm.prob != null ? ` · 성사 확률 ${l.tm.prob}%` : ""}</span><em>{l.tm.date}</em></div>
      )}
      {l.news.map((n, i) => (
        <div key={i} className="rm-src-row">
          <span className="rm-chip" style={{ ["--c" as string]: STAGE[n.stage].c }}>{STAGE[n.stage].ko}</span>
          <span>
            <span className="rm-src-who"><b>{n.outlet}</b>{n.journalists ? ` · ${n.journalists}` : ""}
              <i title="지난 닫힌 이적시장 적중률 — 평균 매체 대비 배수">적중 ×{n.trust}</i></span>
            {n.headline && (n.link ? <a href={n.link} target="_blank" rel="noreferrer">{n.headline}</a> : <span>{n.headline}</span>)}
          </span>
          <em>{n.date}</em>
        </div>
      ))}
      {l.n_news > l.news.length && <p className="net-note">기사 {l.n_news - l.news.length}건 더</p>}
    </div>
  );
}

function Heat({ v, stage }: { v: number; stage: RumorStage }) {
  return (
    <span className="rm-heat" title={HEAT_NOTE}>
      <i style={{ width: Math.max(4, Math.round(v * 0.56)), background: STAGE[stage].c }} /><b>{v}</b>
    </span>
  );
}

export default function NetRumors({ team, accent, logo }: { team: string; accent: string; logo: string }) {
  const peek = usePeek();
  const [d, setD] = useState<RumorMap | null>(null);
  const [err, setErr] = useState(false);
  const [sel, setSel] = useState<Sel>(null);
  useEffect(() => {
    let a = true;
    setD(null); setErr(false); setSel(null);
    getRumorMap(team).then((x) => a && setD(x)).catch(() => a && setErr(true));
    return () => { a = false; };
  }, [team]);
  const ins = useMemo(() => (d?.in ?? []).slice(0, MAX_ROWS), [d]);
  const outs = useMemo(() => (d?.out ?? []).slice(0, MAX_ROWS), [d]);
  useEffect(() => {
    if (d && !sel) setSel(ins[0] ? { kind: "in", x: ins[0] } : outs[0] ? { kind: "out", x: outs[0] } : null);
  }, [d, ins, outs, sel]);

  if (err) return <p className="net-empty">이적설 지도를 불러오지 못했습니다</p>;
  if (!d) return <Skel h={420} r={14} />;
  if (!d.available) return <p className="net-empty">{d.reason || "이 클럽과 엮인 이적설이 없습니다"}</p>;

  const rows = Math.max(ins.length, outs.length, 1);
  const H = TOP + rows * ROW + 6, CY = TOP + (rows * ROW) / 2;
  const yIn = (i: number) => TOP + ROW / 2 + i * ROW + ((rows - ins.length) * ROW) / 2;
  const yOut = (i: number) => TOP + ROW / 2 + i * ROW + ((rows - outs.length) * ROW) / 2;
  const isSel = (k: "in" | "out", p: string) => sel?.kind === k && sel.x.player === p;
  const curve = (x1: number, y1: number, x2: number, y2: number) => `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
  const stroke = (l: { heat: number; stage: RumorStage }, on: boolean) => ({
    stroke: STAGE[l.stage].c, strokeWidth: 1 + l.heat / 16, strokeOpacity: on ? 0.95 : 0.3, strokeDasharray: STAGE[l.stage].dash, fill: "none",
  });

  return (
    <div className="net-rumors">
      <div className="net-toolbar">
        <h4 className="net-h">RUMOUR MAP <span>이적설 지도 — 표적 {d.n_in}명 · 우리 선수 {d.n_out}명 · 최근 120일 · 굵기 = 열기</span></h4>
        <span className="net-legend">{(Object.keys(STAGE) as RumorStage[]).map((k) => <span key={k}><i style={{ background: STAGE[k].c }} />{STAGE[k].ko}</span>)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="net-svg rm-svg" role="img"
        aria-label={`${team} 이적설 지도 — 왼쪽은 영입 표적과 경쟁 구단, 오른쪽은 우리 선수와 관심 구단, 선 굵기는 열기`}>
        {[[XR + 30, "RIVALS 경쟁 구단"], [XT, "TARGETS 표적"], [XC, team.toUpperCase()], [XO, "OUR PLAYERS 우리 선수"], [XS + 40, "SUITORS 관심 구단"]].map(([x, t]) => (
          <text key={String(t)} x={Number(x)} y={16} textAnchor="middle" fontSize="10" fontWeight={700} letterSpacing=".06em" fill={hexA("#ffffff", 0.55)}>{t}</text>
        ))}
        {ins.map((x, i) => {
          const y = yIn(i), on = !sel || isSel("in", x.player);
          return (
            <g key={"i" + x.player}>
              <path d={curve(XT + 19, y, XC - 34, CY)} {...stroke(x, on)} />
              {x.rivals.slice(0, 3).map((r, k) => (
                <path key={r.club} d={curve(XR + k * 30 + 11, y, XT - 19, y)} stroke={STAGE[r.stage].c} strokeOpacity={on ? 0.55 : 0.15}
                  strokeWidth={0.8 + r.heat / 30} strokeDasharray="3 3" fill="none" />
              ))}
            </g>
          );
        })}
        {outs.map((o, i) => {
          const y = yOut(i), on = !sel || isSel("out", o.player);
          return (
            <g key={"o" + o.player}>
              <path d={curve(XC + 34, CY, XO - 19, y)} stroke={hexA("#ffffff", on ? 0.35 : 0.12)} strokeWidth={1.2} fill="none" />
              {o.suitors.slice(0, 3).map((s, k) => <path key={s.to} d={curve(XO + 19, y, XS + k * 40 - 13, y)} {...stroke(s, on)} />)}
            </g>
          );
        })}
        <SvgAvatar x={XC} y={CY} r={34} photo={logo} fit="logo" name={team} ring={accent} ringW={3} />
        {ins.map((x, i) => {
          const y = yIn(i), on = isSel("in", x.player);
          return (
            <g key={"in" + x.player}>
              {x.rivals.slice(0, 3).map((r, k) => (
                <SvgAvatar key={r.club} x={XR + k * 30} y={y} r={11} photo={r.logo} fit="logo" name={`${r.club} · 열기 ${r.heat}`} ring={hexA("#ffffff", 0.2)} ringW={1} />
              ))}
              <SvgAvatar x={XT} y={y} r={on ? 20 : 18} photo={x.where?.photo} name={`${x.player} · ${x.from} · 열기 ${x.heat}`}
                ring={on ? accent : STAGE[x.stage].c} ringW={on ? 3 : 1.6} onClick={() => setSel({ kind: "in", x })}>
                {x.from_meta?.logo && <image href={x.from_meta.logo} x={9} y={7} width={14} height={14} />}
                <text y={31} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", on ? 0.95 : 0.72)} style={{ pointerEvents: "none" }}>{short(x.player)}</text>
              </SvgAvatar>
            </g>
          );
        })}
        {outs.map((o, i) => {
          const y = yOut(i), on = isSel("out", o.player);
          return (
            <g key={"out" + o.player}>
              <SvgAvatar x={XO} y={y} r={on ? 20 : 18} photo={o.where?.photo} name={`${o.player} · 열기 ${o.heat}`}
                ring={on ? accent : hexA("#ffffff", 0.3)} ringW={on ? 3 : 1.4} onClick={() => setSel({ kind: "out", x: o })}>
                <text y={31} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", on ? 0.95 : 0.72)} style={{ pointerEvents: "none" }}>{short(o.player)}</text>
              </SvgAvatar>
              {o.suitors.slice(0, 3).map((s, k) => (
                <SvgAvatar key={s.to} x={XS + k * 40} y={y} r={13} photo={s.to_meta.logo} fit="logo" name={`${s.to} · 열기 ${s.heat}`}
                  ring={STAGE[s.stage].c} ringW={1.4} onClick={() => setSel({ kind: "out", x: o })} />
              ))}
            </g>
          );
        })}
      </svg>

      {/* 좁은 화면 — 그림 대신 목록(누르면 아래 근거) */}
      <div className="rm-list">
        {ins.length > 0 && <h5>TARGETS <span>영입 표적</span></h5>}
        {ins.map((x) => (
          <button key={"li" + x.player} className={`rm-li${isSel("in", x.player) ? " on" : ""}`} onClick={() => setSel({ kind: "in", x })}>
            {x.where?.photo ? <img src={x.where.photo} alt="" /> : <span className="net-cap-ph sm" />}
            <span><b>{x.player}</b><em>{x.from}{x.rivals.length ? ` · 경쟁 ${x.rivals.length}` : ""}</em></span>
            <Heat v={x.heat} stage={x.stage} />
          </button>
        ))}
        {outs.length > 0 && <h5>OUR PLAYERS <span>우리 선수 이적설</span></h5>}
        {outs.map((o) => (
          <button key={"lo" + o.player} className={`rm-li${isSel("out", o.player) ? " on" : ""}`} onClick={() => setSel({ kind: "out", x: o })}>
            {o.where?.photo ? <img src={o.where.photo} alt="" /> : <span className="net-cap-ph sm" />}
            <span><b>{o.player}</b><em>{o.suitors.map((s) => s.to).slice(0, 3).join(" · ")}</em></span>
            <Heat v={o.heat} stage={o.suitors[0]?.stage ?? "rumour"} />
          </button>
        ))}
      </div>

      {sel?.kind === "in" && (
        <div className="net-link-sel rm-sel">
          <div className="rm-sel-head">
            <button className="rm-who hoverable" onClick={(e) => peek(e, { name: sel.x.where?.name ?? sel.x.player, club: sel.x.where?.club ?? sel.x.from, hint: { photo: sel.x.where?.photo || undefined } })}>
              {sel.x.where?.photo ? <img src={sel.x.where.photo} alt="" /> : <span className="net-cap-ph sm" />}
              <span><b>{sel.x.player}</b>
                <em>{sel.x.from}{sel.x.where ? ` · ${sel.x.where.league} · OVR ${sel.x.where.ovr}` : " · 8개 리그 밖"}
                  {sel.x.info.age ? ` · ${sel.x.info.age}세` : ""}{sel.x.info.pos ? ` · ${sel.x.info.pos}` : ""}{eur(sel.x.info.value) ? ` · ${eur(sel.x.info.value)}` : ""}</em></span>
            </button>
            <span className="rm-chip lg" style={{ ["--c" as string]: STAGE[sel.x.stage].c }}>{STAGE[sel.x.stage].en} <small>{STAGE[sel.x.stage].ko}</small></span>
            <Heat v={sel.x.heat} stage={sel.x.stage} />
          </div>
          <div className="rm-cols">
            <div>
              <h5>SOURCES <span>근거 · 최신순</span></h5>
              <Sources l={sel.x} stages={d.stages} />
            </div>
            <div>
              <h5>RIVALS <span>같은 선수를 쫓는 클럽</span></h5>
              {sel.x.rivals.length ? sel.x.rivals.map((r) => (
                <div key={r.club} className="rm-club">
                  {r.logo ? <img src={r.logo} alt="" /> : <span className="rm-dot" />}
                  <span><b>{r.club}</b><em>{r.league ?? "8개 리그 밖"} · {STAGE[r.stage].ko}</em></span>
                  <Heat v={r.heat} stage={r.stage} />
                </div>
              )) : <p className="net-note">다른 클럽과 엮인 기록 없음 — 단독 관심</p>}
            </div>
          </div>
        </div>
      )}
      {sel?.kind === "out" && (
        <div className="net-link-sel rm-sel">
          <div className="rm-sel-head">
            <button className="rm-who hoverable" onClick={(e) => peek(e, { name: sel.x.where?.name ?? sel.x.player, club: team, hint: { photo: sel.x.where?.photo || undefined } })}>
              {sel.x.where?.photo ? <img src={sel.x.where.photo} alt="" /> : <span className="net-cap-ph sm" />}
              <span><b>{sel.x.player}</b><em>{team}{sel.x.where ? ` · OVR ${sel.x.where.ovr}` : ""} · 관심 구단 {sel.x.suitors.length}</em></span>
            </button>
          </div>
          {sel.x.suitors.map((s) => (
            <div key={s.to} className="rm-suitor">
              <div className="rm-club">
                {s.to_meta.logo ? <img src={s.to_meta.logo} alt="" /> : <span className="rm-dot" />}
                <span><b>{s.to}</b><em>{s.to_meta.league ?? "8개 리그 밖"} · {STAGE[s.stage].ko}</em></span>
                <Heat v={s.heat} stage={s.stage} />
              </div>
              <Sources l={s} stages={d.stages} />
            </div>
          ))}
        </div>
      )}

      <div className="rm-foot">
        {d.competition.length > 0 && (
          <div>
            <h5>COMPETITION <span>같은 표적을 쫓는 클럽</span></h5>
            {d.competition.map((c) => (
              <div key={c.club} className="rm-club">
                {c.logo ? <img src={c.logo} alt="" /> : <span className="rm-dot" />}
                <span><b>{c.club}</b><em>{c.players.slice(0, 3).join(" · ")}{c.players.length > 3 ? ` 외 ${c.players.length - 3}` : ""}</em></span>
                <b className="rm-n">{c.players.length}</b>
              </div>
            ))}
          </div>
        )}
        {d.outlets.length > 0 && (
          <div>
            <h5>WHO REPORTS <span>보도 매체 · 적중률 배수</span></h5>
            {d.outlets.map((o) => (
              <div key={o.outlet} className="rm-club">
                <span className="rm-dot" />
                <span><b>{o.outlet}</b><em>기사 {o.n}건</em></span>
                <b className="rm-n" title="지난 닫힌 이적시장 적중률(평균 대비)">×{o.trust}</b>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="net-note" style={{ fontSize: 11, color: "var(--muted-2)" }}>{HEAT_NOTE}. 연결 {d.sources.links}건 중 기사 근거 {d.sources.with_news}건.</p>
    </div>
  );
}
