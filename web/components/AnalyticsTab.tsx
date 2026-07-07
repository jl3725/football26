"use client";
import { useEffect, useState } from "react";
import { getAnalytics, fmtEur, type Analytics, type Factor } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";

const LINE_LABEL: Record<string, string> = { GK: "골키퍼", DEF: "수비", MID: "미드필드", ATT: "공격" };
const LINE_COLOR: Record<string, string> = { GK: "#7fb4f0", DEF: "#6aa6e0", MID: "#caa64e", ATT: "#d98169" };

function FactorCard({ f, kind, accent }: { f: Factor; kind: "s" | "w"; accent: string }) {
  const t = tier(f.value);
  return (
    <div className={`fac-card ${kind}`}>
      <div className="fac-top">
        <span className="fac-tag" style={{ color: kind === "s" ? "#4fc27f" : "#e07070" }}>{kind === "s" ? "강점" : "보강"}</span>
        <span className="fac-label">{f.label}</span>
        <span className="fac-val" style={{ color: t.light }}>{f.value}</span>
      </div>
      <div className="fac-players">
        {f.players.map((p, i) => (
          <span className="fac-chip" key={i}>
            {p.photo ? <img src={p.photo} alt="" /> : <span className="fac-ph" />}
            {p.player.split(" ").slice(-1)[0]}
          </span>
        ))}
        {f.players.length === 0 && <span className="fac-none">—</span>}
      </div>
    </div>
  );
}

export default function AnalyticsTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Analytics | null>(null);
  useEffect(() => { let a = true; getAnalytics(team).then((d) => a && setData(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;

  const worst = Object.entries(data.line_share).sort((a, b) => b[1] - a[1])[0];
  const s = data.transfer_summary;
  const tp = data.context.tier_ppg;

  return (
    <div className="fade">
      {/* Match Factor Lab */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Match Factor Lab · 강점 / 보강</h3>
        <div className="fac-grid">
          <div>
            <div className="fac-col-title" style={{ color: "#4fc27f" }}>▲ 강점 팩터</div>
            {data.factors.strengths.map((f, i) => <FactorCard key={i} f={f} kind="s" accent={accent} />)}
          </div>
          <div>
            <div className="fac-col-title" style={{ color: "#e07070" }}>▽ 보강 검토</div>
            {data.factors.weaknesses.map((f, i) => <FactorCard key={i} f={f} kind="w" accent={accent} />)}
          </div>
        </div>
      </div>

      {/* 상대·환경별 성과 */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3>상대·환경별 성과 (PPG)</h3>
        <div className="ctx-grid">
          <div className="ctx-item"><span>홈</span><b style={{ color: accent }}>{data.context.home_ppg}</b></div>
          <div className="ctx-item"><span>원정</span><b style={{ color: accent }}>{data.context.away_ppg}</b></div>
          <div className="ctx-item"><span>상위권</span><b>{tp.top}</b></div>
          <div className="ctx-item"><span>중위권</span><b>{tp.mid}</b></div>
          <div className="ctx-item"><span>하위권</span><b>{tp.bottom}</b></div>
        </div>
      </div>

      {/* 부상 + 라인 공백 */}
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>부상 임팩트 · 결장 경기 상위</h3>
          <div className="inj-list">
            {data.injuries.map((x, i) => (
              <div className="inj-row" key={i}>
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
          <h3>라인별 부상 공백 비중</h3>
          <div className="ls-list">
            {["ATT", "MID", "DEF", "GK"].map((k) => (
              <div className="ls-row" key={k}>
                <span className="ls-label">{LINE_LABEL[k]}</span>
                <div className="ls-bar"><span style={{ width: `${data.line_share[k] || 0}%`, background: LINE_COLOR[k] }} /></div>
                <span className="ls-pct">{data.line_share[k] || 0}%</span>
              </div>
            ))}
          </div>
          {worst && worst[1] > 0 && (
            <div className="diag" style={{ borderColor: hexA(accent, 0.4) }}>
              <b style={{ color: accent }}>진단</b> · 부상 공백이 <b>{LINE_LABEL[worst[0]]}</b>에 {worst[1]}% 집중 — 해당 라인 뎁스 보강이 우선순위입니다.
            </div>
          )}
        </div>
      </div>

      {/* 여름 영입 감사 */}
      {data.audit.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>여름 영입 감사 · 소화도 평가</h3>
          <div className="audit-grid">
            {data.audit.map((a, i) => (
              <div className={`audit-card ${a.tone}`} key={i}>
                <div className="audit-top">
                  {a.photo ? <img className="audit-photo" src={a.photo} alt="" /> : <span className="audit-photo ph" />}
                  <span className="audit-name">{a.player}</span>
                  <span className="audit-fee">{a.fee_text || "-"}</span>
                </div>
                <div className="audit-verdict">{a.verdict}</div>
                <div className="audit-stat">{a.minutes.toLocaleString()}′ · {a.goals}G {a.assists}A</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 감독 전술 진화 */}
      {data.manager_evo && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>감독 전술</h3>
          <div className="evo">
            <div className="evo-col current" style={{ borderColor: hexA(accent, 0.4) }}>
              <div className="evo-tag" style={{ color: accent }}>현재</div>
              <div className="evo-name">{data.manager_evo.name}</div>
              <div className="evo-form">{data.manager_evo.formation}</div>
              <div className="evo-style">{data.manager_evo.style}</div>
              {data.manager_evo.focus && <div className="evo-focus">{data.manager_evo.focus}</div>}
            </div>
            {data.manager_evo.previous && (
              <div className="evo-col prev">
                <div className="evo-tag">이전 · {data.manager_evo.previous.name}</div>
                <div className="evo-form">{data.manager_evo.previous.formation}</div>
                <div className="evo-style">{data.manager_evo.previous.style}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 핸드오프 */}
      <div className="handoff" style={{ borderColor: hexA(accent, 0.4) }}>
        <span className="ho-tag" style={{ background: accent }}>TRANSFER AGENT 입력 신호</span>
        <span>약점 보강: <b>{worst ? LINE_LABEL[worst[0]] : "-"}</b></span>
        <span>이적 지출: <b>{fmtEur(s.spend)}</b></span>
        <span>영입/방출: <b>{s.in_count}/{s.out_count}</b></span>
      </div>
    </div>
  );
}
