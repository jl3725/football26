"use client";
import { useEffect, useState } from "react";
import { getTransfers, getRecommend, fmtEur, type Transfers, type TransferItem, type Recommend } from "@/lib/api";
import { tier } from "@/lib/ui";

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
  useEffect(() => {
    let a = true; setData(null); setRec(null);
    getTransfers(team).then((d) => a && setData(d)).catch(() => {});
    getRecommend(team).then((d) => a && setRec(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;
  const s = data.summary;
  const net = s.net;

  const win = data.window;
  return (
    <div className="fade">
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

      {/* AI 영입 추천 */}
      {rec && rec.recommendations.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>🎯 AI 영입 추천 {rec.weakest && <span style={{ color: accent }}>· 약점: {rec.weakest.label}</span>}</h3>
          <div className="rec-grid">
            {rec.recommendations.map((r, i) => {
              const t = tier(r.ovr);
              const fitC = r.tactical_fit >= 70 ? "#4fc27f" : r.tactical_fit >= 50 ? "#caa64e" : "#e07070";
              const matchC = r.squad_match >= 70 ? "#4fc27f" : r.squad_match >= 50 ? "#caa64e" : "#e07070";
              return (
                <div className="rec-card" key={i}>
                  {r.photo ? <img className="rec-photo" src={r.photo} alt="" /> : <span className="rec-photo ph" />}
                  <div className="rec-ovr" style={{ color: t.light }}>{r.ovr}</div>
                  <div className="rec-name">{r.player}</div>
                  <div className="rec-club">{r.logo && <img src={r.logo} alt="" />}{r.squad}</div>
                  <div className="rec-meta">{r.pos} · {r.age}세 · {fmtEur(r.value_eur)}</div>
                  <div className="rec-fit">
                    <div className="rec-fit-row"><span>{rec.weakest?.fit_label || "적합"}</span><div className="rec-fit-bar"><span style={{ width: `${r.tactical_fit}%`, background: fitC }} /></div><b style={{ color: fitC }}>{r.tactical_fit}</b></div>
                    <div className="rec-fit-row"><span>스쿼드매치</span><div className="rec-fit-bar"><span style={{ width: `${r.squad_match}%`, background: matchC }} /></div><b style={{ color: matchC }}>{r.squad_match}</b></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
