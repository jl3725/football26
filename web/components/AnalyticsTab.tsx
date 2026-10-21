"use client";
import { useEffect, useState } from "react";
import { feeLabel, getAnalytics, fmtEur, type Analytics, type Factor } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { idxMeaning, ppgMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Info from "./Info";
import TeamTerritory from "./TeamTerritory";
import { usePeek } from "./PlayerPeek";
import { SkelTab } from "./Skeleton";
import SectionHead from "./SectionHead";
import TeamTrendsBoard from "./TeamTrends";

const LINE_LABEL: Record<string, string> = { GK: "골키퍼", DEF: "수비", MID: "미드필드", ATT: "공격" };
const LINE_COLOR: Record<string, string> = { GK: "#7fb4f0", DEF: "#6aa6e0", MID: "#caa64e", ATT: "#d98169" };

function FactorCard({ f, kind, accent, team }: { f: Factor; kind: "s" | "w"; accent: string; team: string }) {
  const mn = idxMeaning(f.value);      // 팀 지수(50 = 리그 평균) — OVR 색(tier)을 쓰면 62·38 이 둘 다 회색이었다
  const peek = usePeek();
  return (
    <div className={`fac-card ${kind}`}>
      <div className="fac-top">
        <span className="fac-tag" style={{ color: kind === "s" ? "#4fc27f" : "#e07070" }}>{kind === "s" ? "강점" : "보강"}</span>
        <span className="fac-label">{f.label}</span>
        <span className="fac-val" style={{ color: mn.c }} title={`${f.value} — ${mn.label} (50 = 리그 평균)`}>{f.value}</span>
        <MeaningTag m={mn} sm />
      </div>
      {f.players.length > 0 && <div className="fac-players">
        {f.players.map((p, i) => (
          <span className="fac-chip peekable" key={i}
            onClick={(e) => peek(e, { name: p.player, club: team, hint: { photo: p.photo, ovr: p.ovr } })}>
            {p.photo ? <img src={p.photo} alt="" /> : <span className="fac-ph" />}
            {p.player.split(" ").slice(-1)[0]}
          </span>
        ))}
      </div>}
    </div>
  );
}

export default function AnalyticsTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Analytics | null>(null);
  const peek = usePeek();
  useEffect(() => { let a = true; getAnalytics(team).then((d) => a && setData(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!data) return <SkelTab />;

  const worst = Object.entries(data.line_share).sort((a, b) => b[1] - a[1])[0];
  // 결장 합계가 적으면 비율이 크게 흔들린다 — 5경기 미만이면 진단을 내지 않는다(브뤼헤 3경기로 '수비 67%')
  const missedTotal = Object.values(data.line_missed ?? {}).reduce((a, b) => a + b, 0);
  const weakFactor = data.factors.weaknesses[0];
  const s = data.transfer_summary;
  const tp = data.context.tier_ppg;

  return (
    <div className="fade">
      {/* 경기별 흐름 · 리그 백분위 · 득실 시간대(/api/team-trends) */}
      <TeamTrendsBoard team={team} color={data.color || accent} />

      {/* Match Factor Lab */}
      <div className="card" style={{ marginTop: 16 }}>
        <SectionHead title="MATCH FACTOR LAB" kr="강점 · 보강" meta="팀 지수 상·하위 · 기여 선수" />
        <div className="fac-grid">
          <div>
            <div className="fac-col-title" style={{ color: "#4fc27f" }}>▲ 강점 팩터</div>
            {data.factors.strengths.map((f, i) => <FactorCard key={i} f={f} kind="s" accent={accent} team={team} />)}
            {data.factors.strengths.length === 0 && <div className="fac-none">리그 평균(50)을 넘는 지표가 아직 없습니다</div>}
          </div>
          <div>
            <div className="fac-col-title" style={{ color: "#e07070" }}>▽ 보강 검토 <span className="fac-col-note">리그 평균(50) 아래</span></div>
            {data.factors.weaknesses.map((f, i) => <FactorCard key={i} f={f} kind="w" accent={accent} team={team} />)}
            {data.factors.weaknesses.length === 0 && <div className="fac-none">평균 아래 지표 없음 — 뚜렷한 약점이 보이지 않습니다</div>}
          </div>
        </div>
      </div>

      {/* 팀 포지셔널 맵 (스쿼드 히트맵 집계) */}
      <div className="card" style={{ marginTop: 16 }}>
        <SectionHead title="TERRITORY" kr="팀 포지셔널 맵" meta="평균 위치 · 연결 · 점유 구역" />
        <TeamTerritory team={team} accent={accent} />
      </div>

      {/* 상대·환경별 성과 */}
      <div className="card" style={{ marginTop: 16 }}>
        <SectionHead title="CONTEXT" kr="상대·환경별 성과" meta="리그 경기당 승점(PPG · 0~3)" />
        <div className="ctx-grid">
          {([["홈", data.context.home_ppg], ["원정", data.context.away_ppg], ["vs 상위권", tp.top], ["vs 중위권", tp.mid], ["vs 하위권", tp.bottom]] as [string, number | null][])
            .map(([l, v]) => {
              const mn = ppgMeaning(v);
              return (
                <div className="ctx-item" key={l}><span>{l}</span><b style={{ color: v == null ? undefined : mn.c }}>{v ?? "—"}</b>
                  {v != null && <MeaningTag m={mn} sm />}</div>
              );
            })}
        </div>
        <p className="sp5-note">경기당 승점 기준 <Info label="경기당 승점 기준"><p>38경기로 늘리면 2.2 ≈ 84점(우승권) · 1.75 ≈ 67점(유럽권) · 1.0 ≈ 38점(강등권).</p></Info></p>
      </div>

      {/* 부상 + 라인 공백 */}
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <SectionHead title="INJURY IMPACT" kr="부상 결장" meta="결장 경기 상위" />
          <div className="inj-list">
            {data.injuries.map((x, i) => (
              <div className="inj-row peekable" key={i}
                onClick={(e) => peek(e, { name: x.player, club: team, hint: { photo: x.photo } })}>
                {x.photo ? <img className="inj-photo" src={x.photo} alt="" /> : <span className="inj-photo ph" />}
                <span className="inj-line" style={{ background: hexA(LINE_COLOR[x.line] || "#888", 0.22), color: LINE_COLOR[x.line] || "#aaa" }}>{x.line}</span>
                <div className="inj-info">
                  <div className="inj-name">{x.player}</div>
                  <div className="inj-meta">{x.injury || "부상"} · {x.days_out}일 결장</div>
                </div>
                <span className="inj-gm">{x.games_missed}<span>경기</span></span>
              </div>
            ))}
            {data.injuries.length === 0 && <div className="mgr-meta">부상 결장 기록 없음</div>}
          </div>
        </div>
        <div className="card">
          <SectionHead title="ABSENCE BY LINE" kr="라인별 부상 공백" />
          <div className="ls-list">
            {["ATT", "MID", "DEF", "GK"].map((k) => (
              <div className="ls-row" key={k}>
                <span className="ls-label">{LINE_LABEL[k]}</span>
                <div className="ls-bar"><span style={{ width: `${data.line_share[k] || 0}%`, background: LINE_COLOR[k] }} /></div>
                <span className="ls-pct">{data.line_share[k] || 0}%</span>
              </div>
            ))}
          </div>
          {worst && worst[1] > 0 && missedTotal >= 5 && (
            <div className="diag" style={{ borderColor: hexA(accent, 0.4) }}>
              <b style={{ color: accent }}>진단</b> · 부상 공백 최다: <b>{LINE_LABEL[worst[0]]}</b> {worst[1]}%
              <Info label="부상 공백 진단">
                <p>부상 결장 {missedTotal}경기 중 {LINE_LABEL[worst[0]]} 라인이 {worst[1]}% — 그 라인 뎁스를 점검하세요.</p>
                <p className="muted">전력 자체가 약하다는 뜻은 아님 · 결장 합계 5경기 미만이면 진단하지 않음</p>
              </Info>
            </div>
          )}
        </div>
      </div>

      {/* 여름 영입 감사 */}
      {data.audit.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <SectionHead title="SIGNINGS AUDIT" kr="영입 감사" meta="출전 소화도 평가" />
          <div className="audit-grid">
            {data.audit.map((a, i) => (
              <div className={`audit-card ${a.tone} peekable`} key={i}
                onClick={(e) => peek(e, { name: a.player, club: team, hint: { photo: a.photo, pos: a.pos } })}>
                <div className="audit-top">
                  {a.photo ? <img className="audit-photo" src={a.photo} alt="" /> : <span className="audit-photo ph" />}
                  <span className="audit-name">{a.player}</span>
                  <span className="audit-fee">{feeLabel(a.fee_eur, a.fee_text)}</span>
                </div>
                <div className="audit-verdict">{a.verdict}</div>
                <div className="audit-stat">{a.minutes.toLocaleString()}′ · {a.goals}G {a.assists}A</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 감독 전술 진화 — 감독이 바뀐 팀만(현재 감독 소개·포메이션은 Overview MANAGER 한 곳, 탭 중복 금지 원칙) */}
      {data.manager_evo?.previous && (
        <div className="card" style={{ marginTop: 16 }}>
          <SectionHead title="MANAGER TACTICS" kr="감독 전술" />
          <div className="evo">
            <div className="evo-col current" style={{ borderColor: hexA(accent, 0.4) }}>
              <div className="evo-tag" style={{ color: accent }}>현재</div>
              <div className="evo-name">{data.manager_evo.name}</div>
              <div className="evo-form">{data.manager_evo.formation}</div>
              {data.manager_evo.style && <div className="evo-style">{data.manager_evo.style}</div>}
              {data.manager_evo.focus && <div className="evo-focus">{data.manager_evo.focus}</div>}
              {data.manager_evo.tactics
                ? <div className="evo-focus">{data.manager_evo.tactics}</div>
                : !data.manager_evo.style && <div className="evo-focus">전술 요약 준비 중
                  <Info label="전술 요약 출처"><p>전술 요약은 위키 문서에서 수집되는 대로 표시됩니다.</p></Info></div>}
            </div>
            {data.manager_evo.previous && (
              <div className="evo-col prev">
                <div className="evo-tag">이전 · {data.manager_evo.previous.name}</div>
                <div className="evo-form">{data.manager_evo.previous.formation}</div>
                {data.manager_evo.previous.style && <div className="evo-style">{data.manager_evo.previous.style}</div>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 핸드오프 */}
      <div className="handoff" style={{ borderColor: hexA(accent, 0.4) }}>
        <span className="ho-tag" style={{ background: accent }}>이적 시사점</span>
        <span>약점 보강: <b>{weakFactor ? `${weakFactor.label}(지수 ${weakFactor.value})` : "-"}</b></span>
        {worst && missedTotal >= 5 && <span>부상 공백: <b>{LINE_LABEL[worst[0]]}</b></span>}
        <span>이적 지출: <b>{fmtEur(s.spend)}</b></span>
        <span>영입/방출: <b>{s.in_count}/{s.out_count}</b></span>
      </div>
    </div>
  );
}
