"use client";
import { useEffect, useMemo, useState } from "react";
import { getSchedule, getMatch, type Schedule, type MatchDetail, type Match } from "@/lib/api";
import Pitch from "./Pitch";
import { usePeek } from "./PlayerPeek";
import { Skel, SkelPitch, SkelRows } from "./Skeleton";

const seasonLabel = (s: string) => (s ? s.slice(2, 4) + "/" + s.slice(7, 9) : "");
// 대회 배지 색
const COMP_STYLE: Record<string, string> = {
  "리그": "#8aa0b8", "챔피언스리그": "#5b8def", "유로파리그": "#e08a3c",
  "컨퍼런스리그": "#4fc27f", "FA컵": "#b98cd8", "EFL컵": "#c98a8a", "코파델레이": "#d8b34e",
};
const compColor = (c: string) => COMP_STYLE[c] || "#8aa0b8";

function MatchDetailView({ team, match, accent }: { team: string; match: Match; accent: string }) {
  const [d, setD] = useState<MatchDetail | null>(null);
  const peek = usePeek();
  useEffect(() => {
    let a = true; setD(null);
    if (match.event_id && match.has_lineup) getMatch(team, match.event_id).then((x) => a && setD(x)).catch(() => {});
    return () => { a = false; };
  }, [team, match.event_id, match.has_lineup]);

  const resColor = match.result === "W" ? "#1f8a4c" : match.result === "L" ? "#a5202f" : "#5a6270";
  return (
    <div className="card sc-detail">
      <div className="scd-head" style={{ background: `linear-gradient(120deg, ${accent}33, transparent)` }}>
        <div>
          <div className="scd-gw">
            <span className="comp-badge" style={{ color: compColor(match.comp), borderColor: compColor(match.comp) + "66" }}>{match.comp}</span>
            {match.date} · {match.home_away === "H" ? "홈" : "원정"}
          </div>
          <div className="scd-opp">vs {match.opponent}</div>
        </div>
        <div className="scd-score" style={{ color: match.status === "completed" ? resColor : "#8a93a3" }}>
          {match.status === "completed" ? (match.score || "—") : "예정"}
          <span>{match.result === "W" ? "승" : match.result === "L" ? "패" : match.result === "D" ? "무" : ""}</span>
        </div>
        {match.formation && <div className="scd-form">{match.formation}</div>}
      </div>
      {match.status !== "completed" ? (
        <div className="mgr-meta" style={{ padding: 20 }}>예정 경기 — 라인업은 경기 후 제공됩니다.</div>
      ) : !match.has_lineup ? (
        <div className="mgr-meta" style={{ padding: 20 }}>이 경기의 라인업 데이터가 아직 없습니다{match.comp !== "리그" ? " (컵·유럽 라인업 수집 예정)" : ""}.</div>
      ) : !d ? (
        <SkelPitch />
      ) : (
        <div className="scd-body">
          <Pitch placements={d.placements} formation={d.formation} accent={accent} idKey={`m${match.event_id}`} team={team} />
          <div className="scd-side">
            {d.subs.length > 0 ? (
              <>
                <div className="scd-sub-title">교체 · {d.subs.length}</div>
                {d.subs.map((s, i) => (
                  <div className="scd-sub" key={i}>
                    <span className="scd-min">{s.minute}</span>
                    <span className="scd-in peekable" onClick={(e) => peek(e, { name: s.player_in, club: team })}>▲ {s.player_in}</span>
                    <span className="scd-out peekable" onClick={(e) => peek(e, { name: s.player_out, club: team })}>▼ {s.player_out}</span>
                  </div>
                ))}
              </>
            ) : (
              <>
                <div className="scd-sub-title">벤치 · {d.bench.length}</div>
                {d.bench.map((b, i) => <div className="scd-bench peekable" key={i} onClick={(e) => peek(e, { name: b, club: team })}>{b}</div>)}
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
  const [season, setSeason] = useState<string>("");
  const [comp, setComp] = useState<string>("전체");
  const [sel, setSel] = useState<number>(-1);

  useEffect(() => {
    let a = true; setData(null); setSel(-1); setComp("전체");
    getSchedule(team, season).then((d) => {
      if (!a) return;
      setData(d);
      // 치러진 마지막 경기 선택, 없으면(예정 시즌) 첫 경기
      const played = d.matches.map((m, i) => ({ m, i })).filter((x) => x.m.status === "completed");
      setSel(played.length ? played[played.length - 1].i : (d.matches.length ? 0 : -1));
    }).catch(() => {});
    return () => { a = false; };
  }, [team, season]);
  if (!data) return (
    <div className="skel-wrap">
      <Skel h={64} r={13} style={{ marginBottom: 14 }} />
      <div className="skel-grid" style={{ gridTemplateColumns: "1fr 1.1fr" }}>
        <SkelRows n={10} h={36} />
        <Skel h={420} r={16} />
      </div>
    </div>
  );

  const comps = Array.from(new Set(data.matches.map((m) => m.comp)));
  const shown = data.matches.map((m, i) => ({ m, i })).filter((x) => comp === "전체" || x.m.comp === comp);
  const played = data.matches.filter((m) => m.status === "completed");
  const w = played.filter((m) => m.result === "W").length;
  const dd = played.filter((m) => m.result === "D").length;
  const l = played.filter((m) => m.result === "L").length;
  const ppg = played.length ? ((w * 3 + dd) / played.length).toFixed(2) : "-";
  const upcoming = data.matches.length - played.length;

  return (
    <div className="fade">
      {/* 시즌 토글 */}
      {data.seasons.length > 1 && (
        <div className="season-toggle">
          {data.seasons.map((s) => (
            <button key={s} className={`seg${(data.season === s) ? " active" : ""}`}
              onClick={() => setSeason(s)}
              style={data.season === s ? { background: accent, color: "#0b0f17" } : undefined}>{seasonLabel(s)}</button>
          ))}
        </div>
      )}

      <div className="stat-strip" style={{ marginTop: 10, gridTemplateColumns: "repeat(5,1fr)" }}>
        {played.length > 0 ? (
          <>
            <div className="stat"><div className="v">{played.length}</div><div className="l">Played</div></div>
            <div className="stat"><div className="v" style={{ color: "#4fc27f" }}>{w}</div><div className="l">Won</div></div>
            <div className="stat"><div className="v" style={{ color: "#9aa4b4" }}>{dd}</div><div className="l">Drawn</div></div>
            <div className="stat"><div className="v" style={{ color: "#e07070" }}>{l}</div><div className="l">Lost</div></div>
            <div className="stat"><div className="v" style={{ color: accent }}>{ppg}</div><div className="l">PPG</div></div>
          </>
        ) : (
          <>
            <div className="stat"><div className="v" style={{ color: accent }}>{data.matches.length}</div><div className="l">예정 경기</div></div>
            <div className="stat" style={{ gridColumn: "span 4", textAlign: "left", paddingLeft: 14 }}>
              <div className="l" style={{ marginBottom: 4 }}>{seasonLabel(data.season)} 시즌 · 대회별</div>
              <div className="v" style={{ fontSize: 15 }}>
                {comps.map((c) => <span key={c} className="comp-badge" style={{ color: compColor(c), borderColor: compColor(c) + "66", marginRight: 6 }}>{c} {data.matches.filter((m) => m.comp === c).length}</span>)}
              </div>
            </div>
          </>
        )}
      </div>

      {/* 대회 필터 */}
      <div className="comp-filter">
        {["전체", ...comps].map((c) => (
          <button key={c} className={`comp-pill${comp === c ? " active" : ""}`} onClick={() => { setComp(c); setSel(-1); }}
            style={comp === c ? { background: accent, color: "#0b0f17", borderColor: accent } : { borderColor: c === "전체" ? "var(--line)" : compColor(c) + "55" }}>
            {c}{c !== "전체" ? ` ${data.matches.filter((m) => m.comp === c).length}` : ""}
          </button>
        ))}
      </div>

      <div className="sched-layout">
        <div className="card sched-list-card">
          <h3>{shown.length} Matches{comp !== "전체" ? ` · ${comp}` : ""}</h3>
          <div className="sched-list">
            {shown.map(({ m, i }) => (
              <button className={`sched-row${sel === i ? " active" : ""}`} key={i} onClick={() => setSel(i)}
                style={sel === i ? { background: `${accent}22` } : undefined}>
                <span className="sc-comp" style={{ background: compColor(m.comp) }} title={m.comp} />
                <span className="sc-date">{m.date.slice(5)}</span>
                <span className={`sc-ha ${m.home_away === "H" ? "h" : "a"}`}>{m.home_away}</span>
                {m.opp_logo ? <img className="sc-logo" src={m.opp_logo} alt="" /> : <span className="sc-logo" />}
                <span className="sc-opp">{m.opponent}</span>
                <span className="sc-score">{m.status === "completed" ? (m.score || "—") : "·"}</span>
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
