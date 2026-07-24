"use client";
import { useState } from "react";
import { getFit, fmtEur, type Fit } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import Bar from "./Bar";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";

const ROLES = [
  ["Centre-Back", "센터백"], ["Right-Back", "라이트백"], ["Left-Back", "레프트백"],
  ["Defensive Midfield", "수비형 MF"], ["Central Midfield", "중앙 MF"], ["Attacking Midfield", "공격형 MF"],
  ["Right Winger", "우측 윙"], ["Left Winger", "좌측 윙"], ["Centre-Forward", "센터포워드"],
  ["Second Striker", "세컨 스트라이커"], ["Goalkeeper", "골키퍼"],
];
const COMP_KO: Record<string, string> = {
  RoleFit: "역할 적합", TacticalFit: "전술 적합", TeamNeed: "팀 니즈", Translation: "리그 적응",
  Potential: "성장성", Value: "가치", RecruitFit: "영입 성향", PriceRealism: "가격 현실성",
};
const KIND_KO: Record<string, string> = {
  "Ready-now": "즉시전력", "High-upside development": "성장형", "Value-bet": "가성비", "Rotation": "로테이션",
};
const RISK_KO: Record<string, string> = { High: "높음", Medium: "중간", Low: "낮음" };
const VERDICT_KO: Record<string, string> = { within: "적정", stretch: "무리", "over-budget": "예산초과", unknown: "?" };
const VERDICT_COLOR: Record<string, string> = { within: "#4fc27f", stretch: "#f4cf5e", "over-budget": "#e0556b" };

