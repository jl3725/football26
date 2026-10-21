"use client";
import { useMemo } from "react";
import type { Overview } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import Info from "./Info";
import { SvgAvatar, lastName } from "./NetShared";
import { useNarrow } from "./TeamSeason";

// AGE PROFILE — 라인별 선수 사진 비스웜(가로 = 나이, 원 크기 = 출전시간, 테두리 색 = 연령대) + 출전 가중 평균 나이·리그 순위 +
// 연령대별 출전 비중. 예전엔 같은 색 점과 작은 이름만이라 누가 어디 있는지 안 보였다(2026-10-15 사용자 지적).
const LINES = [["ATT", "공격"], ["MID", "미드"], ["DEF", "수비"], ["GK", "GK"]] as const;
const BUCKETS = [
  { key: "u23", label: "U23", color: "#4fc27f", test: (a: number) => a <= 23 },
  { key: "prime", label: "전성기 24–29", color: "#6aa6e0", test: (a: number) => a >= 24 && a <= 29 },
  { key: "vet", label: "30+", color: "#e0a05e", test: (a: number) => a >= 30 },
] as const;
const bucketColor = (a: number) => (BUCKETS.find((b) => b.test(a)) || BUCKETS[1]).color;

const A0 = 16, A1 = 38, PADL = 46, PADR = 16, PADT = 22, AXIS = 22;
type P = Overview["squad_ratings"][number];
type Dot = { p: P; cx: number; dy: number; r: number };

