"use client";
import { useEffect, useState } from "react";
import { getPlayers, getPlayerDetail, getSimilar, getHeatmaps, fmtEur, type Players, type PlayerDetail, type SimilarResult, type HeatmapData } from "@/lib/api";
import { tier, hexA, roleClass } from "@/lib/ui";
import Radar from "./Radar";
import HeatmapPitch from "./HeatmapPitch";

function Bar({ label, pct, raw, accent }: { label: string; pct: number; raw: number; accent: string }) {
  const c = pct >= 80 ? "#5ec98a" : pct >= 60 ? "#6aa6e0" : pct >= 40 ? "#caa64e" : "#d98169";
  return (
    <div className="pm">
      <div className="pm-top"><span>{label}</span><b style={{ color: c }}>{pct}</b></div>
      <div className="pm-bar"><span style={{ width: `${pct}%`, background: c }} /></div>
    </div>
  );
}

function Detail({ team, player, accent, heatmap }: { team: string; player: string; accent: string; heatmap: HeatmapData | null }) {
  const [d, setD] = useState<PlayerDetail | null>(null);
  const [sim, setSim] = useState<SimilarResult[]>([]);
  const hm = heatmap?.players?.find((p) => p.player === player);
  useEffect(() => {
    let a = true; setD(null); setSim([]);
    getPlayerDetail(team, player).then((x) => a && setD(x)).catch(() => {});
    getSimilar(player).then((x) => a && setSim(x.results)).catch(() => {});
    return () => { a = false; };
  }, [team, player]);
  if (!d) return <div className="card"><div className="loading">불러오는 중…</div></div>;
  const t = tier(d.ovr);
  return (
    <div className="card pd-card">
      <div className="pd-head" style={{ background: `linear-gradient(120deg, ${hexA(d.color, 0.28)}, transparent)` }}>
        {d.photo ? <img className="pd-photo" src={d.photo} alt="" /> : <span className="pd-photo ph" />}
        <div style={{ flex: 1 }}>
          <div className="pd-name">{d.player}</div>
          <div className="pd-meta">{d.pos} · {d.age}세 · {d.nationality}</div>
          <div className="pd-meta">{d.minutes.toLocaleString()}′ · {d.goals}G {d.assists}A · {fmtEur(d.value_eur)}</div>
        </div>
        <div className="pd-ovr" style={{ color: t.light, borderColor: hexA(t.light, 0.5) }}>
          <div className="teko" style={{ fontSize: 46, lineHeight: .8 }}>{d.ovr}</div>
          <div style={{ fontSize: 9, letterSpacing: 1, color: "var(--muted)" }}>OVR</div>
        </div>
      </div>
      {d.badges.length > 0 && (
        <div className="pd-badges">
          {d.badges.map((b, i) => (
            <span className="pd-badge" key={i} style={{ borderColor: hexA(accent, 0.5) }}>
              {b.medal} {b.label} <em style={{ color: accent }}>리그 #{b.rank}</em>
            </span>
          ))}
        </div>
      )}
      {d.comp_usage && (
        <div className="pd-comp">
          <div className="pd-comp-head">
            <span className="pd-comp-title">이번 시즌 대회별 출전</span>
            <span className={"role-tag " + roleClass(d.comp_usage.role)}>{d.comp_usage.role}</span>
            {d.comp_usage.big_match && <span className="role-bm" title="UCL/UEL 급 무대 검증">⚡ 빅매치 검증</span>}
          </div>
          <div className="pd-comp-chips">
            <div className="cchip lg">
              <span className="cchip-comp">리그</span>
              <span className="cchip-val">{d.comp_usage.league_min.toLocaleString()}′</span>
            </div>
            {d.comp_usage.comps.map((c) => (
              <div className="cchip" key={c.key}>
                <span className="cchip-comp">{c.label}</span>
                <span className="cchip-val">{c.starts}선발 · {c.apps}출전</span>
              </div>
            ))}
            {d.comp_usage.comps.length === 0 && (
              <div className="cchip empty"><span className="cchip-comp">컵·유럽 출전 없음</span></div>
            )}
          </div>
        </div>
      )}
      <div className="pd-body">
        <div className="pd-cats">
          {d.categories.map((c, i) => (
            <div className="pd-cat" key={i}>
              <div className="pd-cat-head">
                <span>{c.name}</span>
                <b style={{ color: tier(c.avg).light }}>{c.avg}</b>
              </div>
              {c.metrics.map((m, j) => <Bar key={j} label={m.label} pct={m.pct} raw={m.raw} accent={accent} />)}
            </div>
          ))}
        </div>
        <div className="pd-radar"><Radar data={d.radar} color={accent} /></div>
      </div>
      {hm && heatmap && (
        <div className="pd-heatmap" style={{ marginTop: 4 }}>
          <div className="pd-sim-title">시즌 활동 구역 <span style={{ opacity: 0.5, fontWeight: 400, fontSize: 11 }}>· {hm.n_points.toLocaleString()} 위치 표본 · Sofascore</span></div>
          <div style={{ maxWidth: 470 }}><HeatmapPitch grid={hm.grid} gw={heatmap.gw} gh={heatmap.gh} id={`pd-${player.replace(/\s+/g, "")}`} /></div>
        </div>
      )}
      {sim.length > 0 && (
        <div className="pd-similar">
          <div className="pd-sim-title">스타일 유사 선수</div>
          <div className="pd-sim-list">
            {sim.map((s, i) => (
              <div className="pd-sim-row" key={i}>
                {s.logo ? <img src={s.logo} alt="" /> : <span className="pd-sim-logo" />}
                <span className="pd-sim-name">{s.player}</span>
                <span className="pd-sim-squad">{s.squad}</span>
                <span className="pd-sim-score" style={{ color: accent }}>{s.score}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PlayerTab({ team, accent, initialPlayer }: { team: string; accent: string; initialPlayer?: string }) {
  const [data, setData] = useState<Players | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [hm, setHm] = useState<HeatmapData | null>(null);
  useEffect(() => { let a = true; setHm(null); getHeatmaps(team).then((x) => a && setHm(x)).catch(() => a && setHm(null)); return () => { a = false; }; }, [team]);
  useEffect(() => {
    let a = true;
    setData(null); setSel(null);
    getPlayers(team).then((d) => {
      if (!a) return;
      setData(d);
      // 딥링크(전역 검색)로 지정된 선수가 스쿼드에 있으면 그걸 선택, 없으면 첫 선수
      const hit = initialPlayer && d.players.find((p) => p.player === initialPlayer);
      setSel((hit ? hit.player : d.players[0]?.player) ?? null);
    }).catch(() => {});
    return () => { a = false; };
  }, [team, initialPlayer]);
  if (!data) return <div className="loading">불러오는 중…</div>;

  return (
    <div className="fade player-layout">
      <div className="pl-grid">
        {data.players.map((p) => {
          const t = tier(p.ovr);
          return (
            <button key={p.player} className={`pl-card${sel === p.player ? " active" : ""}`}
              onClick={() => setSel(p.player)}
              style={sel === p.player ? { borderColor: accent } : undefined}>
              <span className="pl-ovr" style={{ color: t.light }}>{p.ovr}</span>
              {p.big_match && <span className="pl-bm" title="UCL/UEL 급 무대 검증">⚡</span>}
              {p.photo ? <img className="pl-photo" src={p.photo} alt="" /> : <span className="pl-photo ph" />}
              <div className="pl-name">{p.player}</div>
              <div className="pl-pos">{p.pos} · {p.age}</div>
              {p.role && <span className={"pl-role role-tag sm " + roleClass(p.role)}>{p.role}</span>}
            </button>
          );
        })}
      </div>
      <div className="pl-detail">
        {sel && <Detail team={team} player={sel} accent={accent} heatmap={hm} />}
      </div>
    </div>
  );
}
