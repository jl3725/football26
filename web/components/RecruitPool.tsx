"use client";
import { useEffect, useMemo, useState } from "react";
import { getDiscover, fmtEur, type Discover, type DiscoverPick } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";

const POS_BTNS: [string, string][] = [
  ["", "전체"], ["Centre-Back", "CB"], ["Left-Back", "LB"], ["Right-Back", "RB"],
  ["Defensive Midfield", "DM"], ["Central Midfield", "CM"], ["Attacking Midfield", "AM"],
  ["Left Winger", "LW"], ["Right Winger", "RW"], ["Centre-Forward", "CF"],
];
const LEAGUES: [string, string][] = [
  ["EPL", "Premier League"], ["LaLiga", "La Liga"], ["SerieA", "Serie A"], ["Bundesliga", "Bundesliga"],
  ["Ligue1", "Ligue 1"], ["LigaPortugal", "Liga Portugal"], ["Eredivisie", "Eredivisie"],
];
const SORTS: [string, string][] = [["style", "유사도"], ["ovr", "예상 OVR"], ["value", "시장가"], ["age", "나이"]];

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent: string }) {
  return (
    <div className="card" style={{ padding: "12px 14px" }}>
      <div style={{ fontSize: 10.5, opacity: 0.55, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 21, fontWeight: 800, marginTop: 2, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: 10, opacity: 0.5 }}>{sub}</div>}
    </div>
  );
}

