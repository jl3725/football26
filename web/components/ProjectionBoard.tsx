"use client";
import { useEffect, useState } from "react";
import { getProjection, type Projection } from "@/lib/api";
import { hexA } from "@/lib/ui";
import Pitch from "./Pitch";

export default function ProjectionBoard({ team, accent }: { team: string; accent: string }) {
  const [pj, setPj] = useState<Projection | null>(null);
  const [view, setView] = useState<"cur" | "next">("next");
  useEffect(() => { let a = true; setPj(null); getProjection(team).then((d) => a && setPj(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!pj) return null;

  const board = view === "cur" ? pj.current : pj.projected;
  const losses = pj.diagnosis.filter((d) => d.kind === "loss");
  const gains = pj.diagnosis.filter((d) => d.kind === "gain");
  const hasChange = losses.length > 0 || gains.length > 0;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>🔮 시즌별 예상 XI · 이적 반영 진단</h3>
      <div className="proj-toggle">
        <button className={view === "cur" ? "active" : ""} onClick={() => setView("cur")}
          style={view === "cur" ? { background: accent, color: "#0b0f17" } : undefined}>{pj.current_label} 현재</button>
        <button className={view === "next" ? "active" : ""} onClick={() => setView("next")}
          style={view === "next" ? { background: accent, color: "#0b0f17" } : undefined}>{pj.next_label} 예상</button>
      </div>

      <div className="proj-grid">
        <div>
          <div className="pitch-title">{view === "cur" ? pj.current_label : pj.next_label} <span>· {board.formation}</span></div>
          <Pitch placements={board.placements} accent={accent} idKey={"proj" + view} />
        </div>
        <div className="diag-panel">
          {!hasChange && <div className="mgr-meta">이번 이적창 반영 변화 없음 — 스쿼드 유지</div>}
          {losses.length > 0 && (
            <>
              <div className="diag-h" style={{ color: "#e07070" }}>▼ 이탈 · 대체 필요</div>
              {losses.map((d, i) => (
                <div className="diag-row loss" key={i}>
                  {d.photo ? <img src={d.photo} alt="" /> : <span className="diag-ph" />}
                  <div className="diag-body">
                    <div className="diag-top"><b>{d.player}</b><span className="diag-tag">{d.severity} · {d.slot}</span></div>
                    <div className="diag-note">→ {d.to || "이적"} · {d.note}</div>
                  </div>
                </div>
              ))}
            </>
          )}
          {gains.length > 0 && (
            <>
              <div className="diag-h" style={{ color: "#4fc27f", marginTop: losses.length ? 12 : 0 }}>▲ 영입 · 보강</div>
              {gains.map((d, i) => (
                <div className="diag-row gain" key={i}>
                  {d.photo ? <img src={d.photo} alt="" /> : <span className="diag-ph" />}
                  <div className="diag-body">
                    <div className="diag-top"><b>{d.player}</b><span className="diag-tag">{d.slot} · {d.fee || ""}</span></div>
                    <div className="diag-note">{d.note}</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
