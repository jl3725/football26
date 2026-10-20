"use client";
import { useEffect, useMemo, useState } from "react";
import { getIntlComp, getIntlHub, getIntlMatches, type IntlCompCard, type IntlCompDetail, type IntlHub, type IntlMatch } from "@/lib/api";
import SectionHead from "./SectionHead";
import { Skel, SkelRows } from "./Skeleton";
import WorldCup from "./WorldCup";

// INTERNATIONAL — 국가대표 허브. 대회는 손으로 적지 않고 ESPN 리그 목록에서 자동 발견(src/intl_comps.py),
// 상태(예정·진행·종료·우승)는 일정·결과에서 계산한다. 지저분하지 않게:
//   NOW         지금 중요한 것만(진행·임박한 대회, 다음 A매치 기간, 오늘 경기)
//   MATCHES     기본 '주요 경기'(FIFA 30위 안·우리 리그 선수 4명+ 소집국) — 대륙·종류 칩으로 좁힘
//   TOURNAMENTS 대륙별(세계·유럽·아시아·아프리카·남미·북중미) — 본선 먼저, 끝난 예선은 접어 둠
type Tab = "now" | "matches" | "tournaments";
const STATUS: Record<string, { en: string; c: string }> = {
  live: { en: "LIVE", c: "#4fc27f" }, upcoming: { en: "UPCOMING", c: "#e0a53a" }, finished: { en: "FINISHED", c: "#8a94a8" },
};
const md = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "");
const dday = (d: string, today: string) => Math.round((new Date(d).getTime() - new Date(today).getTime()) / 864e5);
const kst = (iso: string) => {
  if (!iso) return "";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? "" : t.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
};

function CompCard({ c, today, onOpen }: { c: IntlCompCard; today: string; onOpen: (c: IntlCompCard) => void }) {
  const e = c.edition;
  const st = STATUS[e.status];
  return (
    <button className="it-comp" onClick={() => onOpen(c)}>
      <div className="it-comp-top">
        <span className="it-kind">{c.kind_ko}</span>
        <span className="it-st" style={{ color: st.c, borderColor: st.c }}>
          {e.status === "upcoming" ? `D-${dday(e.start, today)}` : st.en}
        </span>
      </div>
      <b className="it-comp-name">{c.name_ko}</b>
      <span className="it-comp-sub">{e.season} · {md(e.start)}~{md(e.end)} · {e.played}/{e.matches}경기</span>
      {e.champion && <span className="it-champ">🏆 {e.champion}{e.runner_up ? <em> · 준우승 {e.runner_up}</em> : null}</span>}
    </button>
  );
}

function MatchRow({ m }: { m: IntlMatch }) {
  const done = m.state === "post" && m.hg != null && m.ag != null;
  return (
    <div className="it-m">
      <span className="it-m-when">{kst(m.kickoff) || md(m.date)}</span>
      <span className="it-m-comp">{m.comp}{m.stage ? ` · ${m.stage}` : ""}</span>
      <span className="it-m-h">{m.home}{m.home_logo ? <img src={m.home_logo} alt="" /> : null}</span>
      <b className="it-m-s">{done ? `${m.hg}-${m.ag}` : "vs"}</b>
      <span className="it-m-a">{m.away_logo ? <img src={m.away_logo} alt="" /> : null}{m.away}</span>
    </div>
  );
}