// 비스웜 — 출전 많은 선수부터 가운데, 겹치면 위·아래로 번갈아 민다
function swarm(ps: P[], x: (a: number) => number, rad: (m: number) => number): Dot[] {
  const out: Dot[] = [];
  for (const p of [...ps].sort((a, b) => b.minutes - a.minutes)) {
    const cx = x(p.age), r = rad(p.minutes);
    for (let k = 0; k < 60; k++) {
      const dy = k === 0 ? 0 : (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 3;
      if (!out.some((q) => Math.hypot(q.cx - cx, q.dy - dy) < q.r + r + 1.5)) { out.push({ p, cx, dy, r }); break; }
    }
  }
  return out;
}

// 이름 — 출전 많은 선수부터 사진 아래에, 다른 사진·이름과 겹치면 생략(호버로 확인)
function labels(dots: Dot[], mid: number) {
  const boxes = dots.map((d) => ({ x0: d.cx - d.r, x1: d.cx + d.r, y0: mid + d.dy - d.r, y1: mid + d.dy + d.r }));
  const out: { name: string; short: string; x: number; y: number }[] = [];
  for (const d of [...dots].sort((a, b) => b.p.minutes - a.p.minutes)) {
    const short = lastName(d.p.player), w = short.length * 4.6 + 4;
    const y = mid + d.dy + d.r + 9;
    const box = { x0: d.cx - w / 2, x1: d.cx + w / 2, y0: y - 8, y1: y + 2 };
    if (boxes.some((q) => box.x0 < q.x1 && box.x1 > q.x0 && box.y0 < q.y1 && box.y1 > q.y0)) continue;
    boxes.push(box);
    out.push({ name: d.p.player, short, x: d.cx, y });
  }
  return out;
}

export default function AgeStructure({ ov, accent }: { ov: Overview; accent: string }) {
  const peek = usePeek();
  const sr = useMemo(() => ov.squad_ratings || [], [ov]);
  // 폰에선 좁은 viewBox(가로 스크롤 없이 화면 폭에 맞춤) — 예전엔 520px 최소폭이라 30대 선수가 잘렸다
  const narrow = useNarrow("(max-width: 560px)");
  const W = narrow ? 400 : 680;
  const x = (a: number) => PADL + (Math.max(A0, Math.min(A1, a)) - A0) / (A1 - A0) * (W - PADL - PADR);
  const rad = (m: number) => (narrow ? 7.5 : 9) + Math.min(1, m / 1500) * (narrow ? 4.5 : 6);
  const rows = useMemo(() => LINES.map(([k, ko]) => {
    const dots = swarm(sr.filter((p) => p.line === k), x, rad);
    const half = Math.max(24, ...dots.map((d) => Math.abs(d.dy) + d.r + 12));   // 아래 이름 자리
    return { k, ko, dots, h: half * 2 };
  }).filter((r) => r.dots.length), [sr, narrow]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!sr.length) return <div className="mgr-meta">데이터 부족</div>;

  const s = ov.age_summary;
  const totMin = sr.reduce((t, p) => t + p.minutes, 0) || 1;
  const wavg = s?.wavg ?? sr.reduce((t, p) => t + p.age * p.minutes, 0) / totMin;
  const shares = BUCKETS.map((b) => ({ ...b, pct: s ? s[b.key] : Math.round(100 * sr.filter((p) => b.test(p.age)).reduce((t, p) => t + p.minutes, 0) / totMin) }));
  const H = PADT + rows.reduce((t, r) => t + r.h, 0) + AXIS;
  let yAcc = PADT;
  const young = s && s.rank_young <= Math.ceil(s.n / 3), old = s && s.rank_young > s.n - Math.ceil(s.n / 3);

  return (
    <div className="agep">
      <div className="agep-kpi">
        <div className="agep-big">
          <strong>{wavg.toFixed(1)}</strong><span>세 · 출전 가중 평균</span>
          {s && (
            <em className={young ? "y" : old ? "o" : ""} title={`리그 ${s.n}팀 중 출전 가중 평균 나이 순위(1 = 가장 젊다) · 리그 평균 ${s.league_wavg}세`}>
              리그 {s.rank_young}번째로 젊음 · 리그 평균 {s.league_wavg}
            </em>
          )}
        </div>
        <div className="agep-share" title="출전시간 비중(연령대별)">
          <div className="bar">{shares.map((b) => b.pct > 0 && <i key={b.key} style={{ width: `${b.pct}%`, background: b.color }}>{b.pct >= 12 ? `${b.pct}%` : ""}</i>)}</div>
          <div className="leg">{shares.map((b) => <span key={b.key}><i style={{ background: b.color }} />{b.label} {b.pct}%</span>)}</div>
        </div>
      </div>

      <div className="net-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} className="agep-svg" role="img"
          aria-label={`라인별 나이 분포 — 출전 가중 평균 ${wavg.toFixed(1)}세`}>
          <rect x={x(24)} y={PADT - 6} width={x(29.5) - x(24)} height={H - PADT - AXIS + 6} rx={6} fill={hexA("#6aa6e0", 0.07)} />
          <text x={(x(24) + x(29.5)) / 2} y={PADT - 9} textAnchor="middle" fontSize="9" fontWeight={700} letterSpacing="0.12em" fill={hexA("#6aa6e0", 0.8)}>PEAK</text>
          <line x1={x(wavg)} x2={x(wavg)} y1={PADT - 4} y2={H - AXIS} stroke={accent} strokeWidth="1.5" strokeDasharray="3 3" opacity={0.85} />
          <text x={x(wavg) + 4} y={H - AXIS - 4} fontSize="9" fontWeight={700} fill={accent}>{wavg.toFixed(1)}</text>
          {rows.map((r, ri) => {
            const top = yAcc; yAcc += r.h;
            const mid = top + r.h / 2;
            return (
              <g key={r.k}>
                {ri > 0 && <line x1={PADL - 4} x2={W - PADR} y1={top} y2={top} stroke={hexA("#ffffff", 0.06)} />}
                <text x={PADL - 10} y={mid + 4} textAnchor="end" fontSize="10.5" fontWeight={700} fill={hexA("#ffffff", 0.7)}>{r.ko}</text>
                {r.dots.map((d) => (
                  <SvgAvatar key={d.p.player} x={d.cx} y={mid + d.dy} r={d.r} photo={d.p.photo} ring={bucketColor(d.p.age)} ringW={2}
                    name={`${d.p.player} · ${d.p.age}세 · ${d.p.minutes.toLocaleString()}′ · OVR ${d.p.ovr}`}
                    onClick={(e) => peek(e, { name: d.p.player, club: ov.team, hint: { photo: d.p.photo, ovr: d.p.ovr, age: d.p.age } })} />
                ))}
                {labels(r.dots, mid).map((l) => (
                  <text key={"l" + l.name} x={l.x} y={l.y} textAnchor="middle" fontSize="8.5" fill={hexA("#ffffff", 0.7)}
                    style={{ pointerEvents: "none" }}>{l.short}</text>
                ))}
              </g>
            );
          })}
          {[16, 20, 24, 28, 32, 36].map((a) => (
            <text key={a} x={x(a)} y={H - 6} textAnchor="middle" fontSize="9" fill={hexA("#ffffff", 0.4)}>{a}</text>
          ))}
        </svg>
      </div>
      <p className="sp5-note">45분+ 출전 선수 <Info label="나이 분포 읽는 법"><p>가로 = 나이 · 원 크기 = 이번 시즌 출전시간 · 테두리 = 연령대 · 점선 = 출전 가중 평균.</p><p className="muted">이름이 겹치면 생략(점에 마우스를 올리면 보임).</p></Info></p>
    </div>
  );
}
