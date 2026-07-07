"use client";
import { useEffect, useRef, useState } from "react";
import { getScout, fmtEur, type Scout } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";

type Msg = { role: "user" | "assistant"; text: string; data?: Scout };

const EXAMPLES = [
  "여름 보강 우선순위 짜줘",
  "이 팀은 어떤 팀이야?",
  "de Jong 우리 팀 CM으로 맞아?",
  "Pedri랑 비슷한 선수",
  "이 팀에 Arteta 오면?",
];
const VERDICT_KO: Record<string, string> = { within: "적정", stretch: "무리", "over-budget": "예산초과" };
const TAG_KO: Record<string, string> = {
  "high-press": "고압박", possession: "점유", "chance-creation": "찬스메이킹", attacking: "공격적",
  "aerial-strong": "공중강세", "disruptive-defense": "수비압박", "reactive/low-block": "로우블록", balanced: "균형",
  press: "고압박", direct: "직선·역습", low_block: "로우블록", wing: "측면", aerial: "세트피스·공중",
};

function Chip({ t, accent }: { t: string; accent: string }) {
  return <span style={{ fontSize: 10.5, padding: "2px 7px", borderRadius: 9, background: hexA(accent, 0.14), color: accent }}>{t}</span>;
}

function fmtCell(v: unknown): string {
  if (v == null) return "-";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// intent 별 컴팩트 결과 카드(자세히는 Overview/Recruit 탭)
function ResultCard({ d, accent, onNavigate }: { d: Scout; accent: string; onNavigate?: (t: string, l?: string) => void }) {
  const r = d.result;
  if (!r) return null;
  if (r.available === false) return <div style={{ fontSize: 12, opacity: 0.6 }}>🔌 {r.reason}</div>;
  if (r.error) return <div style={{ fontSize: 12, opacity: 0.6 }}>🔍 {r.error}</div>;
  const box: React.CSSProperties = { marginTop: 8, padding: "10px 12px", borderRadius: 10, background: hexA("#ffffff", 0.04), border: `1px solid ${hexA(accent, 0.15)}` };

  if (d.intent === "recommend") {
    const picks = (r.recommendations || []).slice(0, 6);
    return (
      <div style={box}>
        {r.weakest?.label && <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 6 }}>약점 라인: {r.weakest.label}</div>}
        {picks.map((p: any, i: number) => (
          <div key={i} onClick={() => p.squad && onNavigate?.(p.squad, p.source_league)} title={p.squad ? `${p.squad} 보기` : ""}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", cursor: onNavigate && p.squad ? "pointer" : "default", borderBottom: i < picks.length - 1 ? `1px solid ${hexA("#fff", 0.05)}` : "none" }}>
            {p.photo ? <img src={p.photo} alt="" style={{ width: 26, height: 26, borderRadius: "50%", objectFit: "cover" }} /> : <span style={{ width: 26 }} />}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600 }}>{p.player} <span style={{ opacity: 0.5, fontWeight: 400 }}>{p.squad}</span></div>
              <div style={{ fontSize: 10.5, opacity: 0.6 }}>{p.pos} · {fmtEur(p.value_eur)}{p.cross_league ? ` · ↗${p.source_league}` : ""}
                {p.style_fit != null ? <span style={{ color: accent }}> · 스타일 {p.style_fit}</span> : null}</div>
            </div>
            <div style={{ fontSize: 15, fontWeight: 800, color: tier(p.ovr).light }}>{p.projected_ovr || p.ovr}</div>
          </div>
        ))}
      </div>
    );
  }
  if (d.intent === "fit") {
    const c = r.components; if (!c) return null;
    const af = r.affordability;
    return (
      <div style={box}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontSize: 30, fontWeight: 800, color: tier(r.fit_score).light }}>{r.fit_score}</div>
          <div style={{ fontSize: 11.5 }}>
            <div><b>{r.candidate}</b> → {r.target_club} / {r.role}</div>
            <div style={{ opacity: 0.6 }}>{r.signing_type} · Risk {r.risk_level} · {r.base_ovr}→{r.proj_ovr}</div>
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 10px", marginTop: 8, fontSize: 11 }}>
          {[["역할", c.RoleFit], ["전술", c.TacticalFit], ["니즈", c.TeamNeed], ["성장", c.Potential], ["가격", c.PriceRealism], ["영입성향", c.RecruitFit]].map(([k, v]: any) => (
            <span key={k} style={{ opacity: 0.8 }}>{k} <b style={{ color: tier(v).light }}>{v}</b></span>
          ))}
        </div>
        {af && <div style={{ fontSize: 11, opacity: 0.7, marginTop: 6 }}>예산: {af.likely_fee_eur ? fmtEur(af.likely_fee_eur) : "?"} / 상한 {af.ceiling_eur ? fmtEur(af.ceiling_eur) : "?"} → {VERDICT_KO[af.verdict] || af.verdict}</div>}
      </div>
    );
  }
  if (d.intent === "similar") {
    const res = (r.results || []).slice(0, 6);
    return (
      <div style={box}>
        {res.map((p: any, i: number) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12 }}>
            <span>{p.player} <span style={{ opacity: 0.5 }}>{p.squad} · {p.pos}</span></span>
            <b style={{ color: accent }}>{Math.round((p.score || 0) * 100)}</b>
          </div>
        ))}
      </div>
    );
  }
  if (d.intent === "managersim") {
    return (
      <div style={box}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{r.target_club} ← {r.new_manager}</div>
        {(r.vector_changes || []).slice(0, 4).map((c: any) => (
          <div key={c.axis} style={{ fontSize: 11, opacity: 0.8 }}>{c.axis}: {c.from}→<b>{c.to}</b> {c.delta > 0 ? "▲" : "▼"}{Math.abs(c.delta)}</div>
        ))}
        {(r.priorities || []).slice(0, 2).map((p: any, i: number) => (
          <div key={i} style={{ fontSize: 11, marginTop: 5 }}><b>{p.role}</b>: {(p.candidates || []).slice(0, 3).join(", ") || "-"}</div>
        ))}
      </div>
    );
  }
  if (d.intent === "graph") {
    const rows: Record<string, unknown>[] = r.rows || [];
    if (r.error) return <div style={{ fontSize: 12, opacity: 0.6 }}>🔍 {r.error}</div>;
    if (rows.length === 0) return <div style={{ fontSize: 12, opacity: 0.6, ...box }}>결과 없음{r.cypher ? <div style={{ opacity: 0.4, marginTop: 4, fontFamily: "monospace", fontSize: 10 }}>{r.cypher}</div> : null}</div>;
    const cols = Object.keys(rows[0]);
    return (
      <div style={box}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%" }}>
            <thead><tr>{cols.map((c) => <th key={c} style={{ textAlign: "left", padding: "3px 8px", opacity: 0.6, borderBottom: `1px solid ${hexA(accent, 0.3)}`, whiteSpace: "nowrap" }}>{c.replace(/^[a-z]\./, "")}</th>)}</tr></thead>
            <tbody>{rows.slice(0, 15).map((row, i) => (
              <tr key={i}>{cols.map((c) => <td key={c} style={{ padding: "3px 8px", borderBottom: `1px solid ${hexA("#fff", 0.05)}`, whiteSpace: "nowrap" }}>{fmtCell(row[c])}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
        {r.count > 15 ? <div style={{ fontSize: 10, opacity: 0.5, marginTop: 4 }}>+{r.count - 15}건 더</div> : null}
        {r.cypher ? <div style={{ opacity: 0.35, marginTop: 6, fontFamily: "monospace", fontSize: 9.5, whiteSpace: "pre-wrap" }}>◆ {r.cypher}</div> : null}
      </div>
    );
  }
  if (d.intent === "identity") {
    const tc = r.tactics, rc = r.recruitment, bg = r.budget;
    return (
      <div style={box}>
        {tc && <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
          <span style={{ fontSize: 11, opacity: 0.6, alignSelf: "center" }}>{tc.manager} ·</span>
          {(tc.current_tags || []).map((t: string, i: number) => <Chip key={i} t={TAG_KO[t] || t} accent={accent} />)}</div>}
        {rc && <div style={{ fontSize: 11.5 }}>영입 성향: <b>{rc.profile}</b> · 평균영입 {rc.avg_age}세</div>}
        {bg && <div style={{ fontSize: 11.5, opacity: 0.8 }}>예산: {bg.spend_tier} tier · 가격상한 {fmtEur(bg.price_ceiling_eur)}</div>}
      </div>
    );
  }
  return null;
}

export default function ScoutChat({ team, league, accent, onNavigate, embedded }:
  { team: string; league: string; accent: string; onNavigate?: (t: string, l?: string) => void; embedded?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState("");
  const [needAuth, setNeedAuth] = useState(false);
  const [pw, setPw] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { setToken(localStorage.getItem("scout_token") || ""); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, loading]);

  const send = (q = input, tok = token) => {
    const text = q.trim();
    if (!text || loading) return;
    const hist = msgs.map((m) => ({ role: m.role, content: m.text }));   // 대화 메모리(후속 질문용)
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput(""); setLoading(true);
    getScout(text, team, league, tok, hist)
      .then((d) => {
        if (d.auth_required) { setNeedAuth(true); setMsgs((m) => [...m, { role: "assistant", text: "🔒 " + (d.reason || "비밀번호가 필요합니다") }]); return; }
        setMsgs((m) => [...m, { role: "assistant", text: d.answer || d.reason || d.error || "응답 없음", data: d }]);
      })
      .catch(() => setMsgs((m) => [...m, { role: "assistant", text: "요청 실패 — API/키 확인" }]))
      .finally(() => setLoading(false));
  };
  const saveToken = () => {
    const t = pw.trim(); if (!t) return;
    localStorage.setItem("scout_token", t); setToken(t); setNeedAuth(false); setPw("");
  };

  return (
    <div className="fade" style={{ display: "flex", flexDirection: "column", height: embedded ? "100%" : "calc(100vh - 190px)" }}>
      {!embedded && (
        <div className="card" style={{ marginBottom: 10 }}>
          <h3>💬 Ask Scout <span style={{ fontSize: 11, fontWeight: 400, opacity: 0.5 }}>· Chief Scout에게 물어보세요 (현재 팀: {team})</span></h3>
          <div style={{ fontSize: 10.5, opacity: 0.45 }}>ℹ️ 판단·수치는 데이터 엔진, LLM은 라우팅·설명만 · 로컬(OpenAI) 사용</div>
        </div>
      )}
      {embedded && <div style={{ fontSize: 10.5, opacity: 0.5, padding: "8px 2px" }}>현재 팀: <b>{team || "-"}</b> · 판단은 데이터 엔진, LLM은 라우팅·설명</div>}

      {/* 메시지 */}
      <div style={{ flex: 1, overflowY: "auto", paddingRight: 4 }}>
        {msgs.length === 0 && (
          <div style={{ textAlign: "center", opacity: 0.5, marginTop: 30, fontSize: 13 }}>
            예: “아스날 6번 추천해줘”, “이 선수 왜 추천했어?”, “비슷한데 더 싼 선수 없나?”
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", margin: "10px 0" }}>
            <div style={{ maxWidth: "82%", padding: "9px 13px", borderRadius: 12, fontSize: 13, lineHeight: 1.55,
              background: m.role === "user" ? hexA(accent, 0.18) : hexA("#ffffff", 0.05),
              border: m.role === "user" ? `1px solid ${hexA(accent, 0.3)}` : `1px solid ${hexA("#ffffff", 0.07)}` }}>
              {m.role === "assistant" && <span style={{ fontSize: 11, opacity: 0.5, marginRight: 5 }}>🤖 Chief Scout</span>}
              <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
              {m.data && <ResultCard d={m.data} accent={accent} onNavigate={onNavigate} />}
            </div>
          </div>
        ))}
        {loading && <div style={{ opacity: 0.55, fontSize: 12, margin: "10px 0" }}>🤖 스카우트가 데이터를 뒤지는 중…</div>}
        <div ref={endRef} />
      </div>

      {/* 예시 칩 */}
      {msgs.length === 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0" }}>
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => send(e)} style={{ fontSize: 11.5, padding: "4px 10px", borderRadius: 12, cursor: "pointer",
              background: hexA(accent, 0.1), border: `1px solid ${hexA(accent, 0.25)}`, color: "inherit" }}>{e}</button>
          ))}
        </div>
      )}

      {/* 비밀번호 게이트 */}
      {needAuth && (
        <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", padding: "8px 10px", borderRadius: 10, background: hexA("#e0a53a", 0.1), border: `1px solid ${hexA("#e0a53a", 0.4)}` }}>
          <span style={{ fontSize: 12 }}>🔒 접근 비밀번호</span>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveToken()}
            placeholder="SCOUT_TOKEN" style={{ flex: 1, padding: "6px 10px", borderRadius: 8, fontSize: 12, background: hexA("#ffffff", 0.06), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }} />
          <button onClick={saveToken} style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none", background: accent, color: "#0a0a0a" }}>저장</button>
        </div>
      )}

      {/* 입력 */}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="스카우트에게 질문… (예: 우리 팀 여름 보강 우선순위)"
          style={{ flex: 1, padding: "10px 13px", borderRadius: 10, fontSize: 13, background: hexA("#ffffff", 0.06),
            border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }} />
        <button onClick={() => send()} disabled={!input.trim() || loading}
          style={{ padding: "10px 20px", borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer", border: "none",
            background: accent, color: "#0a0a0a", opacity: (!input.trim() || loading) ? 0.5 : 1 }}>보내기</button>
      </div>
    </div>
  );
}
