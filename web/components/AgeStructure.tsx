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

const A0 = 15, A1 = 38, W = 640, ROW = 60, PADL = 46, PADR = 14, PADT = 26, AXIS = 24;

type P = Overview["squad_ratings"][number];
type Dot = { p: P; cx: number; cy: number; rad: number; label?: { tx: number; anchor: "start" | "end"; name: string } };

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
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", margin: "2px 0 10px" }}>
        <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5 }}>{avg.toFixed(1)}<span style={{ fontSize: 11.5, opacity: 0.55, marginLeft: 3, fontWeight: 500 }}>세 평균</span></span>
        {totals.map((t) => (
          <span key={t.key} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, opacity: 0.85 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: t.color, display: "inline-block" }} />
            {t.label} <b style={{ fontWeight: 700 }}>{t.n}</b>
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {/* 라인 행 배경 (교차) */}
        {rows.map((r, ri) => (
          <rect key={"bg" + r.k} x={PADL - 4} y={PADT + ri * ROW + 3} width={W - PADR - PADL + 8} height={ROW - 6}
            rx={7} fill={ri % 2 === 1 ? hexA("#ffffff", 0.018) : "transparent"} />
        ))}
        {/* 전성기 구간(24-29) 음영 */}
        <rect x={x(24)} y={PADT} width={x(29) - x(24)} height={rows.length * ROW} fill={hexA("#6aa6e0", 0.06)} />
        {/* 팀 평균 나이선 */}
        <line x1={x(avg)} x2={x(avg)} y1={PADT - 2} y2={PADT + rows.length * ROW} stroke={accent} strokeWidth="1.5" strokeDasharray="3 3" opacity={0.8} />
        <text x={x(avg)} y={15} textAnchor="middle" fontSize="9" fontWeight={700} fill={accent} letterSpacing={0.2}>평균 {avg.toFixed(1)}</text>

        {rows.map((r, ri) => {
          const rowY = PADT + ri * ROW + ROW / 2;
          // 나이별 그룹 → 같은 나이는 세로로 스택
          const groups: Record<number, P[]> = {};
          r.players.forEach((p) => { (groups[p.age] ||= []).push(p); });
          const dots: Dot[] = [];
          for (const [age, ps] of Object.entries(groups)) {
            ps.sort((a, b) => b.minutes - a.minutes);
            ps.forEach((p, k) => dots.push({ p, cx: x(Number(age)), cy: rowY - (ps.length - 1) * 8 + k * 16, rad: rr(p.minutes) }));
          }
          // 라벨 충돌 회피 — 출전시간 많은 선수 우선, 겹치면 숨김(호버로 확인)
          const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
          [...dots].sort((a, b) => b.p.minutes - a.p.minutes).forEach((d) => {
            const name = d.p.player.split(" ").slice(-1)[0];
            const w = name.length * 4.5 + 2;
            for (const side of ["start", "end"] as const) {
              const x0 = side === "start" ? d.cx + d.rad + 3 : d.cx - d.rad - 3 - w;
              if (x0 < PADL || x0 + w > W - 2) continue;
              const rect = { x0, x1: x0 + w, y0: d.cy - 5, y1: d.cy + 5 };
              if (placed.some((q) => rect.x0 < q.x1 && rect.x1 > q.x0 && rect.y0 < q.y1 && rect.y1 > q.y0)) continue;
              placed.push(rect);
              d.label = { tx: side === "start" ? d.cx + d.rad + 3 : d.cx - d.rad - 3, anchor: side, name };
              break;
            }
          });
          return (
            <g key={r.k}>
              <line x1={PADL} x2={W - PADR} y1={rowY} y2={rowY} stroke={hexA("#ffffff", 0.06)} />
              <text x={PADL - 9} y={rowY + 4} textAnchor="end" fontSize="10.5" fontWeight={600} fill={hexA("#ffffff", 0.7)}>{r.ko}</text>
              {dots.map((d) => {
                const c = bucketColor(d.p.age);
                return (
                  <g key={d.p.player}>
                    <circle cx={d.cx} cy={d.cy} r={d.rad} fill={hexA(c, 0.92)} stroke={hexA("#0b0f17", 0.55)} strokeWidth="1.2">
                      <title>{`${d.p.player} · ${d.p.age}세 · ${d.p.minutes.toLocaleString()}′`}</title>
                    </circle>
                    {d.label && (
                      <text x={d.label.tx} y={d.cy + 3} textAnchor={d.label.anchor} fontSize="8.5"
                        fill={hexA("#ffffff", 0.68)} style={{ pointerEvents: "none" }}>{d.label.name}</text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}

        {[16, 20, 24, 28, 32, 36].map((a) => (
          <text key={a} x={x(a)} y={H - 6} textAnchor="middle" fontSize="9" fill={hexA("#ffffff", 0.38)}>{a}</text>
        ))}
      </svg>

      <div style={{ marginTop: 8, fontSize: 10.5, opacity: 0.5 }}>
        가로 = 나이 · 색 = 연령대 · 원 크기 = 출전시간 · 세로선 = 팀 평균 · 이름 겹치면 호버
      </div>
    </div>
  );
}
