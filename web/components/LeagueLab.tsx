"use client";
import { useState } from "react";
import type { LabFinish, LabCreate, LabPlaymaker, LabBallWinner, TeamStyle } from "@/lib/api";
import { usePeek } from "./PlayerPeek";

// 리그 분석 랩(홈 LEAGUE FOCUS) — /api/league-lab/{league}, Sofascore 시즌 기록.
// 분석가가 실제로 보는 형태로: 기대값 대비(골 vs xG·도움 vs xA), 팀 스타일 사분면, 90분당 수비 액션.
type Pick = (team: string, league?: string) => void;

const lastName = (n: string) => { const p = n.split(" "); return p.length > 1 ? p[p.length - 1] : n; };

// ── 골 vs xG / 도움 vs xA 산점도 ──
type Pt = { player: string; club: string; x: number; y: number; tip: string };
function Scatter({ pts, xLabel, yLabel, league }: { pts: Pt[]; xLabel: string; yLabel: string; league: string }) {
  const peek = usePeek();
  const W = 640, H = 300, L = 40, R = 14, T = 12, B = 36;
  const max = Math.max(2, Math.ceil(Math.max(...pts.map((p) => Math.max(p.x, p.y))) + 0.5));
  const step = max > 10 ? 2 : 1;
  const sx = (v: number) => L + (v / max) * (W - L - R);
  const sy = (v: number) => T + (1 - v / max) * (H - T - B);
  const diff = (p: Pt) => p.y - p.x;
  // 이름표: 기대 대비 차이가 큰 5명 + 실제 수치 상위 3명. 겹치면 위·아래로 비켜 보고 그래도 겹치면 생략.
  const cand = [...new Set([
    ...[...pts].sort((a, b) => Math.abs(diff(b)) - Math.abs(diff(a))).slice(0, 5).map((p) => p.player),
    ...[...pts].sort((a, b) => b.y - a.y).slice(0, 3).map((p) => p.player),
  ])];
  const boxes: { x: number; y: number; w: number; h: number }[] = pts.map((p) => ({ x: sx(p.x) - 5, y: sy(p.y) - 5, w: 10, h: 10 }));
  const hit = (b: { x: number; y: number; w: number; h: number }) => boxes.some((o) => b.x < o.x + o.w && o.x < b.x + b.w && b.y < o.y + o.h && o.y < b.y + b.h);
  const lab: Record<string, { x: number; y: number }> = {};
  for (const name of cand) {
    const p = pts.find((q) => q.player === name)!;
    const w = lastName(name).length * 6.6 + 4, cx = sx(p.x), cy = sy(p.y);
    for (const [dx, dy] of [[9, 4], [9, -9], [9, 16], [-w - 9, 4]]) {
      const b = { x: cx + dx, y: cy + dy - 10, w, h: 12 };
      if (!hit(b) && b.x + w < W - R + 30) { boxes.push(b); lab[name] = { x: cx + dx, y: cy + dy }; break; }
    }
  }
  const labeled = new Set(Object.keys(lab));
  return (
    <svg className="sc5" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${yLabel} 대 ${xLabel}`}>
      <polygon points={`${sx(0)},${sy(0)} ${sx(0)},${sy(max)} ${sx(max)},${sy(max)}`} className="sc5-over" />
      <polygon points={`${sx(0)},${sy(0)} ${sx(max)},${sy(0)} ${sx(max)},${sy(max)}`} className="sc5-under" />
      {Array.from({ length: Math.floor(max / step) + 1 }, (_, k) => k * step).map((v) => (
        <g key={v}>
          <line x1={sx(v)} x2={sx(v)} y1={T} y2={H - B} className="sc5-grid" />
          <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="sc5-grid" />
          <text x={sx(v)} y={H - B + 15} className="sc5-tx">{v}</text>
          <text x={L - 8} y={sy(v) + 4} className="sc5-ty">{v}</text>
        </g>
      ))}
      <line x1={sx(0)} y1={sy(0)} x2={sx(max)} y2={sy(max)} className="sc5-diag" />
      <text x={sx(max) - 6} y={sy(max) + 16} className="sc5-q over">기대 이상 ↑</text>
      <text x={sx(max) - 6} y={sy(0) - 8} className="sc5-q under">기대 이하 ↓</text>
      <text x={(L + W - R) / 2} y={H - 4} className="sc5-axis">{xLabel}</text>
      <text x={12} y={(T + H - B) / 2} className="sc5-axis" transform={`rotate(-90 12 ${(T + H - B) / 2})`}>{yLabel}</text>
      {pts.map((p) => {
        const d = diff(p);
        const cls = d >= 1 ? "pos" : d <= -1 ? "neg" : "mid";
        return (
          <g key={p.player + p.club} className={`sc5-pt ${cls}`} onClick={(e) => peek(e, { name: p.player, club: p.club, league })}>
            <circle cx={sx(p.x)} cy={sy(p.y)} r={labeled.has(p.player) ? 6 : 4.5}><title>{p.tip}</title></circle>
            {lab[p.player] && <text x={lab[p.player].x} y={lab[p.player].y}>{lastName(p.player)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

export function ExpectedBoard({ finishing, creating, league }: { finishing: LabFinish[]; creating: LabCreate[]; league: string }) {
  const [tab, setTab] = useState<"fin" | "cre">("fin");
  const pts: Pt[] = tab === "fin"
    ? finishing.map((p) => ({ player: p.player, club: p.club, x: p.xg, y: p.goals, tip: `${p.player} · ${p.club} — ${p.goals}골 / xG ${p.xg} (${p.goals - p.xg >= 0 ? "+" : ""}${(p.goals - p.xg).toFixed(1)}) · 슈팅 ${p.shots}` }))
    : creating.map((p) => ({ player: p.player, club: p.club, x: p.xa, y: p.assists, tip: `${p.player} · ${p.club} — ${p.assists}도움 / xA ${p.xa} · 키패스 ${p.kp}` }));
  const top = [...pts].sort((a, b) => (b.y - b.x) - (a.y - a.x));
  return (
    <>
      <div className="tabs5" role="tablist">
        <button role="tab" aria-selected={tab === "fin"} className={tab === "fin" ? "on" : ""} onClick={() => setTab("fin")}>FINISHING</button>
        <button role="tab" aria-selected={tab === "cre"} className={tab === "cre" ? "on" : ""} onClick={() => setTab("cre")}>CREATING</button>
      </div>
      {pts.length >= 3 ? <Scatter pts={pts} league={league} xLabel={tab === "fin" ? "기대 득점 xG" : "기대 도움 xA"} yLabel={tab === "fin" ? "실제 득점" : "실제 도움"} /> : <p className="empty5">표본 부족</p>}
      {pts.length >= 3 && (
        <div className="sc5-notes">
          <span><i className="pos" />가장 효율적 <b>{top[0].player}</b> +{(top[0].y - top[0].x).toFixed(1)}</span>
          <span><i className="neg" />가장 아쉬움 <b>{top[top.length - 1].player}</b> {(top[top.length - 1].y - top[top.length - 1].x).toFixed(1)}</span>
        </div>
      )}
    </>
  );
}

// ── 도움왕(찬스 메이커) ──
export function Playmakers({ rows, onPick, league }: { rows: LabPlaymaker[]; onPick: Pick; league: string }) {
  const peek = usePeek();
  if (!rows.length) return <p className="empty5">도움 기록 없음</p>;
  const lead = Math.max(rows[0].assists, 1);
  return (
    <div className="gb5">
      {rows.map((r, i) => (
        <div className="gb5-row" key={r.player + r.club}>
          <span className="pr5-rk">{i + 1}</span>
          <button className="pr5-ph peekable" onClick={(e) => peek(e, { name: r.player, club: r.club, league })} aria-label={`${r.player} 미리보기`}>
            {r.photo ? <img src={r.photo} alt="" /> : r.club_logo ? <img className="logo" src={r.club_logo} alt="" /> : <span />}
          </button>
          <button className="gb5-who" onClick={() => onPick(r.club, league)}>
            <b>{r.player}</b>
            <span className="gb5-bar pm"><i style={{ width: `${(r.assists / lead) * 100}%` }} /></span>
            <em>{r.club_logo && <img src={r.club_logo} alt="" />}xA {r.xa.toFixed(2)} · 빅찬스 {r.bcc} · 키패스 {r.kp}</em>
          </button>
          <span className="gb5-n pm"><b>{r.assists}</b><small>AST</small></span>
        </div>
      ))}
    </div>
  );
}

// ── 볼 위닝(90분당 태클 성공·인터셉트·볼 회수) ──
export function BallWinners({ rows, league }: { rows: LabBallWinner[]; league: string }) {
  const peek = usePeek();
  if (!rows.length) return <p className="empty5">표본 부족</p>;
  const mx = { t: Math.max(...rows.map((r) => r.tackles), 0.1), i: Math.max(...rows.map((r) => r.inter), 0.1), r: Math.max(...rows.map((r) => r.recov), 0.1) };
  return (
    <div className="bw5">
      {rows.map((r) => (
        <button className="bw5-row" key={r.player + r.club} onClick={(e) => peek(e, { name: r.player, club: r.club, league })}>
          <span className="pr5-ph">{r.photo ? <img src={r.photo} alt="" /> : r.club_logo ? <img className="logo" src={r.club_logo} alt="" /> : <span />}</span>
          <span className="bw5-who"><b>{r.player}</b><em>{r.club_logo && <img src={r.club_logo} alt="" />}{r.club}</em></span>
          <span className="bw5-m">
            {([["TKL", r.tackles, mx.t], ["INT", r.inter, mx.i], ["REC", r.recov, mx.r]] as const).map(([k, v, m]) => (
              <span key={k} title={`${k === "TKL" ? "태클 성공" : k === "INT" ? "인터셉트" : "볼 회수"} ${v}/90분`}>
                <i style={{ height: `${Math.max(8, (v / m) * 100)}%` }} /><small>{k}</small><b>{v.toFixed(1)}</b>
              </span>
            ))}
          </span>
        </button>
      ))}
      <p className="bw5-note">90분당 · 태클 성공 + 인터셉트 + 볼 회수(절반 가중) 순</p>
    </div>
  );
}

// ── 팀 스타일 지도: 경기당 xG(공격 기회의 질) vs 경기당 실점 ──
export function TeamStyleMap({ teams, onPick, league }: { teams: TeamStyle[]; onPick: Pick; league: string }) {
  if (teams.length < 3) return <p className="empty5">표본 부족</p>;
  const W = 640, H = 330, L = 40, R = 16, T = 14, B = 36;
  const xs = teams.map((t) => t.xg_pg), ys = teams.map((t) => t.ga_pg);
  const x0 = Math.max(0, Math.min(...xs) - 0.2), x1 = Math.max(...xs) + 0.2;
  const y0 = Math.max(0, Math.min(...ys) - 0.2), y1 = Math.max(...ys) + 0.2;
  const sx = (v: number) => L + ((v - x0) / (x1 - x0)) * (W - L - R);
  const sy = (v: number) => T + ((v - y0) / (y1 - y0)) * (H - T - B);   // 실점 적을수록 위
  const ax = xs.reduce((a, b) => a + b, 0) / xs.length, ay = ys.reduce((a, b) => a + b, 0) / ys.length;
  const ticks = (a: number, b: number) => { const out: number[] = []; for (let v = Math.ceil(a * 2) / 2; v <= b; v += 0.5) out.push(+v.toFixed(1)); return out; };
  return (
    <svg className="sc5 tm5" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="팀 스타일 지도">
      {ticks(x0, x1).map((v) => <g key={"x" + v}><line x1={sx(v)} x2={sx(v)} y1={T} y2={H - B} className="sc5-grid" /><text x={sx(v)} y={H - B + 15} className="sc5-tx">{v}</text></g>)}
      {ticks(y0, y1).map((v) => <g key={"y" + v}><line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="sc5-grid" /><text x={L - 8} y={sy(v) + 4} className="sc5-ty">{v}</text></g>)}
      <line x1={sx(ax)} x2={sx(ax)} y1={T} y2={H - B} className="tm5-avg" />
      <line x1={L} x2={W - R} y1={sy(ay)} y2={sy(ay)} className="tm5-avg" />
      <text x={W - R - 6} y={T + 14} className="tm5-q good">기회 多 · 실점 少</text>
      <text x={L + 6} y={T + 14} className="tm5-q l">수비 단단 · 기회 적음</text>
      <text x={W - R - 6} y={H - B - 8} className="tm5-q">화끈 · 수비 불안</text>
      <text x={L + 6} y={H - B - 8} className="tm5-q l bad">고전</text>
      <text x={(L + W - R) / 2} y={H - 4} className="sc5-axis">경기당 xG (만든 기회의 질) →</text>
      <text x={12} y={(T + H - B) / 2} className="sc5-axis" transform={`rotate(-90 12 ${(T + H - B) / 2})`}>← 경기당 실점 (위가 적음)</text>
      {teams.map((t) => (
        <g key={t.team} className="tm5-team" onClick={() => onPick(t.team, league)}>
          <title>{`${t.team} · ${t.rank}위 — 경기당 xG ${t.xg_pg} · 득점 ${t.gf_pg} · 실점 ${t.ga_pg}`}</title>
          <circle cx={sx(t.xg_pg)} cy={sy(t.ga_pg)} r={13} />
          {t.logo && <image href={t.logo} x={sx(t.xg_pg) - 10} y={sy(t.ga_pg) - 10} width={20} height={20} />}
        </g>
      ))}
    </svg>
  );
}
