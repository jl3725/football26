"use client";
import type { Overview } from "@/lib/api";
import { hexA } from "@/lib/ui";

const LINES = [["ATT", "공격"], ["MID", "미드"], ["DEF", "수비"], ["GK", "GK"]] as const;
const BUCKETS = [
  { key: "u23", label: "U23", color: "#4fc27f", test: (a: number) => a <= 23 },
  { key: "prime", label: "전성기", color: "#6aa6e0", test: (a: number) => a >= 24 && a <= 29 },
  { key: "vet", label: "30+", color: "#e0a05e", test: (a: number) => a >= 30 },
] as const;
const bucketColor = (a: number) => (BUCKETS.find((b) => b.test(a)) || BUCKETS[1]).color;

const A0 = 15, A1 = 38, W = 620, ROW = 56, PADL = 44, PADR = 16, PADT = 22, AXIS = 26;

export default function AgeStructure({ ov, accent }: { ov: Overview; accent: string }) {
  const sr = ov.squad_ratings || [];
  if (!sr.length) return <div className="mgr-meta">데이터 부족</div>;

  const avg = sr.reduce((s, p) => s + p.age, 0) / sr.length;
  const totals = BUCKETS.map((b) => ({ ...b, n: sr.filter((p) => b.test(p.age)).length }));
  const rows = LINES.map(([k, ko]) => ({ k, ko, players: sr.filter((p) => p.line === k) })).filter((r) => r.players.length);
  const H = PADT + rows.length * ROW + AXIS;
  const x = (a: number) => PADL + (Math.max(A0, Math.min(A1, a)) - A0) / (A1 - A0) * (W - PADL - PADR);
  const rr = (m: number) => 4.5 + Math.min(1, m / 1800) * 3.5;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", margin: "2px 0 8px" }}>
        <span style={{ fontSize: 22, fontWeight: 700 }}>{avg.toFixed(1)}<span style={{ fontSize: 12, opacity: 0.6, marginLeft: 2 }}>세 평균</span></span>
        {totals.map((t) => (
          <span key={t.key} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12.5, opacity: 0.85 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: t.color, display: "inline-block" }} />
            {t.label} <b>{t.n}</b>
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {/* 전성기 구간(24-29) 음영 */}
        <rect x={x(24)} y={PADT} width={x(29) - x(24)} height={rows.length * ROW} fill={hexA("#ffffff", 0.045)} />
        {/* 팀 평균 나이선 */}
        <line x1={x(avg)} x2={x(avg)} y1={PADT} y2={PADT + rows.length * ROW} stroke={accent} strokeWidth="1.5" strokeDasharray="4 3" />
        <text x={x(avg)} y={13} textAnchor="middle" fontSize="9.5" fontWeight={700} fill={accent}>평균 {avg.toFixed(1)}</text>

        {rows.map((r, ri) => {
          const rowY = PADT + ri * ROW + ROW / 2;
          const groups: Record<number, typeof r.players> = {};
          r.players.forEach((p) => { (groups[p.age] ||= []).push(p); });
          return (
            <g key={r.k}>
              <line x1={PADL} x2={W - PADR} y1={rowY} y2={rowY} stroke={hexA("#ffffff", 0.07)} />
              <text x={PADL - 8} y={rowY + 4} textAnchor="end" fontSize="11.5" fontWeight={600} fill={hexA("#ffffff", 0.75)}>{r.ko}</text>
              {Object.entries(groups).flatMap(([age, ps]) =>
                ps.map((p, k) => {
                  const cx = x(Number(age));
                  const cy = rowY - (ps.length - 1) * 7 + k * 14;
                  const c = bucketColor(p.age);
                  const right = cx > W * 0.82;
                  const rad = rr(p.minutes);
                  return (
                    <g key={p.player}>
                      <circle cx={cx} cy={cy} r={rad} fill={hexA(c, 0.9)} stroke={hexA("#000", 0.35)} strokeWidth="1">
                        <title>{`${p.player} · ${p.age}세 · ${p.minutes.toLocaleString()}′`}</title>
                      </circle>
                      <text x={right ? cx - rad - 3 : cx + rad + 3} y={cy + 3} textAnchor={right ? "end" : "start"}
                        fontSize="8.5" fill={hexA("#ffffff", 0.72)} style={{ pointerEvents: "none" }}>
                        {p.player.split(" ").slice(-1)[0]}
                      </text>
                    </g>
                  );
                })
              )}
            </g>
          );
        })}

        {[16, 20, 24, 28, 32, 36].map((a) => (
          <text key={a} x={x(a)} y={H - 7} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.4)}>{a}세</text>
        ))}
      </svg>

      <div style={{ marginTop: 8, fontSize: 10.5, opacity: 0.5 }}>
        가로 = 나이 · 색 = 연령대 · 원 크기 = 출전시간 · 세로선 = 팀 평균
      </div>
    </div>
  );
}