function Card({ p, accent }: { p: DiscoverPick; accent: string }) {
  const t = tier(p.ovr);
  const rising = (p.age ?? 30) <= 21;
  return (
    <div className="card" style={{ padding: 13 }}>
      <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
        {p.photo ? <img src={p.photo} alt="" style={{ width: 46, height: 46, borderRadius: "50%", objectFit: "cover", border: `1px solid ${hexA(accent, 0.3)}` }} />
          : <span style={{ width: 46, height: 46, borderRadius: "50%", background: hexA("#fff", 0.06), display: "inline-block" }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, display: "flex", alignItems: "center", gap: 5 }}>
            {p.player}
            {p.kg_rumored && <span title={`이 팀과 루머 연결${p.kg_rumor_prob ? ` ${p.kg_rumor_prob}%` : ""}`} style={{ fontSize: 11 }}>🔗</span>}
          </div>
          <div style={{ fontSize: 10.5, opacity: 0.6, marginTop: 1 }}>{p.squad} · {p.source_league}</div>
          <span style={{ fontSize: 9.5, padding: "1px 6px", borderRadius: 6, background: hexA(accent, 0.14), color: accent, marginTop: 4, display: "inline-block" }}>{p.pos}</span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1, color: t.light }}>{p.ovr}</div>
          <div style={{ fontSize: 9, opacity: 0.5 }}>{p.cross_league ? `↗ ${p.current_ovr}` : "OVR"}</div>
        </div>
      </div>
      {/* 스탯 */}
      <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 11 }}>
        <span><b>{p.goals ?? 0}</b><span style={{ opacity: 0.5 }}> G</span></span>
        <span><b>{p.assists ?? 0}</b><span style={{ opacity: 0.5 }}> A</span></span>
        <span><b>{p.rating ?? "-"}</b><span style={{ opacity: 0.5 }}> 평점</span></span>
        <span style={{ marginLeft: "auto", opacity: 0.7 }}>{p.age ?? "?"}세 · {fmtEur(p.value_eur || 0)}</span>
      </div>
      {/* 유사도 바 */}
      <div style={{ marginTop: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, opacity: 0.6, marginBottom: 2 }}>
          <span>스타일 유사도</span><span style={{ color: accent }}>{p.style_fit}</span>
        </div>
        <div style={{ height: 4, borderRadius: 3, background: hexA("#fff", 0.08) }}>
          <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${p.style_fit}%`, background: accent }} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 5, marginTop: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA(rising ? "#4fc27f" : "#8aa", 0.15), color: rising ? "#4fc27f" : "#9ab" }}>{rising ? "🌱 성장형" : "안정"}</span>
        {p.euro && <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#f4cf5e", 0.15), color: "#f4cf5e" }}>⚡ 유럽검증</span>}
        {p.kg_precedent ? <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA(accent, 0.12), color: accent }}>선례 {p.kg_precedent}</span> : null}
      </div>
    </div>
  );
}

export default function RecruitPool({ team, accent }: { team: string; accent: string }) {
  const [disc, setDisc] = useState<Discover | null>(null);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState("");
  const [lgs, setLgs] = useState<string[]>([]);     // 빈=전체
  const [ageMin, setAgeMin] = useState(16);
  const [ageMax, setAgeMax] = useState(34);
  const [valMax, setValMax] = useState(200);         // M€
  const [sortBy, setSortBy] = useState("style");

  useEffect(() => {
    let a = true; setLoading(true); setDisc(null);
    getDiscover(team, { role, top: 40 }).then((d) => a && setDisc(d)).catch(() => a && setDisc(null)).finally(() => a && setLoading(false));
    return () => { a = false; };
  }, [team, role]);

  const toggleLg = (k: string) => setLgs((s) => s.includes(k) ? s.filter((x) => x !== k) : [...s, k]);

  const picks = useMemo(() => {
    const all = disc?.recommendations || [];
    const f = all.filter((p) => (lgs.length === 0 || lgs.includes(p.source_league))
      && (p.age == null || (p.age >= ageMin && p.age <= ageMax))
      && (!p.value_eur || p.value_eur <= valMax * 1e6));
    const key = (p: DiscoverPick) => sortBy === "ovr" ? p.ovr : sortBy === "value" ? (p.value_eur || 0) : sortBy === "age" ? -(p.age || 99) : p.style_fit;
    return [...f].sort((a, b) => key(b) - key(a));
  }, [disc, lgs, ageMin, ageMax, valMax, sortBy]);

  const kAge = picks.filter((p) => p.age).map((p) => p.age as number);
  const kVal = picks.filter((p) => p.value_eur).map((p) => p.value_eur as number);
  const avgAge = kAge.length ? (kAge.reduce((s, x) => s + x, 0) / kAge.length).toFixed(1) : "-";
  const avgVal = kVal.length ? kVal.reduce((s, x) => s + x, 0) / kVal.length : 0;

  if (disc && !disc.available) return (
    <div className="nodata-card" style={{ marginTop: 16 }}>
      <div style={{ fontSize: 28 }}>🔌</div><b>벡터 추천 비활성</b>
      <div className="mgr-meta" style={{ marginTop: 6 }}>{disc.reason || "Qdrant 스택 필요 (로컬/호스팅)"}</div>
    </div>
  );

  const railLabel: React.CSSProperties = { fontSize: 10, fontWeight: 700, opacity: 0.5, textTransform: "uppercase", letterSpacing: 0.5, margin: "14px 0 7px" };

  return (
    <div style={{ marginTop: 16 }}>
      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 14 }}>
        <Kpi label="후보" value={String(picks.length)} sub="필터 적용" accent={accent} />
        <Kpi label="평균 나이" value={`${avgAge}세`} accent={accent} />
        <Kpi label="평균 시장가" value={fmtEur(avgVal)} accent={accent} />
        <Kpi label="커버 리그" value={String(new Set(picks.map((p) => p.source_league)).size)} accent={accent} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: 16, alignItems: "start" }}>
        {/* 필터 레일 */}
        <div className="card" style={{ position: "sticky", top: 8 }}>
          <div style={{ ...railLabel, marginTop: 0 }}>리그</div>
          {LEAGUES.map(([k, name]) => (
            <label key={k} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, padding: "3px 0", cursor: "pointer", opacity: (lgs.length === 0 || lgs.includes(k)) ? 1 : 0.5 }}>
              <input type="checkbox" checked={lgs.length === 0 || lgs.includes(k)} onChange={() => toggleLg(k)} />
              {name}
            </label>
          ))}
          <div style={railLabel}>포지션</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 5 }}>
            {POS_BTNS.map(([v, lbl]) => (
              <button key={v} onClick={() => setRole(v)} style={{
                fontSize: 11, padding: "5px 0", borderRadius: 7, cursor: "pointer",
                border: `1px solid ${role === v ? accent : hexA(accent, 0.2)}`,
                background: role === v ? hexA(accent, 0.2) : "transparent", color: role === v ? accent : "inherit",
              }}>{lbl}</button>
            ))}
          </div>
          <div style={railLabel}>나이 {ageMin}–{ageMax}</div>
          <input type="range" min={16} max={34} value={ageMin} onChange={(e) => setAgeMin(Math.min(+e.target.value, ageMax))} style={{ width: "100%" }} />
          <input type="range" min={16} max={40} value={ageMax} onChange={(e) => setAgeMax(Math.max(+e.target.value, ageMin))} style={{ width: "100%" }} />
          <div style={railLabel}>시장가 ≤ €{valMax}M</div>
          <input type="range" min={5} max={200} step={5} value={valMax} onChange={(e) => setValMax(+e.target.value)} style={{ width: "100%" }} />
        </div>

        {/* 그리드 */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 12, opacity: 0.7 }}>
              {loading ? "불러오는 중…" : `${picks.length}명`}
              {disc?.target_roles && !role ? <span style={{ opacity: 0.6 }}> · 약점 {disc.target_roles.join("·")}</span> : null}
            </span>
            <label style={{ fontSize: 12, opacity: 0.7 }}>정렬{" "}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ background: hexA("#fff", 0.06), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit", borderRadius: 6, padding: "3px 8px", fontSize: 12 }}>
                {SORTS.map(([v, l]) => <option key={v} value={v} style={{ color: "#111" }}>{l}</option>)}
              </select>
            </label>
          </div>
          {loading ? <div className="loading">불러오는 중…</div>
            : picks.length === 0 ? <div className="mgr-meta">조건에 맞는 후보 없음 — 필터를 넓혀보세요</div>
              : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
                {picks.map((p, i) => <Card key={i} p={p} accent={accent} />)}
              </div>}
        </div>
      </div>
    </div>
  );
}
