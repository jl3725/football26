"use client";
import { useEffect, useState } from "react";
import { getTransfers, getRecommend, getNeeds, fmtEur, type Transfers, type TransferItem, type Recommend, type Needs } from "@/lib/api";
import { tier, roleClass, hexA } from "@/lib/ui";
import FitEvaluator from "./FitEvaluator";
import ManagerSimPanel from "./ManagerSimPanel";
import RecruitPool from "./RecruitPool";
import Bar from "./Bar";

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
  const [view, setView] = useState<"scout" | "fit" | "sim">("scout");
  useEffect(() => {
    let a = true; setData(null); setRec(null); setNeeds(null);
    getTransfers(team).then((d) => a && setData(d)).catch(() => {});
    getRecommend(team).then((d) => a && setRec(d)).catch(() => {});
    getNeeds(team).then((d) => a && setNeeds(d)).catch(() => {});
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
      <div style={{ display: "inline-flex", gap: 2, marginBottom: 16, padding: 3, borderRadius: 10,
        background: hexA("#ffffff", 0.05), border: `1px solid ${hexA(accent, 0.15)}` }}>
        {([["scout", "스카우트 데스크"], ["fit", "적합도 평가"], ["sim", "감독 시뮬레이션"]] as const).map(([v, label]) => (
          <button key={v} onClick={() => setView(v)}
            style={{ padding: "7px 16px", borderRadius: 7, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
              border: "none", letterSpacing: 0.2, transition: "all .15s",
              background: view === v ? accent : "transparent",
              color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{label}</button>
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
            <span className="scout-tag" style={{ color: accent }}>SCOUT DESK</span>
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

      {/* 포지션별 보강 후보 — 벡터 스타일-핏 + 필터/KPI/정렬 (RecruitPool) */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3><Bar c={accent} />스카우팅 풀 <span className="rating-note">· 벡터 스타일-핏 · 전 리그 · KG 신호 · 필터/정렬</span></h3>
        <RecruitPool team={team} accent={accent} />
      </div>

      {/* 드림 타깃 — 최상위급이나 티어·라이벌상 비현실 */}
      {rec && rec.longshots && rec.longshots.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3><Bar c={accent} />드림 타깃 <span className="rating-note">· 포지션 최상위급이나 티어·라이벌상 영입 가능성 낮음</span></h3>
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
          <h3><Bar c={accent} />놓친 타깃 <span className="rating-note">· {rec.weakest?.label} 라인에서 타팀으로 이적</span></h3>
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
