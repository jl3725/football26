"use client";
import { useEffect, useState } from "react";
import { fmtEur, getDigest, type Digest } from "@/lib/api";
import { TONE } from "@/lib/meaning";
import AiNote from "./AiNote";
import { usePeek } from "./PlayerPeek";

// WEEKLY DIGEST — 지난 7일 이 리그에서 '바뀐 것'만(설계도 3단계 주간 스카우팅 다이제스트). 규칙 기반·숫자는 데이터 값.
// 결과·일정·경기 리뷰·이적 속보는 위 섹션이 이미 보여 주므로 여기선 폼 ▲▼ · 부상 변동 · 뉴스 언급 · 루머 · A매치만.
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

export default function WeeklyDigest({ league }: { league: string }) {
  const [d, setD] = useState<Digest | null>(null);
  const peek = usePeek();
  useEffect(() => { let a = true; setD(null); getDigest(league).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, [league]);
  if (!d) return null;
  const P = ({ name, club }: { name: string; club: string }) => (
    <span className="peekable wd-name" onClick={(e) => peek(e, { name, club })}>{name}</span>
  );
  return (
    <div className="wd-wrap">
      {d.summary && <AiNote text={d.summary.text} at={d.summary.at} label="THIS WEEK" sub="AI 주간 서술" />}
      {d.intl && (
        <div className="wd-intl">
          <b>{d.intl.label}</b> {md(d.intl.start)}–{md(d.intl.end)} <em>D-{d.intl.days_to}</em>
          <span> · 리그 휴식 — 팀 일정 탭에서 소집 선수·대표팀 경기</span>
        </div>
      )}
      <div className="wd-grid">
        <div className="card wd-card">
          <h3>FORM ▲<small>폼 지수 상승 · {md(d.form_since ?? d.since)} 이후 · 270분+</small></h3>
          {d.risers.length ? d.risers.map((m) => (
            <div className="wd-row" key={m.squad + m.player}>
              <P name={m.player} club={m.squad} /><span className="wd-sub">{m.squad}</span>
              <b style={{ color: TONE.best.c }}>{m.form} <small>▲{m.delta}</small></b>
            </div>)) : <p className="wd-empty">큰 변화 없음</p>}
        </div>
        <div className="card wd-card">
          <h3>FORM ▼<small>폼 지수 하락</small></h3>
          {d.fallers.length ? d.fallers.map((m) => (
            <div className="wd-row" key={m.squad + m.player}>
              <P name={m.player} club={m.squad} /><span className="wd-sub">{m.squad}</span>
              <b style={{ color: TONE.bad.c }}>{m.form} <small>▼{-m.delta}</small></b>
            </div>)) : <p className="wd-empty">큰 변화 없음</p>}
        </div>
        <div className="card wd-card">
          <h3>INJURIES<small>새 부상 {d.injuries.n_new} · 복귀 {d.injuries.n_back}</small></h3>
          {d.injuries.new.slice(0, 4).map((x) => (
            <div className="wd-row" key={"n" + x.squad + x.player}>
              <span className="wd-tag" style={{ color: TONE.bad.c, background: TONE.bad.bg }}>부상</span>
              <P name={x.player} club={x.squad} /><span className="wd-sub">{x.squad} · {x.injury}</span>
            </div>))}
          {d.injuries.back.slice(0, 4).map((x) => (
            <div className="wd-row" key={"b" + x.squad + x.player}>
              <span className="wd-tag" style={{ color: TONE.best.c, background: TONE.best.bg }}>복귀</span>
              <P name={x.player} club={x.squad} /><span className="wd-sub">{x.squad}</span>
            </div>))}
          {!d.injuries.n_new && !d.injuries.n_back && <p className="wd-empty">변동 없음</p>}
        </div>
        <div className="card wd-card">
          <h3>IN THE NEWS<small>이번 주 기사 언급</small></h3>
          {d.news.length ? d.news.map((x) => (
            <div className="wd-row" key={x.squad + x.player}>
              <P name={x.player} club={x.squad} /><span className="wd-sub">{x.squad}</span><b>{x.articles}<small>건</small></b>
            </div>)) : <p className="wd-empty">집계 전</p>}
        </div>
        <div className="card wd-card">
          <h3>RUMORS<small>새 이적 루머 {d.rumors.n}건</small></h3>
          {d.rumors.clubs.length > 0 && <div className="wd-clubs">{d.rumors.clubs.map((c) => <span key={c.club}>{c.club} {c.n}</span>)}</div>}
          {d.rumors.top.map((r, i) => (
            <div className="wd-row" key={i}>
              <span className="wd-name">{r.player}</span><span className="wd-sub">{r.from} → {r.to}</span>
              {r.value_eur != null && <b>{fmtEur(r.value_eur)}</b>}
            </div>))}
          {!d.rumors.n && <p className="wd-empty">새 루머 없음</p>}
        </div>
      </div>
    </div>
  );
}
