"use client";
import OvrBreakdown from "./OvrBreakdown";
import ScoutTake from "./ScoutTake";
import JustPlayedStrip from "./JustPlayed";
import FormPair, { RecentStrip } from "./FormPair";
import { useEffect, useState } from "react";
import { getPlayers, getPlayerDetail, getSimilar, getHeatmaps, fmtEur, foldName, type Players, type PlayerDetail, type SimilarResult, type HeatmapData } from "@/lib/api";
import { tier, hexA, roleClass, futTier } from "@/lib/ui";
import { lgEn } from "@/lib/match";
import { pctMeaning, scoreMeaning, ovrBand, signTone, FORM_NOTE, RECENT_NOTE } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Radar from "./Radar";
import HeatmapPitch from "./HeatmapPitch";
import ComparePanel from "./ComparePanel";
import ComparePicker, { type CmpRef } from "./ComparePicker";
import { usePeek } from "./PlayerPeek";
import { Skel, SkelCards } from "./Skeleton";
import { TrendArrow, TrendLine } from "./Trend";
import SeasonLog from "./SeasonLog";
import PlayerNews from "./PlayerNews";
import ScoutReport from "./ScoutReport";
import Info from "./Info";

// 실제 기록 값 — 라벨에 '%' 가 있으면 비율(0~100), 그 외(/90·xA)는 90분당.
// 계약 남은 기간 — ' (1년 8개월 남음)'
function contractLeft(until: string): string {
  const d = new Date(until.slice(0, 10));
  if (Number.isNaN(d.getTime())) return "";
  const m = Math.round((d.getTime() - Date.now()) / (30.44 * 864e5));
  if (m < 0) return " (만료)";
  return m >= 12 ? ` (${Math.floor(m / 12)}년${m % 12 ? ` ${m % 12}개월` : ""} 남음)` : ` (${m}개월 남음)`;
}

function fmtRaw(label: string, raw: number): string {
  if (raw == null || Number.isNaN(raw)) return "";
  return label.includes("%") ? `${(Math.round(raw * 10) / 10).toFixed(1)}%` : `${raw.toFixed(2)} /90`;
}

