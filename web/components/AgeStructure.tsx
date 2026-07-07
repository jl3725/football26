"use client";
import type { Overview } from "@/lib/api";
import { hexA } from "@/lib/ui";

const LINES = [["ATT", "공격"], ["MID", "미드"], ["DEF", "수비"], ["GK", "GK"]] as const;
const BUCKETS = [
  { key: "u23", label: "U23", color: "#4fc27f", test: (a: number) => a <= 23 },
  { key: "prime", label: "전성기", color: "#6aa6e0", test: (a: number) => a >= 24 && a <= 29 },
  { key: "vet", label: "30+", color: "#e0a05e", test: (a: number) => a >= 30 },
] as const;

export default function AgeStructure({ ov, accent }: { ov: Overview; accent: string }) {
  const sr = ov.squad_ratings || [];
  if (!sr.length) return <div className="mgr-meta">데이터 부족</div>;

  const avg = sr.reduce((s, p) => s + p.age, 0) / sr.length;
  const totals = BUCKETS.map((b) => ({ ...b, n: sr.filter((p) => b.test(p.age)).length }));
  const rows = LINES.map(([k, ko]) => {
    const players = sr.filter((p) => p.line === k);
    const cells = BUCKETS.map((b) => players.filter((p) => b.test(p.age)));
    const lineAvg = players.length ? players.reduce((s, p) => s + p.age, 0) / players.length : 0;
    return { k, ko, n: players.length, cells, lineAvg };
  }).filter((r) => r.n > 0);
  const maxN = Math.max(1, ...rows.map((r) => r.n));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", margin: "2px 0 12px" }}>
        <span style={{ fontSize: 22, fontWeight: 700 }}>{avg.toFixed(1)}<span style={{ fontSize: 12, opacity: 0.6, marginLeft: 2 }}>세 평균</span></span>
        {totals.map((t) => (
          <span key={t.key} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12.5, opacity: 0.85 }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: t.color, display: "inline-block" }} />
            {t.label} <b>{t.n}</b>
          </span>
        ))}
      </div>

      {rows.map((r) => (
        <div key={r.k} style={{ display: "flex", alignItems: "center", gap: 10, margin: "7px 0" }}>
          <span style={{ width: 34, fontSize: 12, opacity: 0.75, textAlign: "right" }}>{r.ko}</span>
          <div style={{ flex: 1, height: 24, borderRadius: 6, background: hexA("#ffffff", 0.04) }}>
            <div style={{ display: "flex", height: "100%", width: `${(r.n / maxN) * 100}%`, borderRadius: 6, overflow: "hidden" }}>
              {r.cells.map((cell, bi) => cell.length > 0 && (
                <div key={bi}
                  title={`${BUCKETS[bi].label} · ${cell.map((p) => `${p.player}(${p.age})`).join(", ")}`}
                  style={{
                    width: `${(cell.length / r.n) * 100}%`, background: hexA(BUCKETS[bi].color, 0.85),
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 11, fontWeight: 700, color: "#0a0a0a",
                  }}>{cell.length}</div>
              ))}
            </div>
          </div>
          <span style={{ width: 44, fontSize: 11, opacity: 0.6, textAlign: "left" }}>Ø{r.lineAvg.toFixed(1)}</span>
        </div>
      ))}

      <div style={{ marginTop: 10, fontSize: 10.5, opacity: 0.5 }}>
        막대 길이 = 라인 선수 수 · 색 = 연령대 · Ø = 라인 평균 나이
      </div>
    </div>
  );
}
