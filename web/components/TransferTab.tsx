"use client";
import { useEffect, useState } from "react";
import { getTransfers, getRecommend, getNeeds, getDiscover, fmtEur, type Transfers, type TransferItem, type Recommend, type Needs, type Discover } from "@/lib/api";
import { tier, roleClass, hexA } from "@/lib/ui";
import FitEvaluator from "./FitEvaluator";
import ManagerSimPanel from "./ManagerSimPanel";

const MODE: Record<string, { t: string; d: string }> = {
  evaluate: { t: "영입 평가 모드", d: "이번 창 영입이 각 니즈를 얼마나 해소했는지 점검" },
  gap: { t: "공백 분석 모드", d: "방출로 생긴 공백·대체 필요 포지션 점검" },
  recruit: { t: "보강 후보 모드", d: "이번 창 영입 없음 · 니즈 기반 보강 방향" },
};

function Row({ x, dir }: { x: TransferItem; dir: "in" | "out" }) {
  return (
    <div className={`tf2-row ${dir}`}>
      {x.photo ? <img className="tf2-photo" src={x.photo} alt="" /> : <span className="tf2-photo ph" />}
      <div className="tf2-info">
        <div className="tf2-name">{x.player}</div>
        <div className="tf2-meta">{x.pos || "-"} · {x.age || "?"}세 · {dir === "in" ? "from" : "to"} {x.club || "-"}</div>
      </div>
      <span className="tf2-fee">{x.fee_text || fmtEur(x.fee_eur)}</span>
    </div>
  );
}

