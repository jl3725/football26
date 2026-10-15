"use client";
import { useState } from "react";
import { getManagerSim, type ManagerSim } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { idxMeaning, scoreMeaning, TONE, type Meaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Bar from "./Bar";

// 영입 우선순위의 depth 는 0~100 뎁스 점수가 아니라 '그 역할 선수 수'(백엔드가 2명 이하만 보냄) — 인원 기준 단어.
function headcountMeaning(n: number): Meaning {
  if (n <= 0) return { label: "자원 없음", tone: "bad", ...TONE.bad };
  if (n === 1) return { label: "매우 얇음", tone: "bad", ...TONE.bad };
  if (n === 2) return { label: "얇음", tone: "weak", ...TONE.weak };
  return { label: "보통", tone: "avg", ...TONE.avg };
}

const AXIS_KO: Record<string, string> = {
  pressing: "압박", control: "점유·제어", creativity: "창의성", attack_output: "공격생산",
  aerial: "공중", disruption: "수비방해", ball_winning: "볼 탈취", attack_creation: "공격 전개",
};
const TAG_KO: Record<string, string> = {
  "high-press": "고압박", "possession": "점유", "chance-creation": "찬스메이킹", "attacking": "공격적",
  "aerial-strong": "공중강세", "disruptive-defense": "수비압박", "reactive/low-block": "로우블록", "balanced": "균형",
};
const QUICK = ["Barcelona", "Atlético Madrid", "Arsenal", "Bayern Munich", "Liverpool", "PSG"];

function Tags({ tags, accent, outline }: { tags: string[]; accent: string; outline?: boolean }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
      {tags.map((t, i) => (
        <span key={i} style={{ fontSize: 10.5, padding: "2px 7px", borderRadius: 9,
          background: outline ? "transparent" : hexA(accent, 0.16),
          border: outline ? `1px solid ${hexA(accent, 0.4)}` : "none", color: accent }}>{TAG_KO[t] || t}</span>
      ))}
    </div>
  );
}

export default function ManagerSimPanel({ team, accent }: { team: string; accent: string }) {
  const [mgr, setMgr] = useState("");
  const [res, setRes] = useState<ManagerSim | null>(null);
  const [loading, setLoading] = useState(false);

  const run = (m = mgr) => {
    if (!m.trim()) return;
    setLoading(true); setRes(null);
    getManagerSim(team, m.trim()).then(setRes).catch(() => setRes(null)).finally(() => setLoading(false));
  };

  return (
    <div className="fade">
      <div className="card">
        <h3><Bar c={accent} />감독 교체 시뮬레이션</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "6px 0 4px" }}>
          <input value={mgr} onChange={(e) => setMgr(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()} placeholder="새 감독명 또는 클럽명 (예: Hansi Flick / Barcelona)"
            style={{ flex: "1 1 260px", minWidth: 0, padding: "8px 11px", borderRadius: 8, fontSize: 13,
              background: hexA("#ffffff", 0.06), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }} />
          <button onClick={() => run()} disabled={!mgr.trim() || loading}
            style={{ padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer",
              border: "none", background: accent, color: "#0a0a0a", opacity: (!mgr.trim() || loading) ? 0.5 : 1 }}>
            {loading ? "시뮬 중…" : "시뮬레이션"}
          </button>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
          <span style={{ fontSize: 10.5, opacity: 0.5, alignSelf: "center" }}>스타일 예시</span>
          {QUICK.filter((q) => q !== team).map((q) => (
            <button key={q} onClick={() => { setMgr(q); run(q); }}
              style={{ fontSize: 11, padding: "3px 9px", borderRadius: 10, cursor: "pointer",
                background: hexA(accent, 0.12), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }}>{q}</button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="skel-wrap" style={{ marginTop: 16 }}>
          <div className="skel-stack">
            <span className="skel" style={{ height: 70, borderRadius: 14 }} />
            <span className="skel" style={{ height: 180, borderRadius: 14 }} />
          </div>
        </div>
      )}
      {res && !res.available && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <b>로컬 스택 미가동</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>{res.reason}</div>
        </div>
      )}
      {res && res.available && res.error && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <b>{res.error}</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>감독명 또는 클럽명을 확인해주세요 (7대 리그 기준)</div>
        </div>
      )}
      {res && res.available && res.vector_changes && <SimResult r={res} accent={accent} />}
    </div>
  );
}

