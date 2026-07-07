"use client";
import { useEffect, useState } from "react";
import { getIdentity, fmtEur, type Identity } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import HBar from "./Bar";

// 전술 태그 → 한국어. current(팀 벡터 유래) + tendency(descriptor) 두 어휘 모두 커버.
const TAG_KO: Record<string, string> = {
  "high-press": "고압박", "possession": "점유", "chance-creation": "찬스메이킹",
  "attacking": "공격적", "aerial-strong": "공중강세", "disruptive-defense": "수비압박",
  "reactive/low-block": "로우블록", "balanced": "균형",
  "press": "고압박", "direct": "직선·역습", "low_block": "로우블록", "wing": "측면", "aerial": "세트피스·공중",
};
const AGE_KO: Record<string, string> = {
  "prospect-oriented": "유망주형", "balanced-age": "나이균형", "experience-oriented": "즉전·경험형", "unknown": "?",
};
const SPEND_KO: Record<string, string> = {
  "big-spender": "큰손", "bargain/value": "가성비", "moderate-spender": "중간지출", "free/loan-heavy": "무료·임대형",
};
const TIER_KO: Record<string, string> = { elite: "엘리트", big: "상위", mid: "중위", modest: "하위" };
const AXIS_KO: Record<string, string> = {
  pressing: "압박", control: "점유·제어", creativity: "창의성", attack_output: "공격생산",
  aerial: "공중", disruption: "수비방해",
};

function Chip({ text, accent, outline }: { text: string; accent: string; outline?: boolean }) {
  return (
    <span style={{
      fontSize: 11, padding: "2px 8px", borderRadius: 10, whiteSpace: "nowrap",
      background: outline ? "transparent" : hexA(accent, 0.16),
      border: outline ? `1px solid ${hexA(accent, 0.45)}` : "none",
      color: outline ? hexA(accent, 0.95) : accent,
    }}>{text}</span>
  );
}