function CompDetail({ code, season, accent, onBack, onPickTeam }: {
  code: string; season: string; accent: string; onBack: () => void; onPickTeam: (t: string, league?: string) => void;
}) {
  const [d, setD] = useState<IntlCompDetail | null>(null);
  const [s, setS] = useState(season);
  useEffect(() => { let a = true; setD(null); getIntlComp(code, s).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, [code, s]);
  // 월드컵은 조별 순위·득점왕·차출 클럽까지 있는 전용 화면(기록 보관)
  if (code === "fifa.world" && (!d || d.edition.season === "2026")) return (
    <div>
      <button className="it-back" onClick={onBack}>← INTERNATIONAL</button>
      <WorldCup accent={accent} onPickTeam={onPickTeam} />
    </div>
  );
  if (!d) return <div className="skel-wrap"><Skel h={60} r={14} /><SkelRows n={8} /></div>;
  const stages = new Map<string, IntlMatch[]>();
  for (const m of d.matches) {
    const k = m.stage || (m.state === "post" ? "결과" : "일정");
    stages.set(k, [...(stages.get(k) ?? []), m]);
  }
  return (
    <div className="it-detail">
      <button className="it-back" onClick={onBack}>← INTERNATIONAL</button>
      <div className="card it-hero">
        <span className="it-kind">{d.kind_ko}</span>
        <h2>{d.name_ko}</h2>
        <p>{d.edition.season} · {d.edition.start} ~ {d.edition.end} · {d.edition.played}/{d.edition.matches}경기 · {STATUS[d.edition.status].en}</p>
        {d.edition.champion && <p className="it-champ big">🏆 우승 {d.edition.champion}{d.edition.runner_up ? ` · 준우승 ${d.edition.runner_up}` : ""}</p>}
        {d.editions.length > 1 && (
          <div className="it-chips">{d.editions.map((e) => (
            <button key={e.season} className={e.season === d.edition.season ? "on" : ""} onClick={() => setS(e.season)}>{e.season}</button>
          ))}</div>
        )}
      </div>
      {[...stages.entries()].map(([k, ms]) => (
        <section className="card it-sec" key={k}>
          <SectionHead title={k.toUpperCase()} meta={`${ms.length}경기`} />
          <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
        </section>
      ))}
      {d.matches.length === 0 && <p className="pv-empty">이 회차의 경기 정보가 아직 없습니다.</p>}
    </div>
  );
}

export default function International({ accent, onPickTeam, initialComp }: {
  accent: string; onPickTeam: (t: string, league?: string) => void; initialComp?: string;
}) {
  const [hub, setHub] = useState<IntlHub | null>(null);
  // 주소 #tournaments·#matches 로 탭 바로 열기(공유·점검)
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "now";
    const h = window.location.hash.replace("#", "");
    return h === "matches" || h === "tournaments" ? h : "now";
  });
  const [open, setOpen] = useState<{ code: string; season: string } | null>(initialComp ? { code: initialComp, season: "" } : null);
  const [when, setWhen] = useState<"upcoming" | "recent">("upcoming");
  const [scope, setScope] = useState<"key" | "all">("key");
  const [conf, setConf] = useState("");
  const [kind, setKind] = useState("");
  const [ms, setMs] = useState<IntlMatch[] | null>(null);
  const [showDone, setShowDone] = useState(false);
  useEffect(() => { let a = true; getIntlHub().then((x) => a && setHub(x)).catch(() => {}); return () => { a = false; }; }, []);
  useEffect(() => {
    if (tab !== "matches" && tab !== "now") return;
    let a = true; setMs(null);
    getIntlMatches({ scope, when, conf, kind, limit: tab === "now" ? 12 : 120 }).then((x) => a && setMs(x.matches)).catch(() => a && setMs([]));
    return () => { a = false; };
  }, [tab, scope, when, conf, kind]);
  const today = hub?.today ?? new Date().toISOString().slice(0, 10);
  const confs = useMemo(() => (hub?.by_conf ?? []).map((c) => ({ k: c.conf, en: c.en, ko: c.ko })), [hub]);

  if (open) return <CompDetail code={open.code} season={open.season} accent={accent} onBack={() => setOpen(null)} onPickTeam={onPickTeam} />;
  if (!hub) return <div className="skel-wrap"><Skel h={90} r={16} /><SkelRows n={6} /></div>;
  const w = hub.window;
  return (
    <div className="it">
      <div className="it-tabs">
        {(["now", "matches", "tournaments"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {t === "now" ? "NOW" : t === "matches" ? "MATCHES" : "TOURNAMENTS"}<em>{t === "now" ? "지금" : t === "matches" ? "A매치" : "대륙별 대회"}</em>
          </button>
        ))}
      </div>

      {tab === "now" && (
        <>
          <div className="it-now">
            {hub.live.map((c) => (
              <div className="card it-now-c live" key={c.code} onClick={() => setOpen({ code: c.code, season: c.edition.season })}>
                <span className="it-st" style={{ color: STATUS.live.c, borderColor: STATUS.live.c }}>LIVE</span>
                <b>{c.name_ko}</b><span>{md(c.edition.start)}~{md(c.edition.end)} · {c.edition.played}/{c.edition.matches}경기</span>
              </div>
            ))}
            {w && (
              <div className="card it-now-c">
                <span className="it-st" style={{ color: hub.window_state === "now" ? STATUS.live.c : STATUS.upcoming.c, borderColor: hub.window_state === "now" ? STATUS.live.c : STATUS.upcoming.c }}>
                  {hub.window_state === "now" ? "NOW" : `D-${dday(w.start, today)}`}
                </span>
                <b>{w.label}</b>
                <span>{md(w.start)}~{md(w.end)} · {w.matches}경기 · 지난 소집 기준 우리 리그 선수 {hub.callups}명(명단 발표 뒤 갱신) · 팀 화면 일정 탭에서 클럽별 소집 선수</span>
              </div>
            )}
            {hub.next_tournament && (
              <div className="card it-now-c" onClick={() => setOpen({ code: hub.next_tournament!.code, season: hub.next_tournament!.edition.season })}>
                <span className="it-st" style={{ color: STATUS.upcoming.c, borderColor: STATUS.upcoming.c }}>D-{dday(hub.next_tournament.edition.start, today)}</span>
                <b>{hub.next_tournament.name_ko} {hub.next_tournament.edition.season}</b>
                <span>{md(hub.next_tournament.edition.start)}~{md(hub.next_tournament.edition.end)} · {hub.next_tournament.edition.matches}경기 · 리그가 계속돼 소집 선수는 클럽 경기를 빠짐</span>
              </div>
            )}
          </div>
          <section className="card it-sec">
            <SectionHead title="NEXT KEY MATCHES" kr="다가오는 주요 A매치" meta="FIFA 30위 안 · 우리 리그 선수 4명+ 소집국" />
            {ms === null ? <SkelRows n={6} /> : ms.length ? <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
              : <p className="pv-empty">예정된 주요 A매치가 없습니다.</p>}
            <button className="it-more" onClick={() => setTab("matches")}>전체 A매치 보기 →</button>
          </section>
        </>
      )}

      {tab === "matches" && (
        <section className="card it-sec">
          <div className="it-filters">
            <div className="it-chips">
              {(["upcoming", "recent"] as const).map((v) => <button key={v} className={when === v ? "on" : ""} onClick={() => setWhen(v)}>{v === "upcoming" ? "예정" : "결과"}</button>)}
              <span className="it-sep" />
              {(["key", "all"] as const).map((v) => <button key={v} className={scope === v ? "on" : ""} onClick={() => setScope(v)}>{v === "key" ? "주요 경기" : "전체"}</button>)}
            </div>
            <div className="it-chips">
              <button className={conf === "" ? "on" : ""} onClick={() => setConf("")}>전 대륙</button>
              {confs.map((c) => <button key={c.k} className={conf === c.k ? "on" : ""} onClick={() => setConf(c.k)}>{c.ko}</button>)}
              <span className="it-sep" />
              {([["", "전체"], ["tournament", "본선"], ["nations_league", "네이션스리그"], ["qualifier", "예선"], ["friendly", "친선"]] as const).map(([k, l]) => (
                <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{l}</button>
              ))}
            </div>
          </div>
          {ms === null ? <SkelRows n={10} /> : ms.length ? <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
            : <p className="pv-empty">조건에 맞는 경기가 없습니다.</p>}
        </section>
      )}

      {tab === "tournaments" && (
        <>
          {hub.by_conf.map((g) => {
            // 본선·네이션스리그·진행/예정 대회는 늘 보이고, 끝난 예선·친선은 '끝난 대회 보기'로 접는다
            const main = g.comps.filter((c) => c.kind === "tournament" || c.kind === "nations_league" || c.edition.status !== "finished");
            const rest = g.comps.filter((c) => !main.includes(c));
            return (
              <section className="it-conf" key={g.conf}>
                <SectionHead title={g.en} kr={g.ko} meta={`${g.comps.length}개 대회`} />
                <div className="it-grid">
                  {main.map((c) => <CompCard key={c.code} c={c} today={today} onOpen={(x) => setOpen({ code: x.code, season: x.edition.season })} />)}
                  {showDone && rest.map((c) => <CompCard key={c.code} c={c} today={today} onOpen={(x) => setOpen({ code: x.code, season: x.edition.season })} />)}
                </div>
                {!showDone && rest.length > 0 && <button className="it-more" onClick={() => setShowDone(true)}>끝난 예선·친선 {rest.length}개 보기</button>}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}
