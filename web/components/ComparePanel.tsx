"use client";
import { useEffect, useState } from "react";
import { getPlayerDetail, fmtEur, type PlayerDetail } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";

const CB = "#e0a05e";   // B 선수 색(대비)

function CompareRadar({ a, b, ca }: { a: PlayerDetail["radar"]; b: PlayerDetail["radar"]; ca: string }) {
  const R = 62, cx = 95, cy = 92;
  const bmap: Record<string, number> = Object.fromEntries(b.map((x) => [x.axis, x.value]));
  const pt = (i: number, v: number, n: number): [number, number] => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const r = (v / 100) * R;
    return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
  };
  const n = a.length;
  const poly = (vals: number[]) => vals.map((v, i) => pt(i, v, n).join(",")).join(" ");
  return (
    <svg viewBox="0 0 190 184" style={{ width: "100%", maxWidth: 280 }}>
      {[0.34, 0.67, 1].map((f, k) => (
        <polygon key={k} points={poly(a.map(() => f * 100))} fill="none" stroke="rgba(255,255,255,0.08)" />
      ))}
      {a.map((x, i) => { const [px, py] = pt(i, 132, n); return <text key={i} x={px} y={py + 2} fontSize="7.5" fill="rgba(255,255,255,0.5)" textAnchor="middle">{x.axis}</text>; })}
      <polygon points={poly(a.map((x) => bmap[x.axis] ?? 0))} fill={hexA(CB, 0.16)} stroke={CB} strokeWidth="1.5" />
      <polygon points={poly(a.map((x) => x.value))} fill={hexA(ca, 0.22)} stroke={ca} strokeWidth="1.9" />
    </svg>
  );
}

function StatRow({ label, a, b, fmt, higher = "a-good" }: { label: string; a: number; b: number; fmt?: (v: number) => string; higher?: string }) {
  const f = fmt || ((v: number) => String(v));
  const aWin = a > b, bWin = b > a;
  const hl = (win: boolean) => (win ? { color: "#4fc27f", fontWeight: 700 } : {});
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 13 }}>
      <span style={{ textAlign: "right", ...hl(aWin) }}>{f(a)}</span>
      <span style={{ fontSize: 10.5, opacity: 0.5, padding: "0 12px", whiteSpace: "nowrap" }}>{label}</span>
      <span style={{ textAlign: "left", ...hl(bWin) }}>{f(b)}</span>
    </div>
  );
}

export default function ComparePanel({ team, a, b, accent, onClear }: {
  team: string; a: string; b: string; accent: string; onClear: () => void;
}) {
  const [da, setDa] = useState<PlayerDetail | null>(null);
  const [db, setDb] = useState<PlayerDetail | null>(null);
  useEffect(() => {
    let ok = true; setDa(null); setDb(null);
    getPlayerDetail(team, a).then((x) => ok && setDa(x)).catch(() => {});
    getPlayerDetail(team, b).then((x) => ok && setDb(x)).catch(() => {});
    return () => { ok = false; };
  }, [team, a, b]);
  if (!da || !db) return <div className="card"><div className="loading">불러오는 중…</div></div>;

  const head = (d: PlayerDetail, color: string, right = false) => {
    const t = tier(d.ovr);
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexDirection: right ? "row-reverse" : "row", textAlign: right ? "right" : "left" }}>
        {d.photo ? <img src={d.photo} alt="" style={{ width: 46, height: 46, borderRadius: "50%", objectFit: "cover", border: `2px solid ${hexA(color, 0.6)}` }} /> : <span style={{ width: 46 }} />}
        <div>
          <div style={{ fontSize: 14.5, fontWeight: 700 }}>{d.player}</div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>{d.pos} · {d.age}세</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: t.light }}>{d.ovr}</div>
        </div>
      </div>
    );
  };

  return (
    <div className="card pd-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        {head(da, accent)}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <span style={{ fontSize: 11, opacity: 0.5, fontWeight: 700 }}>VS</span>
          <button onClick={onClear} style={{ fontSize: 10.5, padding: "3px 9px", borderRadius: 6, border: "none", background: hexA("#fff", 0.08), color: "inherit", cursor: "pointer", opacity: 0.7 }}>닫기</button>
        </div>
        {head(db, CB, true)}
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 4, fontSize: 11 }}>
        <span style={{ color: accent }}>■ {da.player.split(" ").slice(-1)[0]}</span>
        <span style={{ color: CB }}>■ {db.player.split(" ").slice(-1)[0]}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "center" }}>
        <CompareRadar a={da.radar} b={db.radar} ca={accent} />
      </div>

      <div style={{ maxWidth: 420, margin: "10px auto 0" }}>
        <StatRow label="OVR" a={da.ovr} b={db.ovr} />
        <StatRow label="평점" a={da.ss_rating} b={db.ss_rating} fmt={(v) => v.toFixed(2)} />
        <StatRow label="나이" a={da.age} b={db.age} fmt={(v) => `${v}세`} />
        <StatRow label="시장가치" a={da.value_eur} b={db.value_eur} fmt={fmtEur} />
        <StatRow label="출전(분)" a={da.minutes} b={db.minutes} fmt={(v) => v.toLocaleString()} />
        <StatRow label="득점" a={da.goals} b={db.goals} />
        <StatRow label="도움" a={da.assists} b={db.assists} />
      </div>
    </div>
  );
}