function Bar({ label, value, accent }: { label: string; value: number; accent: string }) {
  const t = tier(value);
  return (
    <div style={{ marginBottom: 5 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, opacity: 0.8, marginBottom: 2 }}>
        <span>{label}</span><span style={{ color: t.light }}>{Math.round(value)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 3, background: hexA("#ffffff", 0.08) }}>
        <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${value}%`,
          background: `linear-gradient(90deg, ${hexA(accent, 0.5)}, ${accent})` }} />
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, opacity: 0.55, marginBottom: 8, textTransform: "uppercase" }}>{title}</div>
      {children}
    </div>
  );
}

export default function IdentityCard({ team, league, accent }: { team: string; league: string; accent: string }) {
  const [d, setD] = useState<Identity | null>(null);
  useEffect(() => {
    let a = true;
    getIdentity(team, league).then((r) => a && setD(r)).catch(() => {});
    return () => { a = false; };
  }, [team, league]);

  if (!d || (!d.tactics && !d.recruitment && !d.budget)) return null;
  const { tactics: tc, recruitment: rc, budget: bg } = d;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3><HBar c={accent} />팀 정체성 <span style={{ fontSize: 11, fontWeight: 400, opacity: 0.5 }}>· 감독 전술 · 영입 성향 · 예산</span></h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 18, marginTop: 6 }}>

        {/* 감독 전술 (현재 스냅샷 + 장기성향 블렌드) */}
        {tc && (
          <Panel title="감독 전술">
            <div style={{ fontSize: 13, fontWeight: 600 }}>{tc.manager || "?"}
              {tc.formation && <span style={{ opacity: 0.55, fontWeight: 400 }}> · {tc.formation}</span>}</div>
            {/* 재임 기반 블렌드 */}
            <div style={{ margin: "8px 0 6px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, opacity: 0.7, marginBottom: 3 }}>
                <span>{tc.tenure.is_new ? "새 부임" : "안정"}{tc.tenure.appointed ? ` · ${tc.tenure.appointed}` : ""}</span>
                <span>현재 {Math.round(tc.tenure.w_current * 100)}% / 성향 {Math.round(tc.tenure.w_tendency * 100)}%</span>
              </div>
              <div style={{ display: "flex", height: 5, borderRadius: 3, overflow: "hidden" }}>
                <span style={{ width: `${tc.tenure.w_current * 100}%`, background: accent }} />
                <span style={{ width: `${tc.tenure.w_tendency * 100}%`, background: hexA(accent, 0.28) }} />
              </div>
            </div>
            {/* 현재 스냅샷 태그 */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 5 }}>
              <span style={{ fontSize: 10, opacity: 0.5, alignSelf: "center" }}>현재</span>
              {tc.current_tags.map((t, i) => <Chip key={i} text={TAG_KO[t] || t} accent={accent} />)}
            </div>
            {/* 감독 장기성향 태그 */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
              <span style={{ fontSize: 10, opacity: 0.5, alignSelf: "center" }}>성향</span>
              {tc.tendency_tags.length > 0
                ? tc.tendency_tags.map((t, i) => <Chip key={i} text={TAG_KO[t] || t} accent={accent} outline />)
                : <span style={{ fontSize: 10.5, opacity: 0.4 }}>데이터 없음</span>}
            </div>
            {Object.entries(tc.vector).slice(0, 4).map(([k, v]) => (
              <Bar key={k} label={AXIS_KO[k] || k} value={v} accent={accent} />
            ))}
          </Panel>
        )}

        {/* 영입 성향 */}
        {rc && (
          <Panel title="영입 성향">
            <div style={{ fontSize: 14, fontWeight: 700, color: accent }}>
              {AGE_KO[rc.age_profile] || rc.age_profile}
              <span style={{ opacity: 0.55, fontWeight: 400, color: "inherit" }}> · {SPEND_KO[rc.spend_profile] || rc.spend_profile}</span>
            </div>
            <div style={{ fontSize: 11, opacity: 0.65, margin: "3px 0 10px" }}>최근 창 {rc.n_signings}건 영입 기준</div>
            {/* 나이 분포 바 */}
            {(rc.u23_ratio != null) && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", fontSize: 0 }}>
                  <span title="U23" style={{ width: `${(rc.u23_ratio || 0) * 100}%`, background: accent }} />
                  <span title="24-29" style={{ width: `${(rc.prime_ratio || 0) * 100}%`, background: hexA(accent, 0.4) }} />
                  <span title="30+" style={{ width: `${(rc.veteran_ratio || 0) * 100}%`, background: hexA("#ffffff", 0.15) }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, opacity: 0.55, marginTop: 3 }}>
                  <span>U23 {Math.round((rc.u23_ratio || 0) * 100)}%</span>
                  <span>전성기 {Math.round((rc.prime_ratio || 0) * 100)}%</span>
                  <span>베테랑 {Math.round((rc.veteran_ratio || 0) * 100)}%</span>
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: 16 }}>
              <div><div style={{ fontSize: 17, fontWeight: 700 }}>{rc.avg_age ?? "-"}</div><div style={{ fontSize: 10, opacity: 0.55 }}>평균 영입나이</div></div>
              <div><div style={{ fontSize: 17, fontWeight: 700 }}>{rc.avg_fee_eur ? fmtEur(rc.avg_fee_eur) : "-"}</div><div style={{ fontSize: 10, opacity: 0.55 }}>평균 이적료</div></div>
            </div>
          </Panel>
        )}

        {/* 예산 (프록시) */}
        {bg && (
          <Panel title="예산 (추정)">
            <span style={{ display: "inline-block", fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 8,
              background: hexA(accent, 0.18), color: accent }}>{TIER_KO[bg.spend_tier] || bg.spend_tier} tier</span>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 12px", margin: "12px 0 8px" }}>
              <div><div style={{ fontSize: 15, fontWeight: 700 }}>{fmtEur(bg.squad_value_eur)}</div><div style={{ fontSize: 10, opacity: 0.55 }}>스쿼드 가치</div></div>
              <div><div style={{ fontSize: 15, fontWeight: 700, color: bg.net_spend_eur > 0 ? "#e0857a" : "#4fc27f" }}>
                {bg.net_spend_eur > 0 ? "+" : ""}{fmtEur(Math.abs(bg.net_spend_eur))}</div><div style={{ fontSize: 10, opacity: 0.55 }}>순지출</div></div>
              <div><div style={{ fontSize: 15, fontWeight: 700 }}>{fmtEur(bg.max_fee_paid_eur)}</div><div style={{ fontSize: 10, opacity: 0.55 }}>최고 이적료</div></div>
              <div><div style={{ fontSize: 15, fontWeight: 700, color: accent }}>{fmtEur(bg.price_ceiling_eur)}</div><div style={{ fontSize: 10, opacity: 0.55 }}>가격 상한(추정)</div></div>
            </div>
            <div style={{ fontSize: 9.5, opacity: 0.4 }}>ℹ️ 시장가치+드러난 지출 기반 추정 · 실제 예산·급여 아님</div>
          </Panel>
        )}
      </div>
    </div>
  );
}