export default function TransferTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Transfers | null>(null);
  const [rec, setRec] = useState<Recommend | null>(null);
  const [needs, setNeeds] = useState<Needs | null>(null);
  const [disc, setDisc] = useState<Discover | null>(null);
  const [view, setView] = useState<"scout" | "fit" | "sim">("scout");
  useEffect(() => {
    let a = true; setData(null); setRec(null); setNeeds(null); setDisc(null);
    getTransfers(team).then((d) => a && setData(d)).catch(() => {});
    getRecommend(team).then((d) => a && setRec(d)).catch(() => {});
    getNeeds(team).then((d) => a && setNeeds(d)).catch(() => {});
    getDiscover(team).then((d) => a && setDisc(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;
  const s = data.summary;
  const net = s.net;

  const win = data.window;
  const mode = needs ? (MODE[needs.mode] || MODE.recruit) : null;
  const POSD: Record<string, string> = {
    CB: "Centre-Back", RB: "Right-Back", LB: "Left-Back", RWB: "Right-Back", LWB: "Left-Back",
    DM: "Defensive Midfield", CM: "Central Midfield", AM: "Attacking Midfield", RM: "Right Midfield",
    LM: "Left Midfield", RW: "Right Winger", LW: "Left Winger", CF: "Centre-Forward", SS: "Second Striker", GK: "Goalkeeper",
  };
  const suggestions = (rec?.recommendations || []).map((r) => ({
    player: r.player, role: POSD[(r.pos || "").split(/[ ,/]/)[0]] || "",
  }));
  return (
    <div className="fade">
      {/* 서브탭 토글 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {([["scout", "🧭 스카우트 데스크"], ["fit", "🎯 Fit 평가"], ["sim", "🔄 감독 시뮬"]] as const).map(([v, label]) => (
          <button key={v} onClick={() => setView(v)}
            style={{ padding: "7px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer",
              border: `1px solid ${view === v ? accent : hexA(accent, 0.25)}`,
              background: view === v ? hexA(accent, 0.18) : "transparent",
              color: view === v ? accent : "inherit", opacity: view === v ? 1 : 0.7 }}>{label}</button>
        ))}
      </div>

      {view === "fit" ? (
        <FitEvaluator team={team} accent={accent} suggestions={suggestions} />
      ) : view === "sim" ? (
        <ManagerSimPanel team={team} accent={accent} />
      ) : (<>
      {/* ── SCOUT DESK ── */}
      {needs && (
        <div className="scout-desk">
          <div className="scout-hd">
            <span className="scout-tag" style={{ color: accent }}>🧭 SCOUT DESK</span>
            <b>{mode?.t}</b>
            <span className="scout-d">{mode?.d}</span>
            <span className="scout-cnt">영입 {needs.window.signings.length} · 방출 {needs.window.departures.length}</span>
          </div>
          {needs.needs.length > 0 ? (
            <div className="need-grid">
              {needs.needs.map((n, i) => (
                <div className={`need-card st-${n.status}`} key={i}>
                  <div className="need-top">
                    <span className="need-line">{n.line_label}</span>
                    <span className="need-title">{n.title}</span>
                    <span className={`need-sev ${n.severity}`}>{n.severity === "high" ? "높음" : n.severity === "med" ? "중간" : "낮음"}</span>
                  </div>
                  <div className="need-reason">{n.reason}</div>
                  {n.status === "addressed" && <div className="need-status ok">✅ {n.player} 영입으로 보강</div>}
                  {n.status === "worsened" && <div className="need-status bad">⚠ {n.player} 방출로 공백</div>}
                </div>
              ))}
            </div>
          ) : <div className="mgr-meta">감지된 주요 니즈 없음 ✓</div>}
        </div>
      )}

      <div className="season-note" style={{ marginTop: 0, marginBottom: 14 }}>
        {win?.is_open
          ? <><b style={{ color: accent }}>{win.label} {win.kr} 이적시장 OPEN</b>{!data.window_has_data && " · 이번 창 이적 없음 (전체 표시)"}</>
          : <><b>{data.data_season} 시즌</b> · 현재 이적시장 마감</>}
      </div>
      <div className="stat-strip" style={{ marginTop: 0 }}>
        <div className="stat"><div className="v" style={{ color: "#e07070" }}>{fmtEur(s.spend)}</div><div className="l">지출</div></div>
        <div className="stat"><div className="v" style={{ color: "#4fc27f" }}>{fmtEur(s.income)}</div><div className="l">수입</div></div>
        <div className="stat"><div className="v" style={{ color: net > 0 ? "#e07070" : "#4fc27f" }}>{net > 0 ? "-" : "+"}{fmtEur(Math.abs(net))}</div><div className="l">순수지</div></div>
        <div className="stat"><div className="v" style={{ color: accent }}>{s.in_count}/{s.out_count}</div><div className="l">IN / OUT</div></div>
      </div>

      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 style={{ color: "#4fc27f" }}>▲ 영입 · IN ({data.in.length})</h3>
          <div className="tf2-list">
            {data.in.map((x, i) => <Row key={i} x={x} dir="in" />)}
            {data.in.length === 0 && <div className="mgr-meta">영입 없음</div>}
          </div>
        </div>
        <div className="card">
          <h3 style={{ color: "#e07070" }}>▼ 방출 · OUT ({data.out.length})</h3>
          <div className="tf2-list">
            {data.out.map((x, i) => <Row key={i} x={x} dir="out" />)}
            {data.out.length === 0 && <div className="mgr-meta">방출 없음</div>}
          </div>
        </div>
      </div>

      {/* 포지션별 보강 후보 — 벡터(Qdrant) 스타일-핏 · 전 리그 · KG 신호 */}
      {disc && !disc.available && (
        <div className="nodata-card" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 28 }}>🔌</div><b>벡터 추천 비활성</b>
          <div className="mgr-meta" style={{ marginTop: 6 }}>{disc.reason || "Qdrant 스택 필요 (로컬/호스팅)"}</div>
        </div>
      )}
      {disc && disc.available && disc.recommendations.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>🎯 포지션별 보강 후보 <span className="rating-note">· 벡터 스타일-핏 · 전 리그 · KG 신호</span></h3>
          {(() => {
            const order: string[] = [];
            const byPos: Record<string, typeof disc.recommendations> = {};
            for (const r of disc.recommendations) {
              const key = r.pos || "기타";
              if (!byPos[key]) { byPos[key] = []; order.push(key); }
              byPos[key].push(r);
            }
            return order.map((pos) => (
              <div className="rec-pos-group" key={pos}>
                <div className="rec-pos-h" style={{ borderColor: accent }}>
                  <span style={{ color: accent }}>◎</span> {pos}
                  <span className="rec-pos-n">{byPos[pos].length}명</span>
                </div>
                <div className="rec-grid">
                  {byPos[pos].map((r, i) => {
                    const t = tier(r.ovr);
                    return (
                      <div className="rec-card" key={i}>
                        {r.photo ? <img className="rec-photo" src={r.photo} alt="" /> : <span className="rec-photo ph" />}
                        <div className="rec-ovr" style={{ color: t.light }}>{r.ovr}</div>
                        <div className="rec-name">{r.player}{r.kg_rumored && <span title="이미 이 클럽과 루머로 연결(KG)"> 🔗</span>}</div>
                        <div className="rec-club">{r.squad}</div>
                        <div style={{ margin: "5px 0" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, opacity: 0.7, marginBottom: 2 }}>
                            <span>스타일 적합</span><span style={{ color: accent }}>{r.style_fit}</span></div>
                          <div style={{ height: 4, borderRadius: 3, background: hexA("#ffffff", 0.08) }}>
                            <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${r.style_fit}%`, background: accent }} /></div>
                        </div>
                        {r.cross_league && <div className="rec-cross">↗ {r.source_league} · 현재 {r.current_ovr} → 예상 {r.projected_ovr}</div>}
                        <div className="rec-meta">{r.age ? r.age + "세 · " : ""}{fmtEur(r.value_eur || 0)}{r.euro ? " · ⚡유럽" : ""}</div>
                        <div className="rec-why">
                          {r.why_fit.map((w, k) => <span className="why fit" key={"f" + k}>✓ {w}</span>)}
                        </div>
                        {r.kg_precedent ? <div className="rec-conf" style={{ color: accent }}>◆ 선례 {r.kg_precedent}건 (KG)</div> : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ));
          })()}
        </div>
      )}

      {/* 드림 타깃 — 최상위급이나 티어·라이벌상 비현실 */}
      {rec && rec.longshots && rec.longshots.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>🌟 드림 타깃 <span className="rating-note">· 포지션 최상위급이나 티어·라이벌상 영입 가능성 낮음</span></h3>
          <div className="rec-grid">
            {rec.longshots.map((l, i) => {
              const t = tier(l.ovr);
              return (
                <div className="rec-card longshot" key={i}>
                  {l.photo ? <img className="rec-photo" src={l.photo} alt="" /> : <span className="rec-photo ph" />}
                  <div className="rec-ovr" style={{ color: t.light }}>{l.ovr}</div>
                  <div className="rec-name">{l.player}</div>
                  <div className="rec-club">{l.logo && <img src={l.logo} alt="" />}{l.squad}</div>
                  {l.cross_league && <div className="rec-cross">↗ {l.source_league} · 현재 {l.current_ovr}</div>}
                  {l.bucket_label && <div className="rec-target" style={{ color: accent }}>◎ {l.bucket_label}</div>}
                  {l.role && <div className="rec-role"><span className={"role-tag " + roleClass(l.role)}>{l.role}</span></div>}
                  <div className="rec-why"><span className="why risk">✕ {l.reason}</span></div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Lost Target Review */}
      {rec && rec.lost_targets && rec.lost_targets.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>🕵 놓친 타깃 · Lost Targets <span className="rating-note">· {rec.weakest?.label} 라인에서 타팀으로 이적</span></h3>
          <div className="tf2-list">
            {rec.lost_targets.map((l, i) => (
              <div className={`tf2-row${l.top_loss ? " top-loss" : ""}`} key={i}>
                {l.photo ? <img className="tf2-photo" src={l.photo} alt="" /> : <span className="tf2-photo ph" />}
                <div className="tf2-info">
                  <div className="tf2-name">{l.top_loss && <span title="가장 아까운 이탈">⭐ </span>}{l.player} <span className="lt-ovr">OVR {l.ovr}</span>
                    {l.role && <span className={"role-tag sm " + roleClass(l.role)}>{l.role}</span>}</div>
                  <div className="tf2-meta">{l.pos} · {l.from} → <b style={{ color: "#e07070" }}>{l.to}</b></div>
                </div>
                <span className="tf2-fee" style={{ color: "#e07070" }}>{l.top_loss ? "최대 손실" : "이적 완료"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
