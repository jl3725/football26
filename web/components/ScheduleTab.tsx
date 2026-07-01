"use client";
import { useEffect, useState } from "react";
import { getSchedule, getMatch, type Schedule, type MatchDetail, type Match } from "@/lib/api";
import Pitch from "./Pitch";

function MatchDetailView({ team, match, accent }: { team: string; match: Match; accent: string }) {
  const [d, setD] = useState<MatchDetail | null>(null);
  useEffect(() => {
    let a = true; setD(null);
    if (match.event_id) getMatch(team, match.event_id).then((x) => a && setD(x)).catch(() => {});
    return () => { a = false; };
  }, [team, match.event_id]);

  const resColor = match.result === "W" ? "#1f8a4c" : match.result === "L" ? "#a5202f" : "#5a6270";
  return (
    <div className="card sc-detail">
      <div className="scd-head" style={{ background: `linear-gradient(120deg, ${accent}33, transparent)` }}>
        <div>
          <div className="scd-gw">GW{match.gw} · {match.date} · {match.home_away === "H" ? "홈" : "원정"}</div>
          <div className="scd-opp">vs {match.opponent}</div>
        </div>
        <div className="scd-score" style={{ color: resColor }}>{match.score || "—"}
          <span>{match.result === "W" ? "승" : match.result === "L" ? "패" : match.result === "D" ? "무" : ""}</span>
        </div>
        {match.formation && <div className="scd-form">{match.formation}</div>}
      </div>
      {!match.event_id ? (
        <div className="mgr-meta" style={{ padding: 20 }}>이 경기의 라인업 데이터가 없습니다.</div>
      ) : !d ? (
        <div className="loading" style={{ padding: 30 }}>불러오는 중…</div>
      ) : (
        <div className="scd-body">
          <Pitch placements={d.placements} formation={d.formation} accent={accent} idKey={`m${match.event_id}`} />
          <div className="scd-side">
            {d.subs.length > 0 ? (
              <>
                <div className="scd-sub-title">교체 · {d.subs.length}</div>
                {d.subs.map((s, i) => (
                  <div className="scd-sub" key={i}>
                    <span className="scd-min">{s.minute}</span>
                    <span className="scd-in">▲ {s.player_in}</span>
                    <span className="scd-out">▼ {s.player_out}</span>
                  </div>
                ))}
              </>
            ) : (
              <>
                <div className="scd-sub-title">벤치 · {d.bench.length}</div>
                {d.bench.map((b, i) => <div className="scd-bench" key={i}>{b}</div>)}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ScheduleTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Schedule | null>(null);
  const [sel, setSel] = useState<number>(-1);
  useEffect(() => {
    let a = true; setData(null); setSel(-1);
    getSchedule(team).then((d) => {
      if (!a) return;
      setData(d);
      const played = d.matches.map((m, i) => ({ m, i })).filter((x) => x.m.event_id);
      setSel(played.length ? played[played.length - 1].i : (d.matches.length - 1));
    }).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;

  const played = data.matches.filter((m) => m.result);
  const w = played.filter((m) => m.result === "W").length;
  const dd = played.filter((m) => m.result === "D").length;
  const l = played.filter((m) => m.result === "L").length;
  const ppg = played.length ? ((w * 3 + dd) / played.length).toFixed(2) : "-";

  return (
    <div className="fade">
      <div className="stat-strip" style={{ marginTop: 0, gridTemplateColumns: "repeat(5,1fr)" }}>
        <div className="stat"><div className="v">{played.length}</div><div className="l">Played</div></div>
        <div className="stat"><div className="v" style={{ color: "#4fc27f" }}>{w}</div><div className="l">Won</div></div>
        <div className="stat"><div className="v" style={{ color: "#9aa4b4" }}>{dd}</div><div className="l">Drawn</div></div>
        <div className="stat"><div className="v" style={{ color: "#e07070" }}>{l}</div><div className="l">Lost</div></div>
        <div className="stat"><div className="v" style={{ color: accent }}>{ppg}</div><div className="l">PPG</div></div>
      </div>

      <div className="sched-layout">
        <div className="card sched-list-card">
          <h3>{data.matches.length} Matches</h3>
          <div className="sched-list">
            {data.matches.map((m, i) => (
              <button className={`sched-row${sel === i ? " active" : ""}`} key={i} onClick={() => setSel(i)}
                style={sel === i ? { background: `${accent}22` } : undefined}>
                <span className="sc-gw">GW{m.gw}</span>
                <span className={`sc-ha ${m.home_away === "H" ? "h" : "a"}`}>{m.home_away}</span>
                {m.opp_logo ? <img className="sc-logo" src={m.opp_logo} alt="" /> : <span className="sc-logo" />}
                <span className="sc-opp">{m.opponent}</span>
                <span className="sc-score">{m.score || "—"}</span>
                {m.result
                  ? <span className={`sc-res ${m.result}`}>{m.result}</span>
                  : <span className="sc-res upcoming">·</span>}
              </button>
            ))}
          </div>
        </div>
        {sel >= 0 && data.matches[sel] && <MatchDetailView team={team} match={data.matches[sel]} accent={accent} />}
      </div>
    </div>
  );
}
