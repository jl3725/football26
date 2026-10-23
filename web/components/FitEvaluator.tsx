"use client";
import { useEffect, useState } from "react";
import { getFit, fmtEur, type Fit } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import { scoreMeaning, ovrMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Bar from "./Bar";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";
import Info from "./Info";

// 첫 칸 '자동' = 후보의 본 포지션(TM). 예전 기본값이 '중앙 MF'라 이름을 직접 넣으면 크바라츠헬리아도 CM 으로 평가됐다(2026-10-19)
const ROLES = [
  ["", "자동 · 본 포지션"], ["Centre-Back", "센터백"], ["Right-Back", "라이트백"], ["Left-Back", "레프트백"],
  ["Defensive Midfield", "수비형 MF"], ["Central Midfield", "중앙 MF"], ["Attacking Midfield", "공격형 MF"],
  ["Right Winger", "우측 윙"], ["Left Winger", "좌측 윙"], ["Centre-Forward", "센터포워드"],
  ["Second Striker", "세컨 스트라이커"], ["Goalkeeper", "골키퍼"],
];
const ROLE_KO: Record<string, string> = Object.fromEntries(ROLES.filter(([v]) => v));
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

// 0~100 점수(높을수록 좋음) — 색·단어는 scoreMeaning. 리스크(danger)는 높을수록 나쁨이라 뒤집어 색을 고른다.
function CompBar({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  const m = danger ? scoreMeaning(100 - value) : scoreMeaning(value);
  return (
    <div style={{ marginBottom: 7 }} title={danger ? `리스크 ${value} / 100 — 높을수록 감점` : `${label} ${value} / 100 (${m.label})`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, fontSize: 11.5, marginBottom: 3 }}>
        <span style={{ opacity: 0.75 }}>{label}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          {!danger && <MeaningTag sm m={m} />}
          <b style={{ color: m.c }}>{value}{danger ? " (감점)" : ""}</b>
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: hexA("#ffffff", 0.08) }}>
        <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${value}%`, background: m.bar }} />
      </div>
    </div>
  );
}

export default function FitEvaluator({ team, accent, suggestions, initial }:
  { team: string; accent: string; suggestions: { player: string; role: string }[];
    initial?: { player: string; role: string } | null }) {   // 이적 작업대 SHORTLIST 의 FIT 버튼으로 바로 평가
  const [cand, setCand] = useState("");
  const [role, setRole] = useState("");
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
  useEffect(() => { if (initial?.player) pick(initial); }, [initial?.player, initial?.role]); // eslint-disable-line react-hooks/exhaustive-deps

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
          <b>평가 서버 준비 중</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>잠시 후 다시 시도하세요</div>
        </div>
      )}
      {res && res.available && res.error && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <b>{res.error}</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>선수명·역할을 확인해주세요</div>
        </div>
      )}
      {res && res.available && res.components && <FitCard r={res} accent={accent} />}
    </div>
  );
}

function FitCard({ r, accent }: { r: Fit; accent: string }) {
  const c = r.components!;
  const fm = scoreMeaning(r.fit_score ?? null);
  const td = r.tactical_detail;
  const af = r.affordability;
  const peek = usePeek();
  return (
    <div className="card" style={{ marginTop: 16 }}>
      {/* 헤더 + 총점 */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 220px", minWidth: 0 }}>
          <div style={{ fontSize: 17, fontWeight: 800 }}>{r.candidate}</div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>{r.source_league} → {r.target_club} · {ROLE_KO[r.role] || r.role}
            {r.natural_role && r.natural_role !== r.role ? "" : " (본 포지션)"}</div>
          {r.role_note && <div style={{ fontSize: 11.5, color: "#e0a53a", marginTop: 3 }}>⚠ 본 포지션 {ROLE_KO[r.natural_role || ""] || r.natural_role} — {ROLE_KO[r.role] || r.role} 로 평가 중</div>}
          <div style={{ fontSize: 12, marginTop: 4, display: "flex", flexWrap: "wrap", alignItems: "center", gap: "3px 5px" }}>
            <span>현재 OVR <b>{r.base_ovr}</b> → 우리 리그 예상 <b style={{ color: r.proj_ovr != null ? tier(r.proj_ovr).light : accent }}>{r.proj_ovr}</b></span>
            {r.proj_ovr != null && <MeaningTag sm m={ovrMeaning(r.proj_ovr)} />}
            <span style={{ opacity: 0.55 }}>({r.target_league})</span>
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1, color: fm.c }}>{r.fit_score}</div>
          <div style={{ fontSize: 10, margin: "2px 0 3px", display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ opacity: 0.55 }}>FIT SCORE <span style={{ opacity: 0.8 }}>/ 100</span></span>
            <Info label="FIT SCORE 설명">
              <p><b>FIT SCORE</b> 0~100 — 역할·전술·니즈·리그 적응·성장성·가치 등을 합친 종합 적합도(높을수록 잘 맞음).</p>
              <p>항목 점수 0~100 · 45+ 보통 · 65+ 높음 · 80+ 매우 높음. 리스크는 높을수록 감점.</p>
              <p className="muted">현재 OVR = 지금 뛰는 리그 기준 · 예상 OVR = 우리 리그 수준으로 보정한 값.</p>
            </Info>
          </div>
          <MeaningTag sm m={fm} />
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
          .map((k) => <CompBar key={k} label={COMP_KO[k]} value={c[k]} />)}
        <CompBar label="리스크" value={c.Risk} danger />
      </div>

      {/* 전술 블렌드 설명 */}
      {td && (
        <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, background: hexA(accent, 0.06),
          borderLeft: `3px solid ${hexA(accent, 0.5)}`, fontSize: 12 }}>
          <b>전술 적합</b> · 현재 전술 <b style={{ color: scoreMeaning(td.current_fit).c }}>{td.current_fit}</b>
          {" "}· 감독 성향 <b style={{ color: scoreMeaning(td.tendency_fit).c }}>{td.tendency_fit}</b>
          {" "}→ 블렌드 <b style={{ color: scoreMeaning(td.blended).c }}>{td.blended}</b> <MeaningTag sm m={scoreMeaning(td.blended)} />{" "}
          <Info label="전술 적합 설명">
            <p>0~100 = 이 선수 스타일이 현재 팀 전술·감독 성향과 얼마나 닮았나(100 = 완전 일치, 리그 평균 기준 아님).</p>
            <p>블렌드 비중: 현재 전술 <b>{Math.round(td.w_current * 100)}%</b> / 감독 성향 <b>{Math.round(td.w_tendency * 100)}%</b></p>
            <p className="muted">감독 {td.is_new_manager ? "새 부임" : "안정"}{td.appointed ? ` · ${td.appointed} 부임` : ""} — 새 감독일수록 감독 성향 비중이 커집니다.</p>
          </Info>
          {td.is_new_manager && td.descriptor_tags.length === 0 &&
            <div style={{ opacity: 0.5, marginTop: 3 }}>감독 성향 데이터 없음</div>}
        </div>
      )}

      {/* 예산 판정 */}
      {af && (
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", fontSize: 12 }}>
          <span style={{ fontWeight: 700 }}>예산</span>
          <span>적정 이적료 <b>{af.likely_fee_eur ? fmtEur(af.likely_fee_eur) : "?"}</b> / 상한 <b>{af.ceiling_eur ? fmtEur(af.ceiling_eur) : "?"}</b></span>
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
        <span title="같은 리그 경로(출신 리그 → 우리 리그) 이적 사례 수">선례 {r.precedent_transfers ?? 0}</span> · 유럽경험 {r.euro_experience ? "O" : "X"}
        {r.notes ? ` · ${r.notes}` : ""}
      </div>
    </div>
  );
}
