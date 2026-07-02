"use client";
import { useEffect, useState } from "react";
import { getTransfers, getRecommend, getNeeds, fmtEur, type Transfers, type TransferItem, type Recommend, type Needs } from "@/lib/api";
import { tier } from "@/lib/ui";

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
  return (
    <div className="fade">
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

      {/* 후보 평가 */}
      {rec && rec.recommendations.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>🎯 후보 평가 · {rec.weakest?.label} 라인
            {rec.addressed && <span className="rec-addr">· 이번 창 보강됨, 추가 옵션</span>}</h3>
          <div className="rec-grid">
            {rec.recommendations.map((r, i) => {
              const t = tier(r.ovr);
              const cf = r.confidence === "high" ? "#4fc27f" : r.confidence === "med" ? "#f4cf5e" : "#e0556b";
              const cfl = r.confidence === "high" ? "신뢰 높음" : r.confidence === "med" ? "신뢰 중간" : "표본 적음";
              return (
                <div className="rec-card" key={i}>
                  {r.photo ? <img className="rec-photo" src={r.photo} alt="" /> : <span className="rec-photo ph" />}
                  <div className="rec-ovr" style={{ color: t.light }}>{r.ovr}</div>
                  <div className="rec-name">{r.player}</div>
                  <div className="rec-club">{r.logo && <img src={r.logo} alt="" />}{r.squad}</div>
                  <div className="rec-meta">{r.pos} · {r.age}세 · {fmtEur(r.value_eur)}</div>
                  <div className="rec-why">
                    {r.why_fit.map((w, k) => <span className="why fit" key={"f" + k}>✓ {w}</span>)}
                    {r.why_risk.map((w, k) => <span className="why risk" key={"r" + k}>△ {w}</span>)}
                  </div>
                  <div className="rec-conf" style={{ color: cf }}>◆ 데이터 {cfl}</div>
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
              <div className="tf2-row" key={i}>
                {l.photo ? <img className="tf2-photo" src={l.photo} alt="" /> : <span className="tf2-photo ph" />}
                <div className="tf2-info">
                  <div className="tf2-name">{l.player} <span className="lt-ovr">OVR {l.ovr}</span></div>
                  <div className="tf2-meta">{l.pos} · {l.from} → <b style={{ color: "#e07070" }}>{l.to}</b></div>
                </div>
                <span className="tf2-fee" style={{ color: "#e07070" }}>이적 완료</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
