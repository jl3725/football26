"use client";
import { useEffect, useState } from "react";
import { getLineup, getProjection, type Lineup, type Projection } from "@/lib/api";
import Pitch from "./Pitch";

type Departed = { player: string; left_for: string; pos: string; photo: string };

export default function LineupBoard({ team, accent, departed = [] }: { team: string; accent: string; departed?: Departed[] }) {
  const [lu, setLu] = useState<Lineup | null>(null);
  const [pj, setPj] = useState<Projection | null>(null);
  const [leftView, setLeftView] = useState<"cur" | "next">("next");

  useEffect(() => {
    let a = true; setLu(null); setPj(null); setLeftView("next");
    getLineup(team).then((d) => a && setLu(d)).catch(() => {});
    getProjection(team).then((d) => a && setPj(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);

  const curLabel = pj?.current_label ?? "25/26";
  const nextLabel = pj?.next_label ?? "26/27";
  const leftBoard = leftView === "cur" ? lu?.season : pj?.projected;
  const leftFormation = leftView === "cur" ? lu?.season.formation : pj?.projected.formation;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>포메이션 & 전술 구조</h3>
      <div className="pitch-grid">
        {/* LEFT — 시즌 베스트 XI + 시즌 토글 */}
        <div>
          <div className="proj-toggle" style={{ marginBottom: 10 }}>
            <button className={leftView === "next" ? "active" : ""} onClick={() => setLeftView("next")}
              style={leftView === "next" ? { background: accent, color: "#0b0f17" } : undefined}>🔮 {nextLabel} 예상</button>
            <button className={leftView === "cur" ? "active" : ""} onClick={() => setLeftView("cur")}
              style={leftView === "cur" ? { background: accent, color: "#0b0f17" } : undefined}>{curLabel} BEST XI</button>
          </div>
          {leftBoard
            ? <Pitch placements={leftBoard.placements} accent={accent} />
            : <div className="loading" style={{ padding: 30 }}>불러오는 중…</div>}
          <div className="pitch-cap"><span>{leftFormation || ""}</span></div>
        </div>

        {/* RIGHT — 최근 5경기 XI */}
        <div>
          <div className="proj-toggle" style={{ marginBottom: 10, visibility: "hidden" }}>
            <button>_</button>
          </div>
          {lu?.recent
            ? <Pitch placements={lu.recent.placements} accent={accent} />
            : <div className="loading" style={{ padding: 30 }}>{lu ? "최근 경기 데이터 부족" : "불러오는 중…"}</div>}
          <div className="pitch-cap">🔥 최근 5경기 <span>{lu?.recent?.formation || ""}</span></div>
        </div>
      </div>

      {/* 26/27 예상 효과 — 이탈/보강 진단 */}
      {leftView === "next" && pj && pj.diagnosis.length > 0 && (
        <div className="effect-box">
          <div className="effect-title" style={{ color: accent }}>🔮 {nextLabel} 이적 반영 효과</div>
          <div className="effect-grid">
            {pj.diagnosis.map((d, i) => (
              <div className={`effect-row ${d.kind}`} key={i}>
                {d.photo ? <img src={d.photo} alt="" /> : <span className="effect-ph" />}
                <div className="effect-body">
                  <div className="effect-top">
                    <span className="effect-ar">{d.kind === "loss" ? "▼" : "▲"}</span>
                    <b>{d.player}</b><span className="effect-tag">{d.slot}</span>
                  </div>
                  <div className="effect-note">{d.kind === "loss" ? `→ ${d.to || "이적"} · ` : ""}{d.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 벤치 + 이적 이탈 */}
      {lu?.bench && lu.bench.length > 0 && (
        <div className="bench-strip">
          <div className="bench-title">벤치 뎁스</div>
          {lu.bench.map((b, i) => (
            <div className="bench-chip" key={i}>
              {b.photo ? <img src={b.photo} alt="" /> : <span className="bench-ph" />}
              <span className="bench-name">{b.player.split(" ").slice(-1)[0]}</span>
              <span className="bench-ovr" style={{ color: accent }}>{b.ovr}</span>
            </div>
          ))}
        </div>
      )}
      {departed.length > 0 && (
        <div className="bench-strip departed">
          <div className="bench-title">↪ 시즌 중 이적</div>
          {departed.map((d, i) => (
            <div className="bench-chip" key={i}>
              {d.photo ? <img src={d.photo} alt="" /> : <span className="bench-ph" />}
              <span className="bench-name">{d.player.split(" ").slice(-1)[0]}</span>
              <span className="bench-to">→ {d.left_for}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