function Bar({ label, pct, raw, low, att }: { label: string; pct: number; raw: number; low?: boolean; att?: number | null }) {
  const m = pctMeaning(pct);
  const rv = fmtRaw(label, raw);
  // 표본 부족(시도 10회 미만) — 회색으로, 뜻 꼬리표 대신 '표본 부족'(Gabriel 드리블 성공 100% = 시즌 1회 시도였다)
  if (low) return (
    <div className="pm low" title={`${label} ${rv} — 시도 ${att ?? 0}회뿐이라 백분위(${pct})를 믿기 어렵습니다(10회 미만)`}>
      <div className="pm-top" style={{ alignItems: "center", gap: 6 }}>
        <span style={{ minWidth: 0 }}>{label}{rv && <em style={{ fontStyle: "normal", color: "var(--muted)", fontSize: 11, marginLeft: 5 }}>{rv}</em>}</span>
        <span className="pm-low">표본 부족 · {att ?? 0}회</span>
      </div>
      <div className="pm-bar"><span style={{ width: `${pct}%`, background: "rgba(255,255,255,0.18)" }} /></div>
    </div>
  );
  return (
    <div className="pm" title={`${label} ${rv} — 같은 포지션 중 백분위 ${pct} (${m.label})${att != null ? ` · 시도 ${att}회` : ""}`}>
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
  const [simScope, setSimScope] = useState<"all" | "league">("all");   // 유사 선수 — 8개 리그 | 같은 리그
  const [basis, setBasis] = useState<"blend" | "season">("blend");     // 세부 지표 — 시즌 초 안정화 | 이번 시즌만
  const [comps, setComps] = useState<"all" | "league">("all");          // 세부 지표 — 전 대회(리그 + 유럽·컵) | 리그만
  const peek = usePeek();
  const hm = heatmap?.players?.find((p) => p.player === player);
  useEffect(() => {
    let a = true; setD(null); setSim([]);
    getPlayerDetail(team, player, undefined, basis, comps).then((x) => a && setD(x)).catch(() => {});
    return () => { a = false; };
  }, [team, player, basis, comps]);
  useEffect(() => {
    let a = true; setSim([]);
    getSimilar(player, undefined, simScope).then((x) => a && setSim(x.results)).catch(() => {});
    return () => { a = false; };
  }, [player, simScope]);
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
  // 백분위 지표를 보여 줄 만큼 뛰었나(2분 뛴 선수 레이더 0 문제) — 서버 판정(template.enough: 전 대회 + 안정화로 섞은 지난 시즌 분)
  const sampleMin = d.template?.eff_minutes ?? d.minutes;
  const enough = d.template?.enough ?? sampleMin >= (d.is_gk ? 300 : 450);
  return (
    <div className="card pd-card">
      <div className="pd-head" style={{ background: `linear-gradient(120deg, ${hexA(d.color, 0.28)}, transparent)` }}>
        {d.photo ? <img className="pd-photo" src={d.photo} alt="" /> : <span className="pd-photo ph" />}
        <div style={{ flex: 1 }}>
          <div className="pd-name">{d.player}</div>
          {/* 빈 정보는 숨긴다 — 나이 0·국적 없음이 'DF · 0세 · '로 찍히던 194명(2026-10-20 점검) */}
          <div className="pd-meta">{[d.pos, d.age > 0 ? `${d.age}세` : "", d.nationality].filter(Boolean).join(" · ")}</div>
          {(d.joined || d.contract_until) && (
            <div className="pd-meta">{[d.joined ? `입단 ${d.joined.slice(0, 7).replace("-", ".")}` : "",
              d.contract_until ? `계약 ~${d.contract_until.slice(0, 7).replace("-", ".")}${contractLeft(d.contract_until)}` : ""].filter(Boolean).join(" · ")}</div>
          )}
          <div className="pd-meta">
            리그 {d.minutes.toLocaleString()}′ · {d.goals}G {d.assists}A
            {d.season_log?.available && d.season_log.by_comp.length > 1 && (
              <> · <b>전체 {d.season_log.total.minutes.toLocaleString()}′ · {d.season_log.total.goals}G {d.season_log.total.assists}A</b></>
            )}
            {d.value_eur > 0 && <>{" · "}{fmtEur(d.value_eur)}</>}
          </div>
        </div>
        <div className="pd-ovr" style={{ color: t.light, borderColor: hexA(t.light, 0.5) }}
          title={`OVR ${d.ovr} · ${t.ko} (${ovrBand(d.ovr).range}) — ${ovrBand(d.ovr).desc}`}>
          <div className="teko" style={{ fontSize: 46, lineHeight: .8 }}>{d.ovr}</div>
          <div style={{ fontSize: 10, letterSpacing: 1, color: "var(--muted)" }}>OVR</div>
          <div style={{ fontSize: 11, fontWeight: 700, marginTop: 3, whiteSpace: "nowrap", fontFamily: "var(--font-ui)", letterSpacing: 0 }}>{t.ko}</div>
        </div>
      </div>
      <TrendLine t={d.trend} ovr={d.ovr} />
      <JustPlayedStrip d={d} />
      <ScoutTake t={d.scout_take} />
      {(d.form != null || d.recent) && (
        <div className="pd-form">
          <div className="pd-form-h"><b>FORM</b><span>시즌 vs 최근 5경기</span>
            <Info wide label="폼 기준">
              <p>{FORM_NOTE}</p>
              <p>{RECENT_NOTE}</p>
              <p className="muted">경기 평점 = FotMob(출전 시간 가중) · 시즌 평점은 Sofascore·FotMob 평균</p>
            </Info>
          </div>
          <FormPair season={d.form} recent={d.recent?.score} n={d.recent?.n} />
          {d.recent && d.recent.matches.length > 0 && (
            <>
              <RecentStrip matches={d.recent.matches} />
              <div className="pd-form-cap">최근 {Math.min(d.recent.n, 3)}경기 평균 <b>{d.recent.avg3.toFixed(2)}</b> · {d.recent.n}경기 평균 <b>{d.recent.avg5.toFixed(2)}</b></div>
            </>
          )}
        </div>
      )}
      <OvrBreakdown ovr={d.ovr} parts={d.ovr_parts} ratings={d.ratings} />
      {d.badges.length > 0 && (
        <div className="pd-badges">
          {d.badges.map((b, i) => (
            <span className="pd-badge" key={i} style={{ borderColor: hexA(accent, 0.5) }}>
              {b.medal} {b.label} <em style={{ color: accent }}>{b.scope ?? "리그"} {b.tie ? "공동 " : ""}#{b.rank}</em>
            </span>
          ))}
        </div>
      )}
      {d.comp_usage && (
        <div className="pd-comp">
          <div className="pd-comp-head">
            <span className="pd-comp-title">이번 시즌 역할</span>
            <span className={"role-tag " + roleClass(d.comp_usage.role)} title={d.comp_usage.role_evidence}>{d.comp_usage.role}</span>
            {d.comp_usage.role_evidence && (
              <Info label="역할 근거">
                <p><b>근거</b> — {d.comp_usage.role_evidence}</p>
                <p className="muted">리그 출전 시간·유럽·컵 선발을 풀시즌으로 환산해 판정 · 부상 결장 경기는 뺌</p>
                {d.comp_usage.big_match && <p className="muted">⚡ 빅매치 검증 = UCL/UEL 급 무대 출전 기록</p>}
              </Info>
            )}
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
      {d.value_history && d.value_history.length >= 2 && new Set(d.value_history.map((x) => x.value_eur)).size > 1 && (() => {   // 값이 하나뿐이면 평평한 줄만 남는다
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
      {d.template ? (
        <div className="pd-tpl">
          <span className="pd-tpl-k">{d.template.en}</span>
          <span className="pd-tpl-s">{d.template.scope === "리그" ? "리그" : "8개 리그"} {d.template.ko} {d.template.n}명 대비
            <Info wide label="세부 지표 기준">
              <p><b>백분위</b> — 같은 {d.template.ko} {d.template.n}명({d.template.scope === "리그" ? "같은 리그" : "8개 리그"}) 대비. 50 = 중간.</p>
              <p><b>기록</b> — {d.template.comps === "league" ? "리그 경기만."
                : d.template.x_comps?.length
                  ? <>리그 {(d.template.league_minutes ?? 0).toLocaleString()}′ + {d.template.x_comps.map((c) => `${c.name} ${c.minutes}′${c.weight < 1 ? `(×${c.weight})` : ""}`).join(" · ")}. 유럽·컵은 리그 표 척도로 맞춰 섞음.</>
                  : "전 대회(이번 시즌 유럽·컵 출전 없음)."}
                {(d.template.topup_minutes ?? 0) > 0 ? <> 최근 리그 {d.template.topup_minutes}′는 기본 원천(Sofascore·FBref)에 아직 없어 FotMob 경기별 기록으로 채움.</> : null}</p>
              <p><b>{d.template.basis === "blend" ? "안정화" : "이번 시즌만"}</b> — {d.template.basis === "blend" && (d.template.prior_minutes ?? 0) > 0
                ? <>이번 시즌 {(d.template.cur_minutes ?? 0).toLocaleString()}′ + 지난 시즌 {(d.template.prior_minutes ?? 0).toLocaleString()}′치(비중 {Math.round((d.template.prior_share ?? 0) * 100)}%, 출전이 쌓일수록 줄어듦).</>
                : d.template.basis === "blend" ? <>지난 시즌 기록 없음 — 이번 시즌 {(d.template.cur_minutes ?? 0).toLocaleString()}′.</>
                : <>{(d.template.cur_minutes ?? 0).toLocaleString()}′ — 시즌 초엔 몇 경기로 크게 흔들림.</>}</p>
              {d.template.possession != null && <p><b>수비 횟수</b> — 팀 점유율 {d.template.possession}% 보정(×{d.template.padj}, 50% 기준).</p>}
              <p className="muted">회색 = 시도 10회 미만(표본 부족) · 평균·레이더에서 뺌</p>
            </Info>
          </span>
          <span className="pd-basis">
            <span className="it-chips">{([["all", "전 대회"], ["league", "리그만"]] as const).map(([v, l]) => (
              <button key={v} className={comps === v ? "on" : ""} onClick={() => setComps(v)}>{l}</button>))}</span>
            <span className="it-chips">{([["blend", "안정화"], ["season", "이번 시즌만"]] as const).map(([v, l]) => (
              <button key={v} className={basis === v ? "on" : ""} onClick={() => setBasis(v)}>{l}</button>))}</span>
          </span>
        </div>
      ) : d.peers?.n > 0 && (
        <div style={{ fontSize: 11, opacity: 0.5, margin: "0 0 4px" }}>
          {({ GK: "골키퍼", DEF: "수비수", MID: "미드필더", ATT: "공격수" } as Record<string, string>)[d.peers.line] || "포지션"} {d.peers.n}명 대비 백분위
          <Info label="백분위 기준"><p>리그 경기 기준 · 컵·유럽 제외</p></Info>
        </div>
      )}
      {/* 요약 그림 두 장을 나란히(레이더 = 능력 모양, 히트맵 = 뛰는 자리) — 예전엔 각각 한 줄을 다 차지해 양옆이 비었다 */}
      {(enough || (hm && heatmap)) && (
        <div className="pd-visual">
          {enough && <div className="pd-radar"><Radar data={d.radar} color={accent} scale="pct" /></div>}
          {hm && heatmap && (
            <div className="pd-heatmap">
              <div className="pd-sim-title">시즌 활동 구역
                <Info label="활동 구역 기준">
                  <p>이번 시즌 경기에서 머문 위치를 모은 히트맵 · 밝을수록 자주 머문 곳 · 공격 방향 →</p>
                  <p className="muted">위치 표본 {hm.n_points.toLocaleString()}개 · 출처 Sofascore</p>
                </Info>
              </div>
              <HeatmapPitch grid={hm.grid} gw={heatmap.gw} gh={heatmap.gh} id={`pd-${player.replace(/\s+/g, "")}`} />
            </div>
          )}
        </div>
      )}
      {!enough && (
        <div className="pd-sample">표본 부족 · {d.is_gk ? 300 : 450}′ 이상부터 표시
          <Info label="표본 기준">
            <p>지금 {Math.round(sampleMin).toLocaleString()}′ 출전 — 레이더·세부 지표는 {d.is_gk ? 300 : 450}′ 이상부터 보여 줍니다.</p>
            <p className="muted">출전이 쌓이면 자동으로 나옵니다.</p>
          </Info>
        </div>
      )}
      {enough && <div className="pd-body">
        <div className="pd-cats">
          {d.categories.map((c, i) => {
            const cm = pctMeaning(c.avg ?? 0);
            return (
              <div className="pd-cat" key={i}>
                {/* .pd-cat-head span 규칙(라벨 폰트·자간)이 뜻 꼬리표까지 덮지 않게 인라인으로 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 7 }}
                  title={c.avg == null ? `${c.name} — 지표가 모두 표본 부족` : `${c.name} — 세부 지표 백분위 평균 ${c.avg} (${cm.label})`}>
                  <span style={{ fontFamily: "var(--font-label)", fontSize: 12, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)" }}>{c.name}</span>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    {c.avg == null ? <span className="pm-low">표본 부족</span> : <>
                    <MeaningTag sm m={cm} />
                    <b style={{ color: cm.c, fontFamily: "var(--font-num)", fontSize: 20, lineHeight: 1, fontWeight: 700 }}>{c.avg}</b></>}
                  </div>
                </div>
                {c.metrics.map((m, j) => <Bar key={j} label={m.label} pct={m.pct} raw={m.raw} low={m.low} att={m.att} />)}
              </div>
            );
          })}
        </div>
      </div>}
      {(sim.length > 0 || simScope === "league") && (
        <div className="pd-similar">
          <div className="pd-sim-title" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}><span>스타일 유사 선수
              <Info label="유사도 기준">
                <p><b>% = 유사도</b> — 플레이 스타일 + 기록, 100 = 판박이</p>
                <p className="muted">기록은 리그 수준 보정</p>
              </Info></span>
            <span className="it-chips" style={{ marginLeft: "auto" }}>{([["all", "8개 리그"], ["league", "같은 리그"]] as const).map(([v, l]) => (
              <button key={v} className={simScope === v ? "on" : ""} onClick={() => setSimScope(v)}>{l}</button>))}</span></div>
          <div className="pd-sim-list">
            {sim.map((s, i) => {
              const sm = scoreMeaning(s.score);
              return (
                <div className="pd-sim-row peekable" key={i}
                  onClick={(e) => peek(e, { name: s.player, club: s.squad, hint: { pos: s.pos, age: s.age, value_eur: s.value_eur, logo: s.logo } })}>
                  {s.logo ? <img src={s.logo} alt="" /> : <span className="pd-sim-logo" />}
                  <span className="pd-sim-name">{s.player}</span>
                  <span className="pd-sim-squad">{s.squad}{s.league && <em className={`pd-sim-lg${s.cross_league ? " x" : ""}`}>{lgEn(s.league) || s.league}</em>}</span>
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

export default function PlayerTab({ team, accent, initialPlayer, onPlayer }: {
  team: string; accent: string; initialPlayer?: string; onPlayer?: (p: string) => void;   // 고른 선수 → 주소(공유 링크)
}) {
  const [data, setData] = useState<Players | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [cmpMode, setCmpMode] = useState(false);   // 비교 모드
  const [cmp, setCmp] = useState<string | null>(null);   // 2번째(B) 선수
  const [cmpExt, setCmpExt] = useState<CmpRef | null>(null);   // B — 다른 클럽·리그 선수(P2 ⑥)
  const [hm, setHm] = useState<HeatmapData | null>(null);
  // SCOUT REPORT 한 장 — 주소 &report=1 로 바로 열기(공유 링크), 열고 닫을 때 주소에 반영
  const [report, setReport] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("report") === "1") setReport(true);
  }, []);
  const toggleReport = (on: boolean) => {
    setReport(on);
    try {
      const u = new URL(window.location.href);
      if (on) u.searchParams.set("report", "1"); else u.searchParams.delete("report");
      window.history.replaceState(null, "", u.toString());
    } catch { /* 주소 반영은 편의 기능 */ }
  };
  useEffect(() => { let a = true; setHm(null); getHeatmaps(team).then((x) => a && setHm(x)).catch(() => a && setHm(null)); return () => { a = false; }; }, [team]);
  useEffect(() => {
    let a = true;
    setData(null); setSel(null); setCmp(null); setCmpExt(null);
    getPlayers(team).then((d) => {
      if (!a) return;
      setData(d);
      // 딥링크(전역 검색)로 지정된 선수가 스쿼드에 있으면 그걸 선택, 없으면 첫 선수
      // 악센트·대소문자 무시(주소의 'Odegaard' = 'Ødegaard')
      const hit = initialPlayer && d.players.find((p) => foldName(p.player) === foldName(initialPlayer));
      setSel((hit ? hit.player : d.players[0]?.player) ?? null);
    }).catch(() => {});
    return () => { a = false; };
  }, [team, initialPlayer]);
  useEffect(() => { if (sel) onPlayer?.(sel); }, [sel, onPlayer]);   // 고른 선수를 주소에(공유·새로고침)
  if (!data) return (
    <div className="player-layout skel-wrap">
      <SkelCards n={8} cols="repeat(2, 1fr)" />
      <div className="skel-stack"><Skel h={300} r={16} /><Skel h={180} r={16} /></div>
    </div>
  );

  const CB = "#e0a05e";
  const onCard = (name: string) => {
    if (cmpMode) { if (name !== sel) { setCmp(name === cmp ? null : name); setCmpExt(null); } }
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
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 8 }}>
        <button className="sr-open" onClick={() => sel && toggleReport(true)} disabled={!sel} style={{ borderColor: hexA(accent, 0.5) }}
          title="고른 선수를 한 장으로 — 판단 요약·강약점·폼·가용성·계약·이적설·대안, 인쇄해 PDF 로">
          SCOUT REPORT <em>리포트</em>
        </button>
        <button onClick={() => { setCmpMode((m) => !m); setCmp(null); setCmpExt(null); }}
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
                <div className="pl-pos">{p.pos} · {p.age > 0 ? p.age : "—"} · <span style={{ color: t.light, fontWeight: 600 }}>{t.ko}</span></div>
                {p.role && <span className={"pl-role role-tag sm " + roleClass(p.role)}>{p.role}</span>}
              </button>
            );
          })}
        </div>
        <div className="pl-detail">
          {cmpMode
            ? (<>
                <ComparePicker exclude={sel ?? undefined} onPick={(r) => { setCmpExt(r); setCmp(null); }} />
                {sel && (cmpExt || cmp)
                  ? <ComparePanel team={team} a={sel} b={cmpExt?.player ?? cmp!} bTeam={cmpExt?.team} bLeague={cmpExt?.league}
                      accent={accent} onClear={() => { setCmp(null); setCmpExt(null); }} />
                  : <div className="card"><div className="mgr-meta" style={{ padding: 20 }}><b>B 선수</b>를 카드에서 고르거나 <b>다른 클럽·리그</b>에서 검색 · A: {sel}</div></div>}
              </>)
            : (sel && <Detail team={team} player={sel} accent={accent} heatmap={hm} />)}
        </div>
      </div>
      {report && sel && <ScoutReport team={team} player={sel} accent={accent} onClose={() => toggleReport(false)} />}
    </div>
  );
}
