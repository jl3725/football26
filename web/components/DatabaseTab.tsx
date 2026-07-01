"use client";
import { useEffect, useMemo, useState } from "react";
import { getDatabase, fmtEur, type DbPlayer } from "@/lib/api";
import { tier } from "@/lib/ui";

const LINES = [
  { key: "ALL", label: "전체" }, { key: "GK", label: "GK" }, { key: "DEF", label: "수비" },
  { key: "MID", label: "중원" }, { key: "FWD", label: "공격" },
];
const LIMIT = 24;

export default function DatabaseTab({ accent }: { team: string; accent: string }) {
  const [all, setAll] = useState<DbPlayer[]>([]);
  const [nats, setNats] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [line, setLine] = useState("ALL");
  const [nat, setNat] = useState("ALL");
  const [maxAge, setMaxAge] = useState(40);
  const [maxVal, setMaxVal] = useState(200);

  useEffect(() => { let a = true; getDatabase().then((d) => { if (a) { setAll(d.players); setNats(d.nationalities); } }).catch(() => {}); return () => { a = false; }; }, []);

  const filtered = useMemo(() => all.filter((p) =>
    (!q || p.player.toLowerCase().includes(q.toLowerCase())) &&
    (line === "ALL" || p.line === line) &&
    (nat === "ALL" || p.nationality === nat) &&
    (p.age <= maxAge) &&
    (p.value_eur <= maxVal * 1e6)
  ), [all, q, line, nat, maxAge, maxVal]);

  const shown = filtered.slice(0, LIMIT);

  return (
    <div className="fade">
      <div className="card">
        <h3>전 리그 선수 검색 · {all.length}명</h3>
        <div className="db-filters">
          <div className="search" style={{ margin: 0, flex: "1 1 200px" }}>
            <span>⌕</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="선수 이름…" />
          </div>
          <div className="db-pills">
            {LINES.map((l) => (
              <button key={l.key} className={`db-pill${line === l.key ? " active" : ""}`}
                onClick={() => setLine(l.key)} style={line === l.key ? { background: accent, color: "#0b0f17" } : undefined}>{l.label}</button>
            ))}
          </div>
          <select className="db-select" value={nat} onChange={(e) => setNat(e.target.value)}>
            <option value="ALL">국적 전체</option>
            {nats.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <label className="db-range">나이 ≤ <b>{maxAge}</b><input type="range" min={16} max={40} value={maxAge} onChange={(e) => setMaxAge(+e.target.value)} /></label>
          <label className="db-range">가치 ≤ <b>€{maxVal}M</b><input type="range" min={0} max={200} step={5} value={maxVal} onChange={(e) => setMaxVal(+e.target.value)} /></label>
        </div>
        <div className="db-count">{filtered.length}명 매칭 · OVR 높은 순</div>
      </div>

      <div className="db-grid">
        {shown.map((p, i) => {
          const t = tier(p.ovr);
          return (
            <div className="db-card" key={i}>
              <div className="db-ovr" style={{ color: t.light }}>{p.ovr}</div>
              {p.photo ? <img className="db-photo" src={p.photo} alt="" /> : <span className="db-photo ph" />}
              <div className="db-name">{p.player}</div>
              <div className="db-club">{p.logo && <img src={p.logo} alt="" />}{p.squad}</div>
              <div className="db-meta">{p.pos} · {p.age}세{p.nationality ? " · " + p.nationality : ""}</div>
              <div className="db-val">{fmtEur(p.value_eur)}</div>
            </div>
          );
        })}
      </div>
      {filtered.length > LIMIT && <div className="db-more">… 외 {filtered.length - LIMIT}명 — 필터를 좁히면 더 정확히 찾을 수 있어요.</div>}
      {filtered.length === 0 && <div className="placeholder"><div className="ph-icon">🔎</div><div className="ph-title">결과 없음</div><div className="ph-sub">필터를 완화해 보세요</div></div>}
    </div>
  );
}
