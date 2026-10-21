"use client";
import { useEffect, useState, type ReactNode } from "react";
import { activeLeague, getPlayerDetail, fmtEur, type PlayerDetail } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";
import { ssMeaning, TONE, SS_NOTE } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Info from "./Info";

const CB = "#e0a05e";   // B 선수 색(대비)

// 레이더 값 = 카테고리별 백분위 평균(같은 포지션 대비) — 점선 링 = 50(포지션 중간).
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
      {[0.25, 0.5, 0.75, 1].map((f, k) => (
        <polygon key={k} points={poly(a.map(() => f * 100))} fill="none"
          stroke={f === 0.5 ? "rgba(255,255,255,0.28)" : "rgba(255,255,255,0.08)"} strokeDasharray={f === 0.5 ? "3 3" : undefined} />
      ))}
      <text x={cx + 2} y={cy - R * 0.5 - 2} fontSize="6.5" fill="rgba(255,255,255,0.5)">50 = 중간</text>
      {a.map((x, i) => { const [px, py] = pt(i, 132, n); return <text key={i} x={px} y={py + 2} fontSize="7.5" fill="rgba(255,255,255,0.5)" textAnchor="middle">{x.axis}</text>; })}
      <polygon points={poly(a.map((x) => bmap[x.axis] ?? 0))} fill={hexA(CB, 0.16)} stroke={CB} strokeWidth="1.5" />
      <polygon points={poly(a.map((x) => x.value))} fill={hexA(ca, 0.22)} stroke={ca} strokeWidth="1.9" />
    </svg>
  );
}

// better: high = 클수록 좋음(초록 강조) · low = 작을수록 좋음 · none = 좋고 나쁨 없음(나이 등, 강조 안 함)
function StatRow({ label, a, b, fmt, better = "high", tag, note }: {
  label: string; a: number; b: number; fmt?: (v: number) => string;
  better?: "high" | "low" | "none"; tag?: (v: number) => ReactNode; note?: string;
}) {
  const f = fmt || ((v: number) => String(v));
  const aWin = better === "none" ? false : better === "low" ? a < b : a > b;
  const bWin = better === "none" ? false : better === "low" ? b < a : b > a;
  const hl = (win: boolean) => (win ? { color: TONE.best.c, fontWeight: 700 } : {});
  return (
    <div title={note} style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 13 }}>
      <span style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 5, ...hl(aWin) }}>{tag?.(a)}{f(a)}</span>
      <span style={{ fontSize: 10.5, opacity: 0.5, padding: "0 12px", whiteSpace: "nowrap" }}>{label}</span>
      <span style={{ display: "flex", justifyContent: "flex-start", alignItems: "center", gap: 5, ...hl(bWin) }}>{f(b)}{tag?.(b)}</span>
    </div>
  );
}

