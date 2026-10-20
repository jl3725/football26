"use client";
import { useEffect, useState } from "react";
import { getOpsStatus, type OpsAgent, type OpsFeed, type OpsState, type OpsStatus } from "@/lib/api";
import { TONE } from "@/lib/meaning";
import AiNote from "./AiNote";

// DATA STATUS — 수집 에이전트마다 '마지막 성공이 언제였고, 허용 지연을 넘었는지'(설계도 1단계).
// 원천: /api/ops/status = src/agent_registry.py(소스·주기·허용 지연) × data/ops/runs(실행 원장) × watchdog 결과.
// 사람이 Actions 로그를 뒤지지 않아도 어느 데이터가 언제 멈췄는지 이 화면에서 보이게 한다.

export const STATE: Record<OpsState, { ko: string; en: string; tone: keyof typeof TONE }> = {
  ok: { ko: "정상", en: "OK", tone: "best" },
  warn: { ko: "일부 실패", en: "PARTIAL", tone: "weak" },
  late: { ko: "지연", en: "LATE", tone: "bad" },
  nodata: { ko: "기록 대기", en: "WAITING", tone: "avg" },
};

const kst = (iso: string | null) => iso
  ? new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
  : "—";

function ago(h: number | null): string {
  if (h == null) return "성공 기록 없음";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}분 전`;
  if (h < 48) return `${Math.round(h)}시간 전`;
  return `${Math.round(h / 24)}일 전`;
}

function Chip({ s }: { s: OpsState }) {
  const t = TONE[STATE[s].tone];
  return <span className="ds-chip" style={{ color: t.c, background: t.bg }}>{STATE[s].en}<small>{STATE[s].ko}</small></span>;
}

function FeedRow({ f }: { f: OpsFeed }) {
  const t = TONE[STATE[f.state].tone];
  return (
    <li className="ds-feed">
      <span className="ds-dot" style={{ background: t.c }} title={STATE[f.state].ko} />
      <div className="ds-feed-main">
        <div className="ds-feed-top">
          <b>{f.label}</b>
          <span className="ds-feed-age" style={{ color: f.state === "late" ? t.c : undefined }}>
            {f.state === "nodata" ? "첫 실행 기록 대기" : `마지막 성공 ${ago(f.age_h)}`}
          </span>
        </div>
        <div className="ds-feed-sub">
          {f.cadence} · 허용 {f.max_age_h >= 48 ? `${Math.round(f.max_age_h / 24)}일` : `${f.max_age_h}시간`}
          {f.runs_24h > 0 && <> · 24시간 {f.runs_24h}회{f.fails_24h > 0 && <em> · 실패 {f.fails_24h}</em>}</>}
        </div>
        {f.failing.length > 0 && (
          <div className="ds-fails" title="단계×리그마다 가장 최근 실행이 실패한 것">
            {f.failing.slice(0, 8).map((x) => <span key={x}>{x}</span>)}
            {f.n_failing > 8 && <span>+{f.n_failing - 8}</span>}
          </div>
        )}
      </div>
    </li>
  );
}

function AgentCard({ a }: { a: OpsAgent }) {
  return (
    <section className={`ds-agent card s-${a.state}`}>
      <header>
        <div>
          <h3>{a.en}<small>{a.ko}</small></h3>
          <p>{a.does}</p>
        </div>
        <Chip s={a.state} />
      </header>
      <ul>{a.feeds.map((f) => <FeedRow key={f.key} f={f} />)}</ul>
      <footer>
        <span>SOURCE · {a.sources.join(" · ")}</span>
        {a.checks.length > 0 && <span>CHECK · {a.checks.join(" · ")}</span>}
        {a.extras.map((x) => <span key={x}>{x}</span>)}
      </footer>
    </section>
  );
}

export default function DataStatus() {
  const [d, setD] = useState<OpsStatus | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { getOpsStatus().then(setD).catch(() => setErr(true)); }, []);

  if (err) return <div className="ds-wrap"><p className="ds-note">상태를 불러오지 못했습니다 — 서버가 깨어나는 중일 수 있습니다. 잠시 뒤 새로고침해 주세요.</p></div>;
  if (!d) return <div className="ds-wrap"><p className="ds-note">불러오는 중…</p></div>;

  const wdFail = d.watchdog ? Object.entries(d.watchdog.results).filter(([, v]) => v.length) : [];
  const order: OpsState[] = ["late", "warn", "nodata", "ok"];
  const agents = [...d.agents].sort((x, y) => order.indexOf(x.state) - order.indexOf(y.state));

  return (
    <div className="ds-wrap">
      <div className="ds-head">
        <a href="/" className="ds-back">← SCOUT.AI</a>
        <h1>DATA STATUS<small>데이터 상태 · 수집 에이전트</small></h1>
        <p className="ds-note">
          에이전트마다 마지막 성공 시각과 허용 지연을 비교합니다. 실행 원장 기록 시작 {kst(d.first_entry)} · 갱신 {kst(d.generated)}
        </p>
      </div>

      <div className="ds-summary">
        {(["ok", "warn", "late", "nodata"] as OpsState[]).map((s) => {
          const t = TONE[STATE[s].tone];
          return (
            <div key={s} className="ds-count" style={{ borderColor: d.counts[s] && s !== "ok" ? t.c : undefined }}>
              <b style={{ color: t.c }}>{d.counts[s] ?? 0}</b>
              <span>{STATE[s].en}<small>{STATE[s].ko}</small></span>
            </div>
          );
        })}
      </div>

      <section className="ds-watch card">
        <h3>WATCHDOG<small>운영 점검 · 매일 17:00</small></h3>
        {!d.watchdog ? <p className="ds-note">아직 점검 결과가 없습니다(다음 점검 뒤 표시).</p>
          : wdFail.length === 0 ? <p className="ds-ok">{kst(d.watchdog.checked)} 점검 — {Object.keys(d.watchdog.results).length}개 항목 모두 정상</p>
          : (
            <>
              <p className="ds-note">{kst(d.watchdog.checked)} 점검 — {wdFail.length}개 항목 문제(GitHub 이슈 'watchdog' 에도 열림)</p>
              <ul className="ds-wd">
                {wdFail.map(([k, v]) => <li key={k}><b>{k}</b>{v.map((x, i) => <span key={i}>{x}</span>)}</li>)}
              </ul>
              {d.watchdog.ai_cause && (
                <AiNote lines={d.watchdog.ai_cause.split("\n").map((l) => l.replace(/^-\s*/, "")).filter(Boolean)}
                  at={d.watchdog.checked} label="LIKELY CAUSE" sub="AI 추정 원인 · 참고용" check="숫자 원자료 대조" />
              )}
            </>
          )}
      </section>

      <div className="ds-grid">{agents.map((a) => <AgentCard key={a.key} a={a} />)}</div>

      {d.recent_failures.length > 0 && (
        <section className="ds-recent card">
          <h3>RECENT FAILURES<small>최근 실패 단계</small></h3>
          <div className="ds-table">
            <table>
              <thead><tr><th>시각</th><th>에이전트</th><th>단계</th><th>실행</th><th>메모</th></tr></thead>
              <tbody>
                {d.recent_failures.map((e, i) => (
                  <tr key={i}>
                    <td>{kst(e.t)}</td><td>{e.agent ?? "—"}</td>
                    <td>{e.step}{e.league ? ` · ${e.league}` : ""}</td>
                    <td>{e.runner}{e.code == null ? " · 시간 초과" : ` · exit ${e.code}`}</td>
                    <td>{e.note ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {d.unregistered_steps.length > 0 && (
        <p className="ds-note">레지스트리에 없는 단계: {d.unregistered_steps.join(", ")} — src/agent_registry.py 에 추가 필요</p>
      )}
    </div>
  );
}
