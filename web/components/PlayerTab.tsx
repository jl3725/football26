"use client";
import OvrBreakdown from "./OvrBreakdown";
import FormPair, { RecentStrip } from "./FormPair";
import { useEffect, useState } from "react";
import { getPlayers, getPlayerDetail, getSimilar, getHeatmaps, fmtEur, type Players, type PlayerDetail, type SimilarResult, type HeatmapData } from "@/lib/api";
import { tier, hexA, roleClass, futTier } from "@/lib/ui";
import { pctMeaning, scoreMeaning, ovrBand, signTone } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Radar from "./Radar";
import HeatmapPitch from "./HeatmapPitch";
import ComparePanel from "./ComparePanel";
import { usePeek } from "./PlayerPeek";
import { Skel, SkelCards } from "./Skeleton";
import { TrendArrow, TrendLine } from "./Trend";
import SeasonLog from "./SeasonLog";
import PlayerNews from "./PlayerNews";

// 실제 기록 값 — 라벨에 '%' 가 있으면 비율(0~100), 그 외(/90·xA)는 90분당.
function fmtRaw(label: string, raw: number): string {
  if (raw == null || Number.isNaN(raw)) return "";
  return label.includes("%") ? `${(Math.round(raw * 10) / 10).toFixed(1)}%` : `${raw.toFixed(2)} /90`;
}

function Bar({ label, pct, raw }: { label: string; pct: number; raw: number }) {
  const m = pctMeaning(pct);
  const rv = fmtRaw(label, raw);
  return (
    <div className="pm" title={`${label} ${rv} — 같은 포지션 중 백분위 ${pct} (${m.label})`}>
      <div className="pm-top" style={{ alignItems: "center", gap: 6 }}>
        <span style={{ minWidth: 0 }}>{label}{rv && <em style={{ fontStyle: "normal", color: "var(--muted)", fontSize: 11, marginLeft: 5 }}>{rv}</em>}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
          <MeaningTag sm m={m} />
          <b style={{ color: m.c }}>{pct}</b>
        </span>
      </div>
      <div className="pm-bar"><span style={{ width: `${pct}%`, background: m.bar }} /></div>
    </div>
  );
}