function SimResult({ r, accent }: { r: ManagerSim; accent: string }) {
  const cur = r.current!, nw = r.new!;
  return (
    <>
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>
          {r.target_club} <span style={{ opacity: 0.5 }}>←</span> {r.new_manager}
          <span style={{ fontSize: 12, fontWeight: 400, opacity: 0.55 }}> ({r.new_from_club} 전술 기준)</span>
        </div>
        {/* 현재 vs 새 감독 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 12 }}>
          <div>
            <div style={{ fontSize: 10.5, opacity: 0.5, textTransform: "uppercase", marginBottom: 3 }}>현재</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{cur.manager} <span style={{ opacity: 0.5, fontWeight: 400 }}>{cur.formation || ""}</span></div>
            <Tags tags={cur.style_tags} accent={accent} />
          </div>
          <div style={{ paddingLeft: 14, borderLeft: `1px solid ${hexA(accent, 0.2)}` }}>
            <div style={{ fontSize: 10.5, opacity: 0.5, textTransform: "uppercase", marginBottom: 3 }}>새 감독</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: accent }}>{nw.manager} <span style={{ opacity: 0.5, fontWeight: 400 }}>{nw.formation || ""}</span></div>
            <Tags tags={nw.style_tags} accent={accent} outline />
          </div>
        </div>
        {/* 전술벡터 변화 */}
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.55, textTransform: "uppercase", marginBottom: 3 }}>전술 변화</div>
          <div style={{ fontSize: 10.5, opacity: 0.5, marginBottom: 8 }}>지수 0~99 · 50 = 리그 평균 · 회색 = 현재, 색 = 새 감독 · ▲▼ = 그 성향이 늘거나 줄어듦</div>
          {r.vector_changes!.map((c) => {
            const up = c.delta > 0;
            const tm = idxMeaning(c.to);
            return (
              <div key={c.axis} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, fontSize: 12 }}>
                <span style={{ width: 68, opacity: 0.75 }}>{AXIS_KO[c.axis] || c.axis}</span>
                <div style={{ flex: 1, position: "relative", height: 6, borderRadius: 3, background: hexA("#ffffff", 0.08) }}>
                  <span style={{ position: "absolute", left: 0, height: "100%", borderRadius: 3, width: `${c.from}%`, background: hexA("#ffffff", 0.22) }} />
                  <span style={{ position: "absolute", left: 0, height: "100%", borderRadius: 3, width: `${c.to}%`, background: hexA(accent, 0.7) }} />
                  <span style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: hexA("#ffffff", 0.35) }} title="50 = 리그 평균" />
                </div>
                <span style={{ width: 88, textAlign: "right", opacity: 0.85 }}
                  title={`${AXIS_KO[c.axis] || c.axis}: 현재 ${c.from} (${idxMeaning(c.from).label}) → 새 감독 ${c.to} (${tm.label})`}>
                  {c.from}→<b style={{ color: tm.c }}>{c.to}</b>
                  {c.delta !== 0 && <span style={{ marginLeft: 5, color: TONE.avg.c, fontWeight: 700 }}>{up ? "▲" : "▼"}{Math.abs(c.delta)}</span>}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 스쿼드 미스핏 + 영입 우선순위 2열 */}
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 style={{ color: "#e0857a" }}>새 시스템 부적합 <span className="rating-note">· 교체 검토</span></h3>
          <div className="tf2-list">
            {(r.squad_misfit || []).map((m, i) => {
              const fm = scoreMeaning(m.sys_fit);
              return (
                <div className="tf2-row" key={i}>
                  <div className="tf2-info">
                    <div className="tf2-name">{m.player}</div>
                    <div className="tf2-meta">{m.role}</div>
                  </div>
                  <MeaningTag sm m={fm} />
                  <span className="tf2-fee" style={{ color: fm.c }} title={`새 감독이 이 자리에 쓰는 스타일과의 유사도 ${m.sys_fit} / 100 (${fm.label})`}>적합 {m.sys_fit}</span>
                </div>
              );
            })}
            {(r.squad_misfit || []).length === 0 && <div className="mgr-meta">두드러진 부적합 없음</div>}
          </div>
          {(r.squad_misfit || []).length > 0 && (
            <div style={{ fontSize: 10.5, opacity: 0.5, marginTop: 6 }}>적합 0~100 = 새 감독 시스템의 같은 역할 스타일과 닮은 정도 (45+ 보통 · 65+ 높음)</div>
          )}
        </div>
        <div className="card">
          <h3 style={{ color: accent }}>새 시스템 영입 우선순위 <span className="rating-note">· 강조 역할 · 스쿼드 얇음</span></h3>
          <div className="tf2-list">
            {(r.priorities || []).map((p, i) => (
              <div key={i} style={{ padding: "8px 0", borderBottom: `1px solid ${hexA("#ffffff", 0.06)}` }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                  <b>{p.role}</b>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5, flexWrap: "wrap", justifyContent: "flex-end" }}
                    title={`새 감독이 이 역할에 주는 출전 비중 ${Math.round(p.share * 100)}% · 우리 스쿼드의 이 역할 선수 ${p.depth}명`}>
                    <span style={{ opacity: 0.55 }}>기용 비중 {Math.round(p.share * 100)}% · 현재 {p.depth}명</span>
                    <MeaningTag sm m={headcountMeaning(p.depth)} />
                  </span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 5 }}>
                  {p.candidates.length > 0 ? p.candidates.map((c, k) => (
                    <span key={k} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 9, background: hexA(accent, 0.14), color: accent }}>{c}</span>
                  )) : <span style={{ fontSize: 11, opacity: 0.4 }}>-</span>}
                </div>
              </div>
            ))}
            {(r.priorities || []).length === 0 && <div className="mgr-meta">스쿼드 충분 (얇은 강조 역할 없음)</div>}
          </div>
        </div>
      </div>
    </>
  );
}
