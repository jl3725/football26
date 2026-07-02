"use client";
import { useEffect, useState } from "react";
import { getSquad, fmtEur, type Squad, type SquadPlayer } from "@/lib/api";
import { tier } from "@/lib/ui";

const LINES: { key: string; label: string }[] = [
  { key: "GK", label: "골키퍼" }, { key: "DEF", label: "수비" },
  { key: "MID", label: "미드필드" }, { key: "ATT", label: "공격" },
];
const POS_LABEL: Record<string, string> = {
  GK: "골키퍼", CB: "센터백", RB: "라이트백", LB: "레프트백", DM: "수비형MF",
  CM: "중앙MF", AM: "공격형MF", RW: "우측WG", LW: "좌측WG", W: "윙어", ST: "스트라이커",
};

function Row({ p }: { p: SquadPlayer }) {
  const t = tier(p.ovr);
  return (
    <div className="sq-row">
      <span className="sq-ovr" style={{ color: t.light, borderColor: t.deep }}>{p.ovr}</span>
      {p.photo ? <img className="sq-photo" src={p.photo} alt="" /> : <span className="sq-photo ph" />}
      <div className="sq-info">
        <div className="sq-name">{p.player}</div>
        <div className="sq-meta">{p.pos} · {p.age}세 · {p.minutes.toLocaleString()}′</div>
      </div>
      <span className="sq-val">{fmtEur(p.value_eur)}</span>
    </div>
  );
}

export default function SquadTab({ team }: { team: string; accent: string }) {
  const [data, setData] = useState<Squad | null>(null);
  useEffect(() => { let a = true; getSquad(team).then((d) => a && setData(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;

  return (
    <div className="fade">
      {/* 포지션별 뎁스 차트 */}
      <div className="card">
        <h3>포지션별 뎁스 차트</h3>
        <div className="depth-head">
          <span>POS</span><span>주전</span><span>로테이션 / 백업</span><span>뎁스</span>
        </div>
        {data.buckets.map((b) => {
          const dc = b.depth >= 70 ? "#4fc27f" : b.depth >= 55 ? "#caa64e" : "#e07070";
          const st = tier(b.starter.ovr);
          return (
            <div className="depth-row" key={b.pos}>
              <span className="depth-pos">{POS_LABEL[b.pos] || b.pos}</span>
              <span className="depth-starter">
                <b style={{ color: st.light }}>{b.starter.ovr}</b> {b.starter.player.split(" ").slice(-1)[0]}
              </span>
              <span className="depth-rot">
                {b.rotation.length === 0 ? <em>백업 없음</em> :
                  b.rotation.map((r, i) => <span key={i} className="depth-rp"><b style={{ color: tier(r.ovr).light }}>{r.ovr}</b> {r.player.split(" ").slice(-1)[0]}</span>)}
              </span>
              <span className="depth-score">
                <div className="depth-bar"><span style={{ width: `${b.depth}%`, background: dc }} /></div>
                <b style={{ color: dc }}>{b.depth}</b>
              </span>
            </div>
          );
        })}
      </div>

      {/* 라인별 스쿼드 */}
      <div className="squad-grid" style={{ marginTop: 16 }}>
        {LINES.map((ln) => {
          const players = data.lines[ln.key] || [];
          return (
            <div className="card" key={ln.key}>
              <h3>{ln.label} · {players.length}</h3>
              <div className="sq-list">
                {players.map((p, i) => <Row key={i} p={p} />)}
                {players.length === 0 && <div className="mgr-meta">선수 없음</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