// B 는 같은 스쿼드(bTeam·bLeague 없음) 또는 8개 리그 누구든(P2 ⑥). 리그가 다르면 두 선수 모두 8개 리그 같은 템플릿
// 기준 백분위(peers=all)로 받아 같은 잣대로 놓고, 평점은 EPL 척도로 환산, 서로의 리그로 옮겼을 때 예상 OVR 을 보탠다.
export default function ComparePanel({ team, a, b, bTeam, bLeague, accent, onClear }: {
  team: string; a: string; b: string; bTeam?: string; bLeague?: string; accent: string; onClear: () => void;
}) {
  const [da, setDa] = useState<PlayerDetail | null>(null);
  const [db, setDb] = useState<PlayerDetail | null>(null);
  const aLeague = activeLeague();
  const cross = !!bLeague && bLeague !== aLeague;
  useEffect(() => {
    let ok = true; setDa(null); setDb(null);
    const peers = cross ? "all" : "auto";
    getPlayerDetail(team, a, aLeague, "blend", "all", peers).then((x) => ok && setDa(x)).catch(() => {});
    getPlayerDetail(bTeam ?? team, b, bLeague ?? aLeague, "blend", "all", peers).then((x) => ok && setDb(x)).catch(() => {});
    return () => { ok = false; };
  }, [team, a, b, bTeam, bLeague, aLeague, cross]);
  if (!da || !db) return (
    <div className="card skel-wrap">
      <div className="skel-row" style={{ justifyContent: "space-between" }}>
        <span className="skel skel-circle" style={{ width: 46, height: 46 }} />
        <span className="skel" style={{ width: 90, height: 16 }} />
        <span className="skel skel-circle" style={{ width: 46, height: 46 }} />
      </div>
      <div className="skel-stack" style={{ marginTop: 14 }}>
        <span className="skel" style={{ height: 200, borderRadius: 12 }} />
        <span className="skel" style={{ height: 12 }} /><span className="skel" style={{ height: 12 }} /><span className="skel" style={{ height: 12, width: "70%" }} />
      </div>
    </div>
  );

  const head = (d: PlayerDetail, color: string, right = false) => {
    const t = tier(d.ovr);
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexDirection: right ? "row-reverse" : "row", textAlign: right ? "right" : "left" }}>
        {d.photo ? <img src={d.photo} alt="" style={{ width: 46, height: 46, borderRadius: "50%", objectFit: "cover", border: `2px solid ${hexA(color, 0.6)}` }} /> : <span style={{ width: 46 }} />}
        <div>
          <div style={{ fontSize: 14.5, fontWeight: 700 }}>{d.player}</div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>{d.pos} · {d.age}세{(cross || d.team !== team) ? ` · ${d.team}` : ""}</div>
          {cross && d.league && <div className="cmp-lg">{d.league} <em>수준 {d.league_level ?? "?"}</em></div>}
          <div style={{ fontSize: 16, fontWeight: 800, color: t.light }} title={`OVR ${d.ovr} · ${t.ko}`}>
            {d.ovr} <span style={{ fontSize: 10.5, fontWeight: 700 }}>{t.ko}</span>
          </div>
        </div>
      </div>
    );
  };

  const ssTag = (v: number) => (v ? <MeaningTag sm m={ssMeaning(v)} /> : null);

  const sameTpl = !!da?.template && !!db?.template && da.template.key === db.template.key;
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
        <CompareRadar a={sameTpl ? da.radar : (da.radar_line ?? da.radar)} b={sameTpl ? db.radar : (db.radar_line ?? db.radar)} ca={accent} />
      </div>
      <div style={{ textAlign: "center", fontSize: 10.5, opacity: 0.6, marginTop: -2 }}>
        {sameTpl ? `${da.template?.ko ?? "같은 포지션"} 백분위` : "라인 공통 축"}{cross ? " · 8개 리그 기준" : ""}
        <Info label="비교 기준">
          <p>{sameTpl ? `같은 ${da.template?.ko ?? "포지션"} 템플릿 백분위(전 대회 기록).` : `포지션이 달라(${da.template?.ko ?? "?"} · ${db.template?.ko ?? "?"}) 라인 공통 축으로 비교.`}</p>
          {cross && <p>리그가 달라 두 선수 모두 8개 리그 같은 템플릿과 비교(같은 잣대).</p>}
          <p>점선 = 50(중간) · 바깥일수록 상위 · 초록 = 더 나은 쪽(나이는 표시만).</p>
          {cross && <p>OVR 은 리그 수준이 들어간 절대 척도라 바로 비교 가능. &lsquo;○○ 기준 OVR&rsquo; = 그 리그로 옮기면 예상(더 센 리그로 갈 때만 레벨 차 × 0.1 적응 할인, 30세 이상 −1).</p>}
        </Info>
      </div>

      <div style={{ maxWidth: 420, margin: "10px auto 0" }}>
        <StatRow label="OVR" a={da.ovr} b={db.ovr} />
        <StatRow label="평점" a={da.ss_rating} b={db.ss_rating} fmt={(v) => (v ? v.toFixed(2) : "—")} tag={ssTag} note={SS_NOTE} />
        {cross && da.rating_epl != null && db.rating_epl != null && (
          <StatRow label="평점(EPL 환산)" a={da.rating_epl} b={db.rating_epl} fmt={(v) => v.toFixed(2)}
            note="리그 안 상대평가인 평점을 리그 수준만큼 EPL 척도로(레벨 1점당 0.02) — OVR 경기력 계산과 같은 보정" />
        )}
        {cross && da.league && db.proj?.[da.league] != null && (
          <StatRow label={`${da.league} 기준 OVR`} a={da.ovr} b={db.proj[da.league]}
            note={`${db.player} 가 ${da.league} 로 오면 예상 OVR — 더 센 리그로 갈 때만 레벨 차 × 0.1 적응 할인, 30세 이상 −1`} />
        )}
        {cross && db.league && da.proj?.[db.league] != null && (
          <StatRow label={`${db.league} 기준 OVR`} a={da.proj[db.league]} b={db.ovr}
            note={`${da.player} 가 ${db.league} 로 가면 예상 OVR`} />
        )}
        <StatRow label="나이" a={da.age} b={db.age} fmt={(v) => `${v}세`} better="none" />
        <StatRow label="시장가치" a={da.value_eur} b={db.value_eur} fmt={fmtEur} />
        <StatRow label="출전(분)" a={da.minutes} b={db.minutes} fmt={(v) => v.toLocaleString()} />
        <StatRow label="득점" a={da.goals} b={db.goals} />
        <StatRow label="도움" a={da.assists} b={db.assists} />
      </div>
    </div>
  );
}