function CompBar({ label, value, accent, danger }: { label: string; value: number; accent: string; danger?: boolean }) {
  const col = danger ? "#e0707a" : accent;
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 3 }}>
        <span style={{ opacity: 0.75 }}>{label}</span>
        <b style={{ color: danger ? col : tier(value).light }}>{value}{danger ? " (감점)" : ""}</b>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: hexA("#ffffff", 0.08) }}>
        <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${value}%`,
          background: danger ? `linear-gradient(90deg, ${hexA(col, 0.5)}, ${col})` : `linear-gradient(90deg, ${hexA(accent, 0.5)}, ${accent})` }} />
      </div>
    </div>
  );
}

export default function FitEvaluator({ team, accent, suggestions }:
  { team: string; accent: string; suggestions: { player: string; role: string }[] }) {
  const [cand, setCand] = useState("");
  const [role, setRole] = useState(ROLES[4][0]);
  const [res, setRes] = useState<Fit | null>(null);
  const [loading, setLoading] = useState(false);

  const evaluate = (c = cand, r = role) => {
    if (!c.trim()) return;
    setLoading(true); setRes(null);
    getFit(c.trim(), team, r).then(setRes).catch(() => setRes(null)).finally(() => setLoading(false));
  };
  const pick = (s: { player: string; role: string }) => {
    setCand(s.player); if (s.role) setRole(s.role);
    evaluate(s.player, s.role || role);
  };

  return (
    <div className="fade">
      <div className="card">
        <h3><Bar c={accent} />적합도 평가</h3>
        {/* 입력 */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "6px 0 4px" }}>
          <input value={cand} onChange={(e) => setCand(e.target.value)} list="fit-cands"
            onKeyDown={(e) => e.key === "Enter" && evaluate()} placeholder="후보 선수명 (예: Bruno Guimarães)"
            style={{ flex: "1 1 240px", minWidth: 0, padding: "8px 11px", borderRadius: 8, fontSize: 13,
              background: hexA("#ffffff", 0.06), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }} />
          <datalist id="fit-cands">{suggestions.map((s, i) => <option key={i} value={s.player} />)}</datalist>
          <select value={role} onChange={(e) => setRole(e.target.value)}
            style={{ padding: "8px 11px", borderRadius: 8, fontSize: 13, background: hexA("#ffffff", 0.06),
              border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }}>
            {ROLES.map(([v, k]) => <option key={v} value={v} style={{ color: "#111" }}>{k}</option>)}
          </select>
          <button onClick={() => evaluate()} disabled={!cand.trim() || loading}
            style={{ padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer",
              border: "none", background: accent, color: "#0a0a0a", opacity: (!cand.trim() || loading) ? 0.5 : 1 }}>
            {loading ? "평가 중…" : "평가"}
          </button>
        </div>
        {/* 후보 빠른선택 */}
        {suggestions.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
            <span style={{ fontSize: 10.5, opacity: 0.5, alignSelf: "center" }}>추천 후보</span>
            {suggestions.slice(0, 8).map((s, i) => (
              <button key={i} onClick={() => pick(s)} style={{ fontSize: 11, padding: "3px 9px", borderRadius: 10,
                cursor: "pointer", background: hexA(accent, 0.12), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit" }}>
                {s.player.split(" ").slice(-1)[0]}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && <div style={{ marginTop: 16 }}><SkelCards n={2} cols="1fr" face={false} /></div>}
      {res && !res.available && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <b>로컬 스택 미가동</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>{res.reason}</div>
          <div className="mgr-meta" style={{ marginTop: 6, opacity: 0.7 }}>docker compose up -d 후 QDRANT_URL=http://localhost:6335 로 API 재시작</div>
        </div>
      )}
      {res && res.available && res.error && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <b>{res.error}</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>선수명·역할을 확인해주세요 (전 리그 players_full 기준)</div>
        </div>
      )}
      {res && res.available && res.components && <FitCard r={res} accent={accent} />}
    </div>
  );
}

function FitCard({ r, accent }: { r: Fit; accent: string }) {
  const c = r.components!;
  const t = tier(r.fit_score || 0);
  const td = r.tactical_detail;
  const af = r.affordability;
  const peek = usePeek();
  return (
    <div className="card" style={{ marginTop: 16 }}>
      {/* 헤더 + 총점 */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 220px", minWidth: 0 }}>
          <div style={{ fontSize: 17, fontWeight: 800 }}>{r.candidate}</div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>{r.source_league} → {r.target_club} · {r.role}</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>
            base OVR <b>{r.base_ovr}</b> → proj OVR <b style={{ color: accent }}>{r.proj_ovr}</b>
            <span style={{ opacity: 0.55 }}> ({r.target_league})</span>
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1, color: t.light }}>{r.fit_score}</div>
          <div style={{ fontSize: 10, opacity: 0.55 }}>FIT SCORE</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 8, textAlign: "center",
            background: hexA(accent, 0.16), color: accent }}>{KIND_KO[r.signing_type || ""] || r.signing_type}</span>
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 8, textAlign: "center",
            background: hexA(r.risk_level === "High" ? "#e0556b" : r.risk_level === "Medium" ? "#f4cf5e" : "#4fc27f", 0.16),
            color: r.risk_level === "High" ? "#e0707a" : r.risk_level === "Medium" ? "#f4cf5e" : "#4fc27f" }}>
            Risk {RISK_KO[r.risk_level || ""] || r.risk_level}</span>
        </div>
      </div>

      {/* 컴포넌트 바 2열 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "0 24px", marginTop: 16 }}>
        {(["RoleFit", "TacticalFit", "TeamNeed", "Translation", "Potential", "Value", "RecruitFit", "PriceRealism"] as const)
          .map((k) => <CompBar key={k} label={COMP_KO[k]} value={c[k]} accent={accent} />)}
        <CompBar label="리스크" value={c.Risk} accent={accent} danger />
      </div>

      {/* 전술 블렌드 설명 */}
      {td && (
        <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, background: hexA(accent, 0.06),
          borderLeft: `3px solid ${hexA(accent, 0.5)}`, fontSize: 12 }}>
          <b>전술 적합</b> · 현재 전술 {td.current_fit} · 감독 성향 {td.tendency_fit} → 블렌드 <b style={{ color: accent }}>{td.blended}</b>
          <span style={{ opacity: 0.6 }}> ({td.is_new_manager ? "새 부임" : "안정"}
            {td.appointed ? ` · ${td.appointed}` : ""}: 현재 {Math.round(td.w_current * 100)}% / 성향 {Math.round(td.w_tendency * 100)}%)</span>
          {td.is_new_manager && td.descriptor_tags.length === 0 &&
            <div style={{ opacity: 0.5, marginTop: 3 }}>감독 성향 데이터 없음</div>}
        </div>
      )}

      {/* 예산 판정 */}
      {af && (
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", fontSize: 12 }}>
          <span style={{ fontWeight: 700 }}>예산</span>
          <span>예상 이적료 <b>{af.likely_fee_eur ? fmtEur(af.likely_fee_eur) : "?"}</b> / 상한 <b>{af.ceiling_eur ? fmtEur(af.ceiling_eur) : "?"}</b></span>
          <span style={{ fontWeight: 700, color: VERDICT_COLOR[af.verdict] || "inherit" }}>→ {VERDICT_KO[af.verdict] || af.verdict}</span>
          {af.club_recruit_profile && <span style={{ opacity: 0.6 }}>· 구단성향 {af.club_recruit_profile} (평균영입 {af.club_avg_signing_age ?? "?"}세)</span>}
        </div>
      )}

      {/* 유사선수 · 선례 */}
      {r.similar_players && r.similar_players.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 12, display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" }}>
          <span style={{ opacity: 0.6 }}>유사 스타일:</span>
          {r.similar_players.slice(0, 5).map((sp, i) => (
            <span key={i} className="peekable" style={{ padding: "2px 8px", border: `1px solid ${hexA(accent, 0.25)}`, borderRadius: 9 }}
              onClick={(e) => peek(e, { name: sp })}>{sp}</span>
          ))}
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 11, opacity: 0.55 }}>
        선례(같은 리그점프 이적) {r.precedent_transfers ?? 0}건 · 유럽경험 {r.euro_experience ? "O" : "X"}
        {r.notes ? ` · ${r.notes}` : ""}
      </div>
    </div>
  );
}
