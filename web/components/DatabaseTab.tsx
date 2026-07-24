"use client";
import { useEffect, useMemo, useState } from "react";
import { getDatabase, fmtEur, type DbPlayer } from "@/lib/api";
import { tier, roleClass } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";

const LINES = [
  { key: "ALL", label: "전체" }, { key: "GK", label: "GK" }, { key: "DEF", label: "수비" },
  { key: "MID", label: "중원" }, { key: "ATT", label: "공격" },
];
const ROLES = ["핵심 주전", "주전·유럽 로테이션", "리그 주전", "로테이션", "유망주 출전", "컵 전용", "백업", "주변 자원"];
const LIMIT = 24;

export default function DatabaseTab({ accent }: { team: string; accent: string }) {
  const [all, setAll] = useState<DbPlayer[]>([]);
  const [nats, setNats] = useState<string[]>([]);
  const [leagues, setLeagues] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [line, setLine] = useState("ALL");
  const [lg, setLg] = useState("ALL");
  const [nat, setNat] = useState("ALL");
  const [role, setRole] = useState("ALL");
  const [bmOnly, setBmOnly] = useState(false);
  const [maxAge, setMaxAge] = useState(40);
  const [maxVal, setMaxVal] = useState(200);
  const [limit, setLimit] = useState(LIMIT);
  const peek = usePeek();

  useEffect(() => { let a = true; getDatabase().then((d) => { if (a) { setAll(d.players); setNats(d.nationalities); setLeagues(d.leagues || []); } }).catch(() => {}); return () => { a = false; }; }, []);

  const filtered = useMemo(() => all.filter((p) =>
    (!q || p.player.toLowerCase().includes(q.toLowerCase())) &&
    (lg === "ALL" || p.league === lg) &&
    (line === "ALL" || p.line === line) &&
    (nat === "ALL" || p.nationality === nat) &&
    (role === "ALL" || p.role === role) &&
    (!bmOnly || p.big_match) &&
    (p.age <= maxAge) &&
    (p.value_eur <= maxVal * 1e6)
  ), [all, q, lg, line, nat, role, bmOnly, maxAge, maxVal]);

  // 필터가 바뀌면 표시 수 초기화
  useEffect(() => { setLimit(LIMIT); }, [q, lg, line, nat, role, bmOnly, maxAge, maxVal]);

  const shown = filtered.slice(0, limit);
  if (all.length === 0) return <div className="skel-wrap"><SkelCards n={12} cols="repeat(auto-fill, minmax(200px, 1fr))" /></div>;

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
          {leagues.length > 1 && (
            <div className="db-pills">
              <button className={`db-pill${lg === "ALL" ? " active" : ""}`} onClick={() => setLg("ALL")}
                style={lg === "ALL" ? { background: accent, color: "#0b0f17" } : undefined}>전 리그</button>
              {leagues.map((l) => (
                <button key={l} className={`db-pill${lg === l ? " active" : ""}`} onClick={() => setLg(l)}
                  style={lg === l ? { background: accent, color: "#0b0f17" } : undefined}>{l}</button>
              ))}
            </div>
          )}
          <select className="db-select" value={nat} onChange={(e) => setNat(e.target.value)}>
            <option value="ALL">국적 전체</option>
            {nats.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <select className="db-select" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="ALL">역할 전체</option>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button className={`db-pill${bmOnly ? " active" : ""}`} onClick={() => setBmOnly((v) => !v)}
            style={bmOnly ? { background: accent, color: "#0b0f17" } : undefined}>⚡ 빅매치 검증</button>
          <label className="db-range">나이 ≤ <b>{maxAge}</b><input type="range" min={16} max={40} value={maxAge} onChange={(e) => setMaxAge(+e.target.value)} /></label>
          <label className="db-range">가치 ≤ <b>€{maxVal}M</b><input type="range" min={0} max={200} step={5} value={maxVal} onChange={(e) => setMaxVal(+e.target.value)} /></label>
        </div>
        <div className="db-count">{filtered.length}명 매칭 · OVR 높은 순</div>
      </div>

      <div className="db-grid">
        {shown.map((p, i) => {
          const t = tier(p.ovr);
          return (
            <div className="db-card hoverable" key={i} style={{ cursor: "pointer" }}
              onClick={(e) => peek(e, { name: p.player, club: p.squad, league: p.league, hint: p })}>
              <div className="db-ovr" style={{ color: t.light }}>{p.ovr}</div>
              {p.big_match && <span className="db-bm" title="UCL/UEL 급 무대 검증">⚡</span>}
              {p.photo ? <img className="db-photo" src={p.photo} alt="" /> : <span className="db-photo ph" />}
              <div className="db-name">{p.player}</div>
              <div className="db-club">{p.logo && <img src={p.logo} alt="" />}{p.squad}<span className="db-lg">{p.league}</span></div>
              <div className="db-meta">{p.pos} · {p.age}세{p.nationality ? " · " + p.nationality : ""}</div>
              {p.role && <span className={"role-tag sm " + roleClass(p.role)}>{p.role}</span>}
              <div className="db-val">{fmtEur(p.value_eur)}</div>
            </div>
          );
        })}
      </div>
      {filtered.length > limit && (
        <button className="more-btn" onClick={() => setLimit((v) => v + LIMIT)}>
          더 보기 +{Math.min(LIMIT, filtered.length - limit)} <span style={{ opacity: 0.55 }}>(남은 {filtered.length - limit}명)</span>
        </button>
      )}
      {filtered.length === 0 && <div className="placeholder"><div className="ph-icon">🔎</div><div className="ph-title">결과 없음</div><div className="ph-sub">필터를 완화해 보세요</div></div>}
    </div>
  );
}