function Detail({ team, player, accent, heatmap }: { team: string; player: string; accent: string; heatmap: HeatmapData | null }) {
  const [d, setD] = useState<PlayerDetail | null>(null);
  const [sim, setSim] = useState<SimilarResult[]>([]);
  const peek = usePeek();
  const hm = heatmap?.players?.find((p) => p.player === player);
  useEffect(() => {
    let a = true; setD(null); setSim([]);
    getPlayerDetail(team, player).then((x) => a && setD(x)).catch(() => {});
    getSimilar(player).then((x) => a && setSim(x.results)).catch(() => {});
    return () => { a = false; };
  }, [team, player]);
  if (!d) return (
    <div className="card">
      <div className="skel-row" style={{ padding: 8 }}>
        <Skel w={86} h={86} circle />
        <div className="skel-stack" style={{ flex: 1 }}><Skel w="55%" h={20} /><Skel w="38%" h={12} /><Skel w="46%" h={12} /></div>
        <Skel w={72} h={64} r={13} />
      </div>
      <div className="skel-stack" style={{ padding: 8 }}><Skel h={10} /><Skel h={10} /><Skel w="70%" h={10} /><Skel h={160} r={12} /></div>
    </div>
  );
  const t = tier(d.ovr);
  return (
    <div className="card pd-card">
      <div className="pd-head" style={{ background: `linear-gradient(120deg, ${hexA(d.color, 0.28)}, transparent)` }}>
        {d.photo ? <img className="pd-photo" src={d.photo} alt="" /> : <span className="pd-photo ph" />}
        <div style={{ flex: 1 }}>
          <div className="pd-name">{d.player}</div>
          <div className="pd-meta">{d.pos} · {d.age}세 · {d.nationality}</div>
          <div className="pd-meta">
            리그 {d.minutes.toLocaleString()}′ · {d.goals}G {d.assists}A
            {d.season_log?.available && d.season_log.by_comp.length > 1 && (
              <> · <b>전체 {d.season_log.total.minutes.toLocaleString()}′ · {d.season_log.total.goals}G {d.season_log.total.assists}A</b></>
            )}
            {" · "}{fmtEur(d.value_eur)}
          </div>
        </div>
        <div className="pd-ovr" style={{ color: t.light, borderColor: hexA(t.light, 0.5) }}
          title={`OVR ${d.ovr} · ${t.ko} (${ovrBand(d.ovr).range}) — ${ovrBand(d.ovr).desc}`}>
          <div className="teko" style={{ fontSize: 46, lineHeight: .8 }}>{d.ovr}</div>
          <div style={{ fontSize: 9, letterSpacing: 1, color: "var(--muted)" }}>OVR</div>
          <div style={{ fontSize: 9.5, fontWeight: 700, marginTop: 3, whiteSpace: "nowrap", fontFamily: "var(--font-ui)", letterSpacing: 0 }}>{t.ko}</div>
        </div>
      </div>
      <TrendLine t={d.trend} ovr={d.ovr} />
      {(d.form != null || d.recent) && (
        <div className="pd-form">
          <div className="pd-form-h"><b>FORM</b><span>폼 — 시즌 전체와 최근 5경기(전 대회)를 따로</span></div>
          <FormPair season={d.form} recent={d.recent?.score} n={d.recent?.n} />
          {d.recent && d.recent.matches.length > 0 && (
            <>
              <RecentStrip matches={d.recent.matches} />
              <div className="pd-form-cap">최근 {Math.min(d.recent.n, 3)}경기 평균 <b>{d.recent.avg3.toFixed(2)}</b> · {d.recent.n}경기 평균 <b>{d.recent.avg5.toFixed(2)}</b> <em>(FotMob 경기 평점 · 출전 시간 가중 · 시즌 평점은 Sofascore·FotMob 평균)</em></div>
            </>
          )}
        </div>
      )}
      <OvrBreakdown ovr={d.ovr} parts={d.ovr_parts} ratings={d.ratings} />
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
            <span className="pd-comp-title">이번 시즌 역할</span>
            <span className={"role-tag " + roleClass(d.comp_usage.role)} title={d.comp_usage.role_evidence}>{d.comp_usage.role}</span>
            {d.comp_usage.role_evidence && <span className="pd-comp-ev">{d.comp_usage.role_evidence}</span>}
            {d.comp_usage.big_match && <span className="role-bm" title="UCL/UEL 급 무대 검증">⚡ 빅매치 검증</span>}
          </div>
          {d.season_log?.available ? <SeasonLog log={d.season_log} accent={accent} /> : (
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
          )}
        </div>
      )}
      {d.value_history && d.value_history.length >= 2 && (() => {
        const vs = d.value_history, vals = vs.map((x) => x.value_eur);
        const mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
        const first = vals[0], last = vals[vals.length - 1];
        const pct = first > 0 ? Math.round(((last - first) / first) * 100) : 0;
        const w = 150, h = 34;
        const pts = vs.map((x, i) => `${(i / (vs.length - 1)) * w},${h - ((x.value_eur - mn) / rng) * (h - 6) - 3}`).join(" ");
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "2px 0 10px" }}>
            <div>
              <div style={{ fontSize: 10, opacity: 0.5, letterSpacing: 0.3 }}>시장가치 추이</div>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>{fmtEur(last)}
                {pct !== 0 && <span style={{ color: signTone(pct).c, fontSize: 11, marginLeft: 5 }} title={`첫 기록 대비 ${pct > 0 ? "상승" : "하락"}`}>{pct > 0 ? "▲" : "▼"}{Math.abs(pct)}%</span>}</div>
            </div>
            <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{ overflow: "visible" }}>
              <polyline points={pts} fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        );
      })()}
      {d.peers?.n > 0 && (
        <div style={{ fontSize: 11, opacity: 0.5, margin: "0 0 4px" }}>
          아래 지표 = <b>리그 경기 기준</b> · {({ GK: "골키퍼", DEF: "수비수", MID: "미드필더", ATT: "공격수" } as Record<string, string>)[d.peers.line] || "포지션"} 대비 백분위 · {d.peers.n}명 기준(컵·유럽 제외)
        </div>
      )}
      <div className="pd-body">
        <div className="pd-cats">
          {d.categories.map((c, i) => {
            const cm = pctMeaning(c.avg);
            return (
              <div className="pd-cat" key={i}>
                {/* .pd-cat-head span 규칙(라벨 폰트·자간)이 뜻 꼬리표까지 덮지 않게 인라인으로 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 7 }}
                  title={`${c.name} — 세부 지표 백분위 평균 ${c.avg} (${cm.label})`}>
                  <span style={{ fontFamily: "var(--font-label)", fontSize: 12, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)" }}>{c.name}</span>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <MeaningTag sm m={cm} />
                    <b style={{ color: cm.c, fontFamily: "var(--font-num)", fontSize: 20, lineHeight: 1, fontWeight: 700 }}>{c.avg}</b>
                  </div>
                </div>
                {c.metrics.map((m, j) => <Bar key={j} label={m.label} pct={m.pct} raw={m.raw} />)}
              </div>
            );
          })}
        </div>
        <div className="pd-radar"><Radar data={d.radar} color={accent} scale="pct" /></div>
      </div>
      {hm && heatmap && (
        <div className="pd-heatmap" style={{ marginTop: 4 }}>
          <div className="pd-sim-title">시즌 활동 구역 <span style={{ opacity: 0.5, fontWeight: 400, fontSize: 11 }}>· {hm.n_points.toLocaleString()} 위치 표본 · Sofascore</span></div>
          <div style={{ maxWidth: 470 }}><HeatmapPitch grid={hm.grid} gw={heatmap.gw} gh={heatmap.gh} id={`pd-${player.replace(/\s+/g, "")}`} /></div>
        </div>
      )}
      {sim.length > 0 && (
        <div className="pd-similar">
          <div className="pd-sim-title">스타일 유사 선수 <span style={{ opacity: 0.6, fontWeight: 400, fontSize: 11, letterSpacing: 0 }}>· % = 유사도(스타일 + 기록, 100 = 판박이)</span></div>
          <div className="pd-sim-list">
            {sim.map((s, i) => {
              const sm = scoreMeaning(s.score);
              return (
                <div className="pd-sim-row peekable" key={i}
                  onClick={(e) => peek(e, { name: s.player, club: s.squad, hint: { pos: s.pos, age: s.age, value_eur: s.value_eur, logo: s.logo } })}>
                  {s.logo ? <img src={s.logo} alt="" /> : <span className="pd-sim-logo" />}
                  <span className="pd-sim-name">{s.player}</span>
                  <span className="pd-sim-squad">{s.squad}</span>
                  <span className="pd-sim-score" style={{ color: sm.c, whiteSpace: "nowrap", flexShrink: 0 }}
                    title={`스타일 유사도 ${s.score}% (${sm.label}) — 플레이 스타일 ${s.style} · 기록 ${s.perf}`}>
                    <span style={{ fontSize: 10, opacity: 0.7, fontWeight: 500, marginRight: 4 }}>유사도</span>{s.score}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <PlayerNews player={player} club={team} />
    </div>
  );
}

export default function PlayerTab({ team, accent, initialPlayer }: { team: string; accent: string; initialPlayer?: string }) {
  const [data, setData] = useState<Players | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [cmpMode, setCmpMode] = useState(false);   // 비교 모드
  const [cmp, setCmp] = useState<string | null>(null);   // 2번째(B) 선수
  const [hm, setHm] = useState<HeatmapData | null>(null);
  useEffect(() => { let a = true; setHm(null); getHeatmaps(team).then((x) => a && setHm(x)).catch(() => a && setHm(null)); return () => { a = false; }; }, [team]);
  useEffect(() => {
    let a = true;
    setData(null); setSel(null); setCmp(null);
    getPlayers(team).then((d) => {
      if (!a) return;
      setData(d);
      // 딥링크(전역 검색)로 지정된 선수가 스쿼드에 있으면 그걸 선택, 없으면 첫 선수
      const hit = initialPlayer && d.players.find((p) => p.player === initialPlayer);
      setSel((hit ? hit.player : d.players[0]?.player) ?? null);
    }).catch(() => {});
    return () => { a = false; };
  }, [team, initialPlayer]);
  if (!data) return (
    <div className="player-layout skel-wrap">
      <SkelCards n={8} cols="repeat(2, 1fr)" />
      <div className="skel-stack"><Skel h={300} r={16} /><Skel h={180} r={16} /></div>
    </div>
  );

  const CB = "#e0a05e";
  const onCard = (name: string) => {
    if (cmpMode) { if (name !== sel) setCmp(name === cmp ? null : name); }
    else {
      setSel(name);
      // 모바일(가로 띠 목록)에선 상세가 아래에 있으므로 고른 선수 상세로 내려 준다
      if (typeof window !== "undefined" && window.matchMedia("(max-width: 760px)").matches) {
        setTimeout(() => document.querySelector(".pl-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
      }
    }
  };
  return (
    <div className="fade">
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button onClick={() => { setCmpMode((m) => !m); setCmp(null); }}
          style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
            border: `1px solid ${hexA(accent, 0.3)}`, background: cmpMode ? accent : "transparent", color: cmpMode ? "#0a0a0a" : "inherit" }}>
          ⚖ 선수 비교{cmpMode ? " ON" : ""}
        </button>
      </div>
      <div className="player-layout">
        <div className="pl-grid">
          {data.players.map((p) => {
            const t = tier(p.ovr);
            const isA = sel === p.player, isB = cmp === p.player;
            return (
              <button key={p.player} className={`pl-card fut ${futTier(p.ovr)}${isA ? " active" : ""}`}
                onClick={() => onCard(p.player)}
                style={{ position: "relative", ...(isA ? { borderColor: accent } : isB ? { borderColor: CB } : {}) }}>
                {cmpMode && (isA || isB) && <span style={{ position: "absolute", top: 4, left: 5, fontSize: 10, fontWeight: 800, color: isA ? accent : CB }}>{isA ? "A" : "B"}</span>}
                <span className="pl-ovr" style={{ color: t.light }} title={`OVR ${p.ovr} · ${t.ko}`}>{p.ovr}<TrendArrow t={p.trend} ovr={p.ovr} /></span>
                {p.big_match && <span className="pl-bm" title="UCL/UEL 급 무대 검증">⚡</span>}
                {p.photo ? <img className="pl-photo" src={p.photo} alt="" /> : <span className="pl-photo ph" />}
                <div className="pl-name">{p.player}</div>
                <div className="pl-pos">{p.pos} · {p.age} · <span style={{ color: t.light, fontWeight: 600 }}>{t.ko}</span></div>
                {p.role && <span className={"pl-role role-tag sm " + roleClass(p.role)}>{p.role}</span>}
              </button>
            );
          })}
        </div>
        <div className="pl-detail">
          {cmpMode
            ? (sel && cmp
                ? <ComparePanel team={team} a={sel} b={cmp} accent={accent} onClear={() => setCmp(null)} />
                : <div className="card"><div className="mgr-meta" style={{ padding: 20 }}>비교할 <b>2번째 선수(B)</b>를 왼쪽에서 선택하세요. (현재 A: {sel})</div></div>)
            : (sel && <Detail team={team} player={sel} accent={accent} heatmap={hm} />)}
        </div>
      </div>
    </div>
  );
}
