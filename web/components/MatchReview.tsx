"use client";
import { useEffect, useMemo, useState } from "react";
import { getReview, type Fixture, type MatchReview, type ResultMatch, type ReviewSide } from "@/lib/api";
import { compLabel, compTone, splitKst } from "@/lib/match";
import { liveLabel, useLiveAll, type LiveEvent } from "@/lib/live";
import { useMatchPreview } from "@/lib/matchPreview";
import AiNote from "./AiNote";
import { Crest } from "./MatchCard";
import { Skel } from "./Skeleton";

// 경기 리뷰(Match Review) — /api/review/{event_id}: ESPN 경기 상세(득점·카드·팀 기록)로 만든 규칙 기반 리포트.
// 매치 서랍(종료·진행 중 경기)과 홈·리그 탭의 MATCH RECAP 카드가 함께 쓴다. 유료 AI 없음.

// 리뷰 불러오기 — 진행 중이면 1분마다 다시(서버 캐시도 1분)
export function useReview(eventId: string | null | undefined, comp: string, inPlay: boolean) {
  const [rv, setRv] = useState<MatchReview | null | undefined>(undefined);
  useEffect(() => {
    if (!eventId) { setRv(null); return; }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => getReview(eventId, comp)
      .then((x) => { if (alive) setRv(x); })
      .catch(() => { if (alive) setRv((v) => v ?? null); })
      .finally(() => { if (alive && inPlay) timer = setTimeout(load, 60000); });
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [eventId, comp, inPlay]);
  return rv;
}

const sideCls = (s: ReviewSide) => (s === "home" ? "h" : "a");

// 득점·퇴장·실축 페널티 타임라인 — 홈은 왼쪽, 원정은 오른쪽, 가운데 분
function Timeline({ rv }: { rv: MatchReview }) {
  type Ev = { m: number; minute: string; side: ReviewSide; kind: string; who: string; sub: string };
  const ev: Ev[] = [
    ...rv.goals.map((g) => ({ m: g.m, minute: g.minute, side: g.side, kind: g.kind === "og" ? "og" : "goal", who: g.scorer,
      sub: g.kind === "pen" ? "페널티킥" : g.kind === "og" ? "자책골" : g.assist ? `도움 ${g.assist}` : g.kind === "header" ? "헤더" : "" })),
    ...rv.cards.filter((c) => c.color === "red").map((c) => ({ m: c.m, minute: c.minute, side: c.side, kind: "red", who: c.player, sub: "퇴장" })),
    ...rv.pens.map((p) => ({ m: p.m, minute: p.minute, side: p.side, kind: "pmiss", who: p.player, sub: p.result === "saved" ? "PK 선방" : "PK 실축" })),
  ].sort((a, b) => a.m - b.m);
  if (!ev.length) return <p className="pv-empty">{rv.state === "in" ? "아직 득점 없음" : "득점 없이 끝났습니다"}</p>;
  let htShown = false;
  return (
    <div className="rv5-tl">
      {ev.map((e, i) => {
        const ht = !htShown && rv.ht && e.m > 45 && !e.minute.startsWith("45'");
        if (ht) htShown = true;
        return (
          <div key={i}>
            {ht && <div className="rv5-ht"><span>HT {rv.ht!.home}-{rv.ht!.away}</span></div>}
            <div className={`rv5-ev ${sideCls(e.side)}`}>
              <div className="rv5-ev-side">
                {e.side === "home" && <><span className="rv5-ev-t"><b>{e.who}</b>{e.sub && <em>{e.sub}</em>}</span><i className={`rv5-ico ${e.kind}`} /></>}
              </div>
              <span className="rv5-min">{e.minute}</span>
              <div className="rv5-ev-side">
                {e.side === "away" && <><i className={`rv5-ico ${e.kind}`} /><span className="rv5-ev-t"><b>{e.who}</b>{e.sub && <em>{e.sub}</em>}</span></>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StatBars({ rv, hc, ac }: { rv: MatchReview; hc: string; ac: string }) {
  if (!rv.stats.length) return null;
  const fmt = (v: number, f: string) => (f === "int" ? String(Math.round(v)) : `${Math.round(v)}%`);
  return (
    <>
      {rv.stats.map((s) => {
        const tot = s.h + s.a;
        const share = s.fmt === "int" ? (tot ? (s.h / tot) * 100 : 50) : (s.h / Math.max(1, s.h + s.a)) * 100;
        const lowGood = s.key === "foulsCommitted" || s.key === "offsides";
        const hb = lowGood ? s.h < s.a : s.h > s.a, ab = lowGood ? s.a < s.h : s.a > s.h;
        return (
          <div className="pv-cmp" key={s.key}>
            <b className={hb ? "up" : ""}>{fmt(s.h, s.fmt)}</b>
            <div className="pv-cmp-mid"><span>{s.label}</span>
              <div className="mc5-bar"><span style={{ flexBasis: `${share}%`, background: hc }} /><span style={{ flexBasis: `${100 - share}%`, background: ac }} /></div>
            </div>
            <b className={ab ? "up" : ""}>{fmt(s.a, s.fmt)}</b>
          </div>
        );
      })}
    </>
  );
}

// 매치 서랍 안 리뷰 — 헤드라인·요약·타임라인·기록·데이터 기준 수훈 선수·예측 적중
export function ReviewSections({ m, inPlay, hc, ac }: { m: Fixture; inPlay: boolean; hc: string; ac: string }) {
  const rv = useReview(m.event_id, m.comp_code, inPlay);
  if (rv === undefined) {
    return <section><h3>{inPlay ? "LIVE REPORT" : "MATCH REVIEW"}<span>경기 리뷰</span></h3><Skel h={18} style={{ marginBottom: 10 }} /><Skel h={14} w="90%" style={{ marginBottom: 8 }} /><Skel h={14} w="70%" /></section>;
  }
  if (rv === null) return <section><h3>MATCH REVIEW<span>경기 리뷰</span></h3><p className="pv-empty">경기 상세 기록을 불러오지 못했습니다(ESPN). 잠시 뒤 다시 열어 주세요.</p></section>;
  const name = { home: m.home.team, away: m.away.team };
  return (
    <>
      <section className="rv5">
        <h3>{rv.state === "in" ? "LIVE REPORT" : "MATCH REVIEW"}<span>{rv.state === "in" ? "실시간 리포트 · 1분마다 갱신" : "경기 리뷰 · ESPN 기록 기반"}</span></h3>
        <p className="rv5-head">{rv.headline}</p>
        {rv.ai && <AiNote text={rv.ai.text} at={rv.ai.at} label="AI MATCH REPORT" sub="AI 경기 리포트" />}
        {rv.lines.length > 0 && <ul className="pv-points">{rv.lines.map((l) => <li key={l}>{l}</li>)}</ul>}
        {(rv.star || rv.predictions.length > 0) && (
          <div className="rv5-chips">
            {rv.star && (
              <span className="rv5-star" title="골 2점 · 도움 1점 · 승리 팀 +1 (데이터 기준)">
                <em>{rv.state === "in" ? "TOP PERFORMER" : "STAR OF THE MATCH"}</em><b>{rv.star.player}</b>
                <span>{name[rv.star.side]}{rv.star.goals ? ` · ${rv.star.goals}골` : ""}{rv.star.assists ? ` · ${rv.star.assists}도움` : ""}</span>
              </span>
            )}
            {rv.state === "post" && rv.predictions.map((p) => (
              <span className={`rv5-pred ${p.hit ? "hit" : "miss"}`} key={p.source}>
                <em>{p.source === "팬 투표" ? "FAN VOTE" : p.source === "모델" ? "MODEL" : "CLUBELO"}</em><b>{p.hit ? "적중" : "빗나감"}</b><span>{p.pick} {Math.round(p.p * 100)}%</span>
              </span>
            ))}
          </div>
        )}
      </section>
      <section>
        <h3>TIMELINE<span>득점 · 퇴장 · PK 실축</span></h3>
        <Timeline rv={rv} />
      </section>
      {rv.stats.length > 0 && (
        <section>
          <h3>MATCH STATS<span>경기 기록{rv.state === "in" ? " · 현재까지" : ""}</span></h3>
          {/* 어느 쪽이 어느 팀인지 — 막대 색만으로는 원정 경기에서 헷갈렸다(2026-10-20 점검) */}
          <div className="rv5-sides"><b style={{ color: hc }}>{name.home}</b><span>HOME · AWAY</span><b style={{ color: ac }}>{name.away}</b></div>
          <StatBars rv={rv} hc={hc} ac={ac} />
        </section>
      )}
      {(rv.venue || rv.attendance) && (
        <p className="pv-note">{[rv.venue, rv.attendance ? `관중 ${rv.attendance.toLocaleString()}명` : ""].filter(Boolean).join(" · ")} · 기록 출처 ESPN</p>
      )}
    </>
  );
}

// ── MATCH RECAP: 최근 주요 결과 3경기 리뷰 카드(홈·리그 탭) ──
type RecapItem = { m: Fixture; h: number; a: number; live?: LiveEvent };

function pickRecap(results: ResultMatch[], extra: Fixture[], live: Record<string, LiveEvent>, n: number): RecapItem[] {
  const known = new Set(results.map((r) => r.event_id));
  const items: (RecapItem & { score: number })[] = [];
  for (const f of extra) {   // 아직 결과 파일에 없는 방금 끝난 경기(라이브 FT)
    const lv = f.event_id ? live[f.event_id] : undefined;
    if (!lv || lv.state !== "post" || known.has(f.event_id)) continue;
    known.add(f.event_id);
    items.push({ m: f, h: Number(lv.home.score ?? 0), a: Number(lv.away.score ?? 0), live: lv, score: f.big + 15 });
  }
  for (const r of results) {
    if (!r.event_id) continue;
    // 빅매치 점수 + 이변(줄임 15) + 골 많은 경기 + 큰 클럽(OVR) − 지난 날짜 — 작은 리그 이변 3장만 뽑혀
    // Betis 2-5 Barça·Bayern 6-1 Leipzig 가 빠졌다(2026-10-20 점검)
    const goals = r.home.goals + r.away.goals;
    const topOvr = Math.max(r.home.ovr ?? 0, r.away.ovr ?? 0);
    items.push({ m: r, h: r.home.goals, a: r.away.goals,
      score: r.big + (r.upset ? 15 : 0) + 3 * Math.min(goals, 7) + Math.max(0, topOvr - 80) * 1.5 + 12 * Math.min(0, r.d_day ?? 0) });
  }
  // 리그 다양성 — 한 리그(대회)에서 1경기씩 먼저, 모자라면 나머지에서
  const sorted = items.sort((x, y) => y.score - x.score);
  const out: typeof sorted = [], seen = new Set<string>();
  const keyOf = (it: RecapItem) => it.m.comp_code || it.m.home.league || "";
  for (const it of sorted) if (out.length < n && !seen.has(keyOf(it))) { out.push(it); seen.add(keyOf(it)); }
  for (const it of sorted) if (out.length < n && !out.includes(it)) out.push(it);
  return out;
}

function RecapCard({ it }: { it: RecapItem }) {
  const preview = useMatchPreview();
  const rv = useReview(it.m.event_id, it.m.comp_code, false);
  const { m, h, a } = it;
  const up = (m as ResultMatch).upset;
  return (
    <button className="card rc5" onClick={() => preview?.(m)}>
      <div className="rc5-top">
        <span className={`bdg ${compTone(m.comp_code)}`}>{compLabel(m)}</span>
        <span className="rc5-when">{it.live ? liveLabel(it.live) : splitKst(m.kst).date}</span>
        {up && <span className="bdg warn">UPSET</span>}
      </div>
      <div className="rc5-score">
        <span className={`rc5-t${a > h ? " lose" : ""}`}><Crest s={m.home} size={30} /><b>{m.home.team}</b></span>
        <span className="rc5-num"><span className={h > a ? "w" : ""}>{h}</span>–<span className={a > h ? "w" : ""}>{a}</span></span>
        <span className={`rc5-t r${h > a ? " lose" : ""}`}><b>{m.away.team}</b><Crest s={m.away} size={30} /></span>
      </div>
      {rv === undefined ? <><Skel h={16} style={{ marginBottom: 8 }} /><Skel h={12} w="80%" /></>
        : rv ? (
          <>
            <p className="rc5-head">{rv.headline}</p>
            {rv.lines[0] && <p className="rc5-line">{rv.lines.find((l) => l.startsWith("결승골")) ?? rv.lines[0]}</p>}
            <div className="rc5-foot">
              {rv.star && <span className="rc5-star">★ {rv.star.player}{rv.star.goals ? ` ${rv.star.goals}G` : ""}{rv.star.assists ? ` ${rv.star.assists}A` : ""}</span>}
              <span className="rc5-more">REVIEW →</span>
            </div>
          </>
        ) : <p className="rc5-line">{up || "상세 기록을 불러오지 못했습니다"}</p>}
    </button>
  );
}

export function MatchRecap({ results, extra = [], n = 3 }: { results: ResultMatch[]; extra?: Fixture[]; n?: number }) {
  const live = useLiveAll();
  const items = useMemo(() => pickRecap(results, extra, live, n), [results, extra, live, n]);
  if (!items.length) return null;
  return <div className="rc5-grid">{items.map((it) => <RecapCard key={it.m.event_id!} it={it} />)}</div>;
}
